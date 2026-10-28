import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "version": "v1"}


@pytest.mark.asyncio
async def test_admin_login_bad():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/admin/login", json={"password": "wrong"})
        assert r.status_code == 401
