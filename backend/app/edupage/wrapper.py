from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Any

from ..core.errors import api_error

try:
    from edupage_api import Edupage
    from edupage_api.exceptions import (
        BadCredentialsException, CaptchaException, SecondFactorFailedException,
        MissingDataException, RequestError,
    )
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False


def _to_iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _serialize(obj) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    # dataclass
    if hasattr(obj, "__dataclass_fields__"):
        out = {}
        for f in obj.__dataclass_fields__:
            out[f] = _serialize(getattr(obj, f))
        return out
    # fallback
    if hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


class EduPageWrapper:
    """Thin async wrapper around the synchronous edupage-api library."""

    def __init__(self, account_row, password: str):
        self.account = account_row
        self.password = password
        self._ep = None

    async def login(self):
        if not _AVAILABLE:
            raise api_error("CONFIG_MISSING")
        loop = asyncio.get_event_loop()
        def _do():
            ep = Edupage()
            tf = ep.login(self.account.username, self.password, self.account.subdomain)
            if tf is not None:
                raise api_error("EDUPAGE_2FA")
            return ep
        self._ep = await loop.run_in_executor(None, _do)
        return self._ep

    async def ensure(self):
        if self._ep is None:
            await self.login()
        return self._ep

    async def call(self, fn, *a, **kw):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            return fn(ep, *a, **kw)
        try:
            return await loop.run_in_executor(None, _do)
        except BadCredentialsException:
            raise api_error("BAD_CREDENTIALS")
        except CaptchaException:
            raise api_error("CAPTCHA_REQUIRED")
        except Exception as e:
            raise api_error("UPSTREAM", str(e))

    async def messages(self, since: str | None = None, limit: int = 50, offset: int = 0):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            events = ep.timeline.get_notifications_history(__import__("datetime").date.fromisoformat(since)) if since else ep.timeline.get_notifications()
            return events
        try:
            events = await loop.run_in_executor(None, _do)
        except Exception as e:
            raise api_error("UPSTREAM", str(e))
        items = []
        for ev in (events or []):
            d = _serialize(ev)
            # filter top-level messages only (no replies)
            items.append(d)
        return items

    async def recipients(self):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            return ep.people.get_teachers() or []
        res = await loop.run_in_executor(None, _do)
        return [_serialize(x) for x in res]

    async def homework(self):
        ep = await self.ensure()
        # edupage lib has no dedicated homework fetcher beyond timeline events (HOMEWORK type)
        loop = asyncio.get_event_loop()
        def _do():
            return ep.timeline.get_notifications()
        events = await loop.run_in_executor(None, _do)
        items = []
        for ev in (events or []):
            if getattr(ev, "event_type", None) and str(ev.event_type) == "homework":
                items.append(_serialize(ev))
        return items

    async def timetable_day(self, d: str):
        ep = await self.ensure()
        from datetime import date as _date
        dd = _date.fromisoformat(d)
        loop = asyncio.get_event_loop()
        def _do():
            return ep.timetables.get_my_timetable(dd)
        tt = await loop.run_in_executor(None, _do)
        return _serialize(tt)

    async def timetable_week(self, d: str):
        # fetch 7 days
        from datetime import date as _date, timedelta
        start = _date.fromisoformat(d)
        out = []
        for i in range(7):
            dd = start + timedelta(days=i)
            try:
                tt = await self.timetable_day(dd.isoformat())
            except Exception:
                tt = None
            out.append({"date": dd.isoformat(), "timetable": tt})
        return out

    async def substitutions(self, d: str):
        ep = await self.ensure()
        from datetime import date as _date
        dd = _date.fromisoformat(d)
        loop = asyncio.get_event_loop()
        def _do():
            return ep.substitution.get_timetable_changes(dd)
        res = await loop.run_in_executor(None, _do)
        return [_serialize(x) for x in (res or [])]

    async def agenda(self):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            return ep.timeline.get_notifications()
        events = await loop.run_in_executor(None, _do)
        return [_serialize(x) for x in (events or [])]

    async def grades(self):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            return ep.get_grades()
        res = await loop.run_in_executor(None, _do)
        return [_serialize(x) for x in (res or [])]

    async def weather(self, city: str | None = None):
        # Not in edupage lib; return stub
        return {"city": city, "note": "Wetter wird über eduflow-Parität nicht von edupage-api bereitgestellt"}

    async def search_cities(self, q: str):
        return []

    async def settings_get(self):
        ep = await self.ensure()
        data = getattr(ep, "data", None)
        return {"values": data or {}}

    async def send_message(self, recipients, body):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            return ep.send_message(recipients, body)
        return await loop.run_in_executor(None, _do)

    async def text_grades(self):
        ep = await self.ensure()
        loop = asyncio.get_event_loop()
        def _do():
            return ep.get_text_grades(None, None)
        res = await loop.run_in_executor(None, _do)
        return [_serialize(x) for x in (res or [])]
