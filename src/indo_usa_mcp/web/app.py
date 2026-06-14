"""Assembles the Starlette web app: public + admin + portal routes, signed sessions."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

from ..config import settings
from . import admin, api, chat, landing, pages, portal, public

routes = [*public.routes, *chat.routes, *landing.routes, *admin.routes, *portal.routes,
          *api.routes, *pages.routes]

middleware = [Middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=False)]

app = Starlette(routes=routes, middleware=middleware)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.web_host, port=settings.web_port)
