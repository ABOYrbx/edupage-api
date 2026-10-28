from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException

from ..config import get_settings
from ..core.errors import api_error
from ..edupage import pending as pending_store
from ..edupage.provider import LIBRARY_AVAILABLE, new_client
from ..models import Account, CredentialVault, PendingSecondFactor, ResourceCache
from .vault import open_sealed, seal
from ..core.time import utcnow

PENDING_TTL = timedelta(minutes=10)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _domain(subdomain: str) -> str:
    return subdomain if "." in subdomain else f"{subdomain}.edupage.org"


def _capture_cookies(client) -> dict[str, str]:
    sub = getattr(client, "subdomain", None) or ""
    try:
        return dict(client.session.cookies.get_dict(_domain(sub)))
    except Exception:  # pragma: no cover - defensive
        return {}


def _restore_cookies(client, subdomain: str, cookies: dict[str, str]) -> None:
    for name, value in cookies.items():
        client.session.cookies.set(name, value, domain=_domain(subdomain))


class AccountService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ reads

    async def list_accounts(self) -> list[dict]:
        res = await self.db.execute(select(Account).order_by(Account.created_at.desc()))
        return [await self._account_dict(a) for a in res.scalars().all()]

    async def get(self, account_id: str) -> Account | None:
        res = await self.db.execute(select(Account).where(Account.id == account_id))
        return res.scalar_one_or_none()

    # ----------------------------------------------------------------- writes

    async def add(self, alias: str | None, subdomain: str, username: str, password: str) -> dict:
        alias = (alias or "").strip()[:80] or None
        subdomain = (subdomain or "login1").strip().lower()
        username = (username or "").strip()
        if not username or not password:
            raise api_error("VALIDATION", "Benutzername und Passwort erforderlich.")
        if not LIBRARY_AVAILABLE:
            raise api_error("CONFIG_MISSING", "edupage-api Bibliothek nicht installiert.")

        client = new_client()
        two_factor = self._login(client, username, password, subdomain)
        if two_factor is not None:
            return await self._park_2fa(client, two_factor, alias, username, password, subdomain)

        account = await self._store_account(alias, client.subdomain or subdomain, username, password)
        await self._audit(account.id, "account.added", "ok", f"subdomain={account.subdomain}")
        await self.db.commit()
        return {"status": "ok", "account": await self._account_dict(account)}

    def _login(self, client, username: str, password: str, subdomain: str):
        from edupage_api.exceptions import BadCredentialsException, CaptchaException

        try:
            return client.login(username, password, subdomain)
        except BadCredentialsException:
            raise api_error("BAD_CREDENTIALS")
        except CaptchaException:
            raise api_error("CAPTCHA_REQUIRED")
        except Exception as exc:  # noqa: BLE001 - upstream failures are all 502
            raise api_error("UPSTREAM", f"Login fehlgeschlagen: {exc}")

    async def _park_2fa(self, client, two_factor, alias, username, password, subdomain) -> dict:
        pending_token = secrets.token_urlsafe(32)
        real_subdomain = getattr(client, "subdomain", None) or subdomain
        payload = {
            "alias": alias,
            "username": username,
            "password": password,
            "subdomain": real_subdomain,
            "cookies": _capture_cookies(client),
        }
        token_hash = _hash_token(pending_token)
        ciphertext, nonce = seal(json.dumps(payload))
        self.db.add(
            PendingSecondFactor(
                opaque_token_hash=token_hash,
                challenge={"ciphertext": _b64(ciphertext), "nonce": _b64(nonce)},
                expires_at=utcnow() + PENDING_TTL,
            )
        )
        pending_store.put(token_hash, client, two_factor, int(PENDING_TTL.total_seconds()))
        await self.db.commit()
        return {
            "status": "2fa_required",
            "pending_token": pending_token,
            "pending_expires_in": int(PENDING_TTL.total_seconds()),
            "message": "EduPage verlangt einen Zwei-Faktor-Code.",
        }

    async def finish_2fa(self, pending_token: str, code: str) -> dict:
        code = (code or "").strip()
        if not code:
            raise api_error("VALIDATION", "Code erforderlich.")
        token_hash = _hash_token(pending_token)
        res = await self.db.execute(
            select(PendingSecondFactor).where(
                PendingSecondFactor.opaque_token_hash == token_hash
            )
        )
        pending = res.scalar_one_or_none()
        if (
            pending is None
            or pending.consumed_at is not None
            or pending.expires_at <= utcnow()
        ):
            raise api_error("PENDING_INVALID")
        if not LIBRARY_AVAILABLE:
            raise api_error("CONFIG_MISSING")

        challenge = pending.challenge or {}
        payload = json.loads(
            open_sealed(_unb64(challenge["ciphertext"]), _unb64(challenge["nonce"]))
        )

        from edupage_api.exceptions import SecondFactorFailedException

        live = pending_store.get(token_hash)
        if live is not None:
            client, two_factor = live
        else:
            # The process restarted between the two steps: rebuild the 2FA page.
            from edupage_api.twofactor import TwoFactorLogin

            client = new_client()
            client.subdomain = payload["subdomain"]
            client.username = payload["username"]
            _restore_cookies(client, payload["subdomain"], payload.get("cookies") or {})
            page = client.session.get(
                f"https://{payload['subdomain']}.edupage.org/login/twofactor?sn=1"
            )
            two_factor = TwoFactorLogin.from_page(client, page.content.decode())
            if two_factor is None:
                raise api_error("PENDING_INVALID", "Zwei-Faktor-Sitzung abgelaufen.")

        try:
            two_factor.finish_with_code(code)
        except SecondFactorFailedException:
            raise api_error("INVALID_CODE")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise api_error("UPSTREAM", f"2FA fehlgeschlagen: {exc}")

        pending.consumed_at = utcnow()
        pending_store.drop(token_hash)
        account = await self._store_account(
            payload.get("alias"), payload["subdomain"], payload["username"], payload["password"]
        )
        await self._audit(account.id, "account.added", "ok", "2fa")
        await self.db.commit()
        return {"status": "ok", "account": await self._account_dict(account)}

    async def _store_account(self, alias, subdomain, username, password) -> Account:
        res = await self.db.execute(
            select(Account).where(Account.subdomain == subdomain, Account.username == username)
        )
        account = res.scalar_one_or_none()
        if account is None:
            account = Account(alias=alias, subdomain=subdomain, username=username, status="ok")
            self.db.add(account)
            await self.db.flush()
        else:
            account.alias = alias or account.alias
            account.status = "ok"
            account.last_error = None

        ciphertext, nonce = seal(password)
        res = await self.db.execute(
            select(CredentialVault).where(CredentialVault.account_id == account.id)
        )
        vault = res.scalar_one_or_none()
        if vault is None:
            self.db.add(CredentialVault(account_id=account.id, ciphertext=ciphertext, nonce=nonce))
        else:
            vault.ciphertext = ciphertext
            vault.nonce = nonce
        return account

    async def delete(self, account_id: str) -> None:
        account = await self.get(account_id)
        if account is None:
            raise api_error("NOT_FOUND")
        await self.db.execute(delete(Account).where(Account.id == account_id))
        await self.db.commit()
        from ..edupage.session_cache import drop as drop_session

        drop_session(account_id)

    # ------------------------------------------------------------ credentials

    async def password_for(self, account: Account) -> str:
        res = await self.db.execute(
            select(CredentialVault).where(CredentialVault.account_id == account.id)
        )
        vault = res.scalar_one_or_none()
        if vault is None:
            raise api_error("CONFIG_MISSING", "Für dieses Konto sind keine Zugangsdaten gespeichert.")
        return open_sealed(vault.ciphertext, vault.nonce)

    # ------------------------------------------------------------------ admin

    async def test_account(self, account_id: str) -> dict:
        account = await self.get(account_id)
        if account is None:
            raise api_error("NOT_FOUND")
        from ..edupage.session_cache import drop as drop_session

        from edupage_api.exceptions import BadCredentialsException, CaptchaException

        try:
            password = await self.password_for(account)
            client = new_client()
            two_factor = client.login(account.username, password, account.subdomain)
            if two_factor is not None:
                account.status = "2fa_required"
                account.last_error = "EduPage verlangt einen Zwei-Faktor-Code."
            else:
                account.status = "ok"
                account.last_error = None
                drop_session(account.id)
        except BadCredentialsException:
            account.status = "login_failed"
            account.last_error = "Benutzername oder Passwort ist falsch."
        except CaptchaException:
            account.status = "login_failed"
            account.last_error = "EduPage verlangt ein Captcha."
        except HTTPException as exc:
            account.status = "login_failed"
            account.last_error = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else str(exc.detail)
        except Exception as exc:  # noqa: BLE001
            account.status = "login_failed"
            account.last_error = str(exc)[:500]
        account.last_used_at = utcnow()
        await self.db.commit()
        await self._audit(account.id, "account.tested", account.status, account.last_error)
        return await self._account_dict(account)

    async def refresh(self, account_id: str) -> dict:
        account = await self.get(account_id)
        if account is None:
            raise api_error("NOT_FOUND")
        await self.db.execute(delete(ResourceCache).where(ResourceCache.account_id == account_id))
        await self.db.commit()
        from ..edupage.session_cache import drop as drop_session

        drop_session(account_id)
        return await self.test_account(account_id)

    # ------------------------------------------------------------------ utils

    async def _account_dict(self, account: Account) -> dict:
        from ..models import ApiKey

        res = await self.db.execute(
            select(ApiKey).where(ApiKey.account_id == account.id)
        )
        keys = list(res.scalars().all())
        now = utcnow()
        return {
            "id": account.id,
            "alias": account.alias,
            "subdomain": account.subdomain,
            "username": account.username,
            "status": account.status,
            "last_error": account.last_error,
            "last_used_at": account.last_used_at.isoformat() if account.last_used_at else None,
            "created_at": account.created_at.isoformat(),
            "key_count": len(keys),
            "active_key_count": sum(
                1 for k in keys if k.revoked_at is None and k.expires_at > now
            ),
        }

    async def _audit(self, account_id: str | None, action: str, outcome: str, detail: str | None) -> None:
        from ..models import AuditEvent

        self.db.add(
            AuditEvent(
                account_id=account_id,
                actor="admin",
                action=action,
                outcome=outcome,
                detail=detail,
            )
        )
