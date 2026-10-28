from __future__ import annotations

import json
from datetime import datetime, timedelta

from cachetools import TTLCache
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ResourceCache
from ..core.time import utcnow

# Shared process-wide hot cache; DB is the durable layer below it.
_memory: TTLCache = TTLCache(maxsize=1024, ttl=300)


class CacheService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def mem_get(self, key: str):
        return _memory.get(key)

    def mem_set(self, key: str, value) -> None:
        _memory[key] = value

    @staticmethod
    def mem_clear(prefix: str | None = None) -> None:
        if prefix is None:
            _memory.clear()
            return
        for key in [k for k in _memory if k.startswith(prefix)]:
            _memory.pop(key, None)

    async def get(self, account_id: str, cache_key: str) -> dict | None:
        res = await self.db.execute(
            select(ResourceCache).where(
                ResourceCache.account_id == account_id,
                ResourceCache.cache_key == cache_key,
            )
        )
        row = res.scalar_one_or_none()
        if row is None or row.expires_at <= utcnow():
            return None
        return row.payload if isinstance(row.payload, dict) else json.loads(row.payload)

    async def set(self, account_id: str, cache_key: str, payload: dict, ttl_s: int) -> None:
        res = await self.db.execute(
            select(ResourceCache).where(
                ResourceCache.account_id == account_id,
                ResourceCache.cache_key == cache_key,
            )
        )
        row = res.scalar_one_or_none()
        expires = utcnow() + timedelta(seconds=ttl_s)
        if row is None:
            self.db.add(
                ResourceCache(
                    account_id=account_id,
                    cache_key=cache_key,
                    payload=payload,
                    expires_at=expires,
                )
            )
        else:
            row.payload = payload
            row.expires_at = expires
        await self.db.commit()

    async def clear(self, account_id: str | None = None) -> int:
        condition = delete(ResourceCache)
        if account_id:
            condition = condition.where(ResourceCache.account_id == account_id)
            self.mem_clear(f"{account_id}:")
        else:
            self.mem_clear()
        result = await self.db.execute(condition)
        await self.db.commit()
        return result.rowcount or 0
