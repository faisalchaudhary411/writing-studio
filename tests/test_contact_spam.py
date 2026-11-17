"""Contact-form abuse protection."""
import time
import pytest
import app as qalam_app

GOOD = {"name": "Ali Khan", "email": "ali@example.org", "category": "support",
        "phone": "", "message": "Hello, my subtitle export fails on long scripts."}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    qalam_app._CONTACT_BUCKETS.clear()
    qalam_app._CONTACT_USED_NONCES.clear()
    monkeypatch.setattr(qalam_app, "CONTACT_MIN_FILL_SEC", 0)
    monkeypatch.setattr(qalam_app.Config, "TURNSTILE_SITE_KEY", "")
    monkeypatch.setattr(qalam_app.Config, "TURNSTILE_SECRET_KEY", "")
    monkeypatch.setattr(qalam_app.Config, "CONTACT_AUTO_REPLY", False)
    sent = []
    monkeypatch.setattr(qalam_app, "_send_mailtrap_email",
                        lambda to, subj, text_body=None, **kw: sent.append(to) or True)
    monkeypatch.setattr(qalam_app.Config, "ADMIN_EMAIL", "admin@example.com")
    return sent


@pytest.fixture
def sent(_fresh):
    return _fresh


def post(client, **over):
    data = dict(GOOD, contact_token=qalam_app._make_contact_token(), **over)
    return client.post("/contact", data=data, follow_redirects=True)


def test_legit_message_notifies_admin_only(sent):
    c = qalam_app.app.test_client()
    r = post(c)
    assert b"received" in r.data
    assert sent == ["admin@example.com"]          # no auto-reply to the visitor


def test_auto_reply_is_opt_in(sent, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "CONTACT_AUTO_REPLY", True)
    post(qalam_app.app.test_client())
    assert sent == ["admin@example.com", "ali@example.org"]


def test_token_is_single_use(sent):
    c = qalam_app.app.test_client()
    tok = qalam_app._make_contact_token()
    d = dict(GOOD, contact_token=tok)
    c.post("/contact", data=d)
    r = c.post("/contact", data=dict(d, email="other@example.org"), follow_redirects=True)
    assert b"reload the page" in r.data
    assert len(sent) == 1


@pytest.mark.parametrize("over", [
    {"message": "Visit http://spam.ru and www.cheap.com now please"},
    {"message": "Best SEO services and backlinks for your site!!"},
    {"name": "http://spam.xyz"},
    {"message": "<a href='x'>click</a> to win something nice"},
])
def test_spam_is_silently_dropped(sent, over):
    r = post(qalam_app.app.test_client(), **over)
    assert b"received" in r.data                 # bot sees success...
    assert sent == []                            # ...but nothing is sent


def test_honeypot_sends_nothing(sent):
    post(qalam_app.app.test_client(), website="http://x.com")
    assert sent == []


def test_per_email_limit(sent):
    c = qalam_app.app.test_client()
    for i in range(4):
        post(c, message=f"Legit message number {i} about my export")
    assert sent.count("admin@example.com") == qalam_app.CONTACT_EMAIL_DAILY_MAX


def test_global_cap(sent, monkeypatch):
    monkeypatch.setattr(qalam_app, "CONTACT_GLOBAL_HOURLY_MAX", 2)
    monkeypatch.setattr(qalam_app, "CONTACT_EMAIL_DAILY_MAX", 99)
    monkeypatch.setattr(qalam_app, "CONTACT_RATE_MAX", 99)
    c = qalam_app.app.test_client()
    for i in range(5):
        post(c, email=f"u{i}@example.org")
    assert len(sent) == 2


def test_crlf_stripped_from_fields(sent):
    assert qalam_app._clean_line("Bob\r\nBcc: x@y.z", 100) == "Bob Bcc: x@y.z"


def test_turnstile_required_when_configured(sent, monkeypatch):
    monkeypatch.setattr(qalam_app.Config, "TURNSTILE_SITE_KEY", "site")
    monkeypatch.setattr(qalam_app.Config, "TURNSTILE_SECRET_KEY", "secret")
    c = qalam_app.app.test_client()
    r = post(c)
    assert b"verification" in r.data and sent == []
    monkeypatch.setattr(qalam_app, "_turnstile_ok", lambda t, ip: True)
    r = post(c, **{"cf-turnstile-response": "tok"})
    assert sent == ["admin@example.com"]


def test_form_renders_widget_only_with_keys(monkeypatch):
    c = qalam_app.app.test_client()
    assert b"cf-turnstile" not in c.get("/contact").data
    monkeypatch.setattr(qalam_app.Config, "TURNSTILE_SITE_KEY", "site")
    monkeypatch.setattr(qalam_app.Config, "TURNSTILE_SECRET_KEY", "secret")
    assert b"cf-turnstile" in c.get("/contact").data
