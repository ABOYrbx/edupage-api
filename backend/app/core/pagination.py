from __future__ import annotations

from fastapi import Query

from .errors import api_error

PAGE_DEFAULT_LIMIT = 50
PAGE_MAX_LIMIT = 200


def parse_page(limit: int | None, offset: int | None) -> tuple[int, int]:
    lim = PAGE_DEFAULT_LIMIT if limit is None else limit
    off = 0 if offset is None else offset
    if lim < 1 or lim > PAGE_MAX_LIMIT:
        raise api_error("VALIDATION", f"limit muss zwischen 1 und {PAGE_MAX_LIMIT} liegen.")
    if off < 0:
        raise api_error("VALIDATION", "offset darf nicht negativ sein.")
    return lim, off


def page_query(limit: int = Query(PAGE_DEFAULT_LIMIT), offset: int = Query(0)) -> tuple[int, int]:
    return parse_page(limit, offset)


def page(items: list, limit: int, offset: int) -> dict:
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }
