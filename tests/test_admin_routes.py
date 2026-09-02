"""
Covers CSRF enforcement on the admin API, and that the admin dashboard's
new "Grant Permanent" / "Revoke" buttons (data-req-action="approve"/"reject"
on a grace-approved row) actually route through approve_request/
reject_request correctly via the existing generic /admin/api/approve-request
and /admin/api/reject-request endpoints.
"""
import datetime as dt

import app as qalam_app
from conftest import csrf_headers


def _fake_grace_request(hours_until_expiry=5, key_assigned=None):
    expires_at = dt.datetime.now() + dt.timedelta(hours=hours_until_expiry)
    return {
        "id": "REQ-ADMIN-TEST-1", "name": "Grace Customer", "email": "grace@example.com",
        "phone": "", "status": "approved", "date": qalam_app._now_str(),
        "key_assigned": key_assigned or "", "ip": "fake-ip", "notified": True,
        "payment_method": "EasyPaisa", "txn_id": "TXN-ADMIN-1", "has_screenshot": True,
        "auto_approved": True, "access_type": "grace",
        "grace_expires": expires_at.strftime("%Y-%m-%d %H:%M"),
        "grace_finalized": False, "grace_reminder_sent": False, "grace_expired_notified": False,
    }


def test_admin_api_requires_admin_auth(client):
    resp = client.post("/admin/api/approve-request", json={"req_id": "whatever"})
    # admin_required redirects to the login page rather than 401ing
    assert resp.status_code in (302, 401, 403)


def test_admin_api_rejects_missing_csrf_token(admin_client):
    resp = admin_client.post("/admin/api/approve-request", json={"req_id": "whatever"})
    assert resp.status_code == 403


def test_admin_api_rejects_wrong_csrf_token(admin_client):
    resp = admin_client.post("/admin/api/approve-request", json={"req_id": "whatever"},
                              headers={"X-CSRF-Token": "not-the-right-token"})
    assert resp.status_code == 403


def test_admin_grant_permanent_finalizes_grace_request(admin_client, monkeypatch):
    monkeypatch.setattr(qalam_app, "_send_key_email", lambda *a, **k: True)
    req = _fake_grace_request()
    qalam_app._save_requests([req])

    resp = admin_client.post("/admin/api/approve-request",
                              json={"req_id": req["id"]},
                              headers=csrf_headers())

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    new_key = body["key"]
    updated = next(r for r in qalam_app._get_requests() if r["id"] == req["id"])
    assert updated["grace_finalized"] is True
    assert updated["key_assigned"] == new_key
    # The finalized key should be permanent (create_new_key() with no
    # grace_hours) — not another temporary grace key.
    assert "grace_expires" not in qalam_app._get_license_keys()[new_key]


def test_admin_revoke_grace_request_revokes_live_key(admin_client):
    key = qalam_app.create_new_key(grace_hours=72)
    req = _fake_grace_request(key_assigned=key)
    qalam_app._save_requests([req])

    resp = admin_client.post("/admin/api/reject-request",
                              json={"req_id": req["id"]},
                              headers=csrf_headers())

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert qalam_app._get_license_keys()[key]["revoked"] is True
    updated = next(r for r in qalam_app._get_requests() if r["id"] == req["id"])
    assert updated["status"] == "rejected"


def test_admin_approve_with_manual_key_uses_provided_key(admin_client, monkeypatch):
    monkeypatch.setattr(qalam_app, "_send_key_email", lambda *a, **k: True)
    req = {"id": "REQ-PENDING-1", "name": "Pending Guy", "email": "pending@example.com",
           "status": "pending", "date": qalam_app._now_str(), "key_assigned": "",
           "access_type": ""}
    qalam_app._save_requests([req])

    resp = admin_client.post("/admin/api/approve-request",
                              json={"req_id": req["id"], "manual_key": "QALAM-PRO-MANUALLYCHOSEN"},
                              headers=csrf_headers())

    assert resp.status_code == 200
    assert resp.get_json()["key"] == "QALAM-PRO-MANUALLYCHOSEN"


def test_admin_dashboard_reports_pending_grace_count(admin_client):
    req = _fake_grace_request()
    qalam_app._save_requests([req])
    resp = admin_client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"awaiting finalization" in resp.data
