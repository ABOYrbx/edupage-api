from __future__ import annotations

import pytest


async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "v1"}


async def test_admin_login_bad(client):
    response = await client.post("/api/v1/admin/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert response.json()["code"] == "BAD_CREDENTIALS"


async def test_admin_login_sets_cookies(client):
    response = await client.post("/api/v1/admin/login", json={"password": "test-password"})
    assert response.status_code == 200
    assert client.cookies.get("epa_session")
    assert client.cookies.get("epa_csrf")

    me = await client.get("/api/v1/admin/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


async def test_admin_requires_login(client):
    response = await client.get("/api/v1/admin/accounts")
    assert response.status_code == 401
    assert response.json() == {"error": "Nicht angemeldet.", "code": "TOKEN_INVALID"}


async def test_post_without_csrf_is_forbidden(admin):
    del admin.headers["X-CSRF-Token"]
    response = await admin.post("/api/v1/admin/accounts", json={"username": "x", "password": "y"})
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_logout_revokes_session(admin):
    assert (await admin.post("/api/v1/admin/logout")).status_code == 200
    admin.cookies.clear()
    response = await admin.get("/api/v1/admin/accounts")
    assert response.status_code == 401


async def test_openapi_is_served(client):
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/messages" in response.json()["paths"]


async def test_path_type_errors_use_error_contract(admin, bearer):
    """FastAPI's default 422 body would break the documented {error, code} shape."""
    response = await admin.get("/api/v1/messages/abc/thread", headers=bearer)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert "event_id" in response.json()["error"]


async def test_missing_query_param_uses_error_contract(admin):
    response = await admin.get("/api/v1/admin/keys")
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error", "code"}
    assert body["code"] == "VALIDATION"
    assert "account" in body["error"]


async def test_bad_body_field_uses_error_contract(admin, bearer):
    response = await admin.post(
        "/api/v1/messages/download-token", headers=bearer, json={"event_id": "abc", "idx": 0}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
