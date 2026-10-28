from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_api_key_account, require_write
from ...config import get_settings
from ...core.errors import api_error
from ...core.pagination import page, parse_page
from ...edupage.wrapper import EduPageWrapper
from ...services.account import AccountService
from ...services.cache import CacheService
from ...services.downloads import DownloadTokens
from ...services.keys import safe_filename

router = APIRouter(tags=["agent"])


async def wrapper_for(account, db: AsyncSession) -> EduPageWrapper:
    password = await AccountService(db).password_for(account)
    return EduPageWrapper(account, password)


def _iso_date(value: str | None, field: str = "date") -> str:
    if not value:
        return date.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise api_error("VALIDATION", f"{field} muss YYYY-MM-DD sein.")


def _int(value, field: str, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise api_error("VALIDATION", f"{field} muss eine Zahl sein.")
    if parsed < minimum:
        raise api_error("VALIDATION", f"{field} muss >= {minimum} sein.")
    return parsed


def _bool(value, field: str, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "ja", "on"):
        return True
    if text in ("0", "false", "no", "nein", "off"):
        return False
    raise api_error("VALIDATION", f"{field} muss ein Wahrheitswert sein.")


def _body(payload) -> dict:
    if not isinstance(payload, dict):
        raise api_error("VALIDATION", "JSON-Objekt erwartet.")
    return payload


async def _cached(db, account, cache_key: str, ttl: int, refresh: bool, producer):
    """Read-through cache helper (DB row + in-memory layer)."""
    cache = CacheService(db)
    if not refresh:
        hit = cache.mem_get(f"{account.id}:{cache_key}")
        if hit is not None:
            return hit, "memory"
        stored = await cache.get(account.id, cache_key)
        if stored is not None:
            cache.mem_set(f"{account.id}:{cache_key}", stored)
            return stored, "db"
    value = await producer()
    await cache.set(account.id, cache_key, value, ttl)
    cache.mem_set(f"{account.id}:{cache_key}", value)
    return value, "miss"


# ------------------------------------------------------------------- meta


@router.get("/me")
async def me(ctx=Depends(get_api_key_account)):
    key, account, _ = ctx
    return {
        "subdomain": account.subdomain,
        "username": account.username,
        "alias": account.alias,
        "key": {
            "id": key.id,
            "name": key.name,
            "prefix": key.key_prefix,
            "can_write": key.can_write,
        },
    }


# --------------------------------------------------------------- messages


@router.get("/messages")
async def list_messages(
    since: str | None = None,
    type: str | None = None,
    q: str | None = None,
    refresh: str | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    ctx=Depends(get_api_key_account),
):
    key, account, db = ctx
    lim, off = parse_page(limit, offset)
    force = _bool(refresh, "refresh")
    wrapper = await wrapper_for(account, db)

    async def produce():
        return {"items": await wrapper.messages(since=since, type_=type, q=q)}

    payload, source = await _cached(
        db, account, f"messages:{since or ''}:{type or ''}:{q or ''}",
        get_settings().cache_ttl_messages, force, produce,
    )
    result = page(payload.get("items", []), lim, off)
    result["cache"] = source
    return result


@router.get("/messages/{event_id}/thread")
async def message_thread(
    event_id: int,
    refresh: str | None = None,
    ctx=Depends(get_api_key_account),
):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)

    async def produce():
        return await wrapper.thread(_int(event_id, "event_id", 1))

    payload, source = await _cached(
        db, account, f"thread:{event_id}", get_settings().cache_ttl_messages,
        _bool(refresh, "refresh"), produce,
    )
    return {**payload, "cache": source}


@router.post("/messages/read")
async def mark_read(payload: dict | None = None, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    body = _body(payload or {})
    ids = body.get("event_ids") or body.get("ids") or []
    if not isinstance(ids, list):
        raise api_error("VALIDATION", "event_ids muss eine Liste sein.")
    wrapper = await wrapper_for(account, db)
    count = await wrapper.mark_messages_read([_int(i, "event_id", 1) for i in ids])
    return {"status": "ok", "marked": count}


@router.get("/recipients")
async def recipients(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)
    items = await wrapper.recipients()
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("/messages/send")
async def send_message(payload: dict, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    require_write(key)
    body = _body(payload)
    to = body.get("recipients") or body.get("to") or []
    text = body.get("body") or body.get("text") or ""
    if isinstance(to, str):
        to = [to]
    if not isinstance(to, list):
        raise api_error("VALIDATION", "recipients muss eine Liste sein.")
    wrapper = await wrapper_for(account, db)
    timeline_id = await wrapper.send_message(to, text)
    return {"status": "ok", "id": timeline_id}


@router.post("/messages/{event_id}/reply")
async def reply(event_id: int, payload: dict, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    require_write(key)
    body = _body(payload)
    text = body.get("body") or body.get("text") or ""
    wrapper = await wrapper_for(account, db)
    result = await wrapper.reply(_int(event_id, "event_id", 1), text)
    return {"status": "ok", "result": result}


@router.post("/messages/download-token")
async def download_token(payload: dict, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    body = _body(payload)
    event_id = _int(body.get("event_id"), "event_id", 1)
    idx = _int(body.get("idx"), "idx", 0)
    # Validate the pair now so agents get a clear error instead of a broken link.
    wrapper = await wrapper_for(account, db)
    await wrapper.attachment_meta(event_id, idx)
    token, ttl = await DownloadTokens(db).issue(account.id, event_id, idx)
    return {"download_token": token, "expires_in": ttl}


@router.get("/messages/{event_id}/attachments/{idx}")
async def attachment(
    event_id: int,
    idx: int,
    dl: str | None = None,
    token: str | None = None,
    ctx=Depends(get_api_key_account),
):
    key, account, db = ctx
    event_id = _int(event_id, "event_id", 1)
    idx = _int(idx, "idx", 0)
    supplied = dl or token
    if supplied:
        await DownloadTokens(db).resolve(supplied, account.id, event_id, idx)
    wrapper = await wrapper_for(account, db)
    file = await wrapper.download_attachment(event_id, idx)
    filename = safe_filename(file["filename"], f"anhang-{event_id}-{idx}")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=file["content"], media_type=file["content_type"], headers=headers)


# --------------------------------------------------------------- homework


@router.get("/homework")
async def homework(
    since: str | None = None,
    status: str = "alle",
    include_tests: str | None = None,
    q: str | None = None,
    refresh: str | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    ctx=Depends(get_api_key_account),
):
    key, account, db = ctx
    lim, off = parse_page(limit, offset)
    if status not in ("alle", "offen", "heute fällig", "überfällig", "erledigt", "ohne Datum"):
        raise api_error(
            "VALIDATION",
            "status muss alle|offen|heute fällig|überfällig|erledigt|ohne Datum sein.",
        )
    wrapper = await wrapper_for(account, db)
    items, counts = await wrapper.homework(
        since=since, status=status, include_tests=_bool(include_tests, "include_tests"), q=q
    )
    hidden = await _hidden_ids(db, account.id)
    if hidden:
        for item in items:
            item["is_hidden"] = str(item.get("id")) in hidden
        items = [item for item in items if not item.get("is_hidden")]
    result = page(items, lim, off)
    result["counts"] = counts
    return result


async def _hidden_ids(db, account_id: str) -> set[str]:
    from sqlalchemy import select

    from ...models import HomeworkFlag

    res = await db.execute(
        select(HomeworkFlag.event_id).where(
            HomeworkFlag.account_id == account_id, HomeworkFlag.hidden.is_(True)
        )
    )
    return {str(value) for value in res.scalars().all()}


@router.post("/homework/{hw_id}/done")
async def homework_done(hw_id: str, payload: dict | None = None, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    require_write(key)
    body = _body(payload or {})
    done = _bool(body.get("done"), "done", default=True)
    wrapper = await wrapper_for(account, db)
    result = await wrapper.set_homework_done(_int(hw_id, "hw_id", 1), done)
    return {"status": "ok", "id": _int(hw_id, "hw_id", 1), "done": done, "result": result}


@router.post("/homework/{hw_id}/trash")
async def homework_trash(hw_id: str, payload: dict | None = None, ctx=Depends(get_api_key_account)):
    """Hide/show homework. EduPage has no trash, so this stays local to the gateway."""
    key, account, db = ctx
    require_write(key)
    body = _body(payload or {})
    hide = _bool(body.get("hide", body.get("trash")), "hide", default=True)
    event_id = _int(hw_id, "hw_id", 1)

    from sqlalchemy import delete, select

    from ...models import HomeworkFlag

    res = await db.execute(
        select(HomeworkFlag).where(
            HomeworkFlag.account_id == account.id, HomeworkFlag.event_id == event_id
        )
    )
    flag = res.scalar_one_or_none()
    if hide and flag is None:
        db.add(HomeworkFlag(account_id=account.id, event_id=event_id, hidden=True))
    elif hide:
        flag.hidden = True
    elif flag is not None:
        await db.execute(delete(HomeworkFlag).where(HomeworkFlag.id == flag.id))
    await db.commit()
    return {"status": "ok", "id": event_id, "hidden": hide}


# -------------------------------------------------------------- timetable


@router.get("/timetable/day")
async def timetable_day(date_: str | None = Query(None, alias="date"), ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)
    return await wrapper.timetable_day(_iso_date(date_))


@router.get("/timetable/week")
async def timetable_week(date_: str | None = Query(None, alias="date"), ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)
    days = await wrapper.timetable_week(_iso_date(date_))
    return {"items": days, "total": len(days), "limit": len(days), "offset": 0}


@router.get("/substitutions/week")
async def substitutions(
    date_: str | None = Query(None, alias="date"),
    ctx=Depends(get_api_key_account),
):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)
    changes = await wrapper.substitutions(_iso_date(date_))
    return {"items": changes, "total": len(changes), "limit": len(changes), "offset": 0}


# ------------------------------------------------------------ school / misc


@router.get("/school/agenda")
async def agenda(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)
    items = await wrapper.agenda()
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.get("/grades")
async def grades(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)

    async def produce():
        return {"items": await wrapper.grades()}

    payload, source = await _cached(
        db, account, "grades", get_settings().cache_ttl_grades, False, produce
    )
    items = payload.get("items", [])
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0, "cache": source}


@router.get("/settings")
async def settings_get(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    wrapper = await wrapper_for(account, db)
    return await wrapper.settings()


@router.get("/lunches")
async def lunches(
    date_: str | None = Query(None, alias="date"),
    refresh: str | None = None,
    ctx=Depends(get_api_key_account),
):
    key, account, db = ctx
    day = _iso_date(date_)
    wrapper = await wrapper_for(account, db)

    async def produce():
        return await wrapper.lunches(day)

    payload, source = await _cached(
        db, account, f"lunches:{day}", get_settings().cache_ttl_messages,
        _bool(refresh, "refresh"), produce,
    )
    return {**payload, "cache": source}


@router.get("/wetter")
async def wetter(
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    ctx=Depends(get_api_key_account),
):
    """Weather for the key's account (EduFlow parity). Needs OPENWEATHER_API_KEY."""
    from ...services.weather import get_weather

    return await get_weather(city, lat, lon)


@router.get("/wetter/suche")
async def wetter_suche(q: str | None = None, ctx=Depends(get_api_key_account)):
    from ...services.weather import search_cities

    items = await search_cities(q)
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("/cache-clear")
async def cache_clear(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    cleared = await CacheService(db).clear(account.id)
    return {"cleared": cleared}
