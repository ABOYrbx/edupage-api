from __future__ import annotations

PAGE_DEFAULT_LIMIT = 50
PAGE_MAX_LIMIT = 200


def parse_page(limit: int | None, offset: int | None) -> tuple[int, int]:
    lim = limit if limit is not None else PAGE_DEFAULT_LIMIT
    off = offset if offset is not None else 0
    if lim < 1 or lim > PAGE_MAX_LIMIT:
        raise ValueError("limit")
    if off < 0:
        raise ValueError("offset")
    return lim, off


def page(items: list, limit: int, offset: int) -> dict:
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }
