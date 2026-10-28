from __future__ import annotations

from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..services.auth_admin import authenticate as auth_admin_session
from ..services.keys import KeyService
from ..services.account import AccountService
from ..core.errors import api_error


async def get_current_admin(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("epa_session")
    if not token:
        raise api_error("TOKEN_INVALID", "Nicht angemeldet.")
    sess = await auth_admin_session(db, token)
    if not sess:
        raise api_error("TOKEN_INVALID", "Session ungültig oder abgelaufen.")
    # CSRF check for state-changing methods
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_cookie = request.cookies.get("epa_csrf")
        csrf_header = request.headers.get("x-csrf-token")
        if not csrf_cookie or csrf_cookie != sess.csrf_token or csrf_cookie != csrf_header:
            raise api_error("FORBIDDEN", "CSRF-Token ungültig.")
    return sess


async def get_api_key_account(request: Request, db: AsyncSession = Depends(get_db)):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        # allow ?token= for attachments
        tok = request.query_params.get("token")
        if not tok:
            raise api_error("TOKEN_INVALID")
        raw = tok
    else:
        raw = auth.split(" ", 1)[1].strip()
    ks = KeyService(db)
    key, account = await ks.authenticate(raw)
    from ..core.rate_limit import agent_guard, client_ip
    agent_guard(request, key.id)
    return key, account, db
