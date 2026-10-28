from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.errors import api_error
from ..core.rate_limit import agent_guard
from ..db import get_db
from ..services.auth_admin import authenticate as auth_admin_session
from ..services.keys import KeyService, bearer_from


async def get_current_admin(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("epa_session")
    if not token:
        raise api_error("TOKEN_INVALID", "Nicht angemeldet.")
    session = await auth_admin_session(db, token)
    if session is None:
        raise api_error("TOKEN_INVALID", "Session ungültig oder abgelaufen.")
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_cookie = request.cookies.get("epa_csrf")
        csrf_header = request.headers.get("x-csrf-token")
        if not csrf_cookie or csrf_cookie != session.csrf_token or csrf_cookie != csrf_header:
            raise api_error("FORBIDDEN", "CSRF-Token ungültig.")
    return session


async def get_api_key_account(request: Request, db: AsyncSession = Depends(get_db)):
    raw = bearer_from(request) or request.query_params.get("token")
    if not raw:
        raise api_error("TOKEN_INVALID", "API-Key fehlt.")
    key, account = await KeyService(db).authenticate(raw)
    agent_guard(request, key.id, get_settings().agent_limit)
    return key, account, db


def require_write(key) -> None:
    if not key.can_write:
        raise api_error("FORBIDDEN", "Dieser Key darf nur lesen.")
