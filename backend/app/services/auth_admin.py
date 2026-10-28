from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AdminSession, AdminUser
from ..config import get_settings
from ..core.time import utcnow


def hash_token(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


async def ensure_admin(db: AsyncSession) -> AdminUser:
    """Create the single admin on first start; the env password is used only then."""
    s = get_settings()
    res = await db.execute(select(AdminUser).where(AdminUser.username == s.admin_username))
    user = res.scalar_one_or_none()
    if user is not None:
        return user

    from argon2 import PasswordHasher

    ph = PasswordHasher()
    password = s.admin_password or secrets.token_urlsafe(16)
    user = AdminUser(username=s.admin_username, password_hash=ph.hash(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    if not s.admin_password:
        # Only an auto-generated password is ever echoed, and only once.
        print(
            f"[edupage-api] Admin '{user.username}' angelegt. Einmalpasswort: {password}\n"
            "[edupage-api] Setze ADMIN_PASSWORD in der .env oder nutze 'python -m app.cli reset-admin'."
        )
    return user


async def login(db: AsyncSession, username: str, password: str) -> tuple[str, str] | None:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    res = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = res.scalar_one_or_none()
    if user is None:
        return None
    ph = PasswordHasher()
    try:
        ph.verify(user.password_hash, password)
    except VerifyMismatchError:
        return None
    # upgrade hash if needed
    if ph.check_needs_rehash(user.password_hash):
        user.password_hash = ph.hash(password)

    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    sess = AdminSession(
        token_hash=hash_token(token),
        username=user.username,
        csrf_token=csrf,
        expires_at=utcnow() + timedelta(hours=8),
    )
    db.add(sess)
    user.last_login_at = utcnow()
    await db.commit()
    return token, csrf


async def authenticate(db: AsyncSession, raw_token: str) -> AdminSession | None:
    res = await db.execute(select(AdminSession).where(AdminSession.token_hash == hash_token(raw_token)))
    sess = res.scalar_one_or_none()
    if not sess or sess.revoked_at is not None or sess.expires_at <= utcnow():
        return None
    return sess


async def revoke(db: AsyncSession, raw_token: str) -> None:
    res = await db.execute(select(AdminSession).where(AdminSession.token_hash == hash_token(raw_token)))
    sess = res.scalar_one_or_none()
    if sess and sess.revoked_at is None:
        sess.revoked_at = utcnow()
        await db.commit()
