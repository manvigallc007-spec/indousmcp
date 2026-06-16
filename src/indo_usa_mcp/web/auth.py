"""Auth for the web app: admin password sessions + passwordless magic-links.

Admin: a single password (settings.admin_password) -> signed session cookie.
Portal: stateless HMAC-signed, expiring magic-link tokens emailed to owners (no passwords,
no table).
"""

from __future__ import annotations

import base64
import hmac
import time
from hashlib import sha256

from starlette.requests import Request
from starlette.responses import RedirectResponse

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
