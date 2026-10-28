from __future__ import annotations

import asyncio
import os
import secrets
import tempfile
from pathlib import Path

import pytest

# Configure an isolated database *before* the app modules import settings.
_TMPDIR = Path(tempfile.mkdtemp(prefix="edupage-api-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMPDIR / 'test.db'}"
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "0" * 64)
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")

ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    """Run the real migration path once, then reset the engine for each test loop."""
    from app import db as app_db
    from app.services.auth_admin import ensure_admin

    async def setup():
        await app_db.prepare_database()
        async with app_db.get_session_factory()() as session:
            await ensure_admin(session)
        await app_db.get_engine().dispose()

    asyncio.run(setup())
    app_db._engine = None
    app_db._session_factory = None
    yield _TMPDIR


@pytest.fixture(autouse=True)
def fake_edupage(monkeypatch):
    """Swap the EduPage client for the offline fake and reset its state."""
    from app.edupage import provider, session_cache
    from tests import fake_edupage as fake

    fake.FakeEdupage.instances = []
    fake.FakeEdupage.require_2fa = False
    fake.FakeEdupage.events = []
    fake.FakeEdupage.grades = []
    fake.FakeEdupage.meals = None
    fake.FakeEdupage.valid_credentials = {("schueler", "geheim")}
    provider.set_client_factory(fake.FakeEdupage)
    session_cache.clear()
    from app.services.cache import CacheService

    CacheService.mem_clear()
    yield fake.FakeEdupage
    provider.set_client_factory(None)
    session_cache.clear()


@pytest.fixture(autouse=True)
def reset_database():
    """Clear every table between tests so fixtures start from a clean slate."""
    from sqlalchemy import delete

    from app import db as app_db
    from app.models import (
        Account,
        AdminSession,
        ApiKey,
        AuditEvent,
        CredentialVault,
        HomeworkFlag,
        PendingSecondFactor,
        ResourceCache,
    )

    async def wipe():
        async with app_db.get_session_factory()() as session:
            for model in (
                ResourceCache,
                HomeworkFlag,
                ApiKey,
                AuditEvent,
                PendingSecondFactor,
                CredentialVault,
                AdminSession,
                Account,
            ):
                await session.execute(delete(model))
            await session.commit()

    asyncio.run(wipe())
    from app.core.rate_limit import reset as reset_limits

    reset_limits()
    yield


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def admin(client):
    """A client that is logged in as admin (cookies + CSRF header applied)."""
    response = await client.post("/api/v1/admin/login", json={"password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("epa_csrf")
    client.headers["X-CSRF-Token"] = csrf
    return client


@pytest.fixture
async def account(admin):
    response = await admin.post(
        "/api/v1/admin/accounts",
        json={"alias": "Testkonto", "subdomain": "login1", "username": "schueler", "password": "geheim"},
    )
    assert response.status_code == 200, response.text
    return response.json()["account"]


@pytest.fixture
async def api_key(admin, account):
    response = await admin.post(
        "/api/v1/admin/keys",
        json={"account_id": account["id"], "name": "Agent", "expires_in_days": 30},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def bearer(api_key):
    return {"Authorization": f"Bearer {api_key['key']}"}


def unique_username() -> str:
    return f"user-{secrets.token_hex(4)}"
