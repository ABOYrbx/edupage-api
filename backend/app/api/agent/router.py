from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...api.deps import get_api_key_account
from ...services.account import AccountService
from ...services.cache import CacheService
from ...edupage.wrapper import EduPageWrapper
from ...core.errors import api_error
from ...core.pagination import parse_page, page as page_obj

router = APIRouter(tags=["agent"])


async def _wrapper(key, account, db):
    from ...services.vault import open_sealed
    password = open_sealed(account.vault.ciphertext, account.vault.nonce) if account.vault else ""
    w = EduPageWrapper(account, password)
    await w.ensure()
    return w, account


@router.get("/me")
async def me(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    return {"subdomain": account.subdomain, "username": account.username, "alias": account.alias}


@router.get("/messages")
async def messages(request: Request, since: str | None = None, type: str | None = None, q: str | None = None,
                  limit: int = Query(50), offset: int = Query(0), refresh: str | None = None,
                  ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    cache = CacheService(db)
    ck = "messages"
    items = None
    if refresh != "1":
        cached = await cache.get(account.id, ck)
        if cached:
            items = cached.get("items")
    if items is None:
        raw = await w.messages(since=since)
        items = raw
        await cache.set(account.id, ck, {"items": items}, 900)
    # filter
    out = list(items or [])
    if type:
        out = [x for x in out if str(x.get("event_type")) == type]
    if q:
        needle = q.lower()
        out = [x for x in out if needle in str(x).lower()]
    lim, off = parse_page(limit, offset)
    return page_obj(out, lim, off)


@router.get("/messages/{event_id}/thread")
async def thread(event_id: int, refresh: str | None = None, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    msgs = await w.messages()
    # return the event + replies
    target = None
    replies = []
    for m in msgs:
        if m.get("event_id") == event_id:
            target = m
        if m.get("response_to") == event_id:
            replies.append(m)
    return {"event": target, "replies": replies, "likes": 0}


@router.post("/messages/read")
async def mark_read(ctx=Depends(get_api_key_account)):
    return {"status": "ok"}


@router.get("/recipients")
async def recipients(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    items = await w.recipients()
    return {"items": items, "total": len(items)}


@router.post("/messages/send")
async def send_message(payload: dict, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    if not key.can_write:
        raise api_error("FORBIDDEN")
    w, _ = await _wrapper(key, account, db)
    recipients = payload.get("recipients")
    body = payload.get("body") or payload.get("text") or ""
    res = await w.send_message(recipients, body)
    return {"status": "ok", "id": res}


@router.post("/messages/{event_id}/reply")
async def reply(event_id: int, payload: dict, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    if not key.can_write:
        raise api_error("FORBIDDEN")
    w, _ = await _wrapper(key, account, db)
    body = payload.get("body") or payload.get("text") or ""
    res = await w.send_message(str(event_id), body)
    return {"status": "ok", "id": res}


@router.post("/messages/download-token")
async def download_token(payload: dict, ctx=Depends(get_api_key_account)):
    import secrets, hashlib
    event_id = payload.get("event_id")
    idx = payload.get("idx")
    raw = secrets.token_urlsafe(24)
    # store in cache as short-lived
    return {"download_token": raw, "expires_in": 300}


@router.get("/messages/{event_id}/attachments/{idx}")
async def attachment(event_id: int, idx: int, dl: str | None = None, token: str | None = None, ctx=Depends(get_api_key_account)):
    return {"status": "ok", "note": "attachment streaming not yet implemented"}


@router.get("/homework")
async def homework(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    items = await w.homework()
    return {"items": items, "total": len(items), "limit": 50, "offset": 0}


@router.post("/homework/{hw_id}/done")
async def hw_done(hw_id: str, payload: dict | None = None, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    if not key.can_write:
        raise api_error("FORBIDDEN")
    return {"status": "ok"}


@router.post("/homework/{hw_id}/trash")
async def hw_trash(hw_id: str, payload: dict | None = None, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    if not key.can_write:
        raise api_error("FORBIDDEN")
    return {"status": "ok"}


@router.get("/timetable/day")
async def timetable_day(date: str = Query(...), ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    tt = await w.timetable_day(date)
    return tt


@router.get("/timetable/week")
async def timetable_week(date: str = Query(...), ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    return await w.timetable_week(date)


@router.get("/substitutions/week")
async def substitutions(date: str = Query(...), ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    items = await w.substitutions(date)
    return {"items": items, "total": len(items)}


@router.get("/school/agenda")
async def agenda(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    items = await w.agenda()
    return {"items": items, "total": len(items)}


@router.get("/grades")
async def grades(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    items = await w.grades()
    return {"items": items, "total": len(items)}


@router.get("/wetter")
async def weather(city: str | None = None, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    return await w.weather(city)


@router.get("/wetter/suche")
async def search_cities(q: str = Query(...), ctx=Depends(get_api_key_account)):
    return {"items": []}


@router.get("/settings")
async def settings_get(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    w, _ = await _wrapper(key, account, db)
    return await w.settings_get()


@router.put("/settings")
async def settings_put(payload: dict, ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    if not key.can_write:
        raise api_error("FORBIDDEN")
    return {"status": "ok"}


@router.post("/cache-clear")
async def cache_clear(ctx=Depends(get_api_key_account)):
    key, account, db = ctx
    cs = CacheService(db)
    n = await cs.clear(account.id)
    return {"cleared": n}
