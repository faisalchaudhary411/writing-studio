"""
Covers the license-expiry hardening from this session:
  - create_new_key()/create_freemius_license() now actually store an expiry
  - check_license() now rejects an expired `expires_at`, not just
    `grace_expires`/`revoked`
  - sync_license_from_freemius_event() handles license.extended/cancelled/
    expired, which the webhook previously didn't handle at all
"""
import datetime as dt

import app as qalam_app


def _mark_used_and_bound(key: str, ip_hash="ip-hash-abc", fp_hash="fp-hash-abc"):
    """check_license() requires a key to be activated (`used`) and to have
    the current device's ip/fp in its rolling history before it'll return
    valid — this stands a key up as if activate_license() had already run,
    without going through the full activation flow in every test."""
    keys = qalam_app._get_license_keys()
    keys[key]["used"] = True
    keys[key]["ip_history"] = [ip_hash]
    keys[key]["fp_history"] = [fp_hash]
    qalam_app._save_license_keys(keys)


def test_create_new_key_has_no_expiry_by_default():
    key = qalam_app.create_new_key()
    info = qalam_app._get_license_keys()[key]
    assert "expires_at" not in info
    assert "grace_expires" not in info


def test_create_new_key_with_grace_hours_sets_grace_expires():
    key = qalam_app.create_new_key(grace_hours=72)
    info = qalam_app._get_license_keys()[key]
    expires = dt.datetime.strptime(info["grace_expires"], "%Y-%m-%d %H:%M")
    assert expires > dt.datetime.now() + dt.timedelta(hours=71)


def test_create_new_key_with_expires_at_stores_it_normalized():
    # Freemius-style timestamp with seconds — must be normalized to this
    # app's "%Y-%m-%d %H:%M" storage format, or check_license()'s strptime
    # would silently fail and swallow the expiry via its bare except.
    future = (dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    key = qalam_app.create_new_key(expires_at=future)
    info = qalam_app._get_license_keys()[key]
    # Should parse cleanly with the app's own storage format
    dt.datetime.strptime(info["expires_at"], "%Y-%m-%d %H:%M")


def test_check_license_rejects_expired_key():
    key = qalam_app.create_new_key(expires_at=(dt.datetime.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M"))
    _mark_used_and_bound(key)
    with qalam_app.app.test_request_context(headers={"User-Agent": "test", "True-Client-IP": "1.2.3.4"}):
        # HARDENING regression test: before this session's fix, expires_at
        # wasn't checked at all here, so this would have returned valid=True.
        result = qalam_app.check_license(key)
    assert result["valid"] is False
    assert "expired" in result["error"].lower()


def test_check_license_accepts_key_with_future_expiry():
    key = qalam_app.create_new_key(expires_at=(dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M"))
    headers = {"User-Agent": "test-agent", "True-Client-IP": "9.9.9.9"}
    with qalam_app.app.test_request_context(headers=headers):
        # Compute the real ip/fp hashes the same way check_license will, so
        # the device-binding check passes and we're only exercising the
        # expiry logic this test is actually about.
        real_ip_hash = qalam_app._hash_ip(qalam_app._get_user_ip())
        real_fp_hash = qalam_app._get_browser_fingerprint()
        _mark_used_and_bound(key, ip_hash=real_ip_hash, fp_hash=real_fp_hash)
        result = qalam_app.check_license(key)
    assert result["valid"] is True


def test_check_license_still_rejects_revoked_key():
    key = qalam_app.create_new_key(expires_at=(dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M"))
    keys = qalam_app._get_license_keys()
    keys[key]["revoked"] = True
    qalam_app._save_license_keys(keys)
    with qalam_app.app.test_request_context():
        result = qalam_app.check_license(key)
    assert result["valid"] is False
    assert "revoked" in result["error"].lower()


def test_create_freemius_license_stores_expiry_from_meta():
    future = (dt.datetime.now() + dt.timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    key, err = qalam_app.create_freemius_license(
        "Test User", "test@example.com",
        {"license_id": "FS-1001", "subscription_id": "FS-SUB-1", "expiration": future},
    )
    assert err is None
    info = qalam_app._get_license_keys()[key]
    assert info.get("expires_at")
    assert info["freemius_license_id"] == "FS-1001"


def test_find_key_by_freemius_id():
    key, _ = qalam_app.create_freemius_license("Test User", "test@example.com",
                                                 {"license_id": "FS-2002"})
    found = qalam_app.find_key_by_freemius_id("FS-2002")
    assert found == key


def test_find_key_by_freemius_id_unknown_returns_none():
    assert qalam_app.find_key_by_freemius_id("FS-DOES-NOT-EXIST") is None


def test_sync_license_extended_pushes_expiry_forward_and_unrevokes():
    key, _ = qalam_app.create_freemius_license("Test User", "test@example.com",
                                                 {"license_id": "FS-3003"})
    keys = qalam_app._get_license_keys()
    keys[key]["revoked"] = True  # simulate a prior expiry before this renewal
    qalam_app._save_license_keys(keys)

    new_expiry = (dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    result = qalam_app.sync_license_from_freemius_event("FS-3003", "license.extended", new_expiry)

    assert result["success"] is True
    assert result["action"] == "extended"
    info = qalam_app._get_license_keys()[key]
    assert info["revoked"] is False
    assert info["renewal_count"] == 1
    expires = dt.datetime.strptime(info["expires_at"], "%Y-%m-%d %H:%M")
    assert expires > dt.datetime.now() + dt.timedelta(days=29)


def test_sync_license_extended_without_explicit_date_defaults_to_30_days():
    key, _ = qalam_app.create_freemius_license("Test User", "test@example.com",
                                                 {"license_id": "FS-3004"})
    result = qalam_app.sync_license_from_freemius_event("FS-3004", "license.extended", "")
    assert result["success"] is True
    info = qalam_app._get_license_keys()[key]
    expires = dt.datetime.strptime(info["expires_at"], "%Y-%m-%d %H:%M")
    assert expires > dt.datetime.now() + dt.timedelta(days=29)


def test_sync_license_expired_revokes_key():
    key, _ = qalam_app.create_freemius_license("Test User", "test@example.com",
                                                 {"license_id": "FS-4004"})
    result = qalam_app.sync_license_from_freemius_event("FS-4004", "license.expired")
    assert result["success"] is True
    assert result["action"] == "revoked_expired"
    assert qalam_app._get_license_keys()[key]["revoked"] is True


def test_sync_license_cancelled_does_not_revoke_immediately():
    # Deliberate: Freemius keeps the license valid through the already-paid
    # period; license.expired fires separately once that period ends.
    key, _ = qalam_app.create_freemius_license("Test User", "test@example.com",
                                                 {"license_id": "FS-5005"})
    result = qalam_app.sync_license_from_freemius_event("FS-5005", "license.cancelled")
    assert result["success"] is True
    assert result["action"] == "cancellation_noted"
    assert qalam_app._get_license_keys()[key]["revoked"] is False


def test_sync_license_unknown_freemius_id_fails_gracefully():
    result = qalam_app.sync_license_from_freemius_event("FS-NEVER-CREATED", "license.extended", "")
    assert result["success"] is False
    assert "No internal key found" in result["error"]


def test_sync_license_missing_freemius_id_fails_gracefully():
    result = qalam_app.sync_license_from_freemius_event("", "license.extended", "")
    assert result["success"] is False
