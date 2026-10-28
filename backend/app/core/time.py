from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp (what the DB columns store), without the utcnow() deprecation."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
