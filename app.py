# ══════════════════════════════════════════════════════════════════════
# QALAM STUDIO — Flask Edition
# v4.0 — Unique glassmorphism design · Full feature parity
# ══════════════════════════════════════════════════════════════════════
import os, json, base64, time, hashlib, hmac, secrets, random, string, re, datetime, threading, smtplib, ssl, html
from functools import wraps
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, session, redirect, url_for,
    flash, jsonify, abort, send_from_directory
)
from werkzeug.middleware.proxy_fix import ProxyFix
import requests as req

load_dotenv()

# ──────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────
class Config:
    # SECURITY: fail hard at import time if SECRET_KEY isn't set in a real
    # deployment. The old fallback (a random value generated per-worker, or
    # later a static "dev-secret-change-me" string) meant either sessions
    # broke silently across gunicorn workers, or every deployment everywhere
    # shared the same publicly-known signing key. Same fix as VoxCraft:
    # require the env var to be set outside local dev, so a missing secret
    # is a loud startup crash instead of a silent, exploitable weakness.
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        if os.environ.get("FLASK_ENV") == "development" or os.environ.get("QALAM_ALLOW_DEV_SECRET") == "1":
            SECRET_KEY = "dev-secret-change-me"
        else:
            raise RuntimeError(
                "SECRET_KEY environment variable is not set. Refusing to start "
                "with an insecure default in production. Set SECRET_KEY, or set "
                "QALAM_ALLOW_DEV_SECRET=1 for local development only."
            )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB uploads
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    # Model slugs are env-overridable, not hardcoded: every provider here has
    # deprecated/renamed models on short notice at least once in the past
    # year (this whole fallback chain exists because llama-3.3-70b-versatile
    # was pulled out from under this app with no warning). If a provider
    # retires another model, set the env var on Render instead of needing a
    # code change. Defaults below are each provider's own currently-
    # recommended general-purpose model as of this writing — verify against
    # each provider's live model list before relying on them long-term.
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "llama-4-scout")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", hashlib.sha256(os.urandom(32)).hexdigest()[:16])
    # Freemius API (replaces LemonSqueezy)
    FREEMIUS_API_KEY = os.environ.get("FREEMIUS_API_KEY", "")
    FREEMIUS_SECRET_KEY = os.environ.get("FREEMIUS_SECRET_KEY", "")
    FREEMIUS_PRODUCT_ID = os.environ.get("FREEMIUS_PRODUCT_ID", "")
    FREEMIUS_DEVELOPER_ID = os.environ.get("FREEMIUS_DEVELOPER_ID", "")
    FREEMIUS_PLUGIN_ID = os.environ.get("FREEMIUS_PLUGIN_ID", "")

    # FileDesk external tool URL
    FILEDESK_URL = os.environ.get("FILEDESK_URL", "")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GH_REPO = os.environ.get("GH_REPO", "faisalchaudhary411/qalamstudio.xyz")
    GH_REPO_PUBLIC = os.environ.get("GH_REPO_PUBLIC", "faisalchaudhary411/qalamstudio-config")
    GH_BRANCH = "main"
    MAILTRAP_API_KEY = os.environ.get("MAILTRAP_API_KEY", "")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")
    WHATSAPP_API_TOKEN = os.environ.get("WHATSAPP_API_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_ADMIN_NUMBER = os.environ.get("WHATSAPP_ADMIN_NUMBER", "")
    WAPPFLY_API_KEY = os.environ.get("WAPPFLY_API_KEY", "")
    WAPPFLY_ADMIN_NUMBER = os.environ.get("WAPPFLY_ADMIN_NUMBER", "")
    # Must be an address on a domain verified in Mailtrap's Sending Domain
    # settings — unverified "from" addresses get rejected by the API.
    CONTACT_FROM_EMAIL = os.environ.get("CONTACT_FROM_EMAIL", "QalamStudio <hello@qalamstudio.xyz>")
    FREE_DAILY_ACTIONS = int(os.environ.get("FREE_DAILY_ACTIONS", "20"))
    # Auto-approve manual Pakistani payments instantly (trust-based with grace period)
    AUTO_APPROVE_MANUAL = os.environ.get("AUTO_APPROVE_MANUAL", "true").lower() == "true"
    MANUAL_GRACE_HOURS = int(os.environ.get("MANUAL_GRACE_HOURS", "72"))
    PRO_PRICE_PKR = int(os.environ.get("PRO_PRICE_PKR", "499"))
    PRO_PRICE_LABEL = os.environ.get("PRO_PRICE_LABEL", "499 PKR")
    FREE_PRICE_LABEL = os.environ.get("FREE_PRICE_LABEL", "مفت")
    CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "/request-pro")

app = Flask(__name__)
app.config.from_object(Config)

# ProxyFix: Render terminates TLS at its edge and forwards over plain HTTP
# to the app, setting X-Forwarded-Proto so Flask can tell the request was
# actually HTTPS (needed for the Secure cookie flag and url_for(_external)
# to generate https:// links instead of http://).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# SECURITY: session cookie hardening. Secure requires HTTPS (true once on the
# VPS behind Nginx+Certbot; set QALAM_INSECURE_COOKIES=1 only for local http
# dev). HttpOnly blocks JS access (XSS mitigation). SameSite=Lax blocks most
# cross-site request forgery vectors for a same-origin cookie-based session.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("QALAM_INSECURE_COOKIES") != "1"

# BUG FIX (the actual "Pro vanishes" root cause): this used to call
# Session(app) with SESSION_TYPE="filesystem", storing session data as files
# on local disk. Render's filesystem is EPHEMERAL — every redeploy, restart,
# or dyno recycle wipes that directory entirely, silently logging out every
# active user until their browser's localStorage-based restore-pro safety net
# happens to fire (explaining why this felt intermittent rather than
# constant — it only shows up in the gap between a restart and the next
# page load). Nothing stored in session[] here is more than a short string
# or boolean (see below), so there's no real reason to need server-side
# session storage at all — switching to Flask's default signed-cookie
# session (stored in the user's browser, not server disk) removes the
# ephemeral-filesystem problem entirely, and matches the same fix already
# applied to VoxCraft. Also making sessions permanent with a real expiry —
# without this, the cookie has no explicit expiry at all, and mobile
# browsers/OSes routinely clear that kind of cookie when backgrounded.
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=90)


@app.before_request
def _make_session_permanent():
    session.permanent = True

# ──────────────────────────────────────────────────────────────────────
# CSRF PROTECTION (admin panel)
# ──────────────────────────────────────────────────────────────────────
# Session-token based, matching VoxCraft: every admin-authenticated POST
# (the /admin/api/* dashboard actions and the /admin login form itself) must
# carry a token that was minted for this session. This defeats CSRF because
# a malicious third-party site can make the browser send the admin's
# cookies automatically, but it can't read or forge the token value, which
# never leaves the dashboard page except as a hidden form/header field.
# The public /api/* routes (restore-pro, activate-license, etc.) and
# /webhook/* (HMAC-signature-verified separately) are exempt.
def _get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

app.jinja_env.globals["csrf_token"] = _get_csrf_token

@app.before_request
def _csrf_protect():
    if request.method != "POST":
        return
    path = request.path
    if path.startswith("/api/") or path.startswith("/webhook/"):
        return
    if path == "/admin" or path.startswith("/admin/api/"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not sent or not hmac.compare_digest(sent, expected):
            abort(403)

# ── In-memory cache for GitHub reads (TTL 60s) ──
_cache = {}
_cache_ttl = 60

# ──────────────────────────────────────────────────────────────────────
# GITHUB PERSISTENCE
# ──────────────────────────────────────────────────────────────────────
_F_BLOGS = "blogs.json"
_F_LIMITS = "limits.json"
_F_USAGE = "usage_tracking.json"
_F_KEYS = "license_keys.json"
_F_REQUESTS = "pro_requests.json"
_F_LOGIN_ATTEMPTS = "admin_login_attempts.json"

def _gh_read(filename: str, repo: str = None):
    repo = repo or Config.GH_REPO
    cache_key = f"{repo}/{filename}"
    now = time.time()
    if cache_key in _cache:
        data, ts = _cache[cache_key]
        if now - ts < _cache_ttl:
            return data
    try:
        tok = Config.GITHUB_TOKEN
        if not tok:
            return None
        h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.v3+json"}
        r = req.get(
            f"https://api.github.com/repos/{repo}/contents/{filename}?ref={Config.GH_BRANCH}",
            headers=h, timeout=10
        )
        if r.status_code == 200:
            data = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
            _cache[cache_key] = (data, now)
            return data
        return None
    except Exception:
        return None

def _gh_write(filename: str, data, msg: str, repo: str = None) -> tuple:
    repo = repo or Config.GH_REPO
    try:
        tok = Config.GITHUB_TOKEN
        if not tok:
            return False, "GITHUB_TOKEN missing"
        h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.v3+json"}
        gr = req.get(
            f"https://api.github.com/repos/{repo}/contents/{filename}?ref={Config.GH_BRANCH}",
            headers=h, timeout=10
        )
        sha = gr.json().get("sha") if gr.status_code == 200 else None
        encoded = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
        payload = {"message": msg, "content": encoded, "branch": Config.GH_BRANCH}
        if sha:
            payload["sha"] = sha
        pr = req.put(
            f"https://api.github.com/repos/{repo}/contents/{filename}",
            headers=h, json=payload, timeout=15
        )
        if pr.status_code in (200, 201):
            cache_key = f"{repo}/{filename}"
            _cache[cache_key] = (data, time.time())
            return True, "OK"
        return False, f"GitHub PUT {pr.status_code}: {pr.text[:300]}"
    except Exception as e:
        return False, f"Exception: {str(e)}"

def _ensure_file(filename, default_data, repo=None):
    data = _gh_read(filename, repo)
    if data is None:
        _gh_write(filename, default_data, f"Initialize {filename}", repo)
        return default_data
    return data

# ──────────────────────────────────────────────────────────────────────
# ATOMIC TRANSACTIONS (GitHub Contents API compare-and-swap)
# ──────────────────────────────────────────────────────────────────────
# GitHub's Contents API already gives us a real concurrency primitive: every
# write must include the `sha` of the version it's replacing, and GitHub
# rejects the write (409/422) if that sha is stale — i.e. someone else wrote
# in between. _gh_write() wasn't using this properly for read-modify-write
# sequences: callers would read (possibly from the 60s in-memory cache),
# mutate a Python dict, then write — with no guarantee the thing they read
# was still current, and no retry if the write got rejected. Two requests
# racing to activate the same key could both read used=False, both flip it
# locally, and both be told "valid": True by activate_license() even though
# only one of their writes could actually land — the loser would silently
# lose Pro status the next time their key was re-checked. This mirrors the
# exact bug VoxCraft's atomic license_key_transaction() was built to close.
def _gh_read_fresh(filename, repo=None):
    """Like _gh_read but always hits the API (never the cache) and also
    returns the current sha, for use inside a CAS transaction."""
    repo = repo or Config.GH_REPO
    tok = Config.GITHUB_TOKEN
    if not tok:
        return None, None
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.v3+json"}
    try:
        r = req.get(
            f"https://api.github.com/repos/{repo}/contents/{filename}?ref={Config.GH_BRANCH}",
            headers=h, timeout=10
        )
        if r.status_code == 200:
            j = r.json()
            data = json.loads(base64.b64decode(j["content"]).decode("utf-8"))
            return data, j.get("sha")
        return None, None
    except Exception:
        return None, None

def _gh_write_cas(filename, data, sha, msg, repo=None):
    """Compare-and-swap write: only succeeds if `sha` still matches what's
    live on GitHub right now. Returns (ok, was_conflict, err)."""
    repo = repo or Config.GH_REPO
    tok = Config.GITHUB_TOKEN
    if not tok:
        return False, False, "GITHUB_TOKEN missing"
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.v3+json"}
    try:
        encoded = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
        payload = {"message": msg, "content": encoded, "branch": Config.GH_BRANCH}
        if sha:
            payload["sha"] = sha
        pr = req.put(
            f"https://api.github.com/repos/{repo}/contents/{filename}",
            headers=h, json=payload, timeout=15
        )
        if pr.status_code in (200, 201):
            _cache[f"{repo}/{filename}"] = (data, time.time())
            return True, False, "OK"
        if pr.status_code in (409, 422):
            return False, True, f"Conflict: {pr.text[:200]}"
        return False, False, f"GitHub PUT {pr.status_code}: {pr.text[:300]}"
    except Exception as e:
        return False, False, f"Exception: {str(e)}"

def _gh_transact(filename, mutate_fn, msg, repo=None, max_retries=5):
    """Atomic read-modify-write. `mutate_fn(fresh_data)` must return
    (new_data, result) — return result=None to abort without writing (e.g.
    a precondition, like "key not already used", no longer holds once we
    have a fresh read). Retries with backoff on a genuine sha conflict
    (someone else wrote in between); gives up immediately on a real error
    (missing token, network failure) rather than retrying forever."""
    for attempt in range(max_retries):
        data, sha = _gh_read_fresh(filename, repo)
        if data is None:
            data = {}
        new_data, result = mutate_fn(data)
        if result is None:
            return None
        ok, conflict, err = _gh_write_cas(filename, new_data, sha, msg, repo)
        if ok:
            return result
        if not conflict:
            return None
        time.sleep(0.15 * (attempt + 1))
    return None

# Initialize files
_ensure_file(_F_REQUESTS, [])
_ensure_file(_F_KEYS, {})
_ensure_file(_F_BLOGS, [])
_ensure_file(_F_USAGE, {})
_ensure_file(_F_LOGIN_ATTEMPTS, {})
_ensure_file(_F_LIMITS, {
    "FREE_DAILY_ACTIONS": Config.FREE_DAILY_ACTIONS,
    "PRO_PRICE_PKR": Config.PRO_PRICE_PKR,
    "PRO_PRICE_LABEL": Config.PRO_PRICE_LABEL,
    "FREE_PRICE_LABEL": Config.FREE_PRICE_LABEL,
    "CHECKOUT_URL": Config.CHECKOUT_URL,
    "FREE_FEATURES": "✓ Urdu AI Writer|✓ Freelancer Toolkit|✓ Subtitle Generator|✓ 20 actions/day|✗ Ads on every generation|✗ Daily action limit",
    "PRO_FEATURES": "✓ All tools unlimited|✓ Unlimited actions/day|✓ Zero ads|✓ Priority generation|✓ All language styles|✓ Batch subtitle translation",
})

# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────
def _get_user_ip():
    # SECURITY FIX (Render-specific — different from the Nginx/VoxCraft
    # setup, which uses X-Real-IP): Render sits behind Cloudflare at its own
    # edge and sets True-Client-IP there, which a client cannot forge — this
    # plays the same trusted-header role X-Real-IP plays behind Nginx.
    # Render never rewrites X-Forwarded-For, only appends to it, so if
    # True-Client-IP isn't present the RIGHTMOST entry in X-Forwarded-For is
    # the one Render's own proxy added (trustworthy); the LEFTMOST entry is
    # whatever the client sent and is fully spoofable — the old code took
    # the leftmost entry, which let anyone fake their IP by just setting
    # the header themselves.
    true_client_ip = request.headers.get("True-Client-IP")
    if true_client_ip:
        return true_client_ip.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.remote_addr or "unknown"

def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]

def _get_browser_fingerprint() -> str:
    """Server-side device fingerprint built from request headers — no
    client-side JS/consent needed. Version numbers are stripped from the
    User-Agent before hashing: Chrome silently bumps its version string
    every few weeks on auto-update, and hashing the raw UA would treat that
    as a brand-new device, breaking device binding for most users roughly
    monthly. Combining the version-stripped UA with Accept-Language and the
    Client-Hints platform header (when the browser sends one) gives a
    reasonably stable per-browser-install signal. Same approach as
    VoxCraft's fingerprinting fix."""
    ua = request.headers.get("User-Agent", "")
    ua_stable = re.sub(r'[\d]+(\.[\d]+)*', '', ua)  # "Chrome/125.0.6422.112" -> "Chrome/"
    accept_lang = request.headers.get("Accept-Language", "").split(",")[0].strip()
    platform = request.headers.get("Sec-Ch-Ua-Platform", "").strip('"')
    raw = f"{ua_stable}|{accept_lang}|{platform}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _today() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def _get_limits():
    lim = _gh_read(_F_LIMITS)
    if not isinstance(lim, dict):
        lim = {}
    defaults = {
        "FREE_DAILY_ACTIONS": Config.FREE_DAILY_ACTIONS,
        "PRO_PRICE_PKR": Config.PRO_PRICE_PKR,
        "PRO_PRICE_LABEL": Config.PRO_PRICE_LABEL,
        "FREE_PRICE_LABEL": Config.FREE_PRICE_LABEL,
        "CHECKOUT_URL": Config.CHECKOUT_URL,
        "FREE_FEATURES": "✓ Urdu AI Writer|✓ Freelancer Toolkit|✓ Subtitle Generator|✓ 20 actions/day|✗ Ads on every generation|✗ Daily action limit",
        "PRO_FEATURES": "✓ All tools unlimited|✓ Unlimited actions/day|✓ Zero ads|✓ Priority generation|✓ All language styles|✓ Batch subtitle translation",
    }
    defaults.update(lim)
    return defaults

def _get_license_keys():
    keys = _gh_read(_F_KEYS)
    return keys if isinstance(keys, dict) else {}

def _save_license_keys(keys):
    return _gh_write(_F_KEYS, keys, "Update license keys")

def _get_requests():
    data = _gh_read(_F_REQUESTS)
    return data if isinstance(data, list) else []

def _save_requests(data):
    return _gh_write(_F_REQUESTS, data, "Update pro requests")

def _get_usage():
    data = _gh_read(_F_USAGE)
    return data if isinstance(data, dict) else {}

def _save_usage(data):
    return _gh_write(_F_USAGE, data, "Update usage")

def _get_login_attempts():
    data = _gh_read(_F_LOGIN_ATTEMPTS)
    return data if isinstance(data, dict) else {}

def _seed_blog_posts():
    """Default ranking content when blogs.json is empty. Admin can replace via dashboard."""
    return [
        {
            "id": "how-to-write-youtube-scripts-in-urdu",
            "title": "How to Write YouTube Scripts in Natural Pakistani Urdu",
            "category": "YouTube",
            "date": "2026-03-01",
            "published": True,
            "excerpt": "A simple workflow: draft in the Urdu AI Writer, time the script, add subtitles, then generate SEO titles.",
            "related_tool_keys": ["urdu_writer", "script_timing", "subtitles", "youtube_seo"],
            "body": """Pakistani YouTube audiences skip stiff, translated Urdu. Use conversational wording the way people speak in Lahore or Karachi.

Step 1 — Draft the script
Open the Urdu AI Writer, choose “YouTube Script (with hook & CTA)”, pick Pure Urdu or Roman Urdu, and describe your topic with local examples.

Step 2 — Check length
Paste the script into Script Timing. Match your target minutes before you record so you do not ramble or cut important points.

Step 3 — Subtitles
Generate an SRT from the same script with the Subtitle Generator. Captions help retention and accessibility.

Step 4 — Titles and description
Run YouTube SEO with a short summary of the video to get title options, a description, and tags.

Publish, watch analytics, and rewrite weak hooks with the writer again. Consistency beats one perfect video."""
        },
        {
            "id": "fiverr-upwork-proposals-that-win",
            "title": "Fiverr and Upwork Proposals That Win (English + Roman Urdu)",
            "category": "Freelancing",
            "date": "2026-03-05",
            "published": True,
            "excerpt": "Stop sending the same generic pitch. Use the Freelancer Toolkit and proofreader to ship specific proposals fast.",
            "related_tool_keys": ["freelancer", "proofread", "resume"],
            "body": """Clients ignore copy-paste proposals. Mention their project name, one risk you will handle, and a clear next step.

1) Open Freelancer Toolkit → Proposal Writer.
2) Select Fiverr or Upwork, add the client brief, and your real experience only.
3) Generate in English for global clients or Roman Urdu for local work.
4) Run the text through the Urdu Proofreader if any Urdu lines feel off.
5) Keep your Resume / CV updated for profile sections that match the proposal.

Send fewer, better proposals. Track which openings convert and reuse winning structures — not identical paragraphs."""
        },
        {
            "id": "whatsapp-business-auto-replies-pakistan",
            "title": "WhatsApp Business Auto-Replies for Pakistani Shops",
            "category": "Small business",
            "date": "2026-03-10",
            "published": True,
            "excerpt": "Welcome, away, price and order messages your customers will actually read — in Roman Urdu.",
            "related_tool_keys": ["whatsapp_replies", "proofread", "urdu_writer"],
            "body": """Most sales in Pakistan still close on WhatsApp. Slow or robotic replies lose the customer to the next seller.

Use the WhatsApp Business Replies tool:
• Pick your business type (shop, clinic, tuition, freelancer…).
• Choose scenarios: welcome, away, price inquiry, order confirmation, or a full set.
• Prefer Roman Urdu unless your audience expects pure Urdu script.
• Fill bracket placeholders like [price] and [delivery area] before saving in WhatsApp Business quick replies.

For product descriptions longer than a chat bubble, draft with the Urdu AI Writer, then shorten. Always proofread before pinning an auto-reply."""
        },
        {
            "id": "urdu-resume-for-local-and-remote-jobs",
            "title": "Build an Urdu or Bilingual Resume for Local and Remote Jobs",
            "category": "Careers",
            "date": "2026-03-15",
            "published": True,
            "excerpt": "One page of facts, not fluff — English for Upwork, bilingual for Pakistani employers.",
            "related_tool_keys": ["resume", "proofread", "freelancer"],
            "body": """HR and clients scan resumes in seconds. List real roles, tools, and results. Do not invent experience.

1) Open Resume Builder and enter name, target role, experience, education, and skills.
2) Choose English for international platforms, Pure Urdu or Bilingual for local applications.
3) Download the text, paste into Google Docs or Word, and apply simple formatting.
4) Proofread Urdu lines. Keep numbers and employer names accurate.

When you apply to gigs, pair the CV with a tailored proposal from the Freelancer Toolkit."""
        },
    ]

def _get_blog_posts():
    data = _gh_read(_F_BLOGS)
    if isinstance(data, list) and len(data) > 0:
        return data
    return _seed_blog_posts()

def _save_blog_posts(data):
    return _gh_write(_F_BLOGS, data, "Update blogs")

def generate_license_key() -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=14))
    return f"QALAM-PRO-{suffix}"

def create_new_key(grace_hours=None, expires_at=None):
    key = generate_license_key()
    keys = _get_license_keys()
    key_data = {
        "used": False, "revoked": False,
        "created": _now_str(),
        "activated_by": "", "activated_on": "",
        # Rolling device-binding history (last 5 of each signal). Seeded on
        # first activation, extended on every OR-matched reactivation.
        "ip_history": [], "fp_history": [],
        # Capped log of silent auto-restore events (page-load Pro checks),
        # visible to admin for support/abuse review.
        "restore_log": [],
    }
    if grace_hours:
        key_data["grace_expires"] = (datetime.datetime.now() + datetime.timedelta(hours=grace_hours)).strftime("%Y-%m-%d %H:%M")
    # A real subscription expiry (Freemius-backed or admin-approved manual
    # Pro) — see the HARDENING note on check_license() for why this field
    # not existing at all before meant every non-grace key was Pro forever.
    if expires_at:
        key_data["expires_at"] = _normalize_freemius_date(expires_at) or expires_at
    keys[key] = key_data
    _save_license_keys(keys)
    return key

def _normalize_freemius_date(raw: str) -> str:
    """Freemius sends license expiration timestamps as
    'YYYY-MM-DD HH:MM:SS' (with seconds, sometimes with a 'T' separator) —
    normalize to this app's 'YYYY-MM-DD HH:MM' storage format used
    everywhere else (grace_expires, created, etc). Returns '' on anything
    unparseable so callers can fall back to a sane default instead of
    storing a string that'll later fail strptime and get silently
    swallowed by the bare except in check_license()."""
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return ""

def find_key_by_freemius_id(freemius_license_id: str):
    """Looks up an internal key by the Freemius license ID stored on it at
    creation time — used by the renewal/cancellation webhook events, which
    only ever carry the Freemius license ID, not our internal key string."""
    if not freemius_license_id:
        return None
    keys = _get_license_keys()
    for k, v in keys.items():
        if str(v.get("freemius_license_id", "")) == str(freemius_license_id):
            return k
    return None

def sync_license_from_freemius_event(freemius_license_id: str, event_type: str, new_expiration: str = "") -> dict:
    """HARDENING — this whole function is new. Handles license.extended /
    license.cancelled / license.expired, which the webhook previously
    didn't handle AT ALL (every event besides the initial purchase fell
    through to "Event ignored"). Combined with create_new_key() never
    setting any expiry on a Freemius-sourced key (see its own note), this
    meant a QalamStudio Pro subscriber who cancelled kept full Pro access
    forever — there was no mechanism that would ever revoke or expire
    their key, no matter how long past their last real payment.

    This mirrors VoxCraft's already-working licensing.py pattern:
      - license.extended: push expires_at out to whatever Freemius says the
        new period ends (never guess +30 days blindly — an annual renewal
        would otherwise get cut off after 30 days), and clear any prior
        revoke (recovers from a failed-then-retried renewal).
      - license.expired: revoke — safety net in case a renewal's extend
        event was ever missed.
      - license.cancelled: deliberately NOT revoked here — Freemius keeps
        the license valid through the period the customer already paid
        for; license.expired fires separately once that period actually
        ends.
    """
    if not freemius_license_id:
        return {"success": False, "error": "No freemius_license_id in webhook payload."}
    key = find_key_by_freemius_id(freemius_license_id)
    if not key:
        return {"success": False, "error": f"No internal key found for Freemius license {freemius_license_id} — was it ever created via the initial purchase webhook?"}
    keys = _get_license_keys()
    info = keys[key]
    if event_type == "license.extended":
        info["expires_at"] = _normalize_freemius_date(new_expiration) if new_expiration else \
            (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
        info["revoked"] = False
        info["renewal_count"] = info.get("renewal_count", 0) + 1
        _save_license_keys(keys)
        return {"success": True, "action": "extended", "key": key, "new_expiry": info["expires_at"]}
    if event_type == "license.expired":
        info["revoked"] = True
        _save_license_keys(keys)
        return {"success": True, "action": "revoked_expired", "key": key}
    if event_type == "license.cancelled":
        return {"success": True, "action": "cancellation_noted", "key": key}
    return {"success": False, "error": "unhandled event"}

def create_freemius_license(user_name, user_email, freemius_meta=None):
    """Mint an internal QalamStudio license key for a completed Freemius purchase.

    BUG FIX: this used to call `POST /plugins/{plugin_id}/licenses.json` on
    Freemius's API to try to CREATE a license there. That endpoint doesn't
    exist anywhere in Freemius's current documented API (checked against
    their live API docs — license endpoints are all under
    /products/{product_id}/licenses..., nothing under /plugins/.../licenses.json).
    That meant every real paying customer's webhook silently failed here,
    so no license key was ever generated for them automatically.

    Per Freemius's own documented pattern ("leverage the webhook mechanism to
    synchronize the license"), there's no need to call their API to create
    anything — Freemius already created ITS OWN license as part of the
    purchase; the webhook is just telling us that happened. We only need our
    own internal key, tied to that purchase, using the exact same generator
    already used for the manual-payment flow.

    HARDENING: previously called create_new_key() with no expiry at all —
    meaning this key, once minted, was valid forever regardless of what
    happens to the actual Freemius subscription afterward. Now takes the
    real expiration Freemius already computed for this purchase (passed in
    via freemius_meta) so license.extended/expired events (see
    sync_license_from_freemius_event above) have an existing expires_at to
    actually update, instead of a permanent key that renewal/cancellation
    logic could never meaningfully touch.
    """
    key = create_new_key(expires_at=(freemius_meta or {}).get("expiration", ""))
    keys = _get_license_keys()
    keys[key]["source"] = "freemius"
    keys[key]["user_email"] = user_email
    keys[key]["user_name"] = user_name
    if freemius_meta:
        # NOTE: exact field names depend on Freemius's webhook payload shape —
        # these are extracted defensively (.get with a default) since I
        # couldn't verify the live payload structure without a real webhook
        # to inspect. Check your admin panel after a real test purchase to
        # confirm these are populating, and adjust the .get() keys below to
        # match whatever Freemius actually sends if they don't.
        keys[key]["freemius_license_id"] = freemius_meta.get("license_id", "")
        keys[key]["freemius_subscription_id"] = freemius_meta.get("subscription_id", "")
    _save_license_keys(keys)
    return key, None

def verify_freemius_license(license_key):
    """Verify a license key directly against Freemius.

    BUG FIX: this used to call `GET /plugins/{plugin_id}/licenses/{key}.json`
    with HMAC signing — same non-existent-endpoint problem as
    create_freemius_license (see its docstring). This was also NEVER CALLED
    anywhere in the app, so it was dead code — meaning there was no way for a
    customer to directly enter a raw Freemius-issued license key; the only
    path to Pro via Freemius was the webhook. Fixed to use the correct,
    currently-documented endpoint: `GET /products/{product_id}/licenses/{id}.json`
    with simple Bearer token auth (product-scoped operations use Bearer auth,
    not HMAC signing — confirmed against Freemius's current API docs), and
    wired into activate_license() as a fallback below so this is reachable.
    """
    if not (Config.FREEMIUS_API_KEY and Config.FREEMIUS_PRODUCT_ID):
        return {"success": False, "valid": False, "error": "Freemius not configured on this deployment."}
    try:
        resp = req.get(
            f"https://api.freemius.com/v1/products/{Config.FREEMIUS_PRODUCT_ID}/licenses/{license_key}.json",
            headers={"Authorization": f"Bearer {Config.FREEMIUS_API_KEY}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"success": False, "valid": False, "error": f"HTTP {resp.status_code}"}
        data = resp.json()
        is_cancelled = bool(data.get("is_cancelled", False))
        expiration = data.get("expiration")
        is_expired = False
        if expiration:
            try:
                is_expired = datetime.datetime.strptime(expiration, "%Y-%m-%d %H:%M:%S") < datetime.datetime.now()
            except Exception:
                is_expired = False
        is_valid = (not is_cancelled) and (not is_expired)
        return {
            "success": True, "valid": is_valid,
            "freemius_license_id": data.get("id", ""),
            "user_email": data.get("user_email", "") or data.get("email", ""),
            "user_name": data.get("user_name", "") or "Pro User",
            # HARDENING: wasn't returned before, so fs_callback (the
            # customer's-browser-lands-here path) had no way to pass a real
            # expiry into create_freemius_license — only the webhook path
            # did. Now both paths mint a key with the actual Freemius
            # billing period instead of one of them being permanent.
            "expiration": expiration or "",
            "error": None if is_valid else ("License cancelled" if is_cancelled else "License expired"),
        }
    except Exception as e:
        return {"success": False, "valid": False, "error": str(e)}

def _push_history(hist_list, value, cap=5):
    """Append `value` to a rolling history list, deduping and capping at
    `cap` most-recent entries. Mutates and returns the list."""
    if not isinstance(hist_list, list):
        hist_list = []
    if value in hist_list:
        hist_list.remove(value)
    hist_list.append(value)
    return hist_list[-cap:]

def check_license(key: str) -> dict:
    """Used by /api/restore-pro to silently re-confirm Pro status for a
    device on page load (JS calls this automatically with the key it has
    stored in localStorage — no user action involved).

    SECURITY: this previously matched on IP alone, so anyone who obtained a
    copy of an already-activated key could get silent Pro on ANY device by
    hitting this endpoint. It's now also fixed to require BOTH the current
    IP hash AND browser fingerprint to appear in the key's rolling history
    (AND, not OR) before granting Pro without any user action — matching
    VoxCraft's device-binding pattern. Requiring both avoids false positives
    on shared IPs (CGNAT, office wifi, campus networks) where a stranger on
    the same IP shouldn't silently inherit someone else's Pro status just
    because a fingerprint happens to overlap, or vice versa. Manual
    reactivation (typing the key back in) is deliberately more lenient —
    see activate_license() — since a real human is present to notice if
    something's wrong.
    """
    key = key.strip()
    keys = _get_license_keys()
    info = keys.get(key)
    if not info:
        return {"valid": False}
    if info.get("revoked"):
        return {"valid": False, "error": "This license has been revoked."}
    if info.get("grace_expires"):
        try:
            expires = datetime.datetime.strptime(info["grace_expires"], "%Y-%m-%d %H:%M")
            if datetime.datetime.now() > expires:
                return {"valid": False, "error": "Grace period expired. Contact support."}
        except Exception:
            pass
    # HARDENING: this check didn't exist at all before — a non-grace key
    # (Freemius-sourced or admin-approved manual Pro) had no expiry
    # concept whatsoever, so a cancelled/lapsed subscriber's key kept
    # returning valid=True forever. See create_new_key/create_freemius_license
    # and sync_license_from_freemius_event for where expires_at now gets
    # set and kept in sync with the real Freemius billing period.
    if info.get("expires_at"):
        try:
            expires = datetime.datetime.strptime(info["expires_at"], "%Y-%m-%d %H:%M")
            if datetime.datetime.now() > expires:
                return {"valid": False, "error": "Your subscription has expired."}
        except Exception:
            pass
    if not info.get("used"):
        return {"valid": False, "error": "This key hasn't been activated yet."}

    current_ip = _get_user_ip()
    ip_hash = _hash_ip(current_ip)
    fp_hash = _get_browser_fingerprint()
    ip_ok = current_ip != "unknown" and ip_hash in (info.get("ip_history") or [])
    fp_ok = fp_hash in (info.get("fp_history") or [])
    if not (ip_ok and fp_ok):
        return {"valid": False, "error": "This key was activated on a different device."}

    # Log the auto-restore event (best-effort, capped at 10) for admin
    # visibility — doesn't block the response if the write is slow/fails.
    def _log_restore(fresh_keys):
        k = fresh_keys.get(key)
        if not k:
            return fresh_keys, None
        log = k.get("restore_log") or []
        log.append({"at": _now_str(), "ip": ip_hash, "fp": fp_hash})
        k["restore_log"] = log[-10:]
        return fresh_keys, True
    threading.Thread(target=lambda: _gh_transact(_F_KEYS, _log_restore, "Log auto-restore"), daemon=True).start()

    return {"valid": True, "name": "Pro User"}

def activate_license(key: str) -> dict:
    """Activates an internal QALAM-PRO-xxx key. If the key isn't found
    locally, falls back to checking it against Freemius directly (for
    customers who have a raw Freemius-issued key rather than one emailed by
    our own webhook flow) — this was previously unreachable since
    verify_freemius_license() was never called from anywhere. On a successful
    Freemius verify, mints an internal key wrapping it (reusing the same one
    on repeat activations from the same Freemius license, rather than
    minting a fresh one every time) so it flows through the same
    device-binding/admin-visibility logic as every other key."""
    key = key.strip()
    keys = _get_license_keys()
    if key in keys:
        info = keys[key]
        if info.get("revoked"):
            return {"valid": False, "error": "This license key has been revoked. Contact support."}

        current_ip = _get_user_ip()
        ip_hash = _hash_ip(current_ip)
        fp_hash = _get_browser_fingerprint()

        if info.get("used"):
            # Manual reactivation (user typed the key back in themselves —
            # e.g. reinstalled their browser, or is on a new device they
            # own). Matches on EITHER signal (OR): a real person is present
            # to notice if this rejects them incorrectly, so we can afford
            # to be more lenient here than the silent auto-restore path.
            ip_ok = current_ip != "unknown" and ip_hash in (info.get("ip_history") or [])
            fp_ok = fp_hash in (info.get("fp_history") or [])
            if ip_ok or fp_ok:
                def _extend(fresh_keys):
                    k = fresh_keys.get(key)
                    if not k or k.get("revoked") or not k.get("used"):
                        return fresh_keys, None
                    k["ip_history"] = _push_history(k.get("ip_history"), ip_hash)
                    k["fp_history"] = _push_history(k.get("fp_history"), fp_hash)
                    return fresh_keys, True
                _gh_transact(_F_KEYS, _extend, "Extend device history")
                return {"valid": True, "name": "Pro User"}
            return {"valid": False, "error": "This key has already been used. Each key is one-time use only."}

        # First activation — CAS transaction against a FRESH read (not the
        # `keys` snapshot above, which may be stale from the 60s cache or
        # already out of date). Closes the race where two simultaneous
        # first-activations of the same key could both be told they won.
        def _claim(fresh_keys):
            k = fresh_keys.get(key)
            if not k or k.get("revoked") or k.get("used"):
                return fresh_keys, None
            k["used"] = True
            k["activated_on"] = _now_str()
            k["activated_by"] = ip_hash  # kept for back-compat / admin display
            k["ip_history"] = _push_history(k.get("ip_history"), ip_hash)
            k["fp_history"] = _push_history(k.get("fp_history"), fp_hash)
            return fresh_keys, True
        claimed = _gh_transact(_F_KEYS, _claim, "Activate license key")
        if claimed:
            return {"valid": True, "name": "Pro User"}
        return {"valid": False, "error": "This key has already been used. Each key is one-time use only."}

    # Not one of ours — try it as a raw Freemius license key.
    result = verify_freemius_license(key)
    if not result.get("success") or not result.get("valid"):
        return {"valid": False, "error": result.get("error") or "Invalid license key."}

    fs_id = result.get("freemius_license_id", "")
    internal_key = None
    for k, v in keys.items():
        if v.get("freemius_license_id") == fs_id and fs_id:
            internal_key = k
            break
    if not internal_key:
        internal_key = create_new_key()
        keys = _get_license_keys()
        keys[internal_key]["source"] = "freemius"
        keys[internal_key]["freemius_license_id"] = fs_id
        keys[internal_key]["user_email"] = result.get("user_email", "")
        keys[internal_key]["user_name"] = result.get("user_name", "")
        _save_license_keys(keys)

    return activate_license(internal_key)

# ──────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ──────────────────────────────────────────────────────────────────────
def _notify_admin(name, email, phone, req_id, payment_method="", txn_id="", screenshot_b64=""):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    payment_line = f"💳 Payment: {payment_method}" if payment_method else "📝 Payment: Not submitted"
    txn_line = f"🧾 Txn/Ref ID: {txn_id}" if txn_id else ""
    message_body = f"""🚀 New Pro Request!

👤 Name: {name}
📧 Email: {email}
📱 Phone: {phone or 'N/A'}
🆔 Request ID: {req_id}
{payment_line}
{txn_line}

Go to Admin Panel → Pro Requests to approve and generate a license key.

---
QalamStudio Admin
"""
    notified = False
    errors = []

    # Mailtrap
    if Config.MAILTRAP_API_KEY and Config.ADMIN_EMAIL:
        try:
            pay_badge = payment_method if payment_method else "Not provided"
            txn_row = f"<tr><td style=\'padding:6px 0;color:#888;font-size:13px\'>Transaction ID</td><td style=\'padding:6px 0;color:#fff;font-size:13px;font-weight:700\'>{txn_id}</td></tr>" if txn_id else ""
            admin_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0f1e;font-family:Arial,sans-serif">
  <div style="max-width:520px;margin:0 auto;padding:24px 16px">
    <div style="background:linear-gradient(135deg,#00c896,#3b82f6);border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
      <div style="font-size:28px;margin-bottom:4px">✍️</div>
      <div style="color:#000;font-size:18px;font-weight:800">New Pro Request!</div>
    </div>
    <div style="background:#111827;border-radius:12px;padding:20px;margin-bottom:16px">
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#888;font-size:13px">Name</td><td style="padding:6px 0;color:#fff;font-size:13px;font-weight:700">{name}</td></tr>
        <tr><td style="padding:6px 0;color:#888;font-size:13px">Email</td><td style="padding:6px 0;color:#00c896;font-size:13px">{email}</td></tr>
        <tr><td style="padding:6px 0;color:#888;font-size:13px">Phone</td><td style="padding:6px 0;color:#fff;font-size:13px">{phone or "—"}</td></tr>
        <tr><td style="padding:6px 0;color:#888;font-size:13px">Request ID</td><td style="padding:6px 0;color:#fff;font-size:11px;font-family:monospace">{req_id}</td></tr>
        <tr><td style="padding:6px 0;color:#888;font-size:13px">Payment</td><td style="padding:6px 0"><span style="background:#00c896;color:#000;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700">{pay_badge}</span></td></tr>
        {txn_row}
      </table>
    </div>
    <a href="https://app.qalamstudio.xyz/admin" style="display:block;background:linear-gradient(135deg,#00c896,#3b82f6);color:#000;text-align:center;padding:12px;border-radius:10px;text-decoration:none;font-weight:800;font-size:14px;margin-bottom:16px">→ Open Admin Panel to Approve</a>
  </div>
</body></html>"""
            from_name, from_email = _parse_from_address(Config.CONTACT_FROM_EMAIL)
            email_payload = {
                "from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
                "to": [{"email": Config.ADMIN_EMAIL}],
                "subject": f"💳 New Pro Payment — {name}",
                "html": admin_html,
                "text": message_body
            }
            if screenshot_b64:
                email_payload["attachments"] = [{
                    "filename": "payment_proof.jpg",
                    "content": screenshot_b64,
                    "type": "image/jpeg"
                }]
            r = req.post("https://send.api.mailtrap.io/api/send",
                headers={"Api-Token": Config.MAILTRAP_API_KEY, "Content-Type": "application/json"},
                json=email_payload, timeout=20)
            if r.status_code == 200:
                notified = True
            else:
                errors.append(f"Mailtrap: {r.status_code}")
            # User confirmation
            if email and notified:
                user_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#06080f;font-family:Arial,sans-serif">
<div style="max-width:520px;margin:0 auto;padding:24px 16px">
  <div style="background:linear-gradient(135deg,#00c896,#3b82f6);border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
    <div style="font-size:32px;margin-bottom:4px">✍️</div>
    <div style="color:#000;font-size:18px;font-weight:800">Payment Received!</div>
  </div>
  <div style="background:#0d1120;border-radius:12px;padding:20px;margin-bottom:16px">
    <p style="color:#ccc;font-size:14px">Hi <strong style="color:#fff">{name}</strong>,</p>
    <p style="color:#ccc;font-size:14px">We have received your payment request for <strong style="color:#00c896">QalamStudio Pro</strong>.</p>
    <div style="background:#0a0f1e;border-radius:8px;padding:12px;margin:16px 0">
      <div style="color:#888;font-size:11px">Your Request ID</div>
      <div style="color:#00c896;font-size:13px;font-family:monospace;font-weight:700">{req_id}</div>
    </div>
  </div>
</div></body></html>"""
                try:
                    req.post("https://send.api.mailtrap.io/api/send",
                        headers={"Api-Token": Config.MAILTRAP_API_KEY, "Content-Type": "application/json"},
                        json={"from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
                              "to": [{"email": email}],
                              "subject": "✅ Payment Received — QalamStudio Pro", "html": user_html}, timeout=15)
                except Exception:
                    pass
        except Exception as e:
            errors.append(f"Mailtrap: {e}")

    # SMTP fallback
    if not notified and Config.SMTP_HOST and Config.SMTP_USER and Config.SMTP_PASS and Config.ADMIN_EMAIL:
        try:
            msg = MIMEMultipart()
            msg["From"] = Config.SMTP_USER
            msg["To"] = Config.ADMIN_EMAIL
            msg["Subject"] = f"🚀 QalamStudio Pro Request - {name}"
            msg.attach(MIMEText(message_body, "plain", "utf-8"))
            if Config.SMTP_PORT == 465:
                import ssl
                server = smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)
                server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASS.replace(" ", ""))
            server.send_message(msg)
            server.quit()
            notified = True
        except Exception as e:
            errors.append(f"SMTP: {e}")

    # WhatsApp
    if not notified and Config.WHATSAPP_API_TOKEN and Config.WHATSAPP_PHONE_NUMBER_ID and Config.WHATSAPP_ADMIN_NUMBER:
        try:
            url = f"https://graph.facebook.com/v22.0/{Config.WHATSAPP_PHONE_NUMBER_ID}/messages"
            headers = {"Authorization": f"Bearer {Config.WHATSAPP_API_TOKEN}", "Content-Type": "application/json"}
            payload = {"messaging_product": "whatsapp", "to": Config.WHATSAPP_ADMIN_NUMBER,
                       "type": "text", "text": {"body": message_body}}
            r = req.post(url, headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                notified = True
        except Exception as e:
            errors.append(f"WhatsApp: {e}")

    # Wappfly
    if not notified and Config.WAPPFLY_API_KEY and Config.WAPPFLY_ADMIN_NUMBER:
        try:
            r = req.post("https://api.wappfly.com/v1/messages",
                headers={"Authorization": f"Bearer {Config.WAPPFLY_API_KEY}", "Content-Type": "application/json"},
                json={"to": Config.WAPPFLY_ADMIN_NUMBER, "type": "text", "text": {"body": message_body}}, timeout=10)
            if r.status_code == 200:
                notified = True
        except Exception as e:
            errors.append(f"Wappfly: {e}")

    return notified

def _send_key_email(user_email, user_name, license_key):
    if not Config.MAILTRAP_API_KEY or not user_email:
        return False
    try:
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#06080f;font-family:Arial,sans-serif">
<div style="max-width:520px;margin:0 auto;padding:24px 16px">
  <div style="background:linear-gradient(135deg,#00c896,#3b82f6);border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
    <div style="font-size:32px;margin-bottom:4px">✍️</div>
    <div style="color:#000;font-size:18px;font-weight:800">Your Pro License is Ready!</div>
  </div>
  <div style="background:#0d1120;border-radius:12px;padding:20px;margin-bottom:16px">
    <p style="color:#ccc;font-size:14px">Hi <strong style="color:#fff">{user_name}</strong>,</p>
    <p style="color:#ccc;font-size:14px">Your payment has been verified. Here is your license key:</p>
    <div style="background:#06080f;border-radius:8px;padding:12px;margin:16px 0;text-align:center">
      <div style="color:#888;font-size:11px">Your License Key</div>
      <div style="color:#00c896;font-size:16px;font-family:monospace;font-weight:700;letter-spacing:1px">{license_key}</div>
    </div>
  </div>
</div></body></html>"""
        from_name, from_email = _parse_from_address(Config.CONTACT_FROM_EMAIL)
        r = req.post("https://send.api.mailtrap.io/api/send",
            headers={"Api-Token": Config.MAILTRAP_API_KEY, "Content-Type": "application/json"},
            json={"from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
                  "to": [{"email": user_email}],
                  "subject": "🎉 Your QalamStudio Pro License Key", "html": html}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def _is_valid_image(b64_data: str) -> bool:
    """Confirms the uploaded 'screenshot' actually decodes as a real image —
    doesn't verify it's a genuine payment screenshot, but filters out blank
    files, corrupted uploads, or non-image files being used to satisfy the
    upload requirement."""
    if not b64_data:
        return False
    try:
        from PIL import Image
        import io as _io
        raw = base64.b64decode(b64_data, validate=True)
        img = Image.open(_io.BytesIO(raw))
        img.verify()
        return True
    except Exception:
        return False


def _device_already_auto_approved(ip_hash: str) -> bool:
    """One auto-approval per device, ever. Without this, the same person
    could resubmit with a new email each time and get a fresh grace-period
    Pro window indefinitely — this closes that loop while still letting a
    genuine first-time visitor get instant access."""
    if not ip_hash or ip_hash == _hash_ip("unknown"):
        return False
    for r in _get_requests():
        if r.get("auto_approved") and r.get("ip") == ip_hash:
            return True
    return False


# ── Fraud-hardening helpers for manual-payment auto-approval ──
# HARDENING: none of this existed before — the only checks were "was a txn
# id typed" and "is the upload a real image". Porting VoxCraft's already-
# working fraud layer (same functions, same logic) since this flow controls
# instant Pro access:
#   - a live (pending/payment_pending/approved) txn_id or screenshot hash
#     seen on a second request is essentially always the same payment being
#     claimed twice, or a fabricated id
#   - OCR cross-checks that the screenshot the customer uploaded actually
#     shows the txn_id they typed AND an amount close to what Pro costs —
#     without this, "upload any image + type any string" was sufficient to
#     get instant grace-period Pro access
_LIVE_STATUSES = ("pending", "payment_pending", "approved")


def _txn_id_is_duplicate(txn_id: str, exclude_req_id: str = "") -> bool:
    txn_id = (txn_id or "").strip().lower()
    if not txn_id:
        return False
    for r in _get_requests():
        if r.get("id") == exclude_req_id:
            continue
        if r.get("status") in _LIVE_STATUSES and (r.get("txn_id") or "").strip().lower() == txn_id:
            return True
    return False


def _screenshot_sha256(screenshot_b64: str) -> str:
    if not screenshot_b64:
        return ""
    try:
        raw = base64.b64decode(screenshot_b64, validate=True)
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        return ""


def _screenshot_is_duplicate(screenshot_hash: str, exclude_req_id: str = "") -> bool:
    if not screenshot_hash:
        return False
    for r in _get_requests():
        if r.get("id") == exclude_req_id:
            continue
        if r.get("status") in _LIVE_STATUSES and r.get("screenshot_sha256") == screenshot_hash:
            return True
    return False


RATE_LIMIT_MAX_PENDING_PER_IP = 3
RATE_LIMIT_WINDOW_HOURS = 24


def _rate_limited(ip_hash: str) -> bool:
    """Caps how many still-open requests one device can have in flight at
    once — stops the admin review queue (and admin's inbox, since every
    submission emails _notify_admin) from being flooded by someone
    spamming the form, without touching a genuine customer who'd only ever
    submit once per purchase."""
    if not ip_hash:
        return False
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=RATE_LIMIT_WINDOW_HOURS)
    count = 0
    for r in _get_requests():
        if r.get("ip") != ip_hash or r.get("status") not in ("pending", "payment_pending"):
            continue
        try:
            if datetime.datetime.strptime(r.get("date", ""), "%Y-%m-%d %H:%M") < cutoff:
                continue
        except Exception:
            pass
        count += 1
    return count >= RATE_LIMIT_MAX_PENDING_PER_IP


def _ocr_extract_text(screenshot_b64: str) -> str:
    """Best-effort OCR of the uploaded screenshot. Returns '' — treated as
    'inconclusive', never as a failure — whenever pytesseract or the
    underlying tesseract-ocr system binary isn't installed.

    DEPLOYMENT NOTE: Render's native Python runtime does NOT have
    tesseract-ocr preinstalled, unlike a VPS where `apt install
    tesseract-ocr` is a one-line fix. Without it, ocr_available is always
    False below, which means auto-approval requires admin review for
    EVERY manual payment — AUTO_APPROVE_MANUAL effectively stops instantly
    approving anyone until tesseract-ocr is available in this deployment
    (e.g. via a Render Dockerfile that apt-installs it, since the native
    runtime has no aptfile mechanism). This is a deliberate trade: silent,
    ungated auto-approval was the actual security hole being closed here."""
    if not screenshot_b64:
        return ""
    try:
        import pytesseract
        from PIL import Image
        import io as _io
        raw = base64.b64decode(screenshot_b64, validate=True)
        img = Image.open(_io.BytesIO(raw))
        return pytesseract.image_to_string(img).lower()
    except Exception:
        return ""


def _digits_only(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _ocr_txn_id_found(ocr_text: str, txn_id: str) -> bool:
    txn_digits = _digits_only(txn_id)
    if len(txn_digits) < 4:
        return False
    return txn_digits in _digits_only(ocr_text)


def _ocr_amount_found(ocr_text: str, expected_amount, tolerance_pct: float = 2.0) -> bool:
    if not expected_amount:
        return False
    try:
        expected = float(expected_amount)
    except Exception:
        return False
    if expected <= 0:
        return False
    tol = max(expected * (tolerance_pct / 100.0), 1.0)
    for token in re.findall(r"\d[\d,]*\.?\d*", ocr_text or ""):
        try:
            val = float(token.replace(",", ""))
        except ValueError:
            continue
        if abs(val - expected) <= tol:
            return True
    return False


def submit_pro_request(name, email, phone="", payment_method="", txn_id="", screenshot_b64=""):
    requests_list = _get_requests()
    req_id = f"REQ-{int(time.time())}-{random.randint(1000,9999)}"
    ip_hash = _hash_ip(_get_user_ip())

    if _rate_limited(ip_hash):
        return {"success": False, "id": req_id,
                "error": "You already have a few payment requests awaiting review. Please wait for those to be processed before submitting another."}

    screenshot_hash = _screenshot_sha256(screenshot_b64)
    duplicate_txn = _txn_id_is_duplicate(txn_id)
    duplicate_screenshot = _screenshot_is_duplicate(screenshot_hash)

    limits = _get_limits()
    expected_amount = int(limits.get("PRO_PRICE_PKR", Config.PRO_PRICE_PKR) or 0)

    ocr_text = _ocr_extract_text(screenshot_b64)
    ocr_available = bool(ocr_text.strip())
    ocr_txn_match = _ocr_txn_id_found(ocr_text, txn_id) if ocr_available else False
    ocr_amount_match = _ocr_amount_found(ocr_text, expected_amount) if ocr_available else False

    auto_approved = False
    auto_rejected = False
    reject_reason = ""
    license_key = ""

    # ---- Auto-reject clear junk (never hits admin inbox) ----
    if duplicate_txn:
        auto_rejected = True
        reject_reason = "This transaction ID was already used on another request."
    elif duplicate_screenshot and screenshot_b64:
        auto_rejected = True
        reject_reason = "This payment screenshot was already used on another request."
    elif payment_method and (not txn_id or len(txn_id.strip()) < 6):
        auto_rejected = True
        reject_reason = "A valid transaction / reference ID (at least 6 characters) is required."
    elif payment_method and screenshot_b64 and not _is_valid_image(screenshot_b64):
        auto_rejected = True
        reject_reason = "The uploaded screenshot is not a valid image. Please upload a clear PNG or JPG."
    elif ocr_available and txn_id.strip() and not ocr_txn_match and screenshot_b64:
        auto_rejected = True
        reject_reason = ("The transaction ID you entered does not appear in the payment screenshot. "
                          "Double-check both and submit again.")

    if auto_rejected:
        status = "rejected"
    # ---- Auto-approve → GRACE access only (never permanent) ----
    # Requires ALL of: AUTO_APPROVE_MANUAL enabled, valid unique image+txn,
    # OCR actually readable (if tesseract missing → admin queue, no blind
    # approve — see _ocr_extract_text's deployment note), OCR finds the
    # typed txn ID AND an amount within ±2% of PRO_PRICE_PKR in the image,
    # and this device hasn't already had a grace auto-approval before.
    elif (Config.AUTO_APPROVE_MANUAL and txn_id.strip() and _is_valid_image(screenshot_b64)
            and not _device_already_auto_approved(ip_hash)
            and ocr_available and ocr_txn_match and ocr_amount_match):
        license_key = create_new_key(grace_hours=Config.MANUAL_GRACE_HOURS)
        auto_approved = True
        status = "approved"
    else:
        status = "pending"

    new_request = {
        "id": req_id, "name": name.strip(), "email": email.strip(), "phone": phone.strip(),
        "status": status, "date": _now_str(), "key_assigned": license_key,
        "ip": ip_hash, "notified": False,
        "payment_method": payment_method, "txn_id": txn_id.strip(),
        "has_screenshot": bool(screenshot_b64), "screenshot_sha256": screenshot_hash,
        "auto_approved": auto_approved, "auto_rejected": auto_rejected, "reject_reason": reject_reason,
        "grace_expires": (datetime.datetime.now() + datetime.timedelta(hours=Config.MANUAL_GRACE_HOURS)).strftime("%Y-%m-%d %H:%M") if auto_approved else "",
        # HARDENING — see sweep_grace_reminders() below for the gap this
        # closes: an auto-approved request's status is already "approved"
        # immediately (it's just a temporary grace key, not permanent), and
        # without this flag there was no way to tell "genuinely finalized"
        # apart from "still just running on borrowed time" — so the admin
        # dashboard's Approved tab treated both identically, with no button
        # to ever finalize a grace approval to a permanent key.
        "access_type": "grace" if auto_approved else "",
        "grace_finalized": False,
        "grace_reminder_sent": False,
        "grace_expired_notified": False,
    }
    if auto_rejected:
        new_request["rejected_date"] = _now_str()
    requests_list.insert(0, new_request)

    # Notify admin (skip for clear junk that was already auto-rejected — no
    # need to alert admin about a duplicate/forged submission that never
    # reaches the review queue)
    notified = False if auto_rejected else _notify_admin(name, email, phone, req_id, payment_method, txn_id, screenshot_b64)
    new_request["notified"] = notified

    # If auto-approved, email key immediately
    if auto_approved and license_key:
        _send_key_email(email, name, license_key)

    ok, err = _save_requests(requests_list)
    return {
        "success": ok, "id": req_id, "notified": notified, 
        "error": err, "auto_approved": auto_approved, 
        "auto_rejected": auto_rejected, "reject_reason": reject_reason,
        "license_key": license_key
    }

def approve_request(req_id, license_key):
    requests = _get_requests()
    user_email = None
    user_name = None
    for r in requests:
        if r["id"] == req_id:
            r["status"] = "approved"
            r["key_assigned"] = license_key
            r["approved_date"] = _now_str()
            # If this was a grace auto-approval, this call IS the
            # finalization to a permanent key — a no-op for a plain
            # (non-grace) approval, which never sets access_type at all.
            # See sweep_grace_reminders(): without this flag, a finalized
            # grace request would keep getting reminder/lapsed emails
            # forever since nothing would ever tell the sweep to stop.
            r["grace_finalized"] = True
            user_email = r.get("email")
            user_name = r.get("name", "Pro User")
            break
    if user_email:
        _save_requests(requests)
        _send_key_email(user_email, user_name, license_key)
        return True
    _save_requests(requests)
    return False

def reject_request(req_id):
    requests = _get_requests()
    for r in requests:
        if r["id"] == req_id:
            r["status"] = "rejected"
            r["rejected_date"] = _now_str()
            # HARDENING: a plain pending reject never had a key issued, so
            # there was nothing to revoke — reject_request only ever needed
            # to flip status. But a grace auto-approval DOES already have a
            # live, activated key by the time admin ever sees the request.
            # Rejecting it here (fraud found on manual review) previously
            # left that key fully working until it happened to hit
            # grace_expires on its own — this cuts it off immediately.
            key = r.get("key_assigned")
            if key and r.get("access_type") == "grace":
                keys = _get_license_keys()
                if key in keys:
                    keys[key]["revoked"] = True
                    _save_license_keys(keys)
                r["grace_finalized"] = True  # rejected is terminal too — stop reminder emails
            _save_requests(requests)
            return True
    return False

# How long before a grace-period auto-approval lapses to send admin a
# heads-up that it still hasn't been converted to a permanent key.
# Comfortably short of the default 72h MANUAL_GRACE_HOURS.
GRACE_REMINDER_HOURS_BEFORE = 12


def _notify_admin_grace_status(subject: str, text: str) -> bool:
    """Minimal plain-text admin email for the grace-reminder sweep — reuses
    the same Mailtrap HTTPS API + config already used elsewhere in this file
    (and already fixed to use the API instead of raw SMTP, see contact()),
    without pulling in the full HTML template _notify_admin builds for a
    brand new payment request."""
    if not (Config.MAILTRAP_API_KEY and Config.ADMIN_EMAIL):
        return False
    try:
        from_name, from_email = _parse_from_address(Config.CONTACT_FROM_EMAIL)
        r = req.post("https://send.api.mailtrap.io/api/send",
            headers={"Api-Token": Config.MAILTRAP_API_KEY, "Content-Type": "application/json"},
            json={"from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
                  "to": [{"email": Config.ADMIN_EMAIL}],
                  "subject": subject, "text": text}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False


def sweep_grace_reminders() -> dict:
    """HARDENING — this whole function is new. Closes the silent dead-end
    in the auto-approval flow: once a manual payment is auto-approved,
    submit_pro_request() immediately sets status="approved" with a
    temporary GRACE key — but the admin dashboard's Approved tab rendered
    a grace-approved row identically to a genuinely finalized one (just the
    key text, a Delete button, nothing to act on), so it had NO way to
    resurface for finalization. Left alone, the customer's temporary access
    just expired at MANUAL_GRACE_HOURS with no reminder, no record anyone
    missed it, and no admin action ever possible short of manually
    cross-referencing raw request data against grace_expires.

    Called from a background thread (see _start_grace_reminder_sweep_thread
    below) — NOT tied to anyone opening /admin, which was exactly the
    problem. Mirrors the same fix already shipped in VoxCraft's
    pro_requests.sweep_grace_reminders():
      1. GRACE_REMINDER_HOURS_BEFORE hours before grace_expires, if still
         not grace_finalized, emails admin once (grace_reminder_sent flag
         stops repeats).
      2. If grace_expires has already passed and it's STILL not finalized,
         emails a separate one-time "lapsed" alert — the safety net for a
         reminder that got missed or never actioned.

    Never touches the customer's actual access — check_license() already
    cuts that off live via grace_expires regardless. This only guarantees a
    human finds out before/around the moment it happens, instead of never.
    """
    reqs = _get_requests()
    changed = False
    now = datetime.datetime.now()
    reminded, missed = 0, 0
    for r in reqs:
        if r.get("access_type") != "grace" or r.get("grace_finalized"):
            continue
        expires_raw = r.get("grace_expires", "")
        if not expires_raw:
            continue
        try:
            expires_at = datetime.datetime.strptime(expires_raw, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue
        name, email, req_id = r.get("name", ""), r.get("email", ""), r.get("id", "")
        if now >= expires_at:
            if not r.get("grace_expired_notified"):
                text = (f"QalamStudio — grace period LAPSED unreviewed\n\n"
                        f"{name} <{email}> (request {req_id}) was auto-approved for temporary "
                        f"Pro access, and that grace window has now passed without ever being "
                        f"finalized to a permanent key — their access has silently cut off.\n\n"
                        f"If the payment was genuine, approve them in the admin panel to restore access.\n")
                _notify_admin_grace_status(f"🚨 Grace period lapsed unreviewed — {name}", text)
                r["grace_expired_notified"] = True
                changed = True
                missed += 1
        elif not r.get("grace_reminder_sent") and (expires_at - now) <= datetime.timedelta(hours=GRACE_REMINDER_HOURS_BEFORE):
            hours_left = round((expires_at - now).total_seconds() / 3600.0, 1)
            text = (f"QalamStudio — grace period expiring soon\n\n"
                    f"{name} <{email}> was auto-approved for temporary Pro access "
                    f"(request {req_id}) and hasn't been finalized to a permanent key yet. "
                    f"Their grace access expires in about {hours_left} hour(s).\n\n"
                    f"Review and finalize in the admin panel.\n")
            _notify_admin_grace_status(f"⏳ Grace period expiring — {name} ({hours_left}h left)", text)
            r["grace_reminder_sent"] = True
            changed = True
            reminded += 1
    if changed:
        _save_requests(reqs)
    return {"reminded": reminded, "missed": missed}


# Runs independently of anyone opening /admin — that page is exactly what
# nobody was opening in time before this fix. Interval is short relative to
# GRACE_REMINDER_HOURS_BEFORE (12h) and MANUAL_GRACE_HOURS (default 72h) so
# a reminder/lapse notice never sits undetected for more than ~20 minutes
# past when it should have fired.
_grace_reminder_sweep_thread = None


def _start_grace_reminder_sweep_thread():
    global _grace_reminder_sweep_thread
    if _grace_reminder_sweep_thread is not None and _grace_reminder_sweep_thread.is_alive():
        return

    def _sweep_loop():
        while True:
            time.sleep(1200)  # 20 minutes
            try:
                sweep_grace_reminders()
            except Exception:
                pass  # never let the sweeper thread itself crash the process

    _grace_reminder_sweep_thread = threading.Thread(target=_sweep_loop, daemon=True)
    _grace_reminder_sweep_thread.start()


_start_grace_reminder_sweep_thread()


def _get_identifier_daily_usage(identifier: str) -> int:
    """Persisted daily action count for one identifier ("ip:<hash>" or
    "fp:<hash>"). Reads through the normal 60s _gh_read cache — enforcement
    doesn't need millisecond freshness, just needs to survive a session
    reset. Returns 0 if unseen or the stored record is from a previous
    day."""
    data = _get_usage()
    rec = data.get(identifier)
    if not rec or rec.get("date") != _today():
        return 0
    return int(rec.get("daily_actions", 0))

def get_user_actions_left():
    if session.get("is_pro"):
        return 9999
    today = _today()
    if session.get("last_action_date") != today:
        session["daily_actions"] = 0
        session["last_action_date"] = today
    limits = _get_limits()
    free_limit = int(limits.get("FREE_DAILY_ACTIONS", Config.FREE_DAILY_ACTIONS))

    # SECURITY FIX: this was purely session-cookie-based, so opening an
    # incognito window (or just clearing cookies) silently reset the count
    # to zero — the free-tier limit was trivially bypassable, same bug
    # VoxCraft had before its fix. Now takes the MAX of the session's own
    # count and whatever's persisted under this device's IP hash AND
    # browser fingerprint hash: a fresh incognito session still carries the
    # same IP and fingerprint, so it inherits the real count even though
    # its own session cookie says zero.
    ip_used = _get_identifier_daily_usage("ip:" + _hash_ip(_get_user_ip()))
    fp_used = _get_identifier_daily_usage("fp:" + _get_browser_fingerprint())
    session_used = session.get("daily_actions", 0)
    effective_used = max(session_used, ip_used, fp_used)
    return max(0, free_limit - effective_used)

def record_action():
    if session.get("is_pro"):
        return True
    today = _today()
    if session.get("last_action_date") != today:
        session["daily_actions"] = 0
        session["last_action_date"] = today
    session["daily_actions"] = session.get("daily_actions", 0) + 1

    # Sync BOTH the IP-keyed and fingerprint-keyed persisted counters in the
    # background, matching the fire-and-forget pattern already used here.
    # This is a deliberate trade-off: a hard CAS transaction (like the
    # license-key one) would add a real network round-trip to every single
    # generation request and burn through GitHub's API rate limit fast at
    # any real traffic volume. Occasionally losing one increment under
    # concurrent load just means a user gets an extra action or two — not a
    # security hole, unlike the license-activation race this file's
    # sibling _gh_transact() closes.
    ip_id = "ip:" + _hash_ip(_get_user_ip())
    fp_id = "fp:" + _get_browser_fingerprint()
    month = datetime.datetime.now().strftime("%Y-%m")

    def _sync_usage():
        try:
            data = _get_usage()
            for identifier in (ip_id, fp_id):
                rec = data.get(identifier, {})
                if rec.get("date") != today:
                    rec = {"date": today, "daily_actions": 0}
                rec["daily_actions"] = rec.get("daily_actions", 0) + 1
                rec["date"] = today
                if rec.get("month") != month:
                    rec["actions_used"] = 0
                rec["actions_used"] = rec.get("actions_used", 0) + 1
                rec["month"] = month
                data[identifier] = rec
            _save_usage(data)
        except Exception:
            pass
    threading.Thread(target=_sync_usage, daemon=True).start()
    return True

def can_act():
    return session.get("is_pro") or get_user_actions_left() > 0

# ──────────────────────────────────────────────────────────────────────
# LLM PROVIDERS — Groq (primary) → Cerebras → OpenRouter (fallbacks)
# ──────────────────────────────────────────────────────────────────────
# Groq deprecated llama-3.3-70b-versatile (shutdown Aug 16, 2026) — the
# model every generation feature on this site was hardcoded to. When Groq
# pulled it, every tool broke at once with no degraded mode, because there
# was exactly one provider and one model. Two independent fixes here: (1)
# the model itself, and (2) the app no longer depends on any single
# provider surviving — if Groq has an outage, gets rate-limited, or
# deprecates a model again, Cerebras and then OpenRouter pick up the
# request instead of every tool on the site going down together.
def _call_groq(system: str, user: str, max_tokens: int):
    if not Config.GROQ_API_KEY:
        return None, "GROQ_API_KEY not set", False
    r = req.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": Config.GROQ_MODEL, "max_tokens": min(max_tokens, 8000),
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=60
    )
    if r.status_code == 200:
        choice = r.json()["choices"][0]
        return choice["message"]["content"], None, choice.get("finish_reason") == "length"
    return None, f"Groq {r.status_code}: {r.text[:200]}", False

def _call_cerebras(system: str, user: str, max_tokens: int):
    if not Config.CEREBRAS_API_KEY:
        return None, "CEREBRAS_API_KEY not set", False
    r = req.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.CEREBRAS_API_KEY}", "Content-Type": "application/json"},
        json={"model": Config.CEREBRAS_MODEL, "max_tokens": min(max_tokens, 8000),
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=60
    )
    if r.status_code == 200:
        choice = r.json()["choices"][0]
        return choice["message"]["content"], None, choice.get("finish_reason") == "length"
    return None, f"Cerebras {r.status_code}: {r.text[:200]}", False

def _call_openrouter(system: str, user: str, max_tokens: int):
    if not Config.OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY not set", False
    r = req.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.OPENROUTER_API_KEY}", "Content-Type": "application/json",
                 # OpenRouter asks for these two headers to attribute traffic
                 # on their public rankings page — harmless to include, and
                 # some free-tier routing behaves better with them set.
                 "HTTP-Referer": "https://qalamstudio.xyz", "X-Title": "QalamStudio"},
        json={"model": Config.OPENROUTER_MODEL, "max_tokens": min(max_tokens, 8000),
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=60
    )
    if r.status_code == 200:
        choice = r.json()["choices"][0]
        return choice["message"]["content"], None, choice.get("finish_reason") == "length"
    return None, f"OpenRouter {r.status_code}: {r.text[:200]}", False

_LLM_PROVIDERS = [("Groq", _call_groq), ("Cerebras", _call_cerebras), ("OpenRouter", _call_openrouter)]

def call_llm(system: str, user: str, max_tokens=2000):
    """Tries each configured provider in order and returns the first
    success. A provider is skipped instantly (no network call) if its API
    key isn't set, so you don't need all three configured — Groq alone
    still works exactly as before, Cerebras/OpenRouter just add resilience
    if you set their keys too.

    BUG FIX (kept from the original single-provider version): the response
    is checked for finish_reason=="length" — if a provider cuts a response
    off for hitting max_tokens, that's reported as `was_truncated` rather
    than silently returned as if it were a complete result. This was very
    likely the source of past 'corrupted/garbage' output reports: long Urdu
    articles, SRT files, and translations can all legitimately exceed a
    fixed max_tokens value, and a cut-off SRT file in particular looks like
    garbage to a video player since the truncation point breaks the file's
    syntax entirely.

    Returns (content, error, was_truncated). `error` is only set if EVERY
    configured provider failed — it's a combined message from all of them,
    for logging/debugging, not meant to be shown to the end user verbatim.
    """
    errors = []
    for name, fn in _LLM_PROVIDERS:
        try:
            content, err, truncated = fn(system, user, max_tokens)
        except Exception as e:
            content, err, truncated = None, str(e), False
        if content is not None:
            return content, None, truncated
        errors.append(f"{name}: {err}")
    return None, " | ".join(errors), False

def get_urdu_prompt(content_type, tone, lang_style, word_count):
    lang = {
        "Pure Urdu (اردو)": """زبان: خالص اردو — مگر عام، قدرتی پاکستانی اردو۔

یاد رکھو:
- لاہوری، کراچی، اسلام آباد کے پڑھے لکھے لوگ جیسے بولتے ہیں — ویسے لکھو
- "مستعار لینا"، "بارگاہ"، "منجانب" جیسے بھاری الفاظ بالکل مت لکھو
- سیدھے، صاف الفاظ: "ملنا"، "کرنا"، "جانا"، "سوچنا"، "سمجھنا"
- جملے چھوٹے رکھو — ایک خیال، ایک جملہ
- ترجمہ شدہ لگے تو دوبارہ لکھو — جب تک انسانی نہ لگے
- اردو اخبار یا کتاب والی اردو نہیں — WhatsApp اور روزمرہ زندگی والی اردو""",

        "Roman Urdu": """Language: Roman Urdu — exactly how Pakistanis type on WhatsApp, Instagram, YouTube comments.

Rules:
- Write like a real Pakistani friend texting, NOT like a translator
- Use expressions: 'yaar', 'bhai', 'matlab', 'waise', 'sach mein', 'bilkul', 'theek hai', 'bas', 'acha'
- Mix in English words naturally where Pakistanis normally do: 'actually', 'basically', 'seriously', 'anyway'
- Short punchy sentences — how people actually talk
- Never translate formal Urdu into Roman — write fresh, conversational Roman Urdu
- Sound like a smart Pakistani friend, not a robot""",

        "Mixed (Urdu + English)": """زبان: Urdu-English mix — جیسے پاکستانی پڑھے لکھے لوگ بولتے ہیں۔

اصول:
- اردو بنیاد ہو، English naturally آئے
- مثال: "یہ actually بہت important point ہے"، "basically اس کا مطلب یہ ہے"
- Technical terms، brand names، modern concepts کے لیے English
- ہر جملے میں English ٹھونسنے کی ضرورت نہیں — صرف جہاں natural لگے
- پاکستانی educated class کی روزمرہ گفتگو جیسا انداز"""
    }[lang_style]

    tone_inst = {
        "Professional":      "لہجہ: سنجیدہ، قابل اعتماد — مگر بوریت والا نہیں۔ جیسے ایک کامیاب پاکستانی professional بات کرتا ہے۔",
        "Friendly & Casual": "لہجہ: دوستانہ اور آرام دہ — جیسے یار کو بتا رہے ہو۔ 'آپ' کی جگہ 'تم' بھی چل سکتا ہے۔",
        "Formal":            "لہجہ: رسمی مگر readable — سرکاری یا کاروباری مگر سمجھ آئے۔",
        "Funny & Engaging":  "لہجہ: ہلکا پھلکا، مزیدار — پاکستانی wit کے ساتھ۔ خود کو serious مت لو۔",
        "Motivational":      "لہجہ: جوش دلانے والا — سچا، دل سے، مبالغہ نہیں۔ جیسے کوئی mentor بات کرے۔",
        "Informational":     "لہجہ: واضح اور سادہ — پیچیدہ باتیں آسان الفاظ میں۔",
    }.get(tone, "لہجہ: قدرتی انسانی انداز۔")

    structure = {
        "YouTube Script (with hook & CTA)": "ساخت: پہلے 3 سیکنڈ میں دلچسپ hook → main content → آخر میں like/subscribe CTA",
        "Blog Post / Article": "ساخت: دلچسپ تعارف → 3-4 حصے (عنوانات کے ساتھ) → مختصر نتیجہ",
        "Facebook Caption": "ساخت: پہلی لائن کھینچنے والی → 2-3 لائن مواد → سوال یا CTA",
        "Instagram Caption": "ساخت: ایک پنچ لائن → مختصر مواد → hashtags نہیں چاہیے",
        "Twitter/X Thread": "ساخت: 1/ سے شروع → ہر tweet ایک خیال → آخری tweet conclusion",
        "Product Description": "ساخت: فائدہ پہلے → features بعد میں → خریدنے کی وجہ",
        "WhatsApp Business Message": "ساخت: مختصر، سیدھی بات، professional مگر warm",
        "Custom Content": "ساخت: موضوع کے حساب سے بہترین انداز اختیار کرو",
    }.get(content_type, "")

    return f"""تم ایک expert Pakistani content writer ہو جو بالکل انسانی انداز میں لکھتا ہے۔

CONTENT TYPE: {content_type}
LENGTH: {word_count}

{lang}

{tone_inst}

{structure}

سب سے ضروری اصول — یہ 5 چیزیں کبھی مت کرو:
1. "آج کے دور میں"، "بلاشبہ"، "یہ بات روز روشن کی طرح عیاں ہے" — یہ کلیشے بالکل نہیں
2. ہر جملہ "یہ بہت ضروری ہے" سے شروع مت کرو
3. AI والا robotic pattern: "پہلا نکتہ... دوسرا نکتہ... تیسرا نکتہ" سے بچو
4. ضرورت سے زیادہ formal — لکھو جیسے انسان بولتا ہے
5. انگریزی کا لفظی ترجمہ — پاکستانی اردو میں naturally لکھو

پاکستانی context استعمال کرو — مثالیں، حوالے، scenarios پاکستان کے ہوں۔"""

# ──────────────────────────────────────────────────────────────────────
# CONTEXT PROCESSORS
# ──────────────────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    limits = _get_limits()
    return {
        "is_pro": session.get("is_pro", False),
        "pro_name": session.get("pro_name", ""),
        "license_key": session.get("license_key", ""),
        "actions_left": get_user_actions_left(),
        "pro_price_label": limits.get("PRO_PRICE_LABEL", Config.PRO_PRICE_LABEL),
        "free_price_label": limits.get("FREE_PRICE_LABEL", Config.FREE_PRICE_LABEL),
        "checkout_url": limits.get("CHECKOUT_URL", Config.CHECKOUT_URL),
        "free_features": limits.get("FREE_FEATURES", "").split("|"),
        "pro_features": limits.get("PRO_FEATURES", "").split("|"),
        "free_daily_actions": int(limits.get("FREE_DAILY_ACTIONS", Config.FREE_DAILY_ACTIONS)),
        "filedesk_url": Config.FILEDESK_URL,
        "year": datetime.datetime.now().year,
        "google_site_verification_code": os.environ.get("GOOGLE_SITE_VERIFICATION", ""),
    }

# ──────────────────────────────────────────────────────────────────────
# DECORATORS
# ──────────────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_auth"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# ──────────────────────────────────────────────────────────────────────
# ROUTES — PUBLIC PAGES
# ──────────────────────────────────────────────────────────────────────
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/urdu-writer")
def urdu_writer():
    return render_template("urdu_writer.html")

@app.route("/freelancer")
def freelancer():
    return render_template("freelancer.html")

@app.route("/subtitles")
def subtitles():
    return render_template("subtitles.html")

@app.route("/proofread")
def proofread():
    return render_template("proofread.html")

@app.route("/youtube-seo")
def youtube_seo():
    return render_template("youtube_seo.html")

@app.route("/resume")
def resume():
    return render_template("resume.html")

@app.route("/whatsapp-replies")
def whatsapp_replies():
    return render_template("whatsapp_replies.html")

@app.route("/script-timing")
def script_timing():
    return render_template("script_timing.html")

@app.route("/blog")
def blog():
    posts = [p for p in _get_blog_posts() if p.get("published")]
    return render_template("blog.html", posts=posts)

@app.route("/blog/<slug>")
def blog_post(slug):
    posts = [p for p in _get_blog_posts() if p.get("published")]
    post = next((p for p in posts if p.get("id") == slug), None)
    if not post:
        abort(404)
    # Resolve related tool keys → internal links for SEO interlinking
    tool_map = {
        "urdu_writer": ("Urdu AI Writer", "urdu_writer"),
        "freelancer": ("Freelancer Toolkit", "freelancer"),
        "subtitles": ("Subtitle Generator", "subtitles"),
        "proofread": ("Urdu Proofreader", "proofread"),
        "youtube_seo": ("YouTube SEO", "youtube_seo"),
        "resume": ("Resume Builder", "resume"),
        "whatsapp_replies": ("WhatsApp Replies", "whatsapp_replies"),
        "script_timing": ("Script Timing", "script_timing"),
    }
    related = []
    for key in post.get("related_tool_keys") or []:
        meta = tool_map.get(key)
        if meta:
            label, endpoint = meta
            related.append({"label": label, "url": url_for(endpoint)})
    post = dict(post)
    post["related_tools"] = related
    return render_template("blog_post.html", post=post)

@app.route("/sitemap.xml")
def sitemap():
    """Dynamically generated — includes every public page plus every
    published blog post, using whatever domain the request actually came in
    on (correct whether you're on Render's default domain or your real one,
    no hardcoded base URL needed)."""
    base = request.url_root.rstrip("/")
    static_paths = [
        ("/", "1.0", "weekly"),
        ("/urdu-writer", "0.9", "weekly"),
        ("/freelancer", "0.9", "weekly"),
        ("/subtitles", "0.9", "weekly"),
        ("/proofread", "0.85", "weekly"),
        ("/youtube-seo", "0.85", "weekly"),
        ("/resume", "0.85", "weekly"),
        ("/whatsapp-replies", "0.85", "weekly"),
        ("/script-timing", "0.8", "weekly"),
        ("/blog", "0.7", "weekly"),
        ("/request-pro", "0.6", "monthly"),
        ("/about", "0.4", "yearly"),
        ("/contact", "0.4", "yearly"),
        ("/privacy", "0.3", "yearly"),
        ("/terms", "0.3", "yearly"),
    ]
    urls = [{"loc": f"{base}{path}", "priority": priority, "changefreq": freq}
            for path, priority, freq in static_paths]

    for post in _get_blog_posts():
        if post.get("published"):
            urls.append({
                "loc": f"{base}/blog/{post.get('id')}",
                "priority": "0.6",
                "changefreq": "monthly",
                "lastmod": post.get("date", ""),
            })

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{u['loc']}</loc>")
        if u.get("lastmod"):
            xml_parts.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        xml_parts.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        xml_parts.append(f"    <priority>{u['priority']}</priority>")
        xml_parts.append("  </url>")
    xml_parts.append("</urlset>")

    return app.response_class("\n".join(xml_parts), mimetype="application/xml")


@app.route("/robots.txt")
def robots_txt():
    base = request.url_root.rstrip("/")
    content = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/

Sitemap: {base}/sitemap.xml
"""
    return app.response_class(content, mimetype="text/plain")


@app.route("/about")
def about():
    return render_template("about.html")

# ──────────────────────────────────────────────────────────────────────
# CONTACT INQUIRIES — Mailtrap API primary, Wappfly admin fallback
# ──────────────────────────────────────────────────────────────────────
def _parse_from_address(raw):
    """Parses a 'Name <email@domain>' string (or a bare email) into
    (name, email) for Mailtrap's {"email": ..., "name": ...} address objects."""
    raw = (raw or "").strip()
    m = re.match(r'^(.*)<(.+)>$', raw)
    if m:
        name = m.group(1).strip().strip('"')
        return (name or None), m.group(2).strip()
    return None, raw

def _send_mailtrap_email(to_email, subject, text_body=None, html_body=None, reply_to=None):
    """Send via Mailtrap's Email Sending API (Render blocks outbound SMTP ports 25/465/587)."""
    if not Config.MAILTRAP_API_KEY:
        app.logger.error("Mailtrap send skipped: MAILTRAP_API_KEY is not set")
        return False
    if not to_email:
        app.logger.error("Mailtrap send skipped: no recipient email provided")
        return False
    try:
        from_name, from_email = _parse_from_address(Config.CONTACT_FROM_EMAIL)
        payload = {
            "from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
            "to": [{"email": to_email}],
            "subject": subject,
        }
        if text_body:
            payload["text"] = text_body
        if html_body:
            payload["html"] = html_body
        if reply_to:
            payload["reply_to"] = {"email": reply_to}
        r = req.post(
            "https://send.api.mailtrap.io/api/send",
            headers={"Api-Token": Config.MAILTRAP_API_KEY, "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        if r.status_code == 200:
            app.logger.info("Mailtrap API: sent to %s from %s", to_email, Config.CONTACT_FROM_EMAIL)
            return True
        app.logger.error("Mailtrap API failed (%s): from=%r to=%r body=%s", r.status_code, Config.CONTACT_FROM_EMAIL, to_email, r.text[:500])
        return False
    except Exception as exc:
        app.logger.error("Mailtrap API request failed (from=%r to=%r): %s", Config.CONTACT_FROM_EMAIL, to_email, exc, exc_info=True)
        return False

def _contact_auto_reply(category, name):
    replies = {
        "support": ("We received your support request", f"Hi {name},\n\nThanks for contacting QalamStudio. Your support request is in our queue. We usually reply within 1–2 business days. If you can include screenshots or the exact error message in a follow-up, it helps us resolve the issue faster.\n\n— QalamStudio Support"),
        "billing": ("We received your billing inquiry", f"Hi {name},\n\nThanks for contacting QalamStudio. We received your billing or Studio Pro inquiry and will review it shortly. For payment proof or a Pro request, you can also use the Request Pro page so everything stays organized.\n\n— QalamStudio"),
        "feature": ("Thanks for your QalamStudio idea", f"Hi {name},\n\nThanks for the feature suggestion. We read product ideas and use them to prioritize future improvements. We cannot promise every feature will be added, but your feedback has been received.\n\n— QalamStudio"),
        "partnership": ("We received your partnership inquiry", f"Hi {name},\n\nThanks for reaching out about a partnership or collaboration. We received your message and will review the details before responding.\n\n— QalamStudio"),
    }
    return replies.get(category, ("We received your message", f"Hi {name},\n\nThanks for contacting QalamStudio. We received your message and will get back to you as soon as possible.\n\n— QalamStudio"))

def _notify_contact_inquiry(name, email, category, message, phone=""):
    safe_name = html.escape(name)
    safe_email = html.escape(email)
    safe_phone = html.escape(phone or "Not provided")
    safe_category = html.escape(category.title())
    safe_message = html.escape(message)
    admin_text = f"""New QalamStudio Contact Inquiry\n\nName: {name}\nEmail: {email}\nPhone: {phone or 'Not provided'}\nCategory: {category.title()}\n\nMessage:\n{message}\n"""
    notified = False
    # Primary: Mailtrap API. Reply-To lets you answer the visitor directly.
    if Config.ADMIN_EMAIL:
        notified = _send_mailtrap_email(
            Config.ADMIN_EMAIL, f"New {category.title()} inquiry — {name}", text_body=admin_text, reply_to=email
        )
    # Fallback: Wappfly WhatsApp notification to the admin.
    if not notified and Config.WAPPFLY_API_KEY and Config.WAPPFLY_ADMIN_NUMBER:
        try:
            r = req.post(
                "https://api.wappfly.com/v1/messages",
                headers={"Authorization": f"Bearer {Config.WAPPFLY_API_KEY}", "Content-Type": "application/json"},
                json={"to": Config.WAPPFLY_ADMIN_NUMBER, "type": "text", "text": {"body": admin_text}},
                timeout=15,
            )
            notified = r.status_code in (200, 201)
            if not notified:
                app.logger.warning("Wappfly contact fallback failed: %s", r.status_code)
        except Exception as exc:
            app.logger.warning("Wappfly contact fallback error: %s", exc)
    return notified

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # Honeypot: bots often fill fields hidden from real visitors.
        if request.form.get("website", "").strip():
            return redirect(url_for("contact"))

        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip()[:254]
        phone = request.form.get("phone", "").strip()[:50]
        category = request.form.get("category", "general").strip().lower()
        message = request.form.get("message", "").strip()[:5000]
        allowed_categories = {"general", "support", "billing", "feature", "partnership"}

        if category not in allowed_categories:
            category = "general"
        if not name or not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Please enter your name and a valid email address.", "error")
            return render_template("contact.html")
        if len(message) < 10:
            flash("Please write a little more detail so we can help you.", "error")
            return render_template("contact.html")

        admin_notified = _notify_contact_inquiry(name, email, category, message, phone)
        # Automated acknowledgement for common inquiry types.
        subject, reply = _contact_auto_reply(category, name)
        _send_mailtrap_email(email, subject, text_body=reply)
        if not admin_notified:
            app.logger.error("CONTACT FORM: admin notification failed for inquiry from %s <%s>. Check MAILTRAP_API_KEY / CONTACT_FROM_EMAIL / ADMIN_EMAIL and Mailtrap domain verification. Full message logged above this line.", name, email)
        flash("Thanks — your message has been received. We’ll get back to you soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/request-pro", methods=["GET", "POST"])
def request_pro():
    if request.method == "POST":
        step = request.form.get("step", "1")
        if step == "1":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            if not name or not email or "@" not in email:
                flash("Name and valid email are required.", "error")
                return redirect(url_for("request_pro"))
            session["_pro_name"] = name
            session["_pro_email"] = email
            session["_pro_phone"] = phone
            return render_template("request_pro.html", step=2, name=name)
        elif step == "2":
            return render_template("request_pro.html", step=3,
                name=session.get("_pro_name", ""),
                email=session.get("_pro_email", ""),
                phone=session.get("_pro_phone", ""))
        elif step == "3":
            name = session.get("_pro_name", "")
            email = session.get("_pro_email", "")
            phone = session.get("_pro_phone", "")
            payment_method = request.form.get("payment_method", "")
            txn_id = request.form.get("txn_id", "").strip()
            screenshot = request.files.get("screenshot")
            screenshot_b64 = ""
            if screenshot and screenshot.filename:
                screenshot_b64 = base64.b64encode(screenshot.read()).decode()
            if not screenshot_b64:
                flash("Please upload your payment screenshot.", "error")
                return render_template("request_pro.html", step=3, name=name, email=email, phone=phone)
            result = submit_pro_request(name, email, phone, payment_method, txn_id, screenshot_b64)
            if result.get("auto_rejected"):
                # HARDENING: previously there was no auto-reject path at
                # all — a duplicate/forged submission would have shown the
                # same "thanks, under review" page as a genuine one, then
                # sat in admin's queue (and inbox) until manually rejected
                # days later. Now the customer gets an immediate, specific,
                # actionable reason instead.
                flash(result.get("reject_reason") or "This request could not be processed.", "error")
                return render_template("request_pro.html", step=3, name=name, email=email, phone=phone)
            if result["success"]:
                # Auto-activate Pro on this device if key was auto-generated
                if result.get("auto_approved") and result.get("license_key"):
                    session["is_pro"] = True
                    session["license_key"] = result["license_key"]
                    session["pro_name"] = name or "Pro User"
                session.pop("_pro_name", None)
                session.pop("_pro_email", None)
                session.pop("_pro_phone", None)
                return render_template("request_pro.html", step=4, req_id=result["id"], 
                    email=email, license_key=result.get("license_key", ""),
                    auto_approved=result.get("auto_approved", False),
                    grace_hours=Config.MANUAL_GRACE_HOURS)
            else:
                flash(f"Failed: {result.get('error', 'Unknown error')}", "error")
                return render_template("request_pro.html", step=3, name=name, email=email, phone=phone)
    return render_template("request_pro.html", step=1)

# ──────────────────────────────────────────────────────────────────────
# API ROUTES
# ──────────────────────────────────────────────────────────────────────
@app.route("/api/restore-pro", methods=["POST"])
def api_restore_pro():
    data = request.get_json() or {}
    key = data.get("key", "").strip()
    if key:
        result = check_license(key)
        if result["valid"]:
            session["is_pro"] = True
            session["license_key"] = key
            session["pro_name"] = result.get("name", "Pro User")
            return jsonify({"success": True})
        # HARDENING: this used to be a bare fall-through to "success: False"
        # with the session left untouched. Combined with app.js only ever
        # calling this endpoint when `!window.IS_PRO` (i.e. never again once
        # a session already has is_pro=True), a key that was later revoked
        # or expired had NO path to ever actually cut off an existing
        # session — PERMANENT_SESSION_LIFETIME is 90 days, so that session
        # cookie alone kept granting unlimited Pro access for up to 90 days
        # after cancellation. Actively clearing the session here — combined
        # with app.js now calling this on every load, not just when not
        # already Pro — is what makes a revoked/expired key actually take
        # effect during an existing session instead of only blocking a
        # brand-new one.
        session["is_pro"] = False
        session["license_key"] = ""
        session["pro_name"] = ""
        return jsonify({"success": False, "error": result.get("error", "")})
    return jsonify({"success": False})

@app.route("/api/activate-license", methods=["POST"])
def api_activate_license():
    data = request.get_json() or {}
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"valid": False, "error": "Enter a license key"})
    result = activate_license(key)
    if result["valid"]:
        session["is_pro"] = True
        session["license_key"] = key
        session["pro_name"] = result.get("name", "Pro User")
    return jsonify(result)

@app.route("/api/deactivate-pro", methods=["POST"])
def api_deactivate_pro():
    session["is_pro"] = False
    session["pro_name"] = ""
    session["license_key"] = ""
    return jsonify({"success": True})

@app.route("/api/generate-urdu", methods=["POST"])
def api_generate_urdu():
    if not can_act():
        return jsonify({"error": f"Daily limit reached. Upgrade to Pro for unlimited access."}), 429
    data = request.get_json() or {}
    content_type = data.get("content_type", "Blog Post / Article")
    tone = data.get("tone", "Professional")
    lang_style = data.get("lang_style", "Pure Urdu (اردو)")
    word_count = data.get("word_count", "Medium (300-500 words)")
    topic = data.get("topic", "").strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    system = get_urdu_prompt(content_type, tone, lang_style, word_count)
    # BUG FIX: max_tokens was fixed at 2000 regardless of the word_count
    # option selected. Urdu/Roman Urdu need noticeably more tokens per word
    # than English (script + tokenizer inefficiency), so "Long (600-1000
    # words)" was very likely to get cut off mid-generation at 2000 tokens.
    # Scaled to roughly cover each tier with headroom, capped under Groq's
    # 8192-token hard ceiling for this model.
    tokens_for_length = {
        "Short (100-200 words)": 1200,
        "Medium (300-500 words)": 2200,
        "Long (600-1000 words)": 4000,
    }.get(word_count, 2200)
    result, err, truncated = call_llm(system, f"اس موضوع پر لکھو: {topic}", tokens_for_length)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "The content was cut off because it ran longer than expected — try a shorter length option, or regenerate."
    return jsonify(resp)

@app.route("/api/generate-proposal", methods=["POST"])
def api_generate_proposal():
    if not can_act():
        return jsonify({"error": "Daily limit reached"}), 429
    data = request.get_json() or {}
    platform = data.get("platform", "Fiverr")
    service = data.get("service", "").strip()
    client_need = data.get("client_need", "").strip()
    your_exp = data.get("your_exp", "").strip()
    prop_lang = data.get("prop_lang", "English (Professional)")
    if not service or not client_need:
        return jsonify({"error": "Service and client needs are required"}), 400
    lm = {
        "English (Professional)": "Write in professional English. Sound human and specific.",
        "Roman Urdu": "Roman Urdu mein likho — bilkul natural Pakistani freelancer style.",
        "Pure Urdu": "قدرتی پاکستانی اردو میں — professional مگر روبوٹ نہیں۔"
    }
    sys_p = f"You are an expert proposal writer for Pakistani freelancers.\n{lm[prop_lang]}\nPlatform: {platform}. Structure: Strong opening hook → Show you understood requirements → Your relevant experience → Clear deliverables → Timeline → CTA."
    result, err, truncated = call_llm(sys_p, f"Service: {service}\nClient needs: {client_need}\nMy experience: {your_exp or 'Not specified'}", 1400)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "The proposal was cut off because it ran longer than expected — try shortening your inputs, or regenerate."
    return jsonify(resp)

@app.route("/api/generate-invoice", methods=["POST"])
def api_generate_invoice():
    if not can_act():
        return jsonify({"error": "Daily limit reached"}), 429
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "At least one item required"}), 400
    yn = data.get("your_name", "")
    cn = data.get("client_name", "")
    if not yn or not cn:
        return jsonify({"error": "Your name and client name required"}), 400
    total = sum(it["qty"] * it["rate"] for it in items)
    cur = data.get("currency", "PKR")
    rows = "\n".join([f"{it['desc']:<28} {it['qty']:>3}  {cur} {it['rate']:>7,}  {cur} {it['qty']*it['rate']:>8,}" for it in items])
    inv_num = datetime.datetime.now().strftime('%Y%m%d%H%M')
    inv_text = f"""╔══════════════════════════════════════════════════════╗
                    INVOICE
╚══════════════════════════════════════════════════════╝

FROM:                              TO:
{yn}                        {cn}
{data.get('your_email','')}                       {data.get('client_email','')}
{data.get('your_phone','')}

Date: {data.get('date', datetime.datetime.now().strftime('%d %B %Y'))}
Invoice #: INV-{inv_num}

──────────────────────────────────────────────────────
DESCRIPTION                    QTY    RATE       AMOUNT
──────────────────────────────────────────────────────
{rows}
──────────────────────────────────────────────────────
                               TOTAL:  {cur} {total:>8,}
══════════════════════════════════════════════════════

Notes: {data.get('note','Thank you for your business!')}

Generated by QalamStudio.xyz"""
    record_action()
    return jsonify({"result": inv_text})

@app.route("/api/generate-email", methods=["POST"])
def api_generate_email():
    if not can_act():
        return jsonify({"error": "Daily limit reached"}), 429
    data = request.get_json() or {}
    etype = data.get("etype", "Project Delivery")
    ectx = data.get("ectx", "").strip()
    elang = data.get("elang", "English (Professional)")
    etone = data.get("etone", "Professional")
    if not ectx:
        return jsonify({"error": "Context required"}), 400
    lm = {
        "English (Professional)": "Write in professional English. Don't use 'I hope this email finds you well'. Sound human.",
        "Roman Urdu": "Roman Urdu mein — natural Pakistani business style.",
        "Pure Urdu": "قدرتی اردو میں — پیشہ ورانہ اور گرمجوش۔"
    }
    sys_e = f"You are an expert email writer for Pakistani freelancers.\n{lm[elang]}\nTone: {etone}. Write for: {etype}.\nInclude Subject, greeting, body, closing. Be concise and human."
    result, err, truncated = call_llm(sys_e, f"Context: {ectx}", 1000)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "The email was cut off because it ran longer than expected — try shortening the context, or regenerate."
    return jsonify(resp)

@app.route("/api/generate-srt", methods=["POST"])
def api_generate_srt():
    if not can_act():
        return jsonify({"error": f"Daily limit reached"}), 429
    data = request.get_json() or {}
    script = data.get("script", "").strip()
    dur = int(data.get("dur", 5))
    slang = data.get("slang", "Urdu (اردو)")
    wps = int(data.get("wps", 8))
    if not script:
        return jsonify({"error": "Script required"}), 400
    # BUG FIX: the UI allowed up to 60 minutes, but max_tokens was fixed at
    # 3000 regardless — and Groq's hard ceiling for this model is 8192
    # tokens/request, which physically cannot fit a proper SRT file for
    # anything close to 60 minutes (realistically needs 20,000+ tokens for
    # that length). No amount of max_tokens tuning fixes this for long
    # durations — it's a one-call-per-request architecture limit. Capping to
    # a duration that reliably fits in one call, and scaling tokens to the
    # actual requested duration instead of a fixed number.
    if dur > 12:
        return jsonify({"error": "Duration is capped at 12 minutes per generation right now — longer subtitle files need to be split into segments. Support for longer files is planned."}), 400
    tokens_needed = min(8000, max(2000, dur * 700))
    li = {"Urdu (اردو)": "قدرتی اردو میں convert کرو۔", "Roman Urdu": "Roman Urdu میں convert کرو۔", "English": "Keep in English.", "Hindi": "Hindi script میں۔", "Arabic": "Arabic script میں۔"}
    sys_s = f"Professional subtitle generator.\n{li[slang]}\nSRT format. Max {wps} words per subtitle. Distribute timing across {dur} minutes.\nOutput ONLY valid SRT. No preamble."
    result, err, truncated = call_llm(sys_s, f"Convert to SRT:\n\n{script}", tokens_needed)
    if err:
        return jsonify({"error": err}), 500
    if truncated:
        # A cut-off SRT file breaks subtitle syntax at the truncation point —
        # genuinely broken output, not just "incomplete". Refuse to hand this
        # back as if it were usable, and don't charge the daily quota for it.
        return jsonify({"error": "The subtitle file was cut off partway through and would be broken in a video player. Try a shorter duration or a shorter script."}), 500
    record_action()
    return jsonify({"result": result})

@app.route("/api/translate-srt", methods=["POST"])
def api_translate_srt():
    if not can_act():
        return jsonify({"error": "Daily limit reached"}), 429
    data = request.get_json() or {}
    eng_srt = data.get("eng_srt", "").strip()
    tstyle = data.get("tstyle", "Pure Urdu (اردو)")
    if not eng_srt:
        return jsonify({"error": "SRT required"}), 400
    # BUG FIX: max_tokens was fixed at 3000 regardless of input length — a
    # translated SRT needs roughly as much output as the input's length (often
    # more, since Urdu/Roman Urdu needs more tokens per word than English), so
    # long input files were very likely to get cut off. Scaling to the actual
    # input size instead, and rejecting cleanly (not charging the daily quota)
    # if it still doesn't fit in one call — a cut-off translated SRT has the
    # same broken-syntax problem as a cut-off generated one.
    input_tokens_est = len(eng_srt) // 3  # rough chars-to-tokens estimate
    if input_tokens_est > 5000:
        return jsonify({"error": "This SRT file is too long to translate in one pass. Please split it into smaller chunks (a few hundred lines each) and translate separately."}), 400
    tokens_needed = min(8000, max(2000, int(input_tokens_est * 2.5) + 500))
    tm = {"Pure Urdu (اردو)": "قدرتی پاکستانی اردو میں translate کرو۔ Timestamps بالکل مت بدلو۔",
          "Roman Urdu": "Roman Urdu میں translate کرو۔ Timestamps identical رکھو۔",
          "Mixed Urdu-English": "Natural Urdu-English mix میں۔ Timestamps مت بدلو۔"}
    sys_t = f"Professional Urdu subtitle translator.\n{tm[tstyle]}\nOutput ONLY translated SRT. Never touch timestamps or numbers."
    result, err, truncated = call_llm(sys_t, f"Translate:\n\n{eng_srt}", tokens_needed)
    if err:
        return jsonify({"error": err}), 500
    if truncated:
        return jsonify({"error": "The translation was cut off partway through and would be broken in a video player. Try splitting the file into smaller chunks."}), 500
    record_action()
    return jsonify({"result": result})

@app.route("/api/proofread", methods=["POST"])
def api_proofread():
    if not can_act():
        return jsonify({"error": "Daily limit reached. Upgrade to Pro for unlimited access."}), 429
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    lang = data.get("lang", "Pure Urdu (اردو)")
    focus = data.get("focus", "Full proofread (grammar + spelling + style)")
    if not text:
        return jsonify({"error": "Text is required"}), 400
    if len(text) > 12000:
        return jsonify({"error": "Text is too long. Please proofread in smaller chunks (under ~3000 words)."}), 400
    lang_inst = {
        "Pure Urdu (اردو)": "Input is in pure Urdu script. Correct grammar, spelling (املا), and natural Pakistani Urdu style. Keep pure Urdu output.",
        "Roman Urdu": "Input is Roman Urdu. Fix spelling, grammar, and make it sound like natural Pakistani WhatsApp-style Roman Urdu. Keep Roman Urdu output.",
        "Mixed (Urdu + English)": "Input mixes Urdu and English. Fix errors while preserving the natural mix. Output in the same mixed style."
    }.get(lang, "Correct the text naturally.")
    focus_inst = {
        "Full proofread (grammar + spelling + style)": "Do a full proofread: fix spelling, grammar, punctuation, and improve awkward phrasing so it sounds natural and human.",
        "Spelling only": "Fix only spelling / املا mistakes. Do not rewrite style or structure unless a spelling fix forces a small change.",
        "Grammar only": "Fix only grammar and sentence structure. Keep the writer's original word choices where possible.",
        "Make more natural / less formal": "Rewrite to sound more natural and less formal/robotic while keeping the meaning. Prefer everyday Pakistani wording."
    }.get(focus, "Full proofread.")
    system = f"""You are an expert Pakistani Urdu editor and proofreader.

{lang_inst}
{focus_inst}

Output format (strict):
1) First output the FULL corrected text.
2) Then a blank line and the separator: ---CHANGES---
3) Then a short bullet list of the main fixes you made (in the same language as the text). If almost nothing needed fixing, say so.

Do not add preamble before the corrected text. Do not invent new content — only correct and lightly polish what was given."""
    tokens = min(6000, max(1500, len(text) // 2 + 800))
    result, err, truncated = call_llm(system, text, tokens)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "Output may be incomplete — try a shorter text chunk."
    return jsonify(resp)

@app.route("/api/generate-youtube-seo", methods=["POST"])
def api_generate_youtube_seo():
    if not can_act():
        return jsonify({"error": "Daily limit reached. Upgrade to Pro for unlimited access."}), 429
    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    lang = data.get("lang", "Pure Urdu (اردو)")
    niche = data.get("niche", "General / Educational")
    channel = data.get("channel", "").strip()
    if not topic:
        return jsonify({"error": "Topic or script summary is required"}), 400
    lang_inst = {
        "Pure Urdu (اردو)": "Write titles, description and tags primarily in pure Pakistani Urdu (Nastaliq-friendly wording).",
        "Roman Urdu": "Write in natural Roman Urdu as Pakistanis type on YouTube.",
        "English": "Write in clear, SEO-friendly English.",
        "Mixed (Urdu + English)": "Use a natural Urdu-English mix common on Pakistani YouTube."
    }.get(lang, "Write in natural language for Pakistani viewers.")
    channel_line = f"Channel name for CTA: {channel}" if channel else "No specific channel name — use generic subscribe CTA."
    system = f"""You are a YouTube growth expert for Pakistani creators.

Niche: {niche}
{lang_inst}
{channel_line}

Given the video topic/summary, produce:

## TITLES (8 options)
- Mix of curiosity, benefit, and keyword-rich titles
- Keep under ~70 characters where possible
- Number them 1-8

## DESCRIPTION
- First 2 lines must be strong (shown in search)
- Include natural keywords
- Add timestamps placeholder section if the topic suits a longer video
- End with CTA (subscribe / related)

## TAGS
- 15-25 comma-separated tags
- Mix broad + specific + long-tail
- Include both Urdu/Roman and English variants where useful

## HASHTAGS
- 3-5 relevant hashtags for the description end

Be specific to the topic. No generic filler. Sound human, not spammy."""
    result, err, truncated = call_llm(system, f"Video topic / summary:\n\n{topic}", 2500)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "Output may be cut off — try a shorter topic summary."
    return jsonify(resp)

@app.route("/api/generate-resume", methods=["POST"])
def api_generate_resume():
    if not can_act():
        return jsonify({"error": "Daily limit reached. Upgrade to Pro for unlimited access."}), 429
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    role = data.get("role", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    location = data.get("location", "").strip()
    lang = data.get("lang", "English (Professional)")
    summary = data.get("summary", "").strip()
    experience = data.get("experience", "").strip()
    education = data.get("education", "").strip()
    skills = data.get("skills", "").strip()
    extra = data.get("extra", "").strip()
    if not name or not role:
        return jsonify({"error": "Name and target role are required"}), 400
    lang_inst = {
        "English (Professional)": "Write the entire CV in professional English.",
        "Pure Urdu (اردو)": "Write the entire CV in clear, professional pure Pakistani Urdu.",
        "Roman Urdu": "Write the entire CV in natural Roman Urdu (professional but readable).",
        "Bilingual (Urdu + English)": "Produce a bilingual CV: section headers and key lines in both English and Urdu where natural; keep it clean and scannable."
    }.get(lang, "Write in professional English.")
    system = f"""You are a career coach and resume writer helping Pakistani freelancers and job seekers (Fiverr, Upwork, local companies).

{lang_inst}

Build a clean, modern plain-text resume (not markdown tables). Structure:

NAME
Role title
Contact line (email · phone · location)

PROFESSIONAL SUMMARY
(2-4 strong sentences; invent a polished summary from the facts if the user left it blank — never invent fake jobs)

EXPERIENCE
(each role: title, company, dates if given, 2-4 achievement bullets)

EDUCATION

SKILLS
(grouped if helpful)

ADDITIONAL
(certs, languages, links)

Rules:
- Do NOT invent employers, degrees, or dates the user did not provide.
- Strengthen weak bullet points into achievement-style language when the facts allow.
- Keep it concise (one page worth of text).
- Output ONLY the resume text, no preamble."""
    user_blob = f"""Name: {name}
Target role: {role}
Email: {email}
Phone: {phone}
Location: {location}
Summary from user: {summary or '(auto-generate from experience)'}
Experience:
{experience or '(none provided)'}
Education:
{education or '(none provided)'}
Skills: {skills or '(none provided)'}
Extra: {extra or '(none)'}"""
    result, err, truncated = call_llm(system, user_blob, 2500)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "Resume may be incomplete — try shortening the experience section."
    return jsonify(resp)

@app.route("/api/generate-whatsapp-replies", methods=["POST"])
def api_generate_whatsapp_replies():
    if not can_act():
        return jsonify({"error": "Daily limit reached. Upgrade to Pro for unlimited access."}), 429
    data = request.get_json() or {}
    biz = data.get("biz", "Online shop / e-commerce")
    lang = data.get("lang", "Roman Urdu")
    name = data.get("name", "").strip()
    scenario = data.get("scenario", "Welcome / greeting message")
    details = data.get("details", "").strip()
    lang_inst = {
        "Roman Urdu": "Write in natural Roman Urdu — exactly how Pakistani shop owners type on WhatsApp.",
        "Pure Urdu (اردو)": "Write in pure Urdu script, short and clear.",
        "Mixed (Urdu + English)": "Natural Urdu-English mix common in Pakistani business WhatsApp.",
        "English": "Clear, friendly professional English."
    }.get(lang, "Natural Roman Urdu.")
    name_line = f"Business name: {name}" if name else "No specific business name — keep generic or use placeholders like [Shop Name]."
    system = f"""You write WhatsApp Business auto-replies for Pakistani small businesses.

Business type: {biz}
Scenario requested: {scenario}
{name_line}
{lang_inst}

Rules:
- Short messages (WhatsApp-friendly). Use line breaks.
- Warm, professional, not robotic.
- Include practical placeholders in [brackets] where the owner should fill details (price, time, link).
- If "Full set" is requested, output clearly labeled separate messages: Welcome, Away, Price inquiry, Order confirmation.
- For a single scenario, output 2-3 alternative versions the owner can choose from.
- No hashtags, no markdown tables. Plain text ready to copy-paste into WhatsApp Business.

Extra context from the owner:
{details or '(none)'}"""
    result, err, truncated = call_llm(system, f"Generate WhatsApp replies for: {scenario}", 2000)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    resp = {"result": result}
    if truncated:
        resp["warning"] = "Output may be cut off — try a narrower scenario."
    return jsonify(resp)

@app.route("/api/estimate-script-timing", methods=["POST"])
def api_estimate_script_timing():
    if not can_act():
        return jsonify({"error": "Daily limit reached. Upgrade to Pro for unlimited access."}), 429
    data = request.get_json() or {}
    script = data.get("script", "").strip()
    lang = data.get("lang", "Pure Urdu (اردو)")
    pace = data.get("pace", "Natural / conversational (~130 wpm)")
    target = data.get("target", "")
    if not script:
        return jsonify({"error": "Script is required"}), 400
    if len(script) > 20000:
        return jsonify({"error": "Script is too long for one pass. Split into sections."}), 400
    # Deterministic word/char stats for reliability
    words = len(script.split())
    chars = len(script.replace(" ", "").replace("\n", ""))
    # Rough WPM from pace label
    wpm_map = {
        "Natural / conversational (~130 wpm)": 130,
        "Slightly fast (YouTube energy ~150 wpm)": 150,
        "Slow & clear (tutorials ~110 wpm)": 110,
        "Very slow / dramatic (~90 wpm)": 90,
    }
    wpm = wpm_map.get(pace, 130)
    # Urdu script tends to have fewer "words" by space-split but slower articulation; bump slightly for pure Urdu
    if lang == "Pure Urdu (اردو)":
        effective_wpm = max(80, int(wpm * 0.85))
    else:
        effective_wpm = wpm
    minutes = words / effective_wpm if effective_wpm else 0
    secs = int(round(minutes * 60))
    mm, ss = divmod(secs, 60)
    target_note = ""
    if target:
        try:
            tmin = float(target)
            if tmin > 0:
                needed_wpm = words / tmin
                target_note = f"Target length: {tmin} min → needed pace ≈ {needed_wpm:.0f} words/min."
        except ValueError:
            pass
    stats_block = f"""QUICK STATS (calculated)
- Word count: {words}
- Characters (no spaces): {chars}
- Selected pace: {pace} (effective ~{effective_wpm} wpm for this language)
- Estimated spoken duration: {mm} min {ss:02d} sec
{target_note}"""
    system = f"""You are a video producer helping Pakistani YouTube/TikTok creators time voice-over scripts.

Language of script: {lang}
Pace preference: {pace}

The user pasted a script. You already have calculated stats (will be shown). Your job:
1) Confirm or slightly adjust the estimate if the script has many pauses, lists, or dense technical terms.
2) Break the script into logical sections with approximate timestamps (0:00, 0:45, ...).
3) Give 3-5 concrete pacing tips (where to slow down, where to cut, ideal target length).
4) If a target length was given and the script is too long/short, suggest what to cut or expand.

Output in clear English with optional Roman Urdu tips. Structure:

## ESTIMATE
(duration + confidence)

## SECTION BREAKDOWN
(timestamp ranges + 1-line summary each)

## PACING TIPS
(bullets)

## IF YOU NEED TO HIT A TARGET
(only if relevant)

Keep it practical. Do not rewrite the full script unless a short example cut is useful."""
    user_msg = f"{stats_block}\n\n--- SCRIPT ---\n{script[:8000]}"
    result, err, truncated = call_llm(system, user_msg, 2200)
    if err:
        return jsonify({"error": err}), 500
    record_action()
    # Prepend deterministic stats so the user always gets numbers even if LLM is vague
    full = stats_block + "\n\n" + (result or "")
    resp = {"result": full}
    if truncated:
        resp["warning"] = "Analysis may be incomplete for very long scripts."
    return jsonify(resp)

@app.route("/api/actions-left")
def api_actions_left():
    limits = _get_limits()
    total = int(limits.get("FREE_DAILY_ACTIONS", Config.FREE_DAILY_ACTIONS))
    left = get_user_actions_left()
    return jsonify({"is_pro": session.get("is_pro", False), "left": left, "total": total})

# ──────────────────────────────────────────────────────────────────────
# FREEMIUS WEBHOOK — Automated Payment → License
# ──────────────────────────────────────────────────────────────────────
@app.route("/fs-callback")
def fs_callback():
    """Freemius redirects the customer's browser here after a successful
    checkout (?license_id=X&email=Y as real query params — this is the
    customer's own browser landing here, NOT a webhook). Matches VoxCraft's
    flow exactly: verify with Freemius, mint (or reuse) an internal key, show
    it with an inline Activate button on this same page.

    IMPORTANT — requires Freemius to be configured to redirect here: in your
    Freemius Developer Dashboard, go to Plans → Customization → enable
    "Redirect Checkout to a custom URL" → set it to
    https://<your-domain>/fs-callback. Without that, customers land on
    Freemius's own generic thank-you page instead of this one.

    This complements (doesn't replace) the existing /webhook/freemius route —
    the webhook handles server-to-server confirmation async, while this page
    is what the customer's browser actually sees right after paying.
    """
    fs_license_id = request.args.get("license_id", "")
    fs_email = request.args.get("email", "")

    if not fs_license_id:
        return render_template("fs_callback.html", error="no_license_id")

    verify_result = verify_freemius_license(fs_license_id)
    if not verify_result.get("valid"):
        return render_template("fs_callback.html", error="not_verified",
                                license_id=fs_license_id,
                                verify_error=verify_result.get("error", "unknown"))

    keys = _get_license_keys()
    existing_key = next((k for k, v in keys.items() if v.get("freemius_license_id") == fs_license_id), None)

    if existing_key:
        license_key = existing_key
    else:
        license_key, err = create_freemius_license(
            verify_result.get("user_name") or "Pro User",
            verify_result.get("user_email") or fs_email,
            {"license_id": fs_license_id, "expiration": verify_result.get("expiration", "")},
        )
        if err:
            return render_template("fs_callback.html", error="not_verified",
                                    license_id=fs_license_id, verify_error=err)

    return render_template("fs_callback.html", success=True, license_key=license_key)


@app.route("/fs-callback/activate", methods=["POST"])
def fs_callback_activate():
    """The inline 'Activate Pro Now' button on the fs_callback success page."""
    key = request.form.get("license_key", "").strip()
    result = activate_license(key)
    if result.get("valid"):
        session["is_pro"] = True
        session["license_key"] = key
        session["pro_name"] = result.get("name", "Pro User")
        return redirect(url_for("urdu_writer"))
    return render_template("fs_callback.html", success=True, license_key=key,
                            activate_error=result.get("error", "Activation failed."))


@app.route("/webhook/freemius", methods=["POST"])
def freemius_webhook():
    """Handle Freemius payment webhooks — auto-generate and email license keys."""
    data = request.get_json() or {}
    event = data.get("event", "")

    # Verify webhook signature if secret is configured
    # BUG FIX: this checked for a header called "X-Freemius-Signature", but
    # Freemius actually sends it as "X-Signature" (confirmed against their
    # docs — PHP's $_SERVER['HTTP_X_SIGNATURE'] maps to the raw header
    # "X-Signature"). Since the wrong header name never matched, `signature`
    # was always empty, which silently skipped verification entirely — ANY
    # POST to this endpoint was processed as if it came from Freemius,
    # regardless of whether FREEMIUS_SECRET_KEY was set. This is a real
    # security gap: without this fix, anyone who finds this URL could POST a
    # fake payload and get a free license key generated and emailed to them.
    signature = request.headers.get("X-Signature", "")
    if Config.FREEMIUS_SECRET_KEY:
        # BUG FIX: previously required BOTH secret key configured AND a
        # signature header present to verify — meaning an attacker could
        # bypass verification just by omitting the header entirely. Once a
        # secret key is configured, a missing/invalid signature is now
        # always rejected rather than silently trusted.
        if not signature:
            return jsonify({"error": "Missing signature"}), 401
        import hmac, hashlib
        expected = hmac.new(
            Config.FREEMIUS_SECRET_KEY.encode(),
            request.get_data(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return jsonify({"error": "Invalid signature"}), 401

    if event in ("license.extended", "license.cancelled", "license.expired"):
        # HARDENING: these three events previously fell straight through to
        # "Event ignored" below — nothing in this app ever handled a
        # renewal, cancellation, or expiration after the first purchase.
        # See sync_license_from_freemius_event's docstring for the real
        # consequence: a cancelled/lapsed Pro subscriber's key never had an
        # expiry to begin with, so it just kept granting Pro access
        # forever, with continued billing or not making no difference at
        # all to their access.
        license_obj = (data.get("objects") or {}).get("license") or {}
        freemius_license_id = str(license_obj.get("id", ""))
        new_expiration = license_obj.get("expiration", "")
        result = sync_license_from_freemius_event(freemius_license_id, event, new_expiration)
        return jsonify(result), (200 if result.get("success") else 404)

    if event in ("payment.completed", "subscription.activated", "license.activated"):
        user = data.get("user", {})
        user_email = user.get("email", "")
        user_name = user.get("first", "") + " " + user.get("last", "")
        user_name = user_name.strip() or "Pro User"

        # Generate our own internal license key tied to this Freemius purchase
        objects = data.get("objects", {})
        license_obj = objects.get("license") or {}
        freemius_meta = {
            "license_id": license_obj.get("id", ""),
            "subscription_id": (objects.get("subscription") or {}).get("id", ""),
            # HARDENING: previously not captured at all — see
            # create_freemius_license's note on why a real expiry matters.
            "expiration": license_obj.get("expiration", ""),
        }
        license_key, error = create_freemius_license(user_name, user_email, freemius_meta)

        if license_key:
            # Send email with license key
            _send_key_email(user_email, user_name, license_key)

            # Also log the automated request
            requests_list = _get_requests()
            requests_list.insert(0, {
                "id": f"AUTO-{int(time.time())}-{random.randint(1000,9999)}",
                "name": user_name,
                "email": user_email,
                "phone": "",
                "status": "approved",
                "date": _now_str(),
                "key_assigned": license_key,
                "ip": "freemius_webhook",
                "notified": True,
                "payment_method": "Freemius (Auto)",
                "txn_id": data.get("payment_id", ""),
                "has_screenshot": False,
                "source": "freemius"
            })
            _save_requests(requests_list)

            return jsonify({"success": True, "license_key": license_key})
        else:
            # Notify admin of failure
            _notify_admin(
                user_name, user_email, "",
                f"AUTO-FAIL-{int(time.time())}",
                payment_method="Freemius",
                txn_id=data.get("payment_id", "")
            )
            return jsonify({"success": False, "error": error}), 500

    return jsonify({"success": True, "message": "Event ignored"})

# ──────────────────────────────────────────────────────────────────────
# FILEDESK — External Tool Tab
# ──────────────────────────────────────────────────────────────────────
@app.route("/filedesk")
def filedsk():
    """Redirect to FileDesk external tool or show embedded view."""
    if Config.FILEDESK_URL:
        return redirect(Config.FILEDESK_URL)
    return render_template("filedesk.html")

# ──────────────────────────────────────────────────────────────────────
# AD SLOTS — isolated iframe pages for each ad placement
# ──────────────────────────────────────────────────────────────────────
# BUG FIX: previously the banner, footer banner, and interstitial ads all
# used the SAME Adsterra zone script, but with invented container-ID suffixes
# (-footer, -interstitial) appended to the one exact ID
# (container-5b0c617f15e7e87967b22cafcc23e1b7) that Adsterra's invoke.js is
# hardcoded to look for. Suffixed IDs never match, so those ads silently never
# render. Removing the suffix instead would just create duplicate-ID HTML
# (multiple elements with the same id on one page), which is equally broken.
# Serving each placement as its own isolated iframe document — each with the
# ORIGINAL unmodified container ID — fixes both problems at once.
_AD_ZONE_SCRIPT = 'https://pl29723111.effectivecpmnetwork.com/5b0c617f15e7e87967b22cafcc23e1b7/invoke.js'
_AD_CONTAINER_ID = 'container-5b0c617f15e7e87967b22cafcc23e1b7'


@app.route("/ads/slot/<slot>")
def ads_slot(slot):
    if session.get("is_pro"):
        return "", 204
    if slot not in ("banner", "interstitial"):
        return "", 404
    height = 90 if slot == "banner" else 140
    html = f"""<!DOCTYPE html><html><head><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{background:transparent;height:{height}px;overflow:hidden;text-align:center;}}
</style></head><body>
<script async data-cfasync="false" src="{_AD_ZONE_SCRIPT}"></script>
<div id="{_AD_CONTAINER_ID}"></div>
</body></html>"""
    return html


# ──────────────────────────────────────────────────────────────────────
# ADMIN LOGIN RATE-LIMITING
# ──────────────────────────────────────────────────────────────────────
# Persisted via GitHub-JSON (same CAS transaction pattern as license
# activation) rather than in-memory: this app runs multiple gunicorn
# workers, so an in-memory counter would let an attacker get N free
# guesses PER WORKER before any of them noticed the others' failures.
# Login attempts are rare enough (unlike per-generation usage tracking)
# that a synchronous transaction on every attempt is fine here — no need
# for the fire-and-forget trade-off used for free-tier action counts.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 900   # 15 min window for counting failures
_LOGIN_LOCKOUT_SECONDS = 900  # 15 min lockout once tripped

def _admin_login_locked(ip_hash: str):
    """Returns seconds remaining if this IP is currently locked out, else 0."""
    data = _get_login_attempts()
    rec = data.get(ip_hash)
    if not rec or not rec.get("locked_until"):
        return 0
    remaining = rec["locked_until"] - time.time()
    return max(0, int(remaining))

def _record_login_failure(ip_hash: str):
    now = time.time()
    def _bump(fresh):
        rec = fresh.get(ip_hash, {})
        # Reset the counter if the last failure was outside the window
        if now - rec.get("window_start", 0) > _LOGIN_WINDOW_SECONDS:
            rec = {"window_start": now, "count": 0}
        rec["count"] = rec.get("count", 0) + 1
        rec["last_attempt"] = now
        if rec["count"] >= _LOGIN_MAX_ATTEMPTS:
            rec["locked_until"] = now + _LOGIN_LOCKOUT_SECONDS
        fresh[ip_hash] = rec
        return fresh, True
    _gh_transact(_F_LOGIN_ATTEMPTS, _bump, "Record failed admin login")

def _clear_login_failures(ip_hash: str):
    def _clear(fresh):
        if ip_hash in fresh:
            del fresh[ip_hash]
            return fresh, True
        return fresh, None  # nothing to clear, skip the write
    _gh_transact(_F_LOGIN_ATTEMPTS, _clear, "Clear admin login attempts")

# ──────────────────────────────────────────────────────────────────────
# ADMIN ROUTES
# ──────────────────────────────────────────────────────────────────────
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_auth"):
        return redirect(url_for("admin_dashboard"))

    ip_hash = _hash_ip(_get_user_ip())
    locked_for = _admin_login_locked(ip_hash)

    if request.method == "POST":
        if locked_for > 0:
            flash(f"Too many failed attempts. Try again in {locked_for // 60 + 1} minute(s).", "error")
            return render_template("admin/login.html", locked=True, locked_for=locked_for)

        email = request.form.get("email", "").strip()
        pwd = request.form.get("password", "")
        # SECURITY: constant-time comparison on BOTH fields, and both must
        # match. Email+password (rather than password alone) means an
        # attacker who somehow guesses/leaks the password still can't get in
        # without also knowing the admin email — a second, independent
        # secret, not just a longer version of the same one. Same fix as
        # VoxCraft. hmac.compare_digest avoids the timing side-channel a
        # plain `==` would leak on either field.
        email_ok = bool(Config.ADMIN_EMAIL) and hmac.compare_digest(email.lower(), Config.ADMIN_EMAIL.lower())
        pwd_ok = hmac.compare_digest(pwd, Config.ADMIN_PASSWORD)
        if email_ok and pwd_ok:
            session["admin_auth"] = True
            session.pop("_csrf_token", None)  # rotate token after login
            _clear_login_failures(ip_hash)
            return redirect(url_for("admin_dashboard"))
        _record_login_failure(ip_hash)
        flash("Wrong email or password", "error")
        locked_for = _admin_login_locked(ip_hash)
    return render_template("admin/login.html", locked=locked_for > 0, locked_for=locked_for)

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    keys = _get_license_keys()
    fresh = sum(1 for v in keys.values() if not v.get("used") and not v.get("revoked"))
    used = sum(1 for v in keys.values() if v.get("used") and not v.get("revoked"))
    revoked = sum(1 for v in keys.values() if v.get("revoked"))
    limits = _get_limits()
    requests_list = _get_requests()
    pending = [r for r in requests_list if r.get("status") == "pending"]
    approved = [r for r in requests_list if r.get("status") == "approved"]
    rejected = [r for r in requests_list if r.get("status") == "rejected"]
    # Grace auto-approvals awaiting finalization — don't show up in `pending`
    # above (their status is already "approved"), so without a separate
    # count here they'd be invisible on the dashboard KPIs too, same blind
    # spot sweep_grace_reminders() fixes for email.
    pending_grace = sum(1 for r in approved if r.get("access_type") == "grace" and not r.get("grace_finalized"))
    posts = _get_blog_posts()
    # Recent lockouts/high-attempt IPs — most-recent-first, capped to the 10
    # most active offenders so this doesn't grow unbounded on the dashboard.
    login_attempts_raw = _get_login_attempts()
    login_attempts = sorted(
        [{"ip_hash": k, **v} for k, v in login_attempts_raw.items()],
        key=lambda r: r.get("last_attempt", 0), reverse=True
    )[:10]
    return render_template("admin/dashboard.html",
        fresh=fresh, used=used, revoked=revoked,
        limits=limits, pending=pending, approved=approved,
        rejected=rejected, pending_grace=pending_grace, posts=posts, keys=keys,
        now=datetime.datetime.now(),
        login_attempts=login_attempts,
        gh_token_set=bool(Config.GITHUB_TOKEN),
        groq_set=bool(Config.GROQ_API_KEY),
        cerebras_set=bool(Config.CEREBRAS_API_KEY),
        openrouter_set=bool(Config.OPENROUTER_API_KEY),
        mailtrap_set=bool(Config.MAILTRAP_API_KEY),
        smtp_set=bool(Config.SMTP_HOST and Config.SMTP_USER and Config.SMTP_PASS),
        wa_set=bool(Config.WHATSAPP_API_TOKEN and Config.WHATSAPP_PHONE_NUMBER_ID),
        wapp_set=bool(Config.WAPPFLY_API_KEY))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_auth", None)
    return redirect(url_for("landing"))

@app.route("/admin/api/generate-key", methods=["POST"])
@admin_required
def admin_generate_key():
    # BUG FIX: same request.form/JSON mismatch as the blog toggle/delete bug —
    # the frontend's api() helper sends JSON, this was reading form data.
    data = request.get_json() or {}
    count = int(data.get("count", 1))
    keys = []
    for _ in range(min(count, 20)):
        keys.append(create_new_key())
    return jsonify({"keys": keys})

@app.route("/admin/api/revoke-key", methods=["POST"])
@admin_required
def admin_revoke_key():
    data = request.get_json() or {}
    key = data.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        keys[key]["revoked"] = True
        _save_license_keys(keys)
    return jsonify({"success": True})

@app.route("/admin/api/unrevoke-key", methods=["POST"])
@admin_required
def admin_unrevoke_key():
    data = request.get_json() or {}
    key = data.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        keys[key]["revoked"] = False
        _save_license_keys(keys)
    return jsonify({"success": True})

@app.route("/admin/api/unlock-login", methods=["POST"])
@admin_required
def admin_unlock_login():
    """Support control: clear a locked-out IP's failure count manually —
    e.g. you (the admin) got locked out yourself after a typo streak, or a
    shared office/CGNAT IP tripped the lockout for someone else on it."""
    data = request.get_json() or {}
    ip_hash = data.get("ip_hash", "").strip()
    if ip_hash:
        _clear_login_failures(ip_hash)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Missing ip_hash"})

@app.route("/admin/api/reset-device-key", methods=["POST"])
@admin_required
def admin_reset_device_lock():
    """Support tool: a legitimate customer got a new phone / reinstalled
    their browser and neither IP nor fingerprint matches their key's
    history anymore, so activate_license()'s OR-match correctly refuses
    them. Rather than revoke+reissue a new key (which loses their purchase
    record), this clears the key's device history so the very next
    activation attempt — from wherever they are — seeds it fresh. Same
    escape hatch as VoxCraft's reset_device_lock()."""
    data = request.get_json() or {}
    key = data.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        keys[key]["ip_history"] = []
        keys[key]["fp_history"] = []
        keys[key]["used"] = False
        keys[key]["activated_by"] = ""
        keys[key]["activated_on"] = ""
        _save_license_keys(keys)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Key not found"})

@app.route("/admin/api/delete-key", methods=["POST"])
@admin_required
def admin_delete_key():
    data = request.get_json() or {}
    key = data.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        del keys[key]
        _save_license_keys(keys)
    return jsonify({"success": True})

@app.route("/admin/api/approve-request", methods=["POST"])
@admin_required
def admin_approve_request():
    data = request.get_json() or {}
    req_id = data.get("req_id", "").strip()
    manual_key = data.get("manual_key", "").strip()
    if manual_key:
        key = manual_key
    else:
        key = create_new_key()
    if approve_request(req_id, key):
        return jsonify({"success": True, "key": key})
    return jsonify({"success": False, "error": "Request not found"})

@app.route("/admin/api/reject-request", methods=["POST"])
@admin_required
def admin_reject_request():
    data = request.get_json() or {}
    req_id = data.get("req_id", "").strip()
    if reject_request(req_id):
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/admin/api/delete-request", methods=["POST"])
@admin_required
def admin_delete_request():
    data = request.get_json() or {}
    req_id = data.get("req_id", "").strip()
    all_reqs = _get_requests()
    all_reqs = [r for r in all_reqs if r["id"] != req_id]
    _save_requests(all_reqs)
    return jsonify({"success": True})

@app.route("/admin/api/save-limits", methods=["POST"])
@admin_required
def admin_save_limits():
    data = request.get_json() or {}
    limits = _get_limits()
    for k in ["FREE_DAILY_ACTIONS", "PRO_PRICE_PKR", "PRO_PRICE_LABEL", "FREE_PRICE_LABEL", "CHECKOUT_URL", "FREE_FEATURES", "PRO_FEATURES"]:
        if k in data:
            limits[k] = data[k]
    ok, err = _gh_write(_F_LIMITS, limits, "Update limits")
    _gh_write(_F_LIMITS, limits, "Update limits", repo=Config.GH_REPO_PUBLIC)
    return jsonify({"success": ok, "error": err})

@app.route("/admin/api/save-blog", methods=["POST"])
@admin_required
def admin_save_blog():
    data = request.get_json() or {}
    posts = _get_blog_posts()
    post_id = data.get("id")
    if post_id:
        for i, p in enumerate(posts):
            if p.get("id") == post_id:
                posts[i].update(data)
                break
        else:
            posts.insert(0, data)
    else:
        data["id"] = f"post_{int(time.time())}"
        posts.insert(0, data)
    ok = _save_blog_posts(posts)
    return jsonify({"success": ok})

@app.route("/admin/api/delete-blog", methods=["POST"])
@admin_required
def admin_delete_blog():
    # BUG FIX: this read request.form.get("id"), but the frontend's api()
    # helper sends JSON (Content-Type: application/json), not form-encoded
    # data — so request.form was always empty and post_id was always "".
    # The delete silently did nothing while still returning {"success": true}.
    data = request.get_json() or {}
    post_id = data.get("id", "").strip()
    posts = _get_blog_posts()
    posts = [p for p in posts if p.get("id") != post_id]
    _save_blog_posts(posts)
    return jsonify({"success": True})

@app.route("/admin/api/toggle-blog", methods=["POST"])
@admin_required
def admin_toggle_blog():
    # Same fix as delete-blog above — was request.form, now request.get_json().
    data = request.get_json() or {}
    post_id = data.get("id", "").strip()
    posts = _get_blog_posts()
    for p in posts:
        if p.get("id") == post_id:
            p["published"] = not p.get("published", False)
            break
    _save_blog_posts(posts)
    return jsonify({"success": True})

@app.route("/admin/api/test-email", methods=["POST"])
@admin_required
def admin_test_email():
    if not Config.MAILTRAP_API_KEY or not Config.ADMIN_EMAIL:
        return jsonify({"success": False, "error": "Mailtrap not configured"})
    try:
        from_name, from_email = _parse_from_address(Config.CONTACT_FROM_EMAIL)
        r = req.post("https://send.api.mailtrap.io/api/send",
            headers={"Api-Token": Config.MAILTRAP_API_KEY, "Content-Type": "application/json"},
            json={"from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
                  "to": [{"email": Config.ADMIN_EMAIL}],
                  "subject": "✅ QalamStudio Test Email",
                  "text": "This is a test notification from QalamStudio admin panel."}, timeout=15)
        if r.status_code == 200:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": f"{r.status_code}: {r.text[:200]}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ──────────────────────────────────────────────────────────────────────
# ERROR HANDLERS
# ──────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("landing.html", not_found=True), 404

# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
