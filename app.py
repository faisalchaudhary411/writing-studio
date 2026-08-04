# ══════════════════════════════════════════════════════════════════════
# QALAM STUDIO — Flask Edition
# v4.0 — Unique glassmorphism design · Full feature parity
# ══════════════════════════════════════════════════════════════════════
import os, json, base64, time, hashlib, random, string, datetime, threading
from functools import wraps
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, session, redirect, url_for,
    flash, jsonify, abort, send_from_directory
)
from flask_session import Session
import requests as req

load_dotenv()

# ──────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_session")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB uploads
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
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
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
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
    FREE_DAILY_ACTIONS = int(os.environ.get("FREE_DAILY_ACTIONS", "20"))
    # Auto-approve manual Pakistani payments instantly (trust-based with grace period)
    AUTO_APPROVE_MANUAL = os.environ.get("AUTO_APPROVE_MANUAL", "true").lower() == "true"
    MANUAL_GRACE_HOURS = int(os.environ.get("MANUAL_GRACE_HOURS", "72"))
    PRO_PRICE_PKR = int(os.environ.get("PRO_PRICE_PKR", "499"))
    PRO_PRICE_LABEL = os.environ.get("PRO_PRICE_LABEL", "499 PKR")
    FREE_PRICE_LABEL = os.environ.get("FREE_PRICE_LABEL", "مفت")
    CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "/request-pro")

os.makedirs(Config.SESSION_FILE_DIR, exist_ok=True)

app = Flask(__name__)
app.config.from_object(Config)
Session(app)

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

# Initialize files
_ensure_file(_F_REQUESTS, [])
_ensure_file(_F_KEYS, {})
_ensure_file(_F_BLOGS, [])
_ensure_file(_F_USAGE, {})
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
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    if request.headers.get("X-Real-Ip"):
        return request.headers.get("X-Real-Ip")
    return request.remote_addr or "unknown"

def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]

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

def _get_blog_posts():
    data = _gh_read(_F_BLOGS)
    return data if isinstance(data, list) else []

def _save_blog_posts(data):
    return _gh_write(_F_BLOGS, data, "Update blogs")

def generate_license_key() -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=14))
    return f"QALAM-PRO-{suffix}"

def create_new_key(grace_hours=None):
    key = generate_license_key()
    keys = _get_license_keys()
    key_data = {
        "used": False, "revoked": False,
        "created": _now_str(),
        "activated_by": "", "activated_on": ""
    }
    if grace_hours:
        key_data["grace_expires"] = (datetime.datetime.now() + datetime.timedelta(hours=grace_hours)).strftime("%Y-%m-%d %H:%M")
    keys[key] = key_data
    _save_license_keys(keys)
    return key

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
    """
    key = create_new_key()
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
            "error": None if is_valid else ("License cancelled" if is_cancelled else "License expired"),
        }
    except Exception as e:
        return {"success": False, "valid": False, "error": str(e)}

def check_license(key: str) -> dict:
    """Used by /api/restore-pro to re-confirm Pro status for a device that
    already activated this key (JS calls this on page load with the key it
    has stored in localStorage).

    SECURITY FIX: this previously didn't verify the calling device matched
    the one that originally activated the key — meaning anyone who obtained
    a copy of an already-activated key (screenshot, leak, guess) could get
    Pro on ANY device by calling this endpoint, completely bypassing the
    one-device-per-key restriction that activate_license() enforces. Now
    mirrors that same device check.
    """
    key = key.strip()
    keys = _get_license_keys()
    info = keys.get(key)
    if not info:
        return {"valid": False}
    if info.get("revoked"):
        return {"valid": False, "error": "This license has been revoked."}
    # Check grace period for auto-approved manual payments
    if info.get("grace_expires"):
        try:
            expires = datetime.datetime.strptime(info["grace_expires"], "%Y-%m-%d %H:%M")
            if datetime.datetime.now() > expires:
                return {"valid": False, "error": "Grace period expired. Contact support."}
        except Exception:
            pass
    if not info.get("used"):
        return {"valid": False, "error": "This key hasn't been activated yet."}
    current_ip = _get_user_ip()
    current_hash = _hash_ip(current_ip)
    if current_ip == "unknown" or info.get("activated_by") != current_hash:
        return {"valid": False, "error": "This key was activated on a different device."}
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
        if info.get("used"):
            current_ip = _get_user_ip()
            current_hash = _hash_ip(current_ip)
            if current_ip != "unknown" and info.get("activated_by") == current_hash:
                return {"valid": True, "name": "Pro User"}
            return {"valid": False, "error": "This key has already been used. Each key is one-time use only."}
        keys[key]["used"] = True
        keys[key]["activated_on"] = _now_str()
        keys[key]["activated_by"] = _hash_ip(_get_user_ip())
        _save_license_keys(keys)
        return {"valid": True, "name": "Pro User"}

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

    # Resend
    if Config.RESEND_API_KEY and Config.ADMIN_EMAIL:
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
            email_payload = {
                "from": "QalamStudio <onboarding@resend.dev>",
                "to": [Config.ADMIN_EMAIL],
                "subject": f"💳 New Pro Payment — {name}",
                "html": admin_html,
                "text": message_body
            }
            if screenshot_b64:
                email_payload["attachments"] = [{
                    "filename": "payment_proof.jpg",
                    "content": screenshot_b64,
                    "content_type": "image/jpeg"
                }]
            r = req.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}", "Content-Type": "application/json"},
                json=email_payload, timeout=20)
            if r.status_code in (200, 201):
                notified = True
            else:
                errors.append(f"Resend: {r.status_code}")
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
                    req.post("https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}", "Content-Type": "application/json"},
                        json={"from": "QalamStudio <onboarding@resend.dev>", "to": [email],
                              "subject": "✅ Payment Received — QalamStudio Pro", "html": user_html}, timeout=15)
                except Exception:
                    pass
        except Exception as e:
            errors.append(f"Resend: {e}")

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
    if not Config.RESEND_API_KEY or not user_email:
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
        r = req.post("https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "QalamStudio <onboarding@resend.dev>", "to": [user_email],
                  "subject": "🎉 Your QalamStudio Pro License Key", "html": html}, timeout=15)
        return r.status_code in (200, 201)
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


def submit_pro_request(name, email, phone="", payment_method="", txn_id="", screenshot_b64=""):
    requests_list = _get_requests()
    req_id = f"REQ-{int(time.time())}-{random.randint(1000,9999)}"
    ip_hash = _hash_ip(_get_user_ip())

    # Auto-approve manual payments instantly if enabled — gated behind three
    # checks now (previously just "was any file uploaded"):
    #   1. a transaction/reference ID was actually provided
    #   2. the uploaded file actually decodes as a real image
    #   3. this device hasn't already received an auto-approval before
    auto_approved = False
    license_key = ""

    if (Config.AUTO_APPROVE_MANUAL and txn_id.strip() and _is_valid_image(screenshot_b64)
            and not _device_already_auto_approved(ip_hash)):
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
        "has_screenshot": bool(screenshot_b64),
        "auto_approved": auto_approved,
        "grace_expires": (datetime.datetime.now() + datetime.timedelta(hours=Config.MANUAL_GRACE_HOURS)).strftime("%Y-%m-%d %H:%M") if auto_approved else ""
    }
    requests_list.insert(0, new_request)

    # Notify admin (always)
    notified = _notify_admin(name, email, phone, req_id, payment_method, txn_id, screenshot_b64)
    new_request["notified"] = notified

    # If auto-approved, email key immediately
    if auto_approved and license_key:
        _send_key_email(email, name, license_key)

    ok, err = _save_requests(requests_list)
    return {
        "success": ok, "id": req_id, "notified": notified, 
        "error": err, "auto_approved": auto_approved, 
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
            _save_requests(requests)
            return True
    return False

# ──────────────────────────────────────────────────────────────────────
# USAGE & LIMITS
# ──────────────────────────────────────────────────────────────────────
def get_user_actions_left():
    if session.get("is_pro"):
        return 9999
    today = _today()
    if session.get("last_action_date") != today:
        session["daily_actions"] = 0
        session["last_action_date"] = today
    limits = _get_limits()
    free_limit = int(limits.get("FREE_DAILY_ACTIONS", Config.FREE_DAILY_ACTIONS))
    return max(0, free_limit - session.get("daily_actions", 0))

def record_action():
    if session.get("is_pro"):
        return True
    today = _today()
    if session.get("last_action_date") != today:
        session["daily_actions"] = 0
        session["last_action_date"] = today
    session["daily_actions"] = session.get("daily_actions", 0) + 1
    # Update GitHub usage tracking
    try:
        month = datetime.datetime.now().strftime("%Y-%m")
        ih = _hash_ip(_get_user_ip())
        data = _get_usage()
        rec = data.get(ih, {"month": month, "actions_used": 0})
        if rec.get("month") != month:
            rec = {"month": month, "actions_used": 0}
        rec["actions_used"] = rec.get("actions_used", 0) + 1
        rec["month"] = month
        data[ih] = rec
        threading.Thread(target=lambda d: _save_usage(d), args=(data,), daemon=True).start()
    except Exception:
        pass
    return True

def can_act():
    return session.get("is_pro") or get_user_actions_left() > 0

# ──────────────────────────────────────────────────────────────────────
# GROQ AI
# ──────────────────────────────────────────────────────────────────────
def call_groq(system: str, user: str, max_tokens=2000):
    """BUG FIX: this never checked Groq's finish_reason field, so when a
    response got cut off because it hit max_tokens (finish_reason=="length"),
    the truncated/incomplete content was returned as if it were a normal,
    complete result — with no way for the caller (or the user) to know it
    was cut off. This is very likely the source of 'corrupted/garbage'
    output reports: for content types with variable output length (long Urdu
    articles, SRT subtitle files, translations of long files), the fixed
    max_tokens value across all endpoints was often too low, and cut-off SRT
    files in particular can look like garbage to a video player since the
    truncation point breaks the file's syntax entirely.

    Returns (content, error, was_truncated) — callers should check
    was_truncated and warn the user rather than presenting a cut-off result
    as if it were complete.
    """
    try:
        if not Config.GROQ_API_KEY:
            return None, "GROQ_API_KEY not set", False
        # Groq's hard ceiling for this model is 8192 output tokens per
        # request — asking for more than that fails outright, so clamp here
        # rather than let a bad max_tokens value break the request.
        max_tokens = min(max_tokens, 8000)
        r = req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=60
        )
        if r.status_code == 200:
            choice = r.json()["choices"][0]
            was_truncated = choice.get("finish_reason") == "length"
            return choice["message"]["content"], None, was_truncated
        return None, f"API error {r.status_code}", False
    except Exception as e:
        return None, str(e), False

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

@app.route("/contact")
def contact():
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
    result, err, truncated = call_groq(system, f"اس موضوع پر لکھو: {topic}", tokens_for_length)
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
    result, err, truncated = call_groq(sys_p, f"Service: {service}\nClient needs: {client_need}\nMy experience: {your_exp or 'Not specified'}", 1400)
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
    result, err, truncated = call_groq(sys_e, f"Context: {ectx}", 1000)
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
    result, err, truncated = call_groq(sys_s, f"Convert to SRT:\n\n{script}", tokens_needed)
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
    result, err, truncated = call_groq(sys_t, f"Translate:\n\n{eng_srt}", tokens_needed)
    if err:
        return jsonify({"error": err}), 500
    if truncated:
        return jsonify({"error": "The translation was cut off partway through and would be broken in a video player. Try splitting the file into smaller chunks."}), 500
    record_action()
    return jsonify({"result": result})

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
            {"license_id": fs_license_id},
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

    if event in ("payment.completed", "subscription.activated", "license.activated"):
        user = data.get("user", {})
        user_email = user.get("email", "")
        user_name = user.get("first", "") + " " + user.get("last", "")
        user_name = user_name.strip() or "Pro User"

        # Generate our own internal license key tied to this Freemius purchase
        objects = data.get("objects", {})
        freemius_meta = {
            "license_id": (objects.get("license") or {}).get("id", ""),
            "subscription_id": (objects.get("subscription") or {}).get("id", ""),
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
# ADMIN ROUTES
# ──────────────────────────────────────────────────────────────────────
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_auth"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == Config.ADMIN_PASSWORD:
            session["admin_auth"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong password", "error")
    return render_template("admin/login.html")

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
    posts = _get_blog_posts()
    return render_template("admin/dashboard.html",
        fresh=fresh, used=used, revoked=revoked,
        limits=limits, pending=pending, approved=approved,
        rejected=rejected, posts=posts, keys=keys,
        now=datetime.datetime.now(),
        gh_token_set=bool(Config.GITHUB_TOKEN),
        resend_set=bool(Config.RESEND_API_KEY),
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
    count = int(request.form.get("count", 1))
    keys = []
    for _ in range(min(count, 20)):
        keys.append(create_new_key())
    return jsonify({"keys": keys})

@app.route("/admin/api/revoke-key", methods=["POST"])
@admin_required
def admin_revoke_key():
    key = request.form.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        keys[key]["revoked"] = True
        _save_license_keys(keys)
    return jsonify({"success": True})

@app.route("/admin/api/unrevoke-key", methods=["POST"])
@admin_required
def admin_unrevoke_key():
    key = request.form.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        keys[key]["revoked"] = False
        _save_license_keys(keys)
    return jsonify({"success": True})

@app.route("/admin/api/delete-key", methods=["POST"])
@admin_required
def admin_delete_key():
    key = request.form.get("key", "").strip()
    keys = _get_license_keys()
    if key in keys:
        del keys[key]
        _save_license_keys(keys)
    return jsonify({"success": True})

@app.route("/admin/api/approve-request", methods=["POST"])
@admin_required
def admin_approve_request():
    req_id = request.form.get("req_id", "").strip()
    manual_key = request.form.get("manual_key", "").strip()
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
    req_id = request.form.get("req_id", "").strip()
    if reject_request(req_id):
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/admin/api/delete-request", methods=["POST"])
@admin_required
def admin_delete_request():
    req_id = request.form.get("req_id", "").strip()
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
    if not Config.RESEND_API_KEY or not Config.ADMIN_EMAIL:
        return jsonify({"success": False, "error": "Resend not configured"})
    try:
        r = req.post("https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "QalamStudio <onboarding@resend.dev>", "to": [Config.ADMIN_EMAIL],
                  "subject": "✅ QalamStudio Test Email",
                  "text": "This is a test notification from QalamStudio admin panel."}, timeout=15)
        if r.status_code in (200, 201):
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
