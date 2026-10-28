from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent


def _event_dict(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "account_id": event.account_id,
        "actor": event.actor,
        "action": event.action,
        "outcome": event.outcome,
        "detail": event.detail,
        "created_at": event.created_at.isoformat(),
    }


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_events(
        self,
        account_id: str | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conditions = []
        if account_id:
            conditions.append(AuditEvent.account_id == account_id)
        if action:
            conditions.append(AuditEvent.action == action)

        total = await self.db.scalar(
            select(func.count()).select_from(AuditEvent).where(*conditions)
        )
        res = await self.db.execute(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_event_dict(event) for event in res.scalars().all()], int(total or 0)

    async def record(
        self,
        account_id: str | None,
        actor: str,
        action: str,
        outcome: str,
        detail: str | None = None,
    ) -> None:
        self.db.add(
            AuditEvent(
                account_id=account_id,
                actor=actor,
                action=action,
                outcome=outcome,
                detail=detail,
            )
        )
        await self.db.commit()
