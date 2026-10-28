"""Short-lived download tokens.

An attachment URL must be fetchable by a browser/agent without handing out the
API key (or a Bearer header). Tokens are opaque, single-purpose and bound to
``(account, event, index)``; they expire after five minutes.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import api_error
from ..models import ResourceCache
from ..core.time import utcnow

PREFIX = "dl:"
TTL_S = 300


def _cache_key(token: str) -> str:
    return PREFIX + hashlib.sha256(token.encode()).hexdigest()


class DownloadTokens:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue(self, account_id: str, event_id: int, idx: int) -> tuple[str, int]:
        raw = secrets.token_urlsafe(24)
        await self.db.execute(
            delete(ResourceCache).where(
                ResourceCache.cache_key.like(PREFIX + "%"),
                ResourceCache.expires_at <= utcnow(),
            )
        )
        self.db.add(
            ResourceCache(
                account_id=account_id,
                cache_key=_cache_key(raw),
                payload={"event_id": event_id, "idx": idx},
                expires_at=utcnow() + timedelta(seconds=TTL_S),
            )
        )
        await self.db.commit()
        return raw, TTL_S

    async def resolve(self, token: str, account_id: str, event_id: int, idx: int) -> None:
        res = await self.db.execute(
            select(ResourceCache).where(ResourceCache.cache_key == _cache_key(token))
        )
        row = res.scalar_one_or_none()
        if row is None or row.expires_at <= utcnow():
            raise api_error("TOKEN_INVALID", "Download-Token ungültig oder abgelaufen.")
        payload = row.payload or {}
        if (
            row.account_id != account_id
            or payload.get("event_id") != event_id
            or payload.get("idx") != idx
        ):
            raise api_error("TOKEN_INVALID", "Download-Token passt nicht zu diesem Anhang.")
