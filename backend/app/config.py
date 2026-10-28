from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/edupage-api.db"
    credential_encryption_key: str = ""
    # File the key is read from when CREDENTIAL_ENCRYPTION_KEY is empty. The Docker
    # entrypoint persists the generated key here so every process (including
    # `docker compose exec`) sees the same one.
    credential_encryption_key_file: Path | None = None
    admin_username: str = "admin"
    admin_password: str = ""
    host: str = "0.0.0.0"
    port: int = 8787
    cors_origins: str = ""
    admin_login_limit: str = "20/10minute"
    agent_limit: str = "120/minute"

    # Optional: enables /wetter and /wetter/suche for agents.
    openweather_api_key: str = ""

    # Set to true when the service runs behind HTTPS (Secure cookies).
    cookie_secure: bool = False

    cache_ttl_messages: int = 900
    cache_ttl_grades: int = 3600
    cache_ttl_timetable: int = 3600
    cache_ttl_weather: int = 300
    session_cache_ttl: int = 300

    data_dir: Path = Field(default=Path("./data"))

    # Where the built SPA lives. Empty = <repo>/frontend/dist (sibling of backend/).
    frontend_dist: Path | None = None

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def encryption_key_bytes(self) -> bytes:
        raw = self.credential_encryption_key.strip()
        if not raw and self.credential_encryption_key_file is not None:
            # Docker: the entrypoint wrote the key to disk on first start.
            try:
                raw = self.credential_encryption_key_file.read_text().strip()
            except OSError:
                raw = ""
        if not raw:
            # Auto-generate on first run; persisted only if caller writes it.
            raw = secrets.token_hex(32)
            self.credential_encryption_key = raw
        if len(raw) == 64:
            try:
                return bytes.fromhex(raw)
            except ValueError:
                pass
        # Allow base64-ish 32-byte keys
        import base64

        try:
            b = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            if len(b) == 32:
                return b
        except Exception:
            pass
        raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be 32 bytes (64 hex chars)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
