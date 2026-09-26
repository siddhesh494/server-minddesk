"""Fernet helpers for optional per-business WhatsApp access tokens."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


def _fernet(settings: Settings) -> Fernet:
    raw = (settings.whatsapp_encryption_key or settings.jwt_secret_key).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None, settings: Settings) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return _fernet(settings).encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None, settings: Settings) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return _fernet(settings).decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
