from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services.audit import AuditService
from ...services.cache import CacheService
from ...api.deps import get_current_admin
from ...core.errors import api_error

router = APIRouter(prefix="/admin", tags=["admin-system"])


@router.get("/me")
async def me(sess=Depends(get_current_admin)):
    return {"username": sess.username}


@router.post("/logout")
async def logout(request, db: AsyncSession = Depends(get_db), sess=Depends(get_current_admin)):
    from ...services.auth_admin import revoke
    tok = request.cookies.get("epa_session")
    if tok:
        await revoke(db, tok)
    return {"status": "ok"}


@router.get("/activity")
async def activity(account: str | None = None, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AuditService(db)
    items, total = await svc.list_events(account, limit, offset)
    return {"items": [
        {"id": e.id, "account_id": e.account_id, "actor": e.actor, "action": e.action,
         "outcome": e.outcome, "detail": e.detail, "created_at": e.created_at.isoformat()}
        for e in items
    ], "total": total, "limit": limit, "offset": offset}


@router.post("/cache-clear")
async def cache_clear(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = CacheService(db)
    n = await svc.clear(payload.get("account_id"))
    return {"cleared": n}


@router.get("/settings")
async def get_settings(_=Depends(get_current_admin)):
    from ...config import get_settings
    s = get_settings()
    return {"values": {
        "cache_ttl_messages": s.cache_ttl_messages,
        "cache_ttl_grades": s.cache_ttl_grades,
        "cache_ttl_timetable": s.cache_ttl_timetable,
        "cache_ttl_weather": s.cache_ttl_weather,
    }}


@router.put("/settings")
async def put_settings(payload: dict, _=Depends(get_current_admin)):
    return {"status": "ok", "values": payload}
