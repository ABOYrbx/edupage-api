from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_admin
from ...config import get_settings as load_settings
from ...core.pagination import parse_page
from ...db import get_db
from ...services.audit import AuditService
from ...services.auth_admin import revoke
from ...services.cache import CacheService

router = APIRouter(prefix="/admin", tags=["admin-system"])


@router.get("/me")
async def me(session=Depends(get_current_admin)):
    return {"username": session.username}


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    token = request.cookies.get("epa_session")
    if token:
        await revoke(db, token)
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("epa_session", path="/")
    response.delete_cookie("epa_csrf", path="/")
    return response


@router.get("/activity")
async def activity(
    account: str | None = None,
    action: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    lim, off = parse_page(limit, offset)
    items, total = await AuditService(db).list_events(account, action, lim, off)
    return {"items": items, "total": total, "limit": lim, "offset": off}


@router.post("/cache-clear")
async def cache_clear(payload: dict | None = None, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    account_id = (payload or {}).get("account_id")
    cleared = await CacheService(db).clear(account_id)
    return {"cleared": cleared}


@router.get("/settings")
async def get_settings_view(_=Depends(get_current_admin)):
    settings = load_settings()
    return {
        "values": {
            "cache_ttl_messages": settings.cache_ttl_messages,
            "cache_ttl_grades": settings.cache_ttl_grades,
            "cache_ttl_timetable": settings.cache_ttl_timetable,
            "cache_ttl_weather": settings.cache_ttl_weather,
            "session_cache_ttl": settings.session_cache_ttl,
            "admin_login_limit": settings.admin_login_limit,
            "agent_limit": settings.agent_limit,
        },
        "features": {
            "weather": bool(settings.openweather_api_key.strip()),
            "secure_cookies": settings.cookie_secure,
        },
        "editable": False,
        "note": "Diese Werte kommen aus der .env und werden beim Start gelesen.",
    }
