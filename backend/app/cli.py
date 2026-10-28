"""Operator CLI: ``python -m app.cli <command>``.

Only touches local state; never prints credentials except a freshly generated
password, which is shown exactly once.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import sys

from .config import get_settings


def _hash(password: str) -> str:
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


def _session():
    from .db import get_session_factory

    return get_session_factory()()


async def reset_admin(username: str | None, password: str | None, generated: bool) -> int:
    """Set a new password for the admin account, or create it if missing."""
    from sqlalchemy import select

    from .models import AdminSession, AdminUser

    settings = get_settings()
    name = (username or settings.admin_username or "admin").strip()
    secret = password or secrets.token_urlsafe(16)

    session = _session()
    async with session:
        res = await session.execute(select(AdminUser).where(AdminUser.username == name))
        user = res.scalar_one_or_none()
        if user is None:
            user = AdminUser(username=name, password_hash=_hash(secret))
            session.add(user)
            print(f"Admin '{name}' wurde angelegt.")
        else:
            user.password_hash = _hash(secret)
            print(f"Passwort für '{name}' wurde geändert.")
        # Any open browser session must not survive a password reset.
        sessions = await session.execute(
            select(AdminSession).where(AdminSession.username == name)
        )
        revoked = 0
        from .core.time import utcnow

        for active in sessions.scalars().all():
            if active.revoked_at is None:
                active.revoked_at = utcnow()
                revoked += 1
        await session.commit()

    if revoked:
        print(f"{revoked} offene Admin-Sitzung(en) wurden abgemeldet.")
    if generated:
        print(f"Neues Passwort (wird nur jetzt angezeigt): {secret}")
        print("Trage es in ADMIN_PASSWORD ein oder bewahre es sicher auf.")
    return 0


async def list_accounts() -> int:
    from sqlalchemy import select

    from .models import Account

    session = _session()
    async with session:
        res = await session.execute(select(Account).order_by(Account.created_at))
        rows = res.scalars().all()
    if not rows:
        print("Keine Konten angelegt.")
        return 0
    for account in rows:
        label = account.alias or account.username
        print(f"{account.id}  {label:<24} {account.subdomain:<16} {account.status}")
    return 0


async def prune_cache() -> int:
    """Drop expired cache rows and stale pending 2FA challenges."""
    from sqlalchemy import delete, or_

    from .core.time import utcnow
    from .models import PendingSecondFactor, ResourceCache

    now = utcnow()
    session = _session()
    async with session:
        cache = await session.execute(delete(ResourceCache).where(ResourceCache.expires_at <= now))
        pending = await session.execute(
            delete(PendingSecondFactor).where(
                or_(PendingSecondFactor.expires_at <= now, PendingSecondFactor.consumed_at.is_not(None))
            )
        )
        await session.commit()
    print(f"{cache.rowcount or 0} Cache-Einträge und {pending.rowcount or 0} 2FA-Vorgänge entfernt.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="edupage-api Verwaltung")
    sub = parser.add_subparsers(dest="command", required=True)

    reset = sub.add_parser("reset-admin", help="Admin-Passwort neu setzen")
    reset.add_argument("--username", help="Standard: ADMIN_USERNAME aus der .env")
    reset.add_argument("--password", help="Neues Passwort (sonst wird eins generiert)")
    reset.add_argument(
        "--stdin",
        action="store_true",
        help="Passwort interaktiv abfragen statt generieren",
    )

    sub.add_parser("list-accounts", help="Angelegte EduPage-Konten anzeigen")
    sub.add_parser("prune-cache", help="Abgelaufene Cache- und 2FA-Einträge löschen")

    args = parser.parse_args(argv)

    if args.command == "reset-admin":
        password = args.password
        if args.stdin and not password:
            password = getpass.getpass("Neues Passwort: ")
            confirm = getpass.getpass("Wiederholen: ")
            if password != confirm:
                print("Passwörter stimmen nicht überein.", file=sys.stderr)
                return 2
            if len(password) < 8:
                print("Passwort muss mindestens 8 Zeichen haben.", file=sys.stderr)
                return 2
        return asyncio.run(reset_admin(args.username, password, generated=password is None))
    if args.command == "list-accounts":
        return asyncio.run(list_accounts())
    if args.command == "prune-cache":
        return asyncio.run(prune_cache())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
