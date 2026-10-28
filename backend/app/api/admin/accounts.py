from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services.account import AccountService
from ...api.deps import get_current_admin
from ...core.errors import api_error
from ...core.rate_limit import admin_login_guard

router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])


@router.get("")
async def list_accounts(db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    items = await svc.list_accounts()
    return {"items": [svc._account_dict(a) for a in items], "total": len(items)}


@router.post("")
async def add_account(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    alias = payload.get("alias")
    subdomain = payload.get("subdomain", "login1")
    username = payload.get("username", "")
    password = payload.get("password", "")
    if not username or not password:
        raise api_error("VALIDATION", "Benutzername und Passwort erforderlich.")
    return await svc.add(alias, subdomain, username, password)


@router.post("/2fa")
async def finish_2fa(payload: dict, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    pt = payload.get("pending_token")
    code = payload.get("code")
    if not pt or not code:
        raise api_error("VALIDATION")
    return await svc.finish_2fa(pt, code)


@router.get("/{account_id}")
async def get_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    a = await svc.get(account_id)
    if not a:
        raise api_error("NOT_FOUND")
    return svc._account_dict(a)


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    a = await svc.get(account_id)
    if not a:
        raise api_error("NOT_FOUND")
    await svc.delete(account_id)
    return {"status": "ok"}


@router.post("/{account_id}/test")
async def test_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    return await svc.test_account(account_id)


@router.post("/{account_id}/refresh")
async def refresh_account(account_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_admin)):
    svc = AccountService(db)
    return await svc.refresh(account_id)
