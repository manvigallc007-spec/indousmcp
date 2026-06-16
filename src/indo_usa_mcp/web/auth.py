"""Auth for the web app: admin password sessions + passwordless magic-links.

Admin: a single password (settings.admin_password) -> signed session cookie.
Portal: stateless HMAC-signed, expiring magic-link tokens emailed to owners (no passwords,
no table).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import random
import time
from hashlib import sha256

from starlette.requests import Request
from starlette.responses import RedirectResponse

from .. import db
from ..config import settings


# ------------------------------------------------------------------ admin sessions
def admin_enabled() -> bool:
    return bool(settings.admin_password)


def is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def require_admin(request: Request) -> RedirectResponse | None:
    """Return a redirect to login when the request isn't an authenticated admin."""
    if is_admin(request):
        return None
    return RedirectResponse("/admin/login", status_code=303)


def login_admin(request: Request, username: str, password: str) -> bool:
    if (admin_enabled()
            and hmac.compare_digest((username or "").strip(), settings.admin_username)
            and hmac.compare_digest(password or "", settings.admin_password)):
        request.session["admin"] = True
        return True
    return False


def logout_admin(request: Request) -> None:
    request.session.pop("admin", None)


# --------------------------------------------------------------- magic-link tokens
def _sign(raw: str) -> str:
    return hmac.new(settings.secret_key.encode(), raw.encode(), sha256).hexdigest()[:32]


def make_magic_token(email: str, ttl_minutes: int | None = None) -> str:
    ttl = ttl_minutes if ttl_minutes is not None else settings.magic_link_ttl_minutes
    raw = f"{email}|{int(time.time()) + ttl * 60}"
    body = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    return f"{body}.{_sign(raw)}"


def verify_magic_token(token: str) -> str | None:
    """Return the email if the token is valid and unexpired, else None."""
    try:
        body, sig = token.split(".", 1)
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        email, exp = raw.rsplit("|", 1)
    except (ValueError, Exception):
        return None
    if not hmac.compare_digest(sig, _sign(raw)):
        return None
    if int(exp) < int(time.time()):
        return None
    return email


def portal_email(request: Request) -> str | None:
    return request.session.get("owner_email")


# ------------------------------------------------------------------ Google OAuth (owner portal)
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


def google_redirect_uri() -> str:
    """Must be registered EXACTLY as an Authorized redirect URI in the Google OAuth client."""
    return settings.public_web_url.rstrip("/") + "/portal/google/callback"


def google_auth_url(state: str) -> str:
    from urllib.parse import urlencode
    return _GOOGLE_AUTH + "?" + urlencode({
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    })


def google_exchange(code: str) -> str | None:
    """Exchange the authorization code for the user's VERIFIED Google email. None on any failure."""
    if not (settings.google_oauth_enabled and code):
        return None
    import httpx
    try:
        tok = httpx.post(_GOOGLE_TOKEN, data={
            "code": code, "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": google_redirect_uri(), "grant_type": "authorization_code",
        }, timeout=10.0).json()
        access = tok.get("access_token")
        if not access:
            return None
        info = httpx.get(_GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access}"},
                         timeout=10.0).json()
        email = (info.get("email") or "").strip().lower()
        if email and info.get("email_verified") in (True, "true", "True"):
            return email
    except Exception:
        return None
    return None


# ------------------------------------------------------ password accounts (business owners)
_PBKDF2_ROUNDS = 200_000


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _PBKDF2_ROUNDS)
    enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${enc(salt)}${enc(dk)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_b64, hash_b64 = stored.split("$")
        dec = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), dec(salt_b64), int(rounds))
        return hmac.compare_digest(dk, dec(hash_b64))
    except Exception:
        return False


def get_user(email: str) -> dict | None:
    try:
        return db.query_one("SELECT * FROM users WHERE email = %s", [(email or "").strip().lower()])
    except Exception:
        return None


def create_user(email: str, password: str) -> dict:
    """Create an unverified account (or return existing). Records Terms acceptance time."""
    email = (email or "").strip().lower()
    existing = get_user(email)
    if existing:
        return {"ok": False, "reason": "exists", "verified": bool(existing.get("email_verified"))}
    db.execute("INSERT INTO users (email, password_hash, terms_accepted_at) VALUES (%s, %s, now()) "
               "ON CONFLICT (email) DO NOTHING", [email, hash_password(password)])
    return {"ok": True}


def set_verified(email: str) -> None:
    db.execute("UPDATE users SET email_verified = TRUE, verified_at = now() WHERE email = %s",
               [(email or "").strip().lower()])


def set_password(email: str, password: str) -> None:
    db.execute("UPDATE users SET password_hash = %s WHERE email = %s",
               [hash_password(password), (email or "").strip().lower()])


def check_login(email: str, password: str) -> dict | None:
    """Return the user row on a correct password, else None. Caller checks email_verified."""
    u = get_user(email)
    if u and u.get("password_hash") and verify_password(password or "", u["password_hash"]):
        try:
            db.execute("UPDATE users SET last_login_at = now() WHERE email = %s", [u["email"]])
        except Exception:
            pass
        return u
    return None


# --------------------------------------------------- purpose-scoped action tokens (verify / reset)
def make_action_token(email: str, purpose: str, ttl_minutes: int = 1440) -> str:
    """Signed, expiring token bound to a purpose ('verify' | 'reset') so one can't be used as another."""
    raw = f"{purpose}|{(email or '').strip().lower()}|{int(time.time()) + ttl_minutes * 60}"
    body = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    return f"{body}.{_sign(raw)}"


def verify_action_token(token: str, purpose: str) -> str | None:
    try:
        body, sig = token.split(".", 1)
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        pp, email, exp = raw.split("|")
    except Exception:
        return None
    if not hmac.compare_digest(sig, _sign(raw)) or pp != purpose or int(exp) < int(time.time()):
        return None
    return email


# ----------------------------------------------------------------------------- captcha
def make_captcha() -> dict:
    """A free, self-contained signed math challenge (no external service, no account)."""
    a, b = random.randint(1, 9), random.randint(1, 9)
    raw = f"{a + b}|{int(time.time()) + 600}"
    token = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=") + "." + _sign(raw)
    return {"question": f"What is {a} + {b}?", "token": token}


def _verify_math_captcha(token: str, answer: str) -> bool:
    try:
        body, sig = (token or "").split(".", 1)
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        expected, exp = raw.split("|")
    except Exception:
        return False
    if not hmac.compare_digest(sig, _sign(raw)) or int(exp) < int(time.time()):
        return False
    try:
        return int(str(answer).strip()) == int(expected)
    except (ValueError, TypeError):
        return False


def verify_captcha(form) -> bool:
    """Validate the captcha from a submitted form. Cloudflare Turnstile if configured, else math."""
    if settings.turnstile_enabled:
        token = (form.get("cf-turnstile-response") or "").strip()
        if not token:
            return False
        try:
            import httpx
            r = httpx.post("https://challenges.cloudflare.com/turnstile/v0/siteverify",
                           data={"secret": settings.turnstile_secret_key, "response": token},
                           timeout=10.0)
            return bool(r.json().get("success"))
        except Exception:
            return False
    return _verify_math_captcha(form.get("captcha_token") or "", form.get("captcha") or "")
