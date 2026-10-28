from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, CredentialVault, PendingSecondFactor, ResourceCache, ApiKey
from ..services.vault import seal, open_sealed
from ..core.errors import api_error
from ..config import get_settings

try:
    from edupage_api import Edupage
    from edupage_api.exceptions import (
        BadCredentialsException, CaptchaException, SecondFactorFailedException,
    )
    _EDUPAGE_AVAILABLE = True
except Exception:  # pragma: no cover
    _EDUPAGE_AVAILABLE = False
    Edupage = None


def _now() -> datetime:
    return datetime.utcnow()


class AccountService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_accounts(self) -> list[Account]:
        res = await self.db.execute(select(Account).order_by(Account.created_at.desc()))
        return list(res.scalars().all())

    async def get(self, account_id: str) -> Account | None:
        res = await self.db.execute(select(Account).where(Account.id == account_id))
        return res.scalar_one_or_none()

    async def delete(self, account_id: str) -> None:
        await self.db.execute(delete(Account).where(Account.id == account_id))
        await self.db.commit()

    async def add(self, alias: str | None, subdomain: str, username: str, password: str) -> dict:
        # Test login
        subdomain = (subdomain or "login1").strip().lower()
        if not _EDUPAGE_AVAILABLE:
            raise api_error("CONFIG_MISSING", "edupage-api Bibliothek nicht installiert")
        ep = Edupage()
        try:
            tf = ep.login(username, password, subdomain)
        except BadCredentialsException:
            raise api_error("BAD_CREDENTIALS")
        except CaptchaException:
            raise api_error("CAPTCHA_REQUIRED")
        except Exception as e:
            raise api_error("UPSTREAM", str(e))
        if tf is not None:
            # 2FA required: store pending, return pending_token
            pending_token = __import__("secrets").token_urlsafe(24)
            from ..core import rate_limit  # noqa
            import hashlib
            th = hashlib.sha256(pending_token.encode()).hexdigest()
            challenge = {
                "kind": "edupage",
                "subdomain": ep.subdomain,
                "username": username,
                "cookies": dict(ep.session.cookies) if hasattr(ep.session, "cookies") else {},
                "fields": None,
            }
            # The edupage lib's TwoFactorLogin holds cookies internally; we store the ep object state via cookies only.
            # For completion we need the TwoFactorLogin object; we instead store enough to re-login? Simpler: store pending token + re-create login on finish.
            # Approach: store pending with challenge containing username/password/subdomain to redo login in finish step.
            challenge = {
                "kind": "edupage",
                "subdomain": subdomain,
                "username": username,
                "password": password,
                "real_subdomain": ep.subdomain,
            }
            psf = PendingSecondFactor(
                opaque_token_hash=th,
                challenge=challenge,
                expires_at=datetime.utcnow() + timedelta(minutes=10),
            )
            self.db.add(psf)
            await self.db.commit()
            return {"status": "2fa_required", "pending_token": pending_token, "message": "Zwei-Faktor-Authentifizierung erforderlich."}
        # OK: store account
        account = await self._store_account(alias, ep.subdomain or subdomain, username, password)
        await self.db.commit()
        return {"status": "ok", "account": self._account_dict(account)}

    async def finish_2fa(self, pending_token: str, code: str) -> dict:
        import hashlib
        th = hashlib.sha256(pending_token.encode()).hexdigest()
        res = await self.db.execute(select(PendingSecondFactor).where(PendingSecondFactor.opaque_token_hash == th))
        psf = res.scalar_one_or_none()
        if not psf or psf.consumed_at is not None or psf.expires_at <= datetime.utcnow():
            raise api_error("PENDING_INVALID")
        ch = psf.challenge if isinstance(psf.challenge, dict) else json.loads(psf.challenge)
        if not _EDUPAGE_AVAILABLE:
            raise api_error("CONFIG_MISSING")
        ep = Edupage()
        try:
            tf = ep.login(ch["username"], ch["password"], ch["subdomain"])
        except Exception as e:
            raise api_error("UPSTREAM", str(e))
        if tf is None:
            # no 2fa needed anymore
            psf.consumed_at = datetime.utcnow()
            account = await self._store_account(None, ep.subdomain or ch["subdomain"], ch["username"], ch["password"])
            await self.db.commit()
            return {"status": "ok", "account": self._account_dict(account)}
        try:
            tf.finish_with_code(code)
        except SecondFactorFailedException:
            raise api_error("INVALID_CODE")
        except Exception as e:
            raise api_error("UPSTREAM", str(e))
        psf.consumed_at = datetime.utcnow()
        real_sub = ep.subdomain or ch.get("real_subdomain") or ch["subdomain"]
        account = await self._store_account(None, real_sub, ch["username"], ch["password"])
        await self.db.commit()
        return {"status": "ok", "account": self._account_dict(account)}

    async def _store_account(self, alias, subdomain, username, password) -> Account:
        # upsert by subdomain+username
        res = await self.db.execute(select(Account).where(Account.subdomain == subdomain, Account.username == username))
        account = res.scalar_one_or_none()
        if account is None:
            account = Account(alias=alias, subdomain=subdomain, username=username, status="ok")
            self.db.add(account)
            await self.db.flush()
        else:
            account.alias = alias or account.alias
            account.status = "ok"
            account.last_error = None
        ct, nonce = seal(password)
        # upsert vault
        if account.vault is None:
            v = CredentialVault(account_id=account.id, ciphertext=ct, nonce=nonce)
            self.db.add(v)
        else:
            account.vault.ciphertext = ct
            account.vault.nonce = nonce
        return account

    def _account_dict(self, a: Account) -> dict:
        return {
            "id": a.id,
            "alias": a.alias,
            "subdomain": a.subdomain,
            "username": a.username,
            "status": a.status,
            "last_used_at": a.last_used_at.isoformat() if a.last_used_at else None,
            "created_at": a.created_at.isoformat(),
            "key_count": len(a.keys) if a.keys else 0,
        }

    async def test_account(self, account_id: str) -> dict:
        a = await self.get(account_id)
        if not a:
            raise api_error("NOT_FOUND")
        try:
            await self.login_for(a)
            a.status = "ok"
            a.last_error = None
        except Exception as e:
            a.status = "login_failed"
            a.last_error = str(e)[:500]
        a.last_used_at = datetime.utcnow()
        await self.db.commit()
        return self._account_dict(a)

    async def login_for(self, account: Account):
        """Returns an edupage Edupage instance logged in for this account."""
        if account.vault is None:
            raise api_error("CONFIG_MISSING")
        from ..services.vault import open_sealed
        password = open_sealed(account.vault.ciphertext, account.vault.nonce)
        if not _EDUPAGE_AVAILABLE:
            raise api_error("CONFIG_MISSING")
        ep = Edupage()
        tf = ep.login(account.username, password, account.subdomain)
        if tf is not None:
            # 2FA required at runtime -> cannot auto
            raise api_error("EDUPAGE_2FA")
        account.last_used_at = datetime.utcnow()
        return ep

    async def refresh(self, account_id: str) -> dict:
        a = await self.get(account_id)
        if not a:
            raise api_error("NOT_FOUND")
        # clear cache
        await self.db.execute(delete(ResourceCache).where(ResourceCache.account_id == account_id))
        await self.db.commit()
        return await self.test_account(account_id)
