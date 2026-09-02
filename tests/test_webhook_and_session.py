"""
Route-level tests for:
  - /webhook/freemius: signature verification, and the new
    license.extended/cancelled/expired handling
  - /api/restore-pro: the session-revalidation hardening (an invalid key
    must now actively clear an existing Pro session, not just decline to
    grant a new one)
"""
import hmac
import hashlib
import json
import datetime as dt
from unittest.mock import patch

import app as qalam_app


def _post_webhook(client, payload, secret=None):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Signature"] = sig
    return client.post("/webhook/freemius", data=body, headers=headers)


# ── signature verification ──

def test_webhook_rejects_missing_signature_when_secret_configured(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "shh-its-a-secret")
    resp = _post_webhook(client, {"event": "license.expired"})  # no signature header
    assert resp.status_code == 401


def test_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "shh-its-a-secret")
    resp = client.post("/webhook/freemius",
                        data=json.dumps({"event": "license.expired"}),
                        headers={"Content-Type": "application/json", "X-Signature": "wrong"})
    assert resp.status_code == 401


def test_webhook_accepts_valid_signature(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "shh-its-a-secret")
    resp = _post_webhook(client, {"event": "unhandled.event"}, secret="shh-its-a-secret")
    assert resp.status_code == 200


def test_webhook_processes_without_signature_when_no_secret_configured(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "")
    resp = _post_webhook(client, {"event": "unhandled.event"})
    assert resp.status_code == 200


# ── renewal / cancellation / expiry (the new handling) ──

def test_webhook_license_extended_updates_existing_key(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "")
    key, _ = qalam_app.create_freemius_license("Renewer", "renew@example.com",
                                                 {"license_id": "FS-9001"})
    new_expiry = (dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    payload = {"event": "license.extended", "objects": {"license": {"id": "FS-9001", "expiration": new_expiry}}}
    resp = _post_webhook(client, payload)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    info = qalam_app._get_license_keys()[key]
    assert info["revoked"] is False
    assert info["renewal_count"] == 1


def test_webhook_license_expired_revokes_key(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "")
    key, _ = qalam_app.create_freemius_license("Lapsed", "lapsed@example.com",
                                                 {"license_id": "FS-9002"})
    payload = {"event": "license.expired", "objects": {"license": {"id": "FS-9002"}}}
    resp = _post_webhook(client, payload)
    assert resp.status_code == 200
    assert qalam_app._get_license_keys()[key]["revoked"] is True


def test_webhook_license_extended_unknown_id_returns_404(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "")
    payload = {"event": "license.extended", "objects": {"license": {"id": "FS-NEVER-CREATED"}}}
    resp = _post_webhook(client, payload)
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_webhook_initial_purchase_stores_expiration(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "")
    monkeypatch.setattr(qalam_app, "_send_key_email", lambda *a, **k: True)
    future = (dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "event": "payment.completed",
        "user": {"email": "buyer@example.com", "first": "Bu", "last": "Yer"},
        "objects": {"license": {"id": "FS-9003", "expiration": future},
                    "subscription": {"id": "FS-SUB-9003"}},
        "payment_id": "PAY-1",
    }
    resp = _post_webhook(client, payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    key = body["license_key"]
    info = qalam_app._get_license_keys()[key]
    assert info.get("expires_at")  # HARDENING regression check: used to never be set
    assert info["freemius_license_id"] == "FS-9003"


def test_webhook_ignores_unhandled_event(client, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "FREEMIUS_SECRET_KEY", "")
    resp = _post_webhook(client, {"event": "some.other.event"})
    assert resp.status_code == 200
    assert "ignored" in resp.get_json().get("message", "").lower()


# ── /api/restore-pro session hardening ──

def test_restore_pro_grants_session_for_valid_key(client):
    key = qalam_app.create_new_key(expires_at=(dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M"))
    with patch.object(qalam_app, "check_license", return_value={"valid": True, "name": "Pro User"}):
        resp = client.post("/api/restore-pro", json={"key": key})
    assert resp.get_json()["success"] is True
    with client.session_transaction() as sess:
        assert sess["is_pro"] is True


def test_restore_pro_clears_existing_pro_session_when_key_invalid(client):
    # Simulates the exact gap this session's fix closes: a session that was
    # already Pro (e.g. from an earlier valid check) must actually lose Pro
    # status once the key comes back invalid — not just fail to re-grant it.
    with client.session_transaction() as sess:
        sess["is_pro"] = True
        sess["license_key"] = "QALAM-PRO-NOWINVALID"
        sess["pro_name"] = "Old Pro User"

    with patch.object(qalam_app, "check_license", return_value={"valid": False, "error": "Your subscription has expired."}):
        resp = client.post("/api/restore-pro", json={"key": "QALAM-PRO-NOWINVALID"})

    assert resp.get_json()["success"] is False
    with client.session_transaction() as sess:
        assert sess.get("is_pro") is False
        assert sess.get("license_key") == ""


def test_restore_pro_no_key_provided(client):
    resp = client.post("/api/restore-pro", json={})
    assert resp.get_json()["success"] is False
