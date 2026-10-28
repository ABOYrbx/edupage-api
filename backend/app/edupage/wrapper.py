"""Async facade over the synchronous ``edupage-api`` library.

All EduPage traffic goes through here. The underlying library is blocking, so
calls run in a worker thread. A logged-in client is memoised per account for
``SESSION_CACHE_TTL`` seconds (see :mod:`app.edupage.session_cache`).
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlparse

from ..config import get_settings
from ..core.errors import api_error
from . import serializers as ser
from . import session_cache
from .provider import LIBRARY_AVAILABLE, new_client
from .serializers import _serialize  # noqa: F401  (re-exported for convenience)

DOWNLOAD_TTL_S = 300


def _parse_date(value: str | None, *, required: bool = False) -> date:
    if not value:
        if required:
            raise api_error("VALIDATION", "Datum erforderlich (YYYY-MM-DD).")
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise api_error("VALIDATION", "Datum muss YYYY-MM-DD sein.")


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "ja", "y", "on"):
        return True
    if text in ("0", "false", "no", "nein", "n", "off"):
        return False
    raise api_error("VALIDATION", f"Ungültiger Wahrheitswert: {value}")


class EduPageWrapper:
    """One wrapper per account; ``ensure()`` yields a logged-in client."""

    def __init__(self, account, password: str):
        self.account = account
        self.password = password
        self._ep = None

    # ------------------------------------------------------------------ login

    async def login(self):
        if not LIBRARY_AVAILABLE:
            raise api_error("CONFIG_MISSING", "edupage-api Bibliothek nicht installiert.")

        def _do():
            client = new_client()
            two_factor = client.login(self.account.username, self.password, self.account.subdomain)
            if two_factor is not None:
                raise api_error("EDUPAGE_2FA")
            return client

        self._ep = await _run(_do, "Login")
        session_cache.put(
            self.account.id, self._ep, get_settings().session_cache_ttl
        )
        return self._ep

    async def ensure(self):
        if self._ep is None:
            cached = session_cache.get(self.account.id)
            self._ep = cached if cached is not None else await self.login()
        return self._ep

    async def call(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        client = await self.ensure()
        return await _run(lambda: fn(client, *args, **kwargs), "Anfrage")

    # --------------------------------------------------------------- messages

    async def timeline(self, since: str | None = None) -> list[Any]:
        def _do(client):
            if since:
                return client.get_notification_history(_parse_date(since))
            return client.get_notifications()

        return list(await self.call(_do) or [])

    async def events(self, since: str | None = None) -> list[dict]:
        return [ser.event_to_dict(event) for event in await self.timeline(since)]

    async def messages(
        self,
        since: str | None = None,
        type_: str | None = None,
        q: str | None = None,
        include_replies: bool = True,
    ) -> list[dict]:
        items = []
        for event in await self.timeline(since):
            event_type = ser._event_type(event)
            if not include_replies and getattr(event, "response_to", None) is not None:
                continue
            if type_ and event_type != type_:
                continue
            if q:
                needle = q.strip().lower()
                haystack = f"{ser.event_text(event)} {ser.event_extra_json(event)}".lower()
                if needle not in haystack:
                    continue
            items.append(ser.event_to_dict(event))
        return items

    async def thread(self, event_id: int) -> dict:
        events = await self.timeline()
        target = None
        replies = []
        for event in events:
            if getattr(event, "event_id", None) == event_id:
                target = event
            group_id = getattr(event, "other_id", None) if ser._event_type(event) == "chat" else None
            if getattr(event, "response_to", None) == event_id or group_id == event_id:
                replies.append(event)
        if target is None and not replies:
            raise api_error("NOT_FOUND", "Nachricht nicht gefunden.")
        replies.sort(key=lambda e: getattr(e, "timestamp", datetime.min))
        return {
            "event": ser.event_to_dict(target) if target else None,
            "replies": [ser.event_to_dict(reply) for reply in replies],
        }

    async def mark_messages_read(self, event_ids: list[int] | None = None) -> int:
        client = await self.ensure()

        def _do():
            import hashlib

            from edupage_api.compression import RequestData

            payload = RequestData.encode_request_body(
                {
                    "lastItemId": json.dumps(event_ids or []),
                    "typ": "sprava",
                }
            )
            url = f"https://{client.subdomain}.edupage.org/timeline/?akcia=readItems"
            response = client.session.post(
                url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            return response.status_code == 200

        await _run(_do, "Nachrichten als gelesen markieren")
        return len(event_ids or [])

    async def recipients(self) -> list[dict]:
        def _do(client):
            people = []
            for getter in ("get_teachers", "get_students"):
                fn = getattr(client, getter, None)
                if fn is None:
                    continue
                try:
                    people.extend(fn() or [])
                except Exception:  # noqa: BLE001 - one list failing must not break the other
                    continue
            return people

        return [_recipient_dict(person) for person in await self.call(_do)]

    async def send_message(self, recipients: list[str] | str, body: str) -> int:
        if isinstance(recipients, str):
            recipients = [recipients]
        recipients = [r for r in recipients if isinstance(r, str) and r.strip()]
        if not recipients:
            raise api_error("VALIDATION", "Mindestens ein Empfänger erforderlich.")
        if not body.strip():
            raise api_error("VALIDATION", "Nachrichtentext fehlt.")
        sent = await self.call(lambda client: client.send_message(recipients, body))
        return int(sent or 0)

    async def reply(self, event_id: int, body: str) -> dict:
        if not body.strip():
            raise api_error("VALIDATION", "Nachrichtentext fehlt.")
        return await self._timeline_action(
            "createReply",
            {"groupid": str(event_id), "recipient": "", "text": body,
             "moredata": json.dumps({"attachements": {}})},
        )

    # --------------------------------------------------------------- homework

    async def homework(
        self,
        since: str | None = None,
        status: str = "alle",
        include_tests: bool = False,
        q: str | None = None,
    ) -> tuple[list[dict], dict]:
        events = await self.timeline(since)
        wanted = set(ser.HOMEWORK_TYPES + (ser.EXAM_TYPES if include_tests else ()))
        items = [ser.homework_to_dict(e) for e in events if ser._event_type(e) in wanted]
        items = ser.sort_homework(items)

        counts = {
            "offen": sum(1 for i in items if i["status"] in ("offen", "heute fällig", "ohne Datum")),
            "ueberfaellig": sum(1 for i in items if i["status"] == "überfällig"),
            "erledigt": sum(1 for i in items if i["status"] == "erledigt"),
        }
        if status != "alle":
            items = [i for i in items if i["status"] == status]
        if q:
            needle = q.strip().lower()
            items = [
                i for i in items
                if needle in " ".join(
                    str(i.get(key, "")) for key in ("title", "subject", "author", "description", "type_label")
                ).lower()
            ]
        return items, counts

    async def set_homework_done(self, event_id: int, done: bool) -> dict:
        return await self._timeline_action(
            "homeworkFlag",
            {"homeworkid": f"timeline:{event_id}", "flag": "done", "value": "1" if done else "0"},
        )

    async def attachment_meta(self, event_id: int, idx: int) -> dict:
        """Resolve an attachment without downloading it (used to mint tokens)."""
        client = await self.ensure()
        events = await self.timeline()
        event = next((e for e in events if getattr(e, "event_id", None) == event_id), None)
        if event is None:
            raise api_error("NOT_FOUND", "Nachricht nicht gefunden.")
        attachments = ser.extract_attachments(getattr(event, "additional_data", None))
        if idx < 0 or idx >= len(attachments):
            raise api_error("NOT_FOUND", "Anhang nicht gefunden.")
        attachment = attachments[idx]
        url = attachment["url"]
        if url.startswith("/"):
            url = f"https://{client.subdomain}.edupage.org{url}"
        if not (urlparse(url).hostname or "").lower().endswith(".edupage.org"):
            raise api_error("VALIDATION", "Ungültiger Anhang-Link.")
        return {**attachment, "url": url}

    # -------------------------------------------------------------- timetable

    async def timetable_day(self, day: str | None = None) -> dict:
        target = _parse_date(day)
        timetable = await self.call(lambda client: client.get_my_timetable(target))
        return {
            "date": target.isoformat(),
            "lessons": [
                ser._serialize(lesson)
                for lesson in (getattr(timetable, "lessons", None) or [])
            ],
        }

    async def timetable_week(self, day: str | None = None) -> list[dict]:
        start = _parse_date(day)
        out = []
        for offset in range(7):
            current = start + timedelta(days=offset)
            if current.weekday() >= 5:  # weekends carry no lessons
                out.append({"date": current.isoformat(), "lessons": []})
                continue
            try:
                out.append(await self.timetable_day(current.isoformat()))
            except Exception as exc:  # noqa: BLE001 - a bad day must not kill the week
                out.append({"date": current.isoformat(), "lessons": [], "error": str(exc)})
        return out

    async def substitutions(self, day: str | None = None) -> list[dict]:
        target = _parse_date(day)
        changes = await self.call(lambda client: client.get_timetable_changes(target))
        return [ser.change_to_dict(change) for change in changes or []]

    # ----------------------------------------------------------------- grades

    async def grades(self) -> list[dict]:
        raw = await self.call(lambda client: _grades_with_id_fix(client))
        return [ser.grade_to_dict(grade) for grade in raw or []]

    async def text_grades(self) -> list[dict]:
        raw = await self.call(lambda client: client.get_text_grades())
        return [ser.grade_to_dict(grade) for grade in raw or []]

    # ------------------------------------------------------------------ mensa

    async def lunches(self, day: str | None = None) -> dict:
        from edupage_api.lunches import Meals

        target = _parse_date(day)
        meals: Meals | None = await self.call(
            lambda client: client.get_meals(target)
        )
        return {
            "date": target.isoformat(),
            "snack": _meal_to_dict(getattr(meals, "snack", None)),
            "lunch": _meal_to_dict(getattr(meals, "lunch", None)),
            "afternoon_snack": _meal_to_dict(getattr(meals, "afternoon_snack", None)),
        }

    # ------------------------------------------------------------------ misc

    async def agenda(self) -> list[dict]:
        events = await self.timeline()
        wanted = {
            "event", "schoolevent", "trip", "excursion", "culture", "meeting", "parentsevening",
            "freeday", "holiday", "sholiday", "contest", "signin", "bmeeting", "ctevent",
        }
        return [ser.event_to_dict(event) for event in events if ser._event_type(event) in wanted]

    async def settings(self) -> dict:
        client = await self.ensure()
        data = getattr(client, "data", None)
        if not isinstance(data, dict):
            return {"user": {}, "school": None, "subdomain": getattr(client, "subdomain", None)}
        return {
            "user": {
                key: ser._serialize(data.get(key))
                for key in ("userid", "user_meno", "user_type", "schoolyear", "child")
                if key in data
            },
            "school": data.get("skola") or None,
            "subdomain": getattr(client, "subdomain", None),
            "username": getattr(client, "username", None),
        }

    async def download_attachment(self, event_id: int, idx: int) -> dict:
        client = await self.ensure()
        attachment = await self.attachment_meta(event_id, idx)
        url = attachment["url"]

        def _do():
            response = client.session.get(url, stream=True)
            if response.status_code != 200:
                raise api_error("UPSTREAM", f"EduPage meldet Status {response.status_code}.")
            content = response.content
            content_type = response.headers.get("content-type", "application/octet-stream")
            return content, content_type.split(";")[0].strip() or "application/octet-stream"

        content, content_type = await _run(_do, "Anhang laden")
        return {
            "filename": attachment["name"] or f"anhang-{event_id}-{idx}",
            "content_type": content_type,
            "content": content,
        }

    async def clear_cache(self) -> None:
        session_cache.drop(self.account.id)

    # --------------------------------------------------------------- internal

    async def _timeline_action(self, action: str, params: dict) -> dict:
        client = await self.ensure()

        def _do():
            from edupage_api.compression import RequestData

            payload = RequestData.encode_request_body(params)
            url = f"https://{client.subdomain}.edupage.org/timeline/?akcia={action}"
            response = client.session.post(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if response.status_code != 200:
                raise api_error("UPSTREAM", f"EduPage meldet Status {response.status_code}.")
            try:
                data = json.loads(response.text)
            except ValueError:
                raise api_error("UPSTREAM", "Unerwartete Antwort von EduPage.")
            if not isinstance(data, dict) or str(data.get("status", "")).lower() != "ok":
                raise api_error("UPSTREAM", "EduPage hat die Änderung nicht bestätigt.")
            return data

        return await _run(_do, "EduPage-Aktion")


def _grades_with_id_fix(client) -> list[Any]:
    """``get_grades`` with an id-type fix.

    The library indexes the grade details with ``grade_details.get(event_id_str)``
    (string keys). Some schools return ``udalostid`` as a JSON *number*, so the
    lookup yields ``None`` and the library dies with
    ``'NoneType' object has no attribute 'get'``. Rewriting the ids to strings
    before parsing makes both layouts work.
    """
    import re

    original_get = client.session.get

    def patched_get(url, *args, **kwargs):
        response = original_get(url, *args, **kwargs)
        if "/znamky/" not in str(url):
            return response
        try:
            text = response.content.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - never break grades over a decode issue
            return response
        fixed = re.sub(r'"udalostid":\s*(\d+)', r'"udalostid": "\1"', text)
        if fixed == text:
            return response

        class _Rewritten:
            def __init__(self, inner, body: str) -> None:
                self._inner = inner
                self.text = body

            @property
            def content(self) -> bytes:
                return self.text.encode()

            def __getattr__(self, name):
                return getattr(self._inner, name)

        return _Rewritten(response, fixed)

    client.session.get = patched_get
    try:
        return client.get_grades()
    finally:
        client.session.get = original_get


def _meal_to_dict(meal: Any) -> dict | None:
    """Flatten an ``edupage_api.lunches.Meal`` (menus, times, ordered choice)."""
    if meal is None:
        return None

    def _time(value: Any) -> str | None:
        return value.strftime("%H:%M") if isinstance(value, datetime) else None

    menus = []
    for menu in getattr(meal, "menus", None) or []:
        menus.append(
            {
                "name": getattr(menu, "name", None),
                "allergens": getattr(menu, "allergens", None),
                "weight": getattr(menu, "weight", None),
                "number": getattr(menu, "number", None),
            }
        )
    meal_type = getattr(meal, "meal_type", None)
    return {
        "title": getattr(meal, "title", None),
        "type": getattr(meal_type, "name", None) if meal_type is not None else None,
        "served_from": _time(getattr(meal, "served_from", None)),
        "served_to": _time(getattr(meal, "served_to", None)),
        "chooseable_menus": list(getattr(meal, "chooseable_menus", None) or []),
        "ordered_meal": getattr(meal, "ordered_meal", None),
        "menus": menus,
    }


def _recipient_dict(person: Any) -> dict:
    if isinstance(person, dict):
        return person
    person_id = None
    for attr in ("person_id", "id", "user_id"):
        person_id = getattr(person, attr, None)
        if person_id:
            break
    name = None
    for attr in ("name", "full_name", "meno"):
        name = getattr(person, attr, None)
        if name:
            break
    kind = type(person).__name__.removeprefix("Edu").lower() or "person"
    return {"id": str(person_id) if person_id is not None else None, "name": name or str(person), "kind": kind}


async def _run(fn: Callable[[], Any], what: str) -> Any:
    from edupage_api.exceptions import (
        BadCredentialsException,
        CaptchaException,
        MissingDataException,
        RequestError,
    )
    from fastapi import HTTPException

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, fn)
    except HTTPException:
        raise
    except BadCredentialsException:
        raise api_error("BAD_CREDENTIALS")
    except CaptchaException:
        raise api_error("CAPTCHA_REQUIRED")
    except MissingDataException as exc:
        raise api_error("UPSTREAM", f"{what}: leere Antwort von EduPage ({exc}).")
    except RequestError as exc:
        raise api_error("UPSTREAM", f"{what}: {exc}")
    except Exception as exc:  # noqa: BLE001
        raise api_error("UPSTREAM", f"{what} fehlgeschlagen: {exc}")
