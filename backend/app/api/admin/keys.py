from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_admin
from ...core.errors import api_error
from ...db import get_db
from ...services.keys import KeyService

router = APIRouter(prefix="/admin/keys", tags=["admin-keys"])


@router.get("")
async def list_keys(
    account: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    items = await KeyService(db).list_for_account(account)
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("")
async def create_key(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    try:
        days = int(payload.get("expires_in_days") or 30)
    except (TypeError, ValueError):
        raise api_error("VALIDATION", "expires_in_days muss eine Zahl sein.")
    if days < 1 or days > 3650:
        raise api_error("VALIDATION", "expires_in_days muss zwischen 1 und 3650 liegen.")
    return await KeyService(db).create(
        account_id=payload.get("account_id") or "",
        name=payload.get("name") or "",
        expires_in_days=days,
        can_write=bool(payload.get("can_write", False)),
    )


@router.post("/{key_id}/revoke")
async def revoke_key(key_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    return await KeyService(db).revoke(key_id)


@router.post("/{key_id}/rotate")
async def rotate_key(key_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    return await KeyService(db).rotate(key_id)


@router.delete("/{key_id}")
async def delete_key(key_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    return await KeyService(db).revoke(key_id)
