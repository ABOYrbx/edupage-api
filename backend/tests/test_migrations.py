from __future__ import annotations

from sqlalchemy import create_engine, inspect


def _sync_url(async_url: str) -> str:
    return async_url.replace("+aiosqlite", "")


def _tables(url: str) -> set[str]:
    engine = create_engine(_sync_url(url))
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


async def test_fresh_database_reaches_head(tmp_path, monkeypatch):
    from app import db as app_db
    from app.config import get_settings
    from app.models import Base

    url = f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(app_db, "_engine", None)
    monkeypatch.setattr(app_db, "_session_factory", None)
    get_settings.cache_clear()
    try:
        await app_db.prepare_database()
        tables = _tables(url)
        assert set(Base.metadata.tables) <= tables
        assert "alembic_version" in tables
    finally:
        await app_db.get_engine().dispose()
        get_settings.cache_clear()


async def test_legacy_create_all_database_is_adopted(tmp_path, monkeypatch):
    """A DB from the old ``create_all`` bootstrap has no version table and may
    lack tables added since. Adoption must add them and stamp, not crash."""
    from app import db as app_db
    from app.config import get_settings
    from app.models import Base

    url = f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}"

    legacy_tables = [
        table for name, table in Base.metadata.tables.items() if name != "homework_flags"
    ]
    engine = create_engine(_sync_url(url))
    Base.metadata.create_all(engine, tables=legacy_tables)
    engine.dispose()
    assert "homework_flags" not in _tables(url)

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(app_db, "_engine", None)
    monkeypatch.setattr(app_db, "_session_factory", None)
    get_settings.cache_clear()
    try:
        await app_db.prepare_database()
        tables = _tables(url)
        assert "homework_flags" in tables
        assert "alembic_version" in tables

        # a second start takes the normal upgrade path
        await app_db.get_engine().dispose()
        monkeypatch.setattr(app_db, "_engine", None)
        monkeypatch.setattr(app_db, "_session_factory", None)
        await app_db.prepare_database()
        assert set(Base.metadata.tables) <= _tables(url)
    finally:
        await app_db.get_engine().dispose()
        get_settings.cache_clear()


async def test_vault_key_file_is_shared_by_every_process(tmp_path, monkeypatch):
    """Docker persists the vault key to a file; a second process (e.g. `compose exec`)
    must read the same key instead of generating a random one."""
    from app.config import Settings

    key_file = tmp_path / "credential.key"
    key_file.write_text("a" * 64 + "\n")

    writer = Settings(credential_encryption_key="", credential_encryption_key_file=key_file, _env_file=None)
    other = Settings(credential_encryption_key="", credential_encryption_key_file=key_file, _env_file=None)
    assert writer.encryption_key_bytes() == other.encryption_key_bytes()
    assert writer.encryption_key_bytes() == bytes.fromhex("a" * 64)


def test_env_var_wins_over_key_file(tmp_path):
    from app.config import Settings

    key_file = tmp_path / "credential.key"
    key_file.write_text("b" * 64)
    settings = Settings(
        credential_encryption_key="c" * 64,
        credential_encryption_key_file=key_file,
        _env_file=None,
    )
    assert settings.encryption_key_bytes() == bytes.fromhex("c" * 64)


def test_missing_key_file_falls_back_to_random_key(tmp_path):
    from app.config import Settings

    settings = Settings(
        credential_encryption_key="",
        credential_encryption_key_file=tmp_path / "absent.key",
        _env_file=None,
    )
    key = settings.encryption_key_bytes()
    assert len(key) == 32
