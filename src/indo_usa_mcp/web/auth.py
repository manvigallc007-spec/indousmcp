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


def login_admin(request: Request, password: str) -> bool:
    if admin_enabled() and hmac.compare_digest(password, settings.admin_password):
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
