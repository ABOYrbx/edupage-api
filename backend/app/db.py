from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

_engine = None
_session_factory = None

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def get_engine():
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_async_engine(s.database_url, echo=False, future=True)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _session_factory


async def get_db():
    async with get_session_factory()() as session:
        yield session


# --------------------------------------------------------------- migrations


def _alembic_config():
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def _run_alembic(action: str) -> None:
    """Run Alembic in a worker thread (its env.py drives its own event loop)."""
    from alembic import command

    config = _alembic_config()
    command.upgrade(config, "head") if action == "upgrade" else command.stamp(config, "head")


async def _table_names() -> set[str]:
    async with get_engine().connect() as conn:
        return set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))


async def _create_missing_tables() -> None:
    """Add tables a legacy ``create_all`` database never got (checkfirst, no drops)."""
    from .models import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def prepare_database() -> None:
    """Bring the schema to ``head``.

    A database created by the old ``create_all`` bootstrap has tables but no
    ``alembic_version``. It is adopted instead of migrated: missing tables are
    created and the version table is stamped, so no data is lost and later
    migrations apply normally.
    """
    loop = asyncio.get_running_loop()
    tables = await _table_names()
    if not tables:
        await loop.run_in_executor(None, _run_alembic, "upgrade")
        return
    if "alembic_version" in tables:
        await loop.run_in_executor(None, _run_alembic, "upgrade")
        return
    await _create_missing_tables()
    await loop.run_in_executor(None, _run_alembic, "stamp")
