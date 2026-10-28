from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services.auth_admin import login
from ...core.rate_limit import admin_login_guard, client_ip
from ...core.errors import api_error
from ...config import get_settings

router = APIRouter(prefix="/admin", tags=["admin-auth"])


@router.post("/login")
async def admin_login(payload: dict, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    admin_login_guard(request, get_settings().admin_login_limit)
    username = payload.get("username") or get_settings().admin_username
    password = payload.get("password", "")
    res = await login(db, username, password)
    if not res:
        raise api_error("BAD_CREDENTIALS")
    token, csrf = res
    cookie_opts = {"httponly": True, "secure": False, "samesite": "lax", "path": "/"}
    response.set_cookie("epa_session", token, max_age=8 * 3600, **cookie_opts)
    response.set_cookie("epa_csrf", csrf, max_age=8 * 3600, httponly=False, secure=False, samesite="lax", path="/")
    return {"status": "ok", "username": username}
