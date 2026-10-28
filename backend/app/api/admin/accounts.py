from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_admin
from ...core.errors import api_error
from ...db import get_db
from ...services.account import AccountService
from ...services.keys import KeyService

router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])


@router.get("")
async def list_accounts(db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    items = await AccountService(db).list_accounts()
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("")
async def add_account(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    return await AccountService(db).add(
        alias=payload.get("alias"),
        subdomain=payload.get("subdomain") or "login1",
        username=payload.get("username") or "",
        password=payload.get("password") or "",
    )


@router.post("/2fa")
async def finish_2fa(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    pending = payload.get("pending_token")
    code = payload.get("code")
    if not pending or not code:
        raise api_error("VALIDATION", "pending_token und code erforderlich.")
    return await AccountService(db).finish_2fa(pending, code)


@router.get("/{account_id}")
async def get_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    service = AccountService(db)
    account = await service.get(account_id)
    if account is None:
        raise api_error("NOT_FOUND")
    data = await service.list_accounts()
    match = next((item for item in data if item["id"] == account_id), None)
    if match is None:
        raise api_error("NOT_FOUND")
    return {**match, "keys": await KeyService(db).list_for_account(account_id)}


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    await AccountService(db).delete(account_id)
    return {"status": "ok"}


@router.post("/{account_id}/test")
async def test_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    return await AccountService(db).test_account(account_id)


@router.post("/{account_id}/refresh")
async def refresh_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    return await AccountService(db).refresh(account_id)
