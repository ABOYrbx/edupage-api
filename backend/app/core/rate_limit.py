from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, HTTPException

from .errors import api_error


class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: int) -> None:
        now = time.time()
        q = self._buckets[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            raise api_error("RATE_LIMITED")
        q.append(now)


_limiter = RateLimiter()


def reset() -> None:
    """Drop all buckets (used by tests)."""
    _limiter._buckets.clear()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def admin_login_guard(request: Request, limit_str: str = "20/10minute") -> None:
    # parse "20/10minute"
    parts = limit_str.split("/")
    n = int(parts[0])
    w = parts[1]
    if w.endswith("minute"):
        mins = int(w.replace("minute", "") or "1")
        window = mins * 60
    elif w.endswith("second"):
        secs = int(w.replace("second", "") or "1")
        window = secs
    else:
        window = 600
    _limiter.check(f"admin_login:{client_ip(request)}", n, window)


def agent_guard(request: Request, key_id: str, limit_str: str = "120/minute") -> None:
    parts = limit_str.split("/")
    n = int(parts[0])
    w = parts[1]
    window = 60 if w.endswith("minute") else 1
    if w.endswith("minute"):
        window = int(w.replace("minute", "") or "1") * 60
    _limiter.check(f"agent:{key_id}", n, window)
