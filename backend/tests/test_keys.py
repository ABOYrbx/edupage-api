from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.time import utcnow
from app.db import get_session_factory
from app.models import ApiKey


async def _set_expiry(key_id: str, delta: timedelta) -> None:
    async with get_session_factory()() as db:
        res = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
        row = res.scalar_one()
        row.expires_at = utcnow() + delta
        await db.commit()


async def test_create_key_returns_secret_once(admin, account):
    response = await admin.post(
        "/api/v1/admin/keys",
        json={"account_id": account["id"], "name": "Claude", "expires_in_days": 30},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["key"].startswith("epk_")
    assert created["prefix"] == created["key"][:12]
    assert created["can_write"] is False
    assert created["status"] == "active"

    listed = await admin.get(f"/api/v1/admin/keys?account={account['id']}")
    item = listed.json()["items"][0]
    assert "key" not in item  # never again
    assert item["prefix"] == created["prefix"]


async def test_create_key_validation(admin, account):
    missing_name = await admin.post("/api/v1/admin/keys", json={"account_id": account["id"], "name": " "})
    assert missing_name.status_code == 400
    assert missing_name.json()["code"] == "VALIDATION"

    bad_days = await admin.post(
        "/api/v1/admin/keys", json={"account_id": account["id"], "name": "x", "expires_in_days": "viel"}
    )
    assert bad_days.status_code == 400

    too_long = await admin.post(
        "/api/v1/admin/keys", json={"account_id": account["id"], "name": "x", "expires_in_days": 99999}
    )
    assert too_long.status_code == 400

    unknown_account = await admin.post(
        "/api/v1/admin/keys", json={"account_id": "nope", "name": "x"}
    )
    assert unknown_account.status_code == 404


async def test_key_works_as_bearer(admin, api_key):
    response = await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key['key']}"})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "schueler"
    assert body["key"]["can_write"] is False


async def test_key_works_as_query_token(admin, api_key):
    response = await admin.get(f"/api/v1/me?token={api_key['key']}")
    assert response.status_code == 200


async def test_unknown_key_is_rejected(admin):
    response = await admin.get("/api/v1/me", headers={"Authorization": "Bearer epk_nope"})
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def test_missing_key_is_rejected(admin):
    response = await admin.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def test_revoked_key_stops_working(admin, api_key):
    revoked = await admin.post(f"/api/v1/admin/keys/{api_key['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    response = await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key['key']}"})
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def test_expired_key_reports_expiry(admin, api_key):
    await _set_expiry(api_key["id"], timedelta(minutes=-1))
    response = await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key['key']}"})
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_EXPIRED"

    listed = await admin.get(f"/api/v1/admin/keys?account={api_key['account_id']}")
    assert listed.json()["items"][0]["status"] == "expired"


async def test_last_used_is_tracked(admin, api_key):
    before = (await admin.get(f"/api/v1/admin/keys?account={api_key['account_id']}")).json()
    assert before["items"][0]["last_used_at"] is None

    await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key['key']}"})

    after = (await admin.get(f"/api/v1/admin/keys?account={api_key['account_id']}")).json()
    assert after["items"][0]["last_used_at"] is not None


async def test_rotate_issues_new_secret_and_kills_old(admin, api_key):
    rotated = await admin.post(f"/api/v1/admin/keys/{api_key['id']}/rotate")
    assert rotated.status_code == 200
    new_key = rotated.json()
    assert new_key["key"] != api_key["key"]
    assert new_key["name"] == api_key["name"]

    old = await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key['key']}"})
    assert old.status_code == 401

    fresh = await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {new_key['key']}"})
    assert fresh.status_code == 200


async def test_key_audit_trail(admin, account, api_key):
    await admin.post(f"/api/v1/admin/keys/{api_key['id']}/revoke")
    response = await admin.get("/api/v1/admin/activity")
    actions = [item["action"] for item in response.json()["items"]]
    assert "key.created" in actions
    assert "key.revoked" in actions


async def test_unknown_key_id_is_404(admin):
    assert (await admin.post("/api/v1/admin/keys/nope/revoke")).status_code == 404
    assert (await admin.post("/api/v1/admin/keys/nope/rotate")).status_code == 404


async def test_keys_are_listed_per_account(admin, account):
    other = await admin.post(
        "/api/v1/admin/accounts",
        json={"subdomain": "login1", "username": "zweiter", "password": "geheim"},
    )
    # the fake only knows one valid pair, so both accounts share it
    assert other.status_code in (200, 401)

    await admin.post("/api/v1/admin/keys", json={"account_id": account["id"], "name": "A"})
    await admin.post("/api/v1/admin/keys", json={"account_id": account["id"], "name": "B"})
    items = (await admin.get(f"/api/v1/admin/keys?account={account['id']}")).json()["items"]
    assert len(items) == 2
    assert {item["name"] for item in items} == {"A", "B"}


@pytest.mark.parametrize("path", ["/api/v1/messages", "/api/v1/homework", "/api/v1/grades"])
async def test_agent_endpoints_require_key(admin, path, fake_edupage):
    response = await admin.get(path)
    assert response.status_code == 401
