from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.admin.accounts import router as admin_accounts_router
from .api.admin.auth import router as admin_auth_router
from .api.admin.keys import router as admin_keys_router
from .api.admin.system import router as admin_system_router
from .api.agent.router import router as agent_router
from .config import get_settings
from .db import get_session_factory

settings = get_settings()

FRONTEND_DIST = (
    settings.frontend_dist
    or Path(__file__).resolve().parents[2] / "frontend" / "dist"
).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .db import prepare_database

    await prepare_database()
    from .services.auth_admin import ensure_admin

    async with get_session_factory()() as db:
        await ensure_admin(db)
    yield


app = FastAPI(
    title="edupage-api",
    version="v1",
    lifespan=lifespan,
    description="Multi-Account-Gateway für EduPage, optimiert für KI-Agenten.",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

_origins = settings.cors_list()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        body = {"error": detail.get("error", ""), "code": detail["code"]}
    else:
        body = {"error": str(detail), "code": "VALIDATION" if exc.status_code < 500 else "UPSTREAM"}
    response = JSONResponse(body, status_code=exc.status_code)
    for name, value in (exc.headers or {}).items():
        response.headers[name] = value
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 body is `{detail: [...]}`; the API contract is `{error, code}`."""
    problems = exc.errors()
    message = "Ungültige Eingabe."
    if problems:
        first = problems[0]
        field = ".".join(str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path"))
        message = f"Ungültige Eingabe: {field} — {first.get('msg', 'ungültig')}" if field else message
    return JSONResponse({"error": message, "code": "VALIDATION"}, status_code=400)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    return JSONResponse({"error": "Interner Fehler.", "code": "UPSTREAM"}, status_code=500)


@app.get("/api/v1/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": "v1"}


@app.get("/api/v1/openapi.json", include_in_schema=False)
async def openapi_json():
    return app.openapi()


app.include_router(admin_auth_router, prefix="/api/v1")
app.include_router(admin_accounts_router, prefix="/api/v1")
app.include_router(admin_keys_router, prefix="/api/v1")
app.include_router(admin_system_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")

if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"error": "Nicht gefunden.", "code": "NOT_FOUND"}, status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
