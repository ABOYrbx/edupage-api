"""In-process store for half-finished 2FA logins.

EduPage's ``TwoFactorLogin`` object only exists inside the process that started
the login. Keeping it here (keyed by the hash of the pending token) means the
second step needs neither the password nor a re-fetch of the 2FA page. If the
process restarted in between, :mod:`app.services.account` falls back to
rebuilding it from the stored session cookies.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_pending: dict[str, tuple[float, Any, Any]] = {}


def put(token_hash: str, client: Any, two_factor: Any, ttl_s: int) -> None:
    with _lock:
        _pending[token_hash] = (time.monotonic() + ttl_s, client, two_factor)


def get(token_hash: str) -> tuple[Any, Any] | None:
    with _lock:
        entry = _pending.get(token_hash)
        if entry is None:
            return None
        expires_at, client, two_factor = entry
        if expires_at <= time.monotonic():
            _pending.pop(token_hash, None)
            return None
        return client, two_factor


def drop(token_hash: str) -> None:
    with _lock:
        _pending.pop(token_hash, None)


def clear() -> None:
    with _lock:
        _pending.clear()
