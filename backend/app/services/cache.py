from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ResourceCache
from cachetools import TTLCache


class CacheService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._mem: TTLCache = TTLCache(maxsize=256, ttl=60)

    def mem_get(self, key: str):
        return self._mem.get(key)

    def mem_set(self, key: str, value):
        self._mem[key] = value

    async def get(self, account_id: str, cache_key: str) -> dict | None:
        res = await self.db.execute(
            select(ResourceCache).where(ResourceCache.account_id == account_id, ResourceCache.cache_key == cache_key)
        )
        row = res.scalar_one_or_none()
        if not row:
            return None
        if row.expires_at <= datetime.utcnow():
            return None
        return row.payload if isinstance(row.payload, dict) else json.loads(row.payload)

    async def set(self, account_id: str, cache_key: str, payload: dict, ttl_s: int) -> None:
        res = await self.db.execute(
            select(ResourceCache).where(ResourceCache.account_id == account_id, ResourceCache.cache_key == cache_key)
        )
        row = res.scalar_one_or_none()
        expires = datetime.utcnow() + timedelta(seconds=ttl_s)
        if row:
            row.payload = payload
            row.expires_at = expires
        else:
            self.db.add(ResourceCache(account_id=account_id, cache_key=cache_key, payload=payload, expires_at=expires))
        await self.db.commit()

    async def clear(self, account_id: str | None = None) -> int:
        q = delete(ResourceCache)
        if account_id:
            q = q.where(ResourceCache.account_id == account_id)
        res = await self.db.execute(q)
        await self.db.commit()
        return res.rowcount or 0
