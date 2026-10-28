from __future__ import annotations

from datetime import date, datetime

import pytest

from tests.fake_edupage import FakeMeal, FakeMealType, FakeMeals, FakeMenu


# ------------------------------------------------------------------- lunches


async def test_lunches_are_serialised(admin, bearer, fake_edupage):
    fake_edupage.meals = FakeMeals(
        lunch=FakeMeal(
            title="Mittagessen",
            meal_type=FakeMealType("LUNCH"),
            served_from=datetime(2026, 10, 28, 11, 30),
            served_to=datetime(2026, 10, 28, 13, 30),
            menus=[FakeMenu("Schnitzel"), FakeMenu("Gemüsecurry", number="B")],
        )
    )

    body = (await admin.get("/api/v1/lunches?date=2026-10-28", headers=bearer)).json()

    assert body["date"] == "2026-10-28"
    assert body["snack"] is None
    assert body["afternoon_snack"] is None
    lunch = body["lunch"]
    assert lunch["title"] == "Mittagessen"
    assert lunch["type"] == "LUNCH"
    assert lunch["served_from"] == "11:30"
    assert lunch["served_to"] == "13:30"
    assert lunch["ordered_meal"] == "A"
    assert lunch["chooseable_menus"] == ["A", "B"]
    assert [menu["name"] for menu in lunch["menus"]] == ["Schnitzel", "Gemüsecurry"]
    assert body["cache"] == "miss"


async def test_lunches_default_to_today(admin, bearer, fake_edupage):
    fake_edupage.meals = FakeMeals()
    body = (await admin.get("/api/v1/lunches", headers=bearer)).json()
    assert body["date"] == date.today().isoformat()
    assert body["lunch"] is None


async def test_lunches_bad_date(admin, bearer):
    response = await admin.get("/api/v1/lunches?date=28.10.2026", headers=bearer)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


# -------------------------------------------------------------------- weather


@pytest.fixture
def weather_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openweather_api_key", "test-key")
    return "test-key"


def _owm_payloads():
    current = {
        "cod": 200,
        "name": "Berlin",
        "timezone": 7200,
        "main": {"temp": 11.6, "temp_max": 13.2, "temp_min": 9.4, "feels_like": 10.1,
                 "humidity": 81, "pressure": 1012},
        "wind": {"speed": 3.5, "deg": 181},
        "clouds": {"all": 75},
        "visibility": 10000,
        "sys": {"sunrise": 1793165400, "sunset": 1793202300},
        "weather": [{"icon": "04d", "description": "bewölkt"}],
    }
    forecast = {
        "city": {"timezone": 7200},
        "list": [
            {"dt": 1793181600, "dt_txt": "2026-10-28 12:00:00", "pop": 0.2,
             "main": {"temp": 12.4}, "weather": [{"icon": "10d", "description": "leichter regen"}]},
            {"dt": 1793192400, "dt_txt": "2026-10-28 15:00:00", "pop": 0.4,
             "main": {"temp": 12.0}, "weather": [{"icon": "10d", "description": "leichter regen"}]},
            {"dt": 1793268000, "dt_txt": "2026-10-29 12:00:00", "pop": 0.1,
             "main": {"temp": 14.6}, "weather": [{"icon": "01d", "description": "klarer himmel"}]},
            {"dt": 1793354400, "dt_txt": "2026-10-30 12:00:00", "pop": 0.6,
             "main": {"temp": 8.2}, "weather": [{"icon": "13d", "description": "schnee"}]},
        ],
    }
    return current, forecast


@pytest.fixture
def fake_owm(monkeypatch):
    from app.services import weather as service

    current, forecast = _owm_payloads()
    calls: list[tuple[str, dict]] = []

    async def fake_fetch(url: str, params: dict, timeout_s: float):
        calls.append((url, params))
        if url.endswith("/data/2.5/weather"):
            return 200, current
        if url.endswith("/data/2.5/forecast"):
            return 200, forecast
        if url.endswith("/geo/1.0/direct"):
            return 200, [
                {"name": "Berlin", "state": "Berlin", "country": "DE"},
                {"name": "Berlin", "state": "", "country": "US"},
            ]
        return 404, None

    monkeypatch.setattr(service, "fetch_json", fake_fetch)
    return calls


async def test_weather_is_prepared_for_agents(admin, bearer, weather_key, fake_owm):
    body = (await admin.get("/api/v1/wetter?city=Berlin", headers=bearer)).json()

    assert body["city"] == "Berlin"
    assert body["today"] == {"temp": 12, "max": 13, "min": 9, "desc": "Bewölkt", "icon": "04d", "pop": 40}
    assert body["tomorrow"]["max"] == 15
    assert body["tomorrow"]["desc"] == "Klarer himmel"
    assert body["day3"]["label"] == "Freitag"
    assert body["day3"]["desc"] == "Schnee"
    assert body["hourly"][0]["time"] == "12:00"
    assert body["hourly"][0]["desc"] == "Leichter regen"
    assert body["details"]["wind_kmh"] == 13
    assert body["details"]["wind_dir"] == "S"
    assert body["details"]["visibility_km"] == 10.0
    assert body["details"]["humidity"] == 81
    assert body["details"]["sunrise"] == "07:30"
    assert body["details"]["sunset"] == "17:45"

    sent = fake_owm[0][1]
    assert sent["q"] == "Berlin"
    assert sent["appid"] == "test-key"
    assert sent["lang"] == "de"


async def test_weather_accepts_coordinates(admin, bearer, weather_key, fake_owm):
    await admin.get("/api/v1/wetter?lat=52.5&lon=13.4", headers=bearer)
    sent = fake_owm[0][1]
    assert sent["lat"] == "52.5"
    assert sent["lon"] == "13.4"
    assert "q" not in sent


async def test_weather_needs_location(admin, bearer, weather_key, fake_owm):
    response = await admin.get("/api/v1/wetter", headers=bearer)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


async def test_weather_without_key_is_config_missing(admin, bearer, fake_owm, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openweather_api_key", "")
    response = await admin.get("/api/v1/wetter?city=Berlin", headers=bearer)
    assert response.status_code == 503
    assert response.json()["code"] == "CONFIG_MISSING"


async def test_weather_upstream_error(admin, bearer, weather_key, monkeypatch):
    from app.services import weather as service

    async def failing(url: str, params: dict, timeout_s: float):
        return 401, {"cod": 401, "message": "Invalid API key"}

    monkeypatch.setattr(service, "fetch_json", failing)
    response = await admin.get("/api/v1/wetter?city=Berlin", headers=bearer)
    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM"
    assert "Invalid API key" in response.json()["error"]


async def test_city_search(admin, bearer, weather_key, fake_owm):
    body = (await admin.get("/api/v1/wetter/suche?q=Ber", headers=bearer)).json()
    assert body["total"] == 2
    assert body["items"][0] == {
        "name": "Berlin",
        "state": "Berlin",
        "country": "DE",
        "label": "Berlin · DE",
        "query": "Berlin, DE",
    }


async def test_city_search_needs_two_letters(admin, bearer, weather_key, fake_owm):
    body = (await admin.get("/api/v1/wetter/suche?q=B", headers=bearer)).json()
    assert body["items"] == []
    assert fake_owm == []
