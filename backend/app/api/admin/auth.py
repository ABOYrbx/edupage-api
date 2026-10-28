from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...core.errors import api_error
from ...core.rate_limit import admin_login_guard
from ...db import get_db
from ...services.auth_admin import login

router = APIRouter(prefix="/admin", tags=["admin-auth"])

SESSION_MAX_AGE = 8 * 3600


@router.post("/login")
async def admin_login(
    payload: dict,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    admin_login_guard(request, settings.admin_login_limit)
    username = (payload.get("username") or settings.admin_username or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise api_error("VALIDATION", "Benutzername und Passwort erforderlich.")

    result = await login(db, username, password)
    if result is None:
        raise api_error("BAD_CREDENTIALS")
    token, csrf = result
    common = {
        "path": "/",
        "max_age": SESSION_MAX_AGE,
        "samesite": "lax",
        "secure": settings.cookie_secure,
    }
    response.set_cookie("epa_session", token, httponly=True, **common)
    response.set_cookie("epa_csrf", csrf, httponly=False, **common)
    return {"status": "ok", "username": username}
