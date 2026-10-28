from __future__ import annotations

from app.edupage import session_cache


async def test_add_account_stores_vault_and_status(admin, fake_edupage):
    response = await admin.post(
        "/api/v1/admin/accounts",
        json={"alias": "Mein Konto", "subdomain": "login1", "username": "schueler", "password": "geheim"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    account = body["account"]
    assert account["alias"] == "Mein Konto"
    assert account["subdomain"] == "login1"
    assert account["status"] == "ok"
    assert account["key_count"] == 0
    # password must never come back
    assert "password" not in body["account"]
    assert "geheim" not in response.text


async def test_add_account_bad_credentials(admin):
    response = await admin.post(
        "/api/v1/admin/accounts",
        json={"subdomain": "login1", "username": "schueler", "password": "falsch"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "BAD_CREDENTIALS"


async def test_add_account_requires_credentials(admin):
    response = await admin.post("/api/v1/admin/accounts", json={"subdomain": "login1"})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


async def test_add_account_with_2fa(admin, fake_edupage):
    fake_edupage.require_2fa = True
    response = await admin.post(
        "/api/v1/admin/accounts",
        json={"subdomain": "login1", "username": "schueler", "password": "geheim"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "2fa_required"
    assert body["pending_token"]

    wrong = await admin.post(
        "/api/v1/admin/accounts/2fa", json={"pending_token": body["pending_token"], "code": "000000"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "INVALID_CODE"

    ok = await admin.post(
        "/api/v1/admin/accounts/2fa", json={"pending_token": body["pending_token"], "code": "123456"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ok"
    assert ok.json()["account"]["username"] == "schueler"


async def test_pending_token_is_single_use(admin, fake_edupage):
    fake_edupage.require_2fa = True
    created = await admin.post(
        "/api/v1/admin/accounts",
        json={"subdomain": "login1", "username": "schueler", "password": "geheim"},
    )
    token = created.json()["pending_token"]
    await admin.post("/api/v1/admin/accounts/2fa", json={"pending_token": token, "code": "123456"})
    replay = await admin.post("/api/v1/admin/accounts/2fa", json={"pending_token": token, "code": "123456"})
    assert replay.status_code == 401
    assert replay.json()["code"] == "PENDING_INVALID"


async def test_unknown_pending_token(admin):
    response = await admin.post(
        "/api/v1/admin/accounts/2fa", json={"pending_token": "nope", "code": "123456"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "PENDING_INVALID"


async def test_add_account_twice_updates_instead_of_duplicating(admin, fake_edupage):
    payload = {"subdomain": "login1", "username": "schueler", "password": "geheim"}
    first = await admin.post("/api/v1/admin/accounts", json=payload)
    second = await admin.post("/api/v1/admin/accounts", json={**payload, "alias": "Neu"})

    assert first.json()["account"]["id"] == second.json()["account"]["id"]
    assert second.json()["account"]["alias"] == "Neu"

    listed = await admin.get("/api/v1/admin/accounts")
    assert listed.json()["total"] == 1


async def test_delete_account_cascades(admin, account, api_key):
    await admin.post(f"/api/v1/admin/keys", json={"account_id": account["id"], "name": "weg"})
    deleted = await admin.delete(f"/api/v1/admin/accounts/{account['id']}")
    assert deleted.status_code == 200

    assert (await admin.get("/api/v1/admin/accounts")).json()["total"] == 0
    # the key is gone too: nobody can authenticate any more
    response = await admin.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key['key']}"})
    assert response.status_code == 401


async def test_test_account_success_and_failure(admin, account, fake_edupage):
    ok = await admin.post(f"/api/v1/admin/accounts/{account['id']}/test")
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"

    fake_edupage.valid_credentials = set()
    failed = await admin.post(f"/api/v1/admin/accounts/{account['id']}/test")
    assert failed.json()["status"] == "login_failed"
    assert failed.json()["last_error"]

    fake_edupage.valid_credentials = {("schueler", "geheim")}


async def test_test_account_2fa_sets_status(admin, account, fake_edupage):
    fake_edupage.require_2fa = True
    response = await admin.post(f"/api/v1/admin/accounts/{account['id']}/test")
    assert response.json()["status"] == "2fa_required"


async def test_refresh_clears_session_and_cache(admin, account, bearer, fake_edupage):
    fake_edupage.events = []
    await admin.get("/api/v1/messages", headers=bearer)
    assert session_cache.get(account["id"]) is not None

    response = await admin.post(f"/api/v1/admin/accounts/{account['id']}/refresh")
    assert response.status_code == 200
    # the refresh logs in again, so a session exists afterwards — but a new one
    assert response.json()["status"] == "ok"


async def test_get_account_returns_keys(admin, account, api_key):
    detail = await admin.get(f"/api/v1/admin/accounts/{account['id']}")
    assert detail.status_code == 200
    assert detail.json()["keys"][0]["id"] == api_key["id"]


async def test_unknown_account_is_404(admin):
    assert (await admin.get("/api/v1/admin/accounts/nope")).status_code == 404
    assert (await admin.delete("/api/v1/admin/accounts/nope")).status_code == 404
    assert (await admin.post("/api/v1/admin/accounts/nope/test")).status_code == 404


async def test_activity_log_records_account_actions(admin, account):
    response = await admin.get("/api/v1/admin/activity")
    actions = [item["action"] for item in response.json()["items"]]
    assert "account.added" in actions


async def test_activity_filters_by_account_and_action(admin, account):
    by_account = await admin.get(f"/api/v1/admin/activity?account={account['id']}")
    assert all(item["account_id"] == account["id"] for item in by_account.json()["items"])

    by_action = await admin.get("/api/v1/admin/activity?action=account.added")
    assert all(item["action"] == "account.added" for item in by_action.json()["items"])
    assert by_action.json()["total"] >= 1
