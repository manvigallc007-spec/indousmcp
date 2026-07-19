"""Assembles the Starlette web app: public + admin + portal routes, signed sessions."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

from ..config import settings
from . import (admin, admin_content, api, chat, errors, landing, me, pages, portal, public,
               qa_web, reviews, today_web)
from .pageviews import PageviewMiddleware
from .security import SecurityHeadersMiddleware

routes = [*public.routes, *chat.routes, *landing.routes, *admin.routes, *admin_content.routes,
          *portal.routes, *me.routes, *today_web.routes, *qa_web.routes, *api.routes, *pages.routes,
          *reviews.routes, *errors.routes]

middleware = [
    Middleware(SecurityHeadersMiddleware),
    Middleware(PageviewMiddleware),
    # SameSite=lax blocks the session cookie on cross-site POSTs (CSRF mitigation for authed
    # admin/portal actions); set SESSION_HTTPS_ONLY=true once served over HTTPS.
    Middleware(SessionMiddleware, secret_key=settings.secret_key,
               https_only=settings.session_https_only, same_site="lax"),
]

app = Starlette(routes=routes, middleware=middleware,
                exception_handlers={404: errors.not_found, 500: errors.server_error})


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.web_host, port=settings.web_port)
