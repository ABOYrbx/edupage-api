from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services.keys import KeyService
from ...api.deps import get_current_admin

router = APIRouter(prefix="/admin/keys", tags=["admin-keys"])


@router.get("")
async def list_keys(account: str = Query(...), db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    ks = KeyService(db)
    return {"items": await ks.list_for_account(account)}


@router.post("")
async def create_key(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    ks = KeyService(db)
    account_id = payload.get("account_id")
    name = payload.get("name", "")
    days = int(payload.get("expires_in_days", 30) or 30)
    can_write = bool(payload.get("can_write", False))
    if not account_id or not name:
        from ...core.errors import api_error
        raise api_error("VALIDATION", "account_id und name erforderlich.")
    return await ks.create(account_id, name, days, can_write)


@router.post("/{key_id}/revoke")
async def revoke_key(key_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    ks = KeyService(db)
    await ks.revoke(key_id)
    return {"status": "ok"}


@router.post("/{key_id}/rotate")
async def rotate_key(key_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    ks = KeyService(db)
    return await ks.rotate(key_id)
