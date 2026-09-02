"""
Covers the grace-period admin dead-end fix from this session:
  - auto-approved requests get access_type/grace_finalized tracking
  - approve_request() marks a grace approval finalized
  - reject_request() now actually revokes a live grace key, not just the
    request's status label
  - sweep_grace_reminders() emails admin before/after a grace window lapses,
    exactly once each, and only for unfinalized grace requests
"""
import uuid
import datetime as dt
from unittest.mock import patch

import app as qalam_app


def _fake_grace_request(hours_until_expiry, finalized=False, reminder_sent=False,
                         expired_notified=False, key_assigned=None):
    expires_at = dt.datetime.now() + dt.timedelta(hours=hours_until_expiry)
    return {
        "id": f"REQ-{uuid.uuid4().hex[:10]}", "name": "Test Customer",
        "email": "test@example.com", "phone": "",
        "status": "approved", "date": qalam_app._now_str(),
        "key_assigned": key_assigned or "", "ip": "fake-ip-hash", "notified": True,
        "payment_method": "JazzCash", "txn_id": "TXN123", "has_screenshot": True,
        "auto_approved": True,
        "access_type": "grace",
        "grace_expires": expires_at.strftime("%Y-%m-%d %H:%M"),
        "grace_finalized": finalized,
        "grace_reminder_sent": reminder_sent,
        "grace_expired_notified": expired_notified,
    }


# ── fraud-hardening: duplicates, rate limiting ──

def test_txn_id_duplicate_detected_across_live_statuses():
    qalam_app._save_requests([
        {"id": "R1", "txn_id": "DUP1234", "status": "pending"},
    ])
    assert qalam_app._txn_id_is_duplicate("dup1234") is True  # case-insensitive
    assert qalam_app._txn_id_is_duplicate("OTHER999") is False


def test_txn_id_duplicate_ignores_rejected_requests():
    qalam_app._save_requests([
        {"id": "R1", "txn_id": "OLD5555", "status": "rejected"},
    ])
    assert qalam_app._txn_id_is_duplicate("OLD5555") is False


def test_screenshot_duplicate_detected_by_exact_hash():
    h = qalam_app._screenshot_sha256("aGVsbG8gd29ybGQ=")  # base64 for "hello world"
    qalam_app._save_requests([
        {"id": "R1", "screenshot_sha256": h, "status": "approved"},
    ])
    assert qalam_app._screenshot_is_duplicate(h) is True


def test_rate_limited_blocks_after_threshold():
    reqs = [{"id": f"R{i}", "ip": "spammer-ip", "status": "pending", "date": qalam_app._now_str()}
            for i in range(qalam_app.RATE_LIMIT_MAX_PENDING_PER_IP)]
    qalam_app._save_requests(reqs)
    assert qalam_app._rate_limited("spammer-ip") is True


def test_rate_limited_false_under_threshold():
    assert qalam_app._rate_limited("fresh-ip") is False


def test_rate_limited_ignores_old_requests_outside_window():
    old_date = (dt.datetime.now() - dt.timedelta(hours=qalam_app.RATE_LIMIT_WINDOW_HOURS + 1)).strftime("%Y-%m-%d %H:%M")
    reqs = [{"id": f"R{i}", "ip": "old-spammer", "status": "pending", "date": old_date}
            for i in range(qalam_app.RATE_LIMIT_MAX_PENDING_PER_IP + 2)]
    qalam_app._save_requests(reqs)
    assert qalam_app._rate_limited("old-spammer") is False


def test_submit_pro_request_rate_limited_returns_error(monkeypatch):
    monkeypatch.setattr(qalam_app, "_rate_limited", lambda ip_hash: True)
    with qalam_app.app.test_request_context(headers={"True-Client-IP": "9.9.9.1"}):
        result = qalam_app.submit_pro_request("Spammer", "spam@example.com",
                                                txn_id="TXN1", screenshot_b64="x")
    assert result["success"] is False
    assert "awaiting review" in result["error"]
    assert qalam_app._get_requests() == []  # never even recorded


def test_submit_pro_request_auto_rejects_duplicate_txn_without_notifying_admin(monkeypatch):
    monkeypatch.setattr(qalam_app, "_is_valid_image", lambda b64: True)
    monkeypatch.setattr(qalam_app.Config, "RESEND_API_KEY", "fake-key")
    monkeypatch.setattr(qalam_app.Config, "ADMIN_EMAIL", "admin@example.com")
    notify_calls = []
    monkeypatch.setattr(qalam_app, "_notify_admin", lambda *a, **k: notify_calls.append(1) or True)

    qalam_app._save_requests([{"id": "EXISTING", "txn_id": "DUPTXN001", "status": "approved"}])

    with qalam_app.app.test_request_context(headers={"True-Client-IP": "9.9.9.2"}):
        result = qalam_app.submit_pro_request("Fraudster", "fraud@example.com",
                                                txn_id="DUPTXN001", screenshot_b64="x")

    assert result["auto_rejected"] is True
    assert "already used" in result["reject_reason"]
    assert notify_calls == []  # admin should NOT be spammed for obvious junk
    assert qalam_app._get_requests()[0]["status"] == "rejected"


def test_ocr_txn_id_found_matches_digits_only():
    assert qalam_app._ocr_txn_id_found("ref no: 1234-5678 thank you", "12345678") is True
    assert qalam_app._ocr_txn_id_found("completely different text", "12345678") is False


def test_ocr_amount_found_within_tolerance():
    assert qalam_app._ocr_amount_found("amount paid: rs 499.00", 499) is True
    assert qalam_app._ocr_amount_found("amount paid: rs 800", 499) is False


def test_ocr_amount_found_does_not_substring_match():
    # 840 must not match inside 8400 — exact numeric-token comparison only.
    assert qalam_app._ocr_amount_found("total paid: rs 8400", 840) is False




def test_submit_pro_request_pending_when_auto_approve_disabled():
    with patch.object(qalam_app.Config, "AUTO_APPROVE_MANUAL", False):
        with qalam_app.app.test_request_context(headers={"True-Client-IP": "5.5.5.5"}):
            result = qalam_app.submit_pro_request("Ali", "ali@example.com", txn_id="TXN1",
                                                    screenshot_b64="")
    assert result["auto_approved"] is False
    reqs = qalam_app._get_requests()
    assert reqs[0]["status"] == "pending"
    assert reqs[0]["access_type"] == ""


def test_submit_pro_request_auto_approves_with_valid_image_and_txn(monkeypatch):
    monkeypatch.setattr(qalam_app, "_is_valid_image", lambda b64: True)
    # OCR must find both the typed txn ID and an amount matching PRO_PRICE_PKR
    # in the screenshot — fake the extracted text accordingly rather than
    # bypassing the OCR match functions themselves.
    price = qalam_app.Config.PRO_PRICE_PKR
    monkeypatch.setattr(qalam_app, "_ocr_extract_text", lambda b64: f"paid rs {price} txn TXN200012 success")
    with qalam_app.app.test_request_context(headers={"True-Client-IP": "6.6.6.6"}):
        result = qalam_app.submit_pro_request("Sara", "sara@example.com",
                                                txn_id="TXN200012", screenshot_b64="fakebase64")
    assert result["auto_approved"] is True
    assert result["license_key"]
    reqs = qalam_app._get_requests()
    req = reqs[0]
    assert req["status"] == "approved"
    assert req["access_type"] == "grace"
    assert req["grace_finalized"] is False
    assert req["grace_reminder_sent"] is False
    assert req["grace_expired_notified"] is False
    # The key itself should carry a grace_expires, not a permanent expires_at
    key_info = qalam_app._get_license_keys()[result["license_key"]]
    assert key_info.get("grace_expires")


def test_submit_pro_request_no_auto_approve_when_ocr_unavailable(monkeypatch):
    # Simulates tesseract-ocr not being installed on this deployment (see
    # _ocr_extract_text's deployment note) — must fall back to admin
    # review, never blindly auto-approve.
    monkeypatch.setattr(qalam_app, "_is_valid_image", lambda b64: True)
    monkeypatch.setattr(qalam_app, "_ocr_extract_text", lambda b64: "")
    with qalam_app.app.test_request_context(headers={"True-Client-IP": "6.6.6.7"}):
        result = qalam_app.submit_pro_request("NoOcr", "noocr@example.com",
                                                txn_id="TXN2X", screenshot_b64="fakebase64")
    assert result["auto_approved"] is False
    assert result["auto_rejected"] is False
    assert qalam_app._get_requests()[0]["status"] == "pending"


def test_submit_pro_request_auto_rejects_txn_not_found_in_screenshot(monkeypatch):
    monkeypatch.setattr(qalam_app, "_is_valid_image", lambda b64: True)
    monkeypatch.setattr(qalam_app, "_ocr_extract_text", lambda b64: "totally unrelated receipt text")
    with qalam_app.app.test_request_context(headers={"True-Client-IP": "6.6.6.8"}):
        result = qalam_app.submit_pro_request("Mismatch", "mismatch@example.com",
                                                txn_id="TXN999999", screenshot_b64="fakebase64")
    assert result["auto_rejected"] is True
    assert "does not appear" in result["reject_reason"]
    assert qalam_app._get_requests()[0]["status"] == "rejected"


def test_submit_pro_request_no_auto_approve_without_txn_id(monkeypatch):
    monkeypatch.setattr(qalam_app, "_is_valid_image", lambda b64: True)
    with qalam_app.app.test_request_context(headers={"True-Client-IP": "7.7.7.7"}):
        result = qalam_app.submit_pro_request("NoTxn", "notxn@example.com",
                                                txn_id="", screenshot_b64="fakebase64")
    assert result["auto_approved"] is False


def test_submit_pro_request_device_already_auto_approved_blocks_second(monkeypatch):
    monkeypatch.setattr(qalam_app, "_is_valid_image", lambda b64: True)
    price = qalam_app.Config.PRO_PRICE_PKR
    with qalam_app.app.test_request_context(headers={"True-Client-IP": "8.8.8.8"}):
        monkeypatch.setattr(qalam_app, "_ocr_extract_text", lambda b64: f"paid rs {price} txn TXNA1001")
        first = qalam_app.submit_pro_request("First", "first@example.com",
                                               txn_id="TXNA1001", screenshot_b64="x")
        monkeypatch.setattr(qalam_app, "_ocr_extract_text", lambda b64: f"paid rs {price} txn TXNB2002")
        second = qalam_app.submit_pro_request("Second", "second@example.com",
                                                txn_id="TXNB2002", screenshot_b64="y")
    assert first["auto_approved"] is True
    assert second["auto_approved"] is False


# ── approve_request / reject_request ──

def test_approve_request_marks_grace_finalized_and_emails_key(monkeypatch):
    req = _fake_grace_request(hours_until_expiry=5)
    qalam_app._save_requests([req])
    sent = {}
    monkeypatch.setattr(qalam_app, "_send_key_email",
                         lambda email, name, key: sent.update(email=email, name=name, key=key) or True)

    ok = qalam_app.approve_request(req["id"], "QALAM-PRO-FAKEPERMANENT")

    assert ok is True
    updated = next(r for r in qalam_app._get_requests() if r["id"] == req["id"])
    assert updated["grace_finalized"] is True
    assert updated["key_assigned"] == "QALAM-PRO-FAKEPERMANENT"
    assert sent["key"] == "QALAM-PRO-FAKEPERMANENT"


def test_approve_request_unknown_id_returns_false():
    assert qalam_app.approve_request("REQ-DOES-NOT-EXIST", "SOME-KEY") is False


def test_reject_request_revokes_live_grace_key():
    key = qalam_app.create_new_key(grace_hours=72)
    req = _fake_grace_request(hours_until_expiry=5, key_assigned=key)
    qalam_app._save_requests([req])

    ok = qalam_app.reject_request(req["id"])

    assert ok is True
    assert qalam_app._get_license_keys()[key]["revoked"] is True
    updated = next(r for r in qalam_app._get_requests() if r["id"] == req["id"])
    assert updated["status"] == "rejected"
    assert updated["grace_finalized"] is True  # terminal — stop reminder emails


def test_reject_request_plain_pending_does_not_touch_any_key():
    # A plain pending request never had a key issued — reject_request must
    # not blow up trying to revoke something that doesn't exist.
    req = {"id": "REQ-PLAIN-1", "name": "Plain", "email": "plain@example.com",
           "status": "pending", "date": qalam_app._now_str(), "key_assigned": "",
           "access_type": ""}
    qalam_app._save_requests([req])
    ok = qalam_app.reject_request(req["id"])
    assert ok is True
    assert qalam_app._get_requests()[0]["status"] == "rejected"


def test_reject_request_unknown_id_returns_false():
    assert qalam_app.reject_request("REQ-DOES-NOT-EXIST") is False


# ── sweep_grace_reminders ──

def test_grace_reminder_sent_within_threshold_and_unfinalized():
    req = _fake_grace_request(hours_until_expiry=qalam_app.GRACE_REMINDER_HOURS_BEFORE - 1)
    qalam_app._save_requests([req])
    with patch.object(qalam_app, "_notify_admin_grace_status", return_value=True) as mock_notify:
        result = qalam_app.sweep_grace_reminders()
    assert result["reminded"] == 1
    mock_notify.assert_called_once()
    updated = qalam_app._get_requests()[0]
    assert updated["grace_reminder_sent"] is True


def test_grace_reminder_not_sent_twice():
    req = _fake_grace_request(hours_until_expiry=2, reminder_sent=True)
    qalam_app._save_requests([req])
    with patch.object(qalam_app, "_notify_admin_grace_status", return_value=True) as mock_notify:
        result = qalam_app.sweep_grace_reminders()
    assert result["reminded"] == 0
    mock_notify.assert_not_called()


def test_grace_reminder_skipped_when_already_finalized():
    req = _fake_grace_request(hours_until_expiry=1, finalized=True)
    qalam_app._save_requests([req])
    with patch.object(qalam_app, "_notify_admin_grace_status", return_value=True) as mock_notify:
        qalam_app.sweep_grace_reminders()
    mock_notify.assert_not_called()


def test_grace_reminder_skipped_for_non_grace_requests():
    req = _fake_grace_request(hours_until_expiry=1)
    req["access_type"] = ""  # a plain (non-grace) approval
    qalam_app._save_requests([req])
    with patch.object(qalam_app, "_notify_admin_grace_status", return_value=True) as mock_notify:
        result = qalam_app.sweep_grace_reminders()
    assert result == {"reminded": 0, "missed": 0}
    mock_notify.assert_not_called()


def test_grace_lapsed_notice_fires_once_after_expiry():
    req = _fake_grace_request(hours_until_expiry=-1)  # already past expiry
    qalam_app._save_requests([req])
    with patch.object(qalam_app, "_notify_admin_grace_status", return_value=True) as mock_notify:
        result = qalam_app.sweep_grace_reminders()
    assert result["missed"] == 1
    mock_notify.assert_called_once()
    updated = qalam_app._get_requests()[0]
    assert updated["grace_expired_notified"] is True


def test_grace_lapsed_notice_not_repeated():
    req = _fake_grace_request(hours_until_expiry=-1, expired_notified=True)
    qalam_app._save_requests([req])
    with patch.object(qalam_app, "_notify_admin_grace_status", return_value=True) as mock_notify:
        qalam_app.sweep_grace_reminders()
    mock_notify.assert_not_called()


def test_grace_sweep_ignores_requests_without_grace_expires():
    req = _fake_grace_request(hours_until_expiry=1)
    req["grace_expires"] = ""
    qalam_app._save_requests([req])
    result = qalam_app.sweep_grace_reminders()
    assert result == {"reminded": 0, "missed": 0}


def test_notify_admin_grace_status_noop_without_config():
    # RESEND_API_KEY/ADMIN_EMAIL are unset by default in conftest — this
    # must fail closed (no exception, no network call) rather than error.
    assert qalam_app._notify_admin_grace_status("subject", "body") is False


def test_notify_admin_grace_status_sends_when_configured(monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "RESEND_API_KEY", "fake-resend-key")
    monkeypatch.setattr(qalam_app.Config, "ADMIN_EMAIL", "admin@example.com")

    class FakeResponse:
        status_code = 200

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(qalam_app.req, "post", fake_post)
    ok = qalam_app._notify_admin_grace_status("Test subject", "Test body")
    assert ok is True
    assert captured["json"]["to"] == ["admin@example.com"]
    assert captured["json"]["subject"] == "Test subject"
