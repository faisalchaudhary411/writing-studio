"""
Shared fixtures for QalamStudio's test suite.

QalamStudio persists everything (license keys, pro requests, limits, login
attempts) through GitHub's Contents API rather than a local database — see
app.py's `_gh_read`/`_gh_write`/`_gh_read_fresh`/`_gh_write_cas`. Tests never
want to hit real GitHub, so `fake_github_store` below replaces those four
functions with an in-memory dict for the duration of each test. Every
higher-level accessor (_get_license_keys, _get_requests, _get_limits, ...)
calls through this boundary, so nothing above it needs to know it's fake —
the same trick VoxCraft's test suite uses for its SQLite layer, adapted to
this app's GitHub-JSON persistence instead.
"""
import os
import sys
import json
import copy

# Must be set BEFORE `import app`, since Config.SECRET_KEY is evaluated
# (and raises RuntimeError if missing) at module import time.
os.environ.setdefault("QALAM_ALLOW_DEV_SECRET", "1")
os.environ.setdefault("GITHUB_TOKEN", "")       # keep persistence calls fake-only
os.environ.setdefault("RESEND_API_KEY", "")     # keep email sends fake-only by default
os.environ.setdefault("ADMIN_EMAIL", "")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password-not-used-in-prod")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import app as qalam_app


@pytest.fixture(autouse=True)
def fake_github_store(monkeypatch):
    """Fresh in-memory store per test — nothing persists across tests, and
    nothing ever touches the real GitHub API or its 60s in-memory cache."""
    store = {}

    def fake_read(filename, repo=None):
        data = store.get(filename)
        return copy.deepcopy(data) if data is not None else None

    def fake_write(filename, data, msg, repo=None):
        store[filename] = json.loads(json.dumps(data))
        return True, "OK"

    def fake_read_fresh(filename, repo=None):
        data = store.get(filename)
        return (copy.deepcopy(data) if data is not None else None), "fake-sha"

    def fake_write_cas(filename, data, sha, msg, repo=None):
        store[filename] = json.loads(json.dumps(data))
        return True, False, "OK"

    monkeypatch.setattr(qalam_app, "_gh_read", fake_read)
    monkeypatch.setattr(qalam_app, "_gh_write", fake_write)
    monkeypatch.setattr(qalam_app, "_gh_read_fresh", fake_read_fresh)
    monkeypatch.setattr(qalam_app, "_gh_write_cas", fake_write_cas)
    monkeypatch.setattr(qalam_app, "_cache", {})
    return store


@pytest.fixture
def client():
    qalam_app.app.config.update(TESTING=True)
    with qalam_app.app.test_client() as c:
        yield c


@pytest.fixture
def admin_client(client):
    """A test client already logged in as admin, with a matching CSRF token
    ready to send on POSTs to /admin/api/* (see _csrf_protect in app.py)."""
    with client.session_transaction() as sess:
        sess["admin_auth"] = True
        sess["_csrf_token"] = "test-csrf-token"
    return client


def csrf_headers():
    return {"X-CSRF-Token": "test-csrf-token"}
