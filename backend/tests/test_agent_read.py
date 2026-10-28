from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from tests.fake_edupage import FakeEvent


def _event(
    event_id: int,
    *,
    text: str = "Hallo",
    event_type: str = "sprava",
    when: datetime | None = None,
    extra: dict | None = None,
    **kwargs,
) -> FakeEvent:
    return FakeEvent(
        event_id=event_id,
        timestamp=when or datetime(2026, 10, 20, 8, 0, 0),
        text=text,
        event_type=event_type,
        additional_data=extra or {},
        **kwargs,
    )


async def test_me_reports_account_and_key(admin, api_key, bearer):
    response = await admin.get("/api/v1/me", headers=bearer)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "schueler"
    assert body["subdomain"] == "login1"
    assert body["alias"] == "Testkonto"
    assert body["key"]["prefix"] == api_key["prefix"]
    assert body["key"]["can_write"] is False


async def test_messages_are_paginated(admin, bearer, fake_edupage):
    fake_edupage.events = [_event(i, text=f"Nachricht {i}") for i in range(1, 8)]

    response = await admin.get("/api/v1/messages?limit=3&offset=0", headers=bearer)
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 7
    assert body["limit"] == 3
    assert body["offset"] == 0
    assert len(body["items"]) == 3

    second = (await admin.get("/api/v1/messages?limit=3&offset=3", headers=bearer)).json()
    assert {i["id"] for i in body["items"]}.isdisjoint({i["id"] for i in second["items"]})


async def test_messages_are_serialised_for_agents(admin, bearer, fake_edupage):
    fake_edupage.events = [
        _event(
            42,
            text="Elternabend am Freitag",
            extra={"messageContent": "Elternabend am Freitag", "attachments": [{"name": "plan.pdf", "url": "/files/plan.pdf"}]},
        )
    ]
    item = (await admin.get("/api/v1/messages", headers=bearer)).json()["items"][0]
    assert item["id"] == 42
    assert item["type"] == "sprava"
    assert item["type_label"] == "Nachricht"
    assert item["author"] == "Lehrer"
    assert item["recipient"] == "Schüler"
    assert item["timestamp_iso"].startswith("2026-10-20T08:00")
    assert item["attachments"] == [{"name": "plan.pdf", "url": "/files/plan.pdf"}]
    assert "extra" in item


async def test_messages_filter_by_type_and_query(admin, bearer, fake_edupage):
    fake_edupage.events = [
        _event(1, text="Mathe Hausaufgabe", event_type="homework"),
        _event(2, text="Elternbrief", event_type="sprava"),
    ]
    by_type = (await admin.get("/api/v1/messages?type=homework", headers=bearer)).json()
    assert [i["id"] for i in by_type["items"]] == [1]

    by_query = (await admin.get("/api/v1/messages?q=elternbrief", headers=bearer)).json()
    assert [i["id"] for i in by_query["items"]] == [2]


async def test_messages_since_filters(admin, bearer, fake_edupage):
    fake_edupage.events = [
        _event(1, when=datetime(2026, 9, 1, 8, 0)),
        _event(2, when=datetime(2026, 10, 1, 8, 0)),
    ]
    body = (await admin.get("/api/v1/messages?since=2026-09-15", headers=bearer)).json()
    assert [i["id"] for i in body["items"]] == [2]


async def test_messages_bad_pagination(admin, bearer):
    too_big = await admin.get("/api/v1/messages?limit=999", headers=bearer)
    assert too_big.status_code == 400
    negative = await admin.get("/api/v1/messages?offset=-1", headers=bearer)
    assert negative.status_code == 400


async def test_messages_are_cached(admin, bearer, fake_edupage, account):
    fake_edupage.events = [_event(1)]
    first = (await admin.get("/api/v1/messages", headers=bearer)).json()
    assert first["cache"] == "miss"

    fake_edupage.events = []  # upstream changed, cache still answers
    second = (await admin.get("/api/v1/messages", headers=bearer)).json()
    assert second["cache"] in ("memory", "db")
    assert second["total"] == 1

    forced = (await admin.get("/api/v1/messages?refresh=1", headers=bearer)).json()
    assert forced["cache"] == "miss"
    assert forced["total"] == 0


async def test_agent_cache_clear(admin, bearer, fake_edupage):
    fake_edupage.events = [_event(1)]
    await admin.get("/api/v1/messages", headers=bearer)
    cleared = await admin.post("/api/v1/cache-clear", headers=bearer)
    assert cleared.json()["cleared"] >= 1

    fake_edupage.events = []
    fresh = (await admin.get("/api/v1/messages", headers=bearer)).json()
    assert fresh["cache"] == "miss"


async def test_thread_returns_event_and_replies(admin, bearer, fake_edupage):
    fake_edupage.events = [
        _event(100, text="Frage"),
        _event(101, text="Antwort", response_to=100, when=datetime(2026, 10, 20, 9, 0)),
    ]
    body = (await admin.get("/api/v1/messages/100/thread", headers=bearer)).json()
    assert body["event"]["id"] == 100
    assert [reply["id"] for reply in body["replies"]] == [101]


async def test_thread_missing_is_404(admin, bearer, fake_edupage):
    fake_edupage.events = []
    response = await admin.get("/api/v1/messages/999/thread", headers=bearer)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_recipients(admin, bearer):
    body = (await admin.get("/api/v1/recipients", headers=bearer)).json()
    names = {item["name"] for item in body["items"]}
    assert "Frau Muster" in names
    assert "Max Mustermann" in names


async def test_homework_view_and_counts(admin, bearer, fake_edupage):
    today = date.today()
    fake_edupage.events = [
        _event(1, event_type="homework", text="Alt", extra={"date": (today - timedelta(days=2)).isoformat()}),
        _event(2, event_type="homework", text="Heute", extra={"date": today.isoformat()}),
        _event(3, event_type="homework", text="Morgen", extra={"date": (today + timedelta(days=1)).isoformat()}),
        _event(4, event_type="homework", text="Fertig", is_done=True, extra={"date": today.isoformat()}),
        _event(5, event_type="sprava", text="Keine Hausaufgabe"),
    ]
    body = (await admin.get("/api/v1/homework", headers=bearer)).json()
    assert body["total"] == 4
    assert body["counts"] == {"offen": 2, "ueberfaellig": 1, "erledigt": 1}
    statuses = {item["id"]: item["status"] for item in body["items"]}
    assert statuses == {1: "überfällig", 2: "heute fällig", 3: "offen", 4: "erledigt"}
    # most urgent first
    assert body["items"][0]["id"] == 1


async def test_homework_status_filter_and_tests(admin, bearer, fake_edupage):
    today = date.today()
    fake_edupage.events = [
        _event(1, event_type="homework", text="Offen", extra={"date": (today + timedelta(days=1)).isoformat()}),
        _event(2, event_type="sexam", text="Test", extra={"date": (today + timedelta(days=3)).isoformat()}),
    ]
    assert (await admin.get("/api/v1/homework?status=offen", headers=bearer)).json()["total"] == 1

    with_tests = (await admin.get("/api/v1/homework?include_tests=1", headers=bearer)).json()
    assert with_tests["total"] == 2

    bad = await admin.get("/api/v1/homework?status=quatsch", headers=bearer)
    assert bad.status_code == 400


async def test_homework_search(admin, bearer, fake_edupage):
    fake_edupage.events = [
        _event(1, event_type="homework", text="Mathe Seite 12"),
        _event(2, event_type="homework", text="Deutsch Aufsatz"),
    ]
    body = (await admin.get("/api/v1/homework?q=mathe", headers=bearer)).json()
    assert [item["id"] for item in body["items"]] == [1]


async def test_timetable_day(admin, bearer):
    body = (await admin.get("/api/v1/timetable/day?date=2026-10-21", headers=bearer)).json()
    assert body["date"] == "2026-10-21"
    assert body["lessons"][0]["subject"] == "Mathe"


async def test_timetable_day_bad_date(admin, bearer):
    response = await admin.get("/api/v1/timetable/day?date=21.10.2026", headers=bearer)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


async def test_timetable_week_covers_seven_days(admin, bearer):
    body = (await admin.get("/api/v1/timetable/week?date=2026-10-19", headers=bearer)).json()
    assert len(body["items"]) == 7
    assert body["items"][0]["date"] == "2026-10-19"
    assert body["items"][6]["date"] == "2026-10-25"
    # weekend days are empty and never hit upstream
    assert body["items"][5]["lessons"] == []
    assert body["items"][6]["lessons"] == []


async def test_substitutions(admin, bearer):
    body = (await admin.get("/api/v1/substitutions/week?date=2026-10-21", headers=bearer)).json()
    assert body["total"] == 1
    assert body["items"][0]["subject"] == "Physik"


async def test_grades(admin, bearer, fake_edupage):
    fake_edupage.grades = [
        type("G", (), {"subject": "Mathe", "grade": 1, "date": datetime(2026, 10, 1), "teacher": "Muster"})()
    ]
    body = (await admin.get("/api/v1/grades", headers=bearer)).json()
    assert body["total"] == 1
    assert body["items"][0]["subject"] == "Mathe"


async def test_agenda_filters_event_types(admin, bearer, fake_edupage):
    fake_edupage.events = [
        _event(1, event_type="event", text="Schulfest"),
        _event(2, event_type="sprava", text="Nachricht"),
        _event(3, event_type="holiday", text="Feiertag"),
    ]
    body = (await admin.get("/api/v1/school/agenda", headers=bearer)).json()
    assert {item["id"] for item in body["items"]} == {1, 3}


async def test_settings(admin, bearer):
    body = (await admin.get("/api/v1/settings", headers=bearer)).json()
    assert body["user"]["userid"] == "1"
    assert body["subdomain"] == "login1"


async def test_agent_error_contract_when_upstream_fails(admin, bearer, fake_edupage, monkeypatch):
    def boom():
        raise RuntimeError("upstream kaputt")

    monkeypatch.setattr(fake_edupage, "get_notifications", lambda self: boom())
    response = await admin.get("/api/v1/messages", headers=bearer)
    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM"
    assert set(response.json()) == {"error", "code"}


async def test_login_is_reused_from_session_cache(admin, bearer, fake_edupage):
    await admin.get("/api/v1/messages", headers=bearer)
    first_count = len(fake_edupage.instances)
    await admin.get("/api/v1/grades", headers=bearer)
    assert len(fake_edupage.instances) == first_count


@pytest.mark.parametrize("path", ["/api/v1/recipients", "/api/v1/school/agenda", "/api/v1/settings"])
async def test_read_endpoints_answer(admin, bearer, path):
    assert (await admin.get(path, headers=bearer)).status_code == 200
