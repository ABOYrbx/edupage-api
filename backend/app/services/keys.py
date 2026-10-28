from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, ApiKey
from ..core.errors import api_error
from ..core.rate_limit import agent_guard
from ..core.time import utcnow

KEY_PREFIX = "epk_"


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def is_key_shaped(raw: str) -> bool:
    return raw.startswith(KEY_PREFIX)


def _public(key: ApiKey) -> dict[str, Any]:
    now = utcnow()
    return {
        "id": key.id,
        "account_id": key.account_id,
        "name": key.name,
        "prefix": key.key_prefix,
        "created_at": key.created_at.isoformat(),
        "expires_at": key.expires_at.isoformat(),
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "can_write": key.can_write,
        "status": "revoked" if key.revoked_at else ("expired" if key.expires_at <= now else "active"),
    }


class KeyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        account_id: str,
        name: str,
        expires_in_days: int = 30,
        can_write: bool = False,
    ) -> dict:
        from ..models import AuditEvent, ApiKey as _ApiKey

        account = await self.db.get(Account, account_id)
        if account is None:
            raise api_error("NOT_FOUND", "Konto nicht gefunden.")
        name = (name or "").strip()[:80]
        if not name:
            raise api_error("VALIDATION", "Name erforderlich.")

        raw = KEY_PREFIX + __import__("secrets").token_urlsafe(32)
        key = _ApiKey(
            account_id=account_id,
            name=name,
            key_hash=hash_key(raw),
            key_prefix=raw[:12],
            expires_at=utcnow() + __import__("datetime").timedelta(days=max(1, int(expires_in_days))),
            can_write=bool(can_write),
        )
        self.db.add(key)
        self.db.add(
            AuditEvent(
                account_id=account_id, actor="admin", action="key.created", outcome="ok", detail=f"name={name}"
            )
        )
        await self.db.commit()
        await self.db.refresh(key)
        payload = _public(key)
        payload["key"] = raw  # shown exactly once
        return payload

    async def list_for_account(self, account_id: str) -> list[dict]:
        from sqlalchemy import select

        res = await self.db.execute(
            select(ApiKey).where(ApiKey.account_id == account_id).order_by(ApiKey.created_at.desc())
        )
        return [_public(key) for key in res.scalars().all()]

    async def get(self, key_id: str) -> ApiKey:
        key = await self.db.get(ApiKey, key_id)
        if key is None:
            raise api_error("NOT_FOUND", "Key nicht gefunden.")
        return key

    async def revoke(self, key_id: str) -> dict:
        from ..models import AuditEvent

        key = await self.get(key_id)
        if key.revoked_at is None:
            key.revoked_at = utcnow()
            self.db.add(
                AuditEvent(
                    account_id=key.account_id,
                    actor="admin",
                    action="key.revoked",
                    outcome="ok",
                    detail=f"prefix={key.key_prefix}",
                )
            )
            await self.db.commit()
        return _public(key)

    async def rotate(self, key_id: str) -> dict:
        from ..models import AuditEvent

        key = await self.get(key_id)
        remaining = (key.expires_at - utcnow()).days
        days = remaining if remaining > 0 else 30
        if key.revoked_at is None:
            key.revoked_at = utcnow()
            self.db.add(
                AuditEvent(
                    account_id=key.account_id,
                    actor="admin",
                    action="key.rotated",
                    outcome="ok",
                    detail=f"prefix={key.key_prefix}",
                )
            )
            await self.db.commit()
        created = await self.create(key.account_id, key.name, days, key.can_write)
        return created

    async def authenticate(self, raw_key: str) -> tuple[ApiKey, Account]:
        from sqlalchemy import select

        raw_key = (raw_key or "").strip()
        if not raw_key:
            raise api_error("TOKEN_INVALID")
        res = await self.db.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(raw_key)))
        key = res.scalar_one_or_none()
        if key is None:
            raise api_error("TOKEN_INVALID")
        if key.revoked_at is not None:
            raise api_error("TOKEN_INVALID", "Key wurde widerrufen.")
        if key.expires_at <= utcnow():
            raise api_error("TOKEN_EXPIRED")
        account = await self.db.get(Account, key.account_id)
        if account is None:
            raise api_error("TOKEN_INVALID", "Konto wurde entfernt.")
        key.last_used_at = utcnow()
        await self.db.commit()
        return key, account


def bearer_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        value = header[7:].strip()
        if value:
            return value
    return None


def safe_filename(name: str, fallback: str = "datei") -> str:
    cleaned = re.sub(r'[\r\n"\\/]', "", name or "").strip()[:120]
    return cleaned or fallback
