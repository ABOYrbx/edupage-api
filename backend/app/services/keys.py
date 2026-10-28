from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApiKey, Account, AuditEvent
from ..core.errors import api_error


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class KeyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, account_id: str, name: str, expires_in_days: int = 30, can_write: bool = False) -> dict:
        res = await self.db.execute(select(Account).where(Account.id == account_id))
        account = res.scalar_one_or_none()
        if not account:
            raise api_error("NOT_FOUND")
        raw = "epk_" + secrets.token_urlsafe(32)
        kh = hash_key(raw)
        prefix = raw[:12]
        key = ApiKey(
            account_id=account_id,
            name=name.strip()[:80] or "Unnamed",
            key_hash=kh,
            key_prefix=prefix,
            expires_at=datetime.utcnow() + timedelta(days=max(1, expires_in_days)),
            can_write=can_write,
        )
        self.db.add(key)
        await self.db.flush()
        self.db.add(AuditEvent(account_id=account_id, actor="admin", action="key.created", outcome="ok", detail=f"name={key.name}"))
        await self.db.commit()
        await self.db.refresh(key)
        return {
            "id": key.id,
            "name": key.name,
            "key": raw,
            "prefix": key.key_prefix,
            "expires_at": key.expires_at.isoformat(),
            "can_write": key.can_write,
        }

    async def list_for_account(self, account_id: str) -> list[dict]:
        res = await self.db.execute(select(ApiKey).where(ApiKey.account_id == account_id).order_by(ApiKey.created_at.desc()))
        out = []
        for k in res.scalars().all():
            out.append({
                "id": k.id,
                "name": k.name,
                "prefix": k.key_prefix,
                "created_at": k.created_at.isoformat(),
                "expires_at": k.expires_at.isoformat(),
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "can_write": k.can_write,
                "active": k.revoked_at is None and k.expires_at > datetime.utcnow(),
            })
        return out

    async def revoke(self, key_id: str) -> None:
        res = await self.db.execute(select(ApiKey).where(ApiKey.id == key_id))
        k = res.scalar_one_or_none()
        if not k:
            raise api_error("NOT_FOUND")
        if k.revoked_at is None:
            k.revoked_at = datetime.utcnow()
            self.db.add(AuditEvent(account_id=k.account_id, actor="admin", action="key.revoked", outcome="ok", detail=f"prefix={k.key_prefix}"))
            await self.db.commit()

    async def rotate(self, key_id: str) -> dict:
        res = await self.db.execute(select(ApiKey).where(ApiKey.id == key_id))
        k = res.scalar_one_or_none()
        if not k:
            raise api_error("NOT_FOUND")
        # revoke old
        if k.revoked_at is None:
            k.revoked_at = datetime.utcnow()
        # create new with same params
        days = max(1, (k.expires_at - k.created_at).days or 30)
        await self.db.commit()
        return await self.create(k.account_id, k.name, days, k.can_write)

    async def authenticate(self, raw_key: str) -> tuple[ApiKey, Account]:
        kh = hash_key(raw_key)
        res = await self.db.execute(select(ApiKey).where(ApiKey.key_hash == kh))
        key = res.scalar_one_or_none()
        if not key or key.revoked_at is not None or key.expires_at <= datetime.utcnow():
            raise api_error("TOKEN_INVALID")
        # load account
        res = await self.db.execute(select(Account).where(Account.id == key.account_id))
        account = res.scalar_one_or_none()
        if not account:
            raise api_error("TOKEN_INVALID")
        key.last_used_at = datetime.utcnow()
        await self.db.commit()
        return key, account
