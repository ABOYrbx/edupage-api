from __future__ import annotations

import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings


def seal(plaintext: str) -> tuple[bytes, bytes]:
    key = get_settings().encryption_key_bytes()
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ct, nonce


def open_sealed(ciphertext: bytes, nonce: bytes) -> str:
    key = get_settings().encryption_key_bytes()
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext, None).decode("utf-8")


def new_key() -> str:
    return secrets.token_hex(32)
