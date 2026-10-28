from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import get_settings
from .db import get_engine
from .models import Base
from .api.admin.auth import router as admin_auth_router
from .api.admin.accounts import router as admin_accounts_router
from .api.admin.keys import router as admin_keys_router
from .api.admin.system import router as admin_system_router
from .api.agent.router import router as agent_router

app = FastAPI(title="edupage-api", version="v1")

s = get_settings()

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=s.cors_list() or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    # create tables (dev; alembic for prod)
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # ensure admin user
    from sqlalchemy.ext.asyncio import AsyncSession
    from .db import get_session_factory
    from .services.auth_admin import ensure_admin
    async with get_session_factory()() as db:
        await ensure_admin(db)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "v1"}


@app.get("/api/v1/openapi.json")
async def openapi():
    return app.openapi()


# Admin routers under /api/v1
app.include_router(admin_auth_router, prefix="/api/v1")
app.include_router(admin_accounts_router, prefix="/api/v1")
app.include_router(admin_keys_router, prefix="/api/v1")
app.include_router(admin_system_router, prefix="/api/v1")

# Agent router under /api/v1 (no prefix extra)
app.include_router(agent_router, prefix="/api/v1")

# Static frontend (if built)
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIST)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # serve index.html for client-side routes (but not api)
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        f = FRONTEND_DIST / full_path
        if f.is_file():
            return FileResponse(str(f))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
