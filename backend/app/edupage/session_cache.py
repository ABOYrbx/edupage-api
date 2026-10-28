"""In-memory cache of logged-in EduPage clients.

Logging in is by far the most expensive call we make, so an account's client is
kept for a short while and reused. Entries expire silently; callers fall back to
a fresh login whenever :func:`get` returns ``None``.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_sessions: dict[str, tuple[float, Any]] = {}


def get(account_id: str) -> Any | None:
    with _lock:
        entry = _sessions.get(account_id)
        if entry is None:
            return None
        expires_at, client = entry
        if expires_at <= time.monotonic():
            _sessions.pop(account_id, None)
            return None
        return client


def put(account_id: str, client: Any, ttl_s: int) -> None:
    with _lock:
        _sessions[account_id] = (time.monotonic() + ttl_s, client)


def drop(account_id: str) -> None:
    with _lock:
        _sessions.pop(account_id, None)


def clear() -> None:
    with _lock:
        _sessions.clear()
