"""OpenWeatherMap proxy (port of eduflow ``edupage/meta.ts``).

The upstream key stays on the server; agents only ever see prepared values.
``fetch_json`` is module-level so tests can swap it without network access.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import httpx

from ..config import get_settings
from ..core.errors import api_error

OWM_BASE = "https://api.openweathermap.org"
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
COMPASS = ("N", "NO", "O", "SO", "S", "SW", "W", "NW")

FetchJson = Callable[[str, dict[str, str], float], Awaitable[tuple[int, Any]]]


async def _http_json(url: str, params: dict[str, str], timeout_s: float) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.get(url, params=params)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, None


fetch_json: FetchJson = _http_json


# ------------------------------------------------------------------- helpers


def _round(value: Any, ndigits: int = 0) -> int | float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = round(float(value), ndigits)
    return int(result) if ndigits == 0 else result


def _cap(value: Any) -> str:
    text = value if isinstance(value, str) else ""
    return text[:1].upper() + text[1:] if text else ""


def _localtime(ts: Any, tz_offset: Any) -> str:
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return "–"
    offset = tz_offset if isinstance(tz_offset, (int, float)) and not isinstance(tz_offset, bool) else 0
    moment = datetime.fromtimestamp(float(ts) + float(offset), tz=timezone.utc)
    return moment.strftime("%H:%M")


def _compass(deg: Any) -> str:
    if not isinstance(deg, (int, float)) or isinstance(deg, bool):
        return "–"
    return COMPASS[int((float(deg) + 22.5) // 45) % 8]


def _record(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _first(sequence: Any) -> dict:
    return _record(sequence[0]) if isinstance(sequence, list) and sequence else {}


def _aggregate_day(forecast: dict, offset: int, today: date) -> dict | None:
    """Condense the 3-hourly list into one max/min/description triple per day."""
    target = today + timedelta(days=offset)
    entries = [
        _record(entry)
        for entry in forecast.get("list") or []
        if str(_record(entry).get("dt_txt", "")).startswith(target.isoformat())
    ]
    temps = [
        entry["main"]["temp"]
        for entry in entries
        if isinstance(_record(entry.get("main")).get("temp"), (int, float))
    ]
    if not temps:
        return None

    conditions = [_first(entry.get("weather")) for entry in entries]
    midday = [
        condition
        for entry, condition in zip(entries, conditions)
        if "12:00:00" in str(entry.get("dt_txt", "")) and condition.get("icon")
    ]
    chosen = midday[0] if midday else {}
    if not chosen:
        counts: dict[str, int] = {}
        for condition in conditions:
            icon = condition.get("icon")
            if isinstance(icon, str) and icon:
                counts[icon] = counts.get(icon, 0) + 1
        if counts:
            best = max(counts, key=counts.get)
            chosen = next((c for c in conditions if c.get("icon") == best), {})

    pops = [entry["pop"] for entry in entries if isinstance(entry.get("pop"), (int, float))]
    return {
        "max": _round(max(temps)),
        "min": _round(min(temps)),
        "desc": _cap(chosen.get("description")),
        "icon": chosen.get("icon") or "",
        "pop": _round(max(pops) * 100) if pops else None,
    }


# --------------------------------------------------------------------- public


async def get_weather(
    city: str | None,
    lat: float | None,
    lon: float | None,
    today: date | None = None,
) -> dict:
    key = get_settings().openweather_api_key.strip()
    if not key:
        raise api_error(
            "CONFIG_MISSING",
            "Wetter ist nicht konfiguriert (OPENWEATHER_API_KEY fehlt).",
            status=503,
        )

    params: dict[str, str] = {"appid": key, "units": "metric", "lang": "de"}
    if lat is not None and lon is not None:
        params.update({"lat": str(lat), "lon": str(lon)})
    elif (city or "").strip():
        params["q"] = city.strip()[:100]
    else:
        raise api_error("VALIDATION", "city oder lat/lon erforderlich.")

    status, current = await _call(f"{OWM_BASE}/data/2.5/weather", params, 8.0)
    if status != 200 or not isinstance(current, dict) or str(current.get("cod", "")) != "200":
        message = current.get("message") if isinstance(current, dict) else None
        raise api_error("UPSTREAM", f"Wetterdienst: {message or f'Status {status}'}")

    status, forecast = await _call(f"{OWM_BASE}/data/2.5/forecast", params, 8.0)
    if status != 200 or not isinstance(forecast, dict):
        raise api_error("UPSTREAM", f"Wetterdienst: Vorhersage fehlgeschlagen (Status {status}).")

    day = today or date.today()
    main = _record(current.get("main"))
    wind = _record(current.get("wind"))
    sys = _record(current.get("sys"))
    clouds = _record(current.get("clouds"))
    weather0 = _first(current.get("weather"))
    tz = _record(forecast.get("city")).get("timezone", current.get("timezone", 0))

    tomorrow = _aggregate_day(forecast, 1, day) or {}
    day3 = _aggregate_day(forecast, 2, day) or {}
    day3["label"] = WEEKDAYS[(day + timedelta(days=2)).weekday()]
    today_pop = _aggregate_day(forecast, 0, day) or {}

    hourly = []
    for entry in (forecast.get("list") or [])[:8]:
        entry = _record(entry)
        condition = _first(entry.get("weather"))
        hourly.append(
            {
                "time": _localtime(entry.get("dt"), tz),
                "temp": _round(_record(entry.get("main")).get("temp")),
                "icon": condition.get("icon") or "",
                "desc": _cap(condition.get("description")),
                "pop": _round(entry["pop"] * 100) if isinstance(entry.get("pop"), (int, float)) else None,
            }
        )

    temp = main.get("temp") if isinstance(main.get("temp"), (int, float)) else 0
    wind_ms = wind.get("speed") if isinstance(wind.get("speed"), (int, float)) else None
    visibility = current.get("visibility") if isinstance(current.get("visibility"), (int, float)) else None

    return {
        "city": current.get("name") if isinstance(current.get("name"), str) else "",
        "today": {
            "temp": _round(temp),
            "max": _round(main.get("temp_max", temp)),
            "min": _round(main.get("temp_min", temp)),
            "desc": _cap(weather0.get("description")),
            "icon": weather0.get("icon") or "",
            "pop": today_pop.get("pop"),
        },
        "tomorrow": tomorrow,
        "day3": day3,
        "hourly": hourly,
        "details": {
            "feels_like": _round(main.get("feels_like")),
            "humidity": _round(main.get("humidity")),
            "pressure": _round(main.get("pressure")),
            "wind_kmh": _round(wind_ms * 3.6) if wind_ms is not None else None,
            "wind_dir": _compass(wind.get("deg")),
            "clouds": _round(clouds.get("all")),
            "visibility_km": _round(visibility / 1000, 1) if visibility is not None else None,
            "sunrise": _localtime(sys.get("sunrise"), tz),
            "sunset": _localtime(sys.get("sunset"), tz),
        },
    }


async def search_cities(query: str | None) -> list[dict]:
    text = (query or "").strip()[:100]
    if len(text) < 2:
        return []
    key = get_settings().openweather_api_key.strip()
    if not key:
        raise api_error(
            "CONFIG_MISSING",
            "Ortssuche ist nicht konfiguriert (OPENWEATHER_API_KEY fehlt).",
            status=503,
        )

    status, payload = await _call(
        f"{OWM_BASE}/geo/1.0/direct",
        {"q": text, "limit": "5", "appid": key},
        5.0,
    )
    if status != 200 or not isinstance(payload, list):
        raise api_error("UPSTREAM", "Ortssuche fehlgeschlagen.")

    items = []
    for raw in payload[:5]:
        place = _record(raw)
        name = (place.get("name") or "").strip() if isinstance(place.get("name"), str) else ""
        if not name:
            continue
        state = place.get("state").strip() if isinstance(place.get("state"), str) else ""
        country = place.get("country").strip() if isinstance(place.get("country"), str) else ""
        parts: list[str] = []
        for part in (name, state, country):
            if part and part.lower() not in {existing.lower() for existing in parts}:
                parts.append(part)
        items.append(
            {
                "name": name,
                "state": state,
                "country": country,
                "label": " · ".join(parts),
                "query": ", ".join(parts)[:100],
            }
        )
    return items


async def _call(url: str, params: dict[str, str], timeout_s: float) -> tuple[int, Any]:
    try:
        return await fetch_json(url, params, timeout_s)
    except httpx.HTTPError as exc:
        raise api_error("UPSTREAM", f"Wetterdienst nicht erreichbar: {exc}")
    except Exception as exc:  # noqa: BLE001 - any transport failure is upstream
        raise api_error("UPSTREAM", f"Wetterdienst nicht erreichbar: {exc}")
