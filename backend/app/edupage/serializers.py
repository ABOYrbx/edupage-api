"""Serialisation helpers for EduPage payloads.

Port of the reference implementation (eduflow `serializers.ts`, itself a port of
the original `app.py`): German labels, tolerant timestamp parsing, attachment
discovery and the homework view.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

TYPE_LABELS: dict[str, str] = {
    "sprava": "Nachricht",
    "chat": "Chat",
    "anketa": "Umfrage",
    "news": "Neuigkeit",
    "genotif": "Mitteilung",
    "homework": "Hausaufgabe",
    "etesthw": "Online-Test",
    "homeworkstudentstav": "Hausaufgaben-Status",
    "bexam": "Schularbeit",
    "sexam": "Test",
    "oexam": "Mündliche Prüfung",
    "pexam": "Projektprüfung",
    "rexam": "Wiederholungsprüfung",
    "testing": "Testung",
    "testpridelenie": "Prüfungszuweisung",
    "testvysledok": "Prüfungsergebnis",
    "znamka": "Note",
    "znamkydoc": "Notendokument",
    "other_cb": "Klassenbucheintrag",
    "ctevent": "Klassenereignis",
    "bmeeting": "Besprechung",
    "culture": "Kulturveranstaltung",
    "event": "Ereignis",
    "excursion": "Exkursion",
    "parentsevening": "Elternabend",
    "process": "Vorgang",
    "schoolevent": "Schulveranstaltung",
    "trip": "Ausflug",
    "signin": "Anmeldung",
    "meeting": "Versammlung",
    "freeday": "Freier Tag",
    "holiday": "Feiertag",
    "sholiday": "Schulferien",
    "ttcancel": "Entfallene Stunde",
    "ctlesson": "Klassenlehrerstunde",
    "distant": "Distanzunterricht",
    "lesson": "Unterricht",
    "project": "Projekt",
    "plesson": "Geplante Stunde",
    "other_safety": "Sicherheitshinweis",
    "rlesson": "Wiederholungsstunde",
    "timetable": "Stundenplan",
    "bookroom": "Raumbuchung",
    "changeroom": "Raumwechsel",
    "substitution": "Vertretung",
    "pipnutie": "Anstupser",
    "ospravedlnenka": "Entschuldigung",
    "representation": "Repräsentation",
    "student_absent": "Fehlzeit",
    "strava_kredit": "Essensguthaben",
    "strava_vydaj": "Essensausgabe",
    "stravamenu": "Speiseplan",
    "h_stravamenu": "Speiseplan (Verlauf)",
    "confirmation": "Bestätigung",
    "contest": "Wettbewerb",
    "album": "Fotoalbum",
    "payments": "Zahlungen",
    "lost": "Fundsache",
    "vcelicka": "Bienchen",
    "other": "Sonstiges",
}

HOMEWORK_TYPES = ("homework",)
EXAM_TYPES = ("bexam", "sexam", "oexam", "pexam", "rexam", "testing", "etesthw", "testpridelenie")

_SK_DE_PHRASES = (
    ("Zverejnený nový rozvrh", "Neuer Stundenplan veröffentlicht"),
    ("Aktualizovaný fotoalbum", "Aktualisiertes Fotoalbum"),
    ("Nová ospravedlnenka", "Neue Entschuldigung"),
    ("Pridelený test", "Zugeteilter Test"),
    ("Udalosť:", "Ereignis:"),
    ("Známka", "Note"),
    ("Zverejneny novy rozvrh", "Neuer Stundenplan veröffentlicht"),
    ("Aktualizovany fotoalbum", "Aktualisiertes Fotoalbum"),
    ("Nova ospravedlnenka", "Neue Entschuldigung"),
    ("Prideleny test", "Zugeteilter Test"),
    ("Udalost:", "Ereignis:"),
    ("Znamka", "Note"),
)

_GERMAN_MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)
_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
_SHORT_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


# --------------------------------------------------------------------- helpers


def as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def parse_server_date(value: str) -> datetime:
    """Parse ``YYYY-MM-DD HH:MM:SS`` as naive local time (EduPage's format)."""
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def format_iso_local(ts: datetime) -> str:
    return ts.isoformat()


def pretty_timestamp(ts: datetime, today: date | None = None) -> str:
    today = today or date.today()
    time_part = ts.strftime("%H:%M")
    delta = (today - ts.date()).days
    if delta == 0:
        return f"Heute · {time_part}"
    if delta == 1:
        return f"Gestern · {time_part}"
    if 1 < delta < 7:
        return f"{_WEEKDAYS[ts.weekday()]} · {time_part}"
    month = _GERMAN_MONTHS[ts.month - 1]
    if ts.year == today.year:
        return f"{ts.day}. {month} · {time_part}"
    return f"{ts.day}. {month} {ts.year} · {time_part}"


def translate_server_text(text: str) -> str:
    if not text:
        return text
    out = text
    for sk, de in _SK_DE_PHRASES:
        if sk in out:
            out = out.replace(sk, de)
    return out


def strip_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def format_person(value: Any) -> str:
    return "–" if value is None or value == "" else str(value)


# ----------------------------------------------------------------- attachments

_ATTACH_NAME_KEYS = ("filename", "fileName", "name", "nazov", "nadpis", "subor", "originalName")
_ATTACH_URL_KEYS = ("url", "file", "src", "href", "link", "downloadLink", "path")
_ATTACH_SKIP_KEYS = ("avatar", "photo", "icon", "thumbnail", "image")


def _looks_like_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "/"))


def _clean_name(name: Any, url: str) -> str:
    label = name.strip() if isinstance(name, str) and name.strip() else url.rsplit("/", 1)[-1]
    label = re.sub(r'[\r\n"]', "", label or "").strip()[:120]
    return label or "Datei"


def extract_attachments(extra: Any) -> list[dict]:
    """Collect ``{name, url}`` pairs from a timeline event's extra payload."""
    found: list[dict] = []
    seen: set[str] = set()

    def add(name: Any, url: Any) -> None:
        if not isinstance(url, str):
            return
        clean = url.strip()
        if not clean or clean in seen or not _looks_like_url(clean):
            return
        seen.add(clean)
        found.append({"name": _clean_name(name, clean), "url": clean})

    def walk(node: Any, depth: int) -> None:
        if node is None or depth > 6:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if isinstance(node, dict):
            name = next(
                (node[k].strip() for k in _ATTACH_NAME_KEYS if isinstance(node.get(k), str) and node[k].strip()),
                None,
            )
            url = next(
                (node[k].strip() for k in _ATTACH_URL_KEYS
                 if isinstance(node.get(k), str) and _looks_like_url(node[k].strip())),
                None,
            )
            if url and (name is not None or "file" in node or "url" in node):
                add(name or url.rsplit("/", 1)[-1], url)
            for key, value in node.items():
                if (
                    isinstance(key, str)
                    and any(skip in key.lower() for skip in _ATTACH_SKIP_KEYS)
                    and not isinstance(value, (dict, list))
                ):
                    continue
                walk(value, depth + 1)
            return
        if isinstance(node, str) and depth <= 2 and "<a " in node:
            for match in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', node, re.I | re.S):
                href = match.group(1).strip()
                label = strip_html(match.group(2))
                if _looks_like_url(href):
                    add(label or None, href)

    try:
        walk(extra or {}, 0)
    except Exception:  # pragma: no cover - best effort, like the reference
        pass
    return found


# --------------------------------------------------------------- timeline view


def event_extra_json(event: Any) -> str:
    extra = getattr(event, "additional_data", None)
    if isinstance(extra, (dict, list)):
        try:
            return json.dumps(extra, indent=2, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return str(extra) if extra else ""


def event_text(event: Any) -> str:
    text = (getattr(event, "text", "") or "").strip()
    extra = as_dict(getattr(event, "additional_data", None))
    if not text:
        for key in ("messageContent", "text", "nazov", "name"):
            candidate = extra.get(key)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate.strip()
                break
    return translate_server_text(text)


def event_to_dict(event: Any, today: date | None = None) -> dict:
    ts = getattr(event, "timestamp", None)
    if not isinstance(ts, datetime):
        ts = parse_server_date(str(ts)) if ts else datetime.now()
    type_value = _event_type(event)
    return {
        "id": getattr(event, "event_id", None),
        "timestamp": pretty_timestamp(ts, today),
        "timestamp_iso": format_iso_local(ts),
        "sort_key": format_iso_local(ts),
        "author": format_person(_person(getattr(event, "author", None))),
        "recipient": format_person(_person(getattr(event, "recipient", None))),
        "type": type_value,
        "type_label": TYPE_LABELS.get(type_value, type_value),
        "text": event_text(event),
        "is_starred": bool(getattr(event, "is_starred", False)),
        "is_done": bool(getattr(event, "is_done", False)),
        "reaction_count": int(getattr(event, "reaction_count", 0) or 0),
        "extra": event_extra_json(event),
        "attachments": extract_attachments(getattr(event, "additional_data", None)),
    }


def _event_type(event: Any) -> str:
    value = getattr(event, "event_type", None)
    if value is None:
        return "unknown"
    raw = getattr(value, "value", value)
    return str(raw)


def _person(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


# -------------------------------------------------------------------- homework

_DUE_RE = (
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$"), ("y", "m", "d", "H", "M")),
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), ("y", "m", "d")),
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})[ ](\d{2}):(\d{2})$"), ("d", "m", "y", "H", "M")),
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$"), ("d", "m", "y")),
)


def parse_due_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for pattern, order in _DUE_RE:
        match = pattern.match(text)
        if not match:
            continue
        parts = {key: int(match.group(i + 1) or 0) for i, key in enumerate(order)}
        try:
            return date(parts["y"], parts["m"], parts["d"])
        except (KeyError, ValueError):
            return None
    return None


def _pick(dicts: list[dict], keys: tuple[str, ...]) -> str:
    for data in dicts:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value not in (None, "") and key in ("predmet", "subject", "subjectid"):
                return str(value)
    return ""


_STATUS_CLASS = {
    "überfällig": "st-ueber",
    "heute fällig": "st-heute",
    "offen": "st-offen",
    "erledigt": "st-erledigt",
}
_TAG_CLASS = {
    "überfällig": "tag-red",
    "heute fällig": "tag-amber",
    "offen": "tag-blue",
    "erledigt": "tag-green",
}


def homework_to_dict(event: Any, today: date | None = None) -> dict:
    today = today or date.today()
    type_value = _event_type(event)
    assigned = getattr(event, "timestamp", None)
    if not isinstance(assigned, datetime):
        assigned = parse_server_date(str(assigned)) if assigned else datetime.now()

    extra = as_dict(getattr(event, "additional_data", None))
    old = as_dict(extra.get("oldVals"))
    sources = [old, extra]

    due_raw = _pick(sources, ("date", "dueDate", "due-date", "dateto", "duedate", "termin", "dateTo"))
    due = parse_due_date(due_raw)
    title_pick = _pick(sources, ("title", "nazov", "name", "nadpis"))
    description_pick = _pick(sources, ("popis", "description", "text", "messageContent", "detail"))
    subject = _pick(sources, ("predmet", "subject", "subjectName", "predmetName"))

    text = event_text(event)
    title = title_pick or (text.splitlines()[0].strip()[:120] if text else f"Hausaufgabe #{getattr(event, 'event_id', '')}")
    description = description_pick or (text if text and text != title else "")

    is_done = bool(getattr(event, "is_done", False))
    done_at = getattr(event, "done_at", None)
    done_at_str = done_at.strftime("%Y-%m-%d %H:%M") if isinstance(done_at, datetime) else ""

    if is_done:
        status = "erledigt"
    elif due is None:
        status = "ohne Datum"
    elif due < today:
        status = "überfällig"
    elif due == today:
        status = "heute fällig"
    else:
        status = "offen"

    return {
        "id": getattr(event, "event_id", None),
        "type": type_value,
        "type_label": TYPE_LABELS.get(type_value, type_value),
        "title": title,
        "description": description,
        "subject": subject,
        "author": format_person(_person(getattr(event, "author", None))),
        "recipient": format_person(_person(getattr(event, "recipient", None))),
        "assigned": assigned.strftime("%Y-%m-%d %H:%M"),
        "assigned_iso": format_iso_local(assigned),
        "due": due.isoformat() if due else "",
        "due_display": (
            f"{_SHORT_WEEKDAYS[due.weekday()]} {due.day:02d}.{due.month:02d}.{due.year}" if due else "–"
        ),
        "due_raw": due_raw,
        "status": status,
        "status_class": _STATUS_CLASS.get(status, "st-ohne"),
        "tag_class": _TAG_CLASS.get(status, "tag-gray"),
        "is_done": is_done,
        "done_at": done_at_str,
        "is_starred": bool(getattr(event, "is_starred", False)),
        "extra": event_extra_json(event),
    }


def homework_rank(item: dict) -> int:
    if item.get("is_hidden"):
        return 3
    status = item.get("status")
    if status == "überfällig":
        return 0
    if status == "erledigt":
        return 2
    return 1


def mark_hidden(items: list[dict], hidden: set[str]) -> tuple[list[dict], list[dict]]:
    visible, deleted = [], []
    for item in items:
        item["is_hidden"] = str(item.get("id")) in hidden
        (deleted if item["is_hidden"] else visible).append(item)
    return visible, deleted


def sort_homework(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            homework_rank(item),
            1 if str(item.get("due", "")) == "" else 0,
            str(item.get("due", "")),
            str(item.get("assigned_iso", "")),
        ),
    )


# ---------------------------------------------------------------------- grades


def grade_to_dict(grade: Any) -> dict:
    if isinstance(grade, dict):
        return {str(k): _plain(v) for k, v in grade.items()}
    out: dict[str, Any] = {}
    for attr in dir(grade):
        if attr.startswith("_"):
            continue
        value = getattr(grade, attr, None)
        if callable(value) or isinstance(value, type):
            continue
        if isinstance(value, (str, int, float, bool, datetime, date)) or value is None:
            out[attr] = _plain(value)
    return out


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value") and isinstance(getattr(value, "value"), (str, int)):
        return value.value
    return value


# ------------------------------------------------------- timetable / changes


def lesson_to_dict(lesson: Any) -> dict:
    if lesson is None:
        return {}
    if isinstance(lesson, dict):
        return {str(k): _plain(v) for k, v in lesson.items()}
    out: dict[str, Any] = {}
    for attr in (
        "period", "subject", "teacher", "classroom", "curriculum", "teachers", "classrooms",
        "classes", "groups", "note", "online", "online_lesson", "start", "end", "raw",
    ):
        value = getattr(lesson, attr, None)
        if value is None:
            continue
        out[attr] = _serialize(value)
    return out


def timetable_to_dict(timetable: Any) -> dict | None:
    if timetable is None:
        return None
    if isinstance(timetable, dict):
        return {str(k): _serialize(v) for k, v in timetable.items()}
    lessons = getattr(timetable, "lessons", None) or []
    return {"lessons": [_serialize(lesson) for lesson in lessons]}


def change_to_dict(change: Any) -> dict:
    if isinstance(change, dict):
        return {str(k): _serialize(v) for k, v in change.items()}
    out: dict[str, Any] = {}
    for attr in ("date", "period", "class_name", "subject", "teacher", "classroom", "action", "note", "type"):
        value = getattr(change, attr, None)
        if value is not None:
            out[attr] = _serialize(value)
    return out


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(v) for v in value]
    if hasattr(value, "value"):
        return _serialize(getattr(value, "value"))
    if hasattr(value, "__dataclass_fields__"):
        return {f: _serialize(getattr(value, f, None)) for f in value.__dataclass_fields__}
    if hasattr(value, "__dict__"):
        return {k: _serialize(v) for k, v in vars(value).items() if not k.startswith("_")}
    return str(value)


def week_days(start: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(7)]
