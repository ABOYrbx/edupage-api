from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_events(self, account_id: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[AuditEvent], int]:
        q = select(AuditEvent)
        if account_id:
            q = q.where(AuditEvent.account_id == account_id)
        q = q.order_by(AuditEvent.created_at.desc())
        res = await self.db.execute(q)
        all_items = list(res.scalars().all())
        total = len(all_items)
        return all_items[offset:offset + limit], total

    async def record(self, account_id: str | None, actor: str, action: str, outcome: str, detail: str | None = None) -> None:
        self.db.add(AuditEvent(account_id=account_id, actor=actor, action=action, outcome=outcome, detail=detail))
        await self.db.commit()
