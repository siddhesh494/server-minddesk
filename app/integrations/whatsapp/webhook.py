"""Meta webhook verification and X-Hub-Signature-256 checks."""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def verify_subscription(mode: str | None, token: str | None, challenge: str | None, settings: Settings) -> str | None:
    if mode != "subscribe" or not challenge:
        return None
    expected = (settings.whatsapp_verify_token or "").strip()
    if not expected or not hmac.compare_digest(token or "", expected):
        logger.info("whatsapp_webhook_verify_rejected")
        return None
    logger.info("whatsapp_webhook_verified")
    return challenge


def verify_signature(raw_body: bytes, header_value: str | None, settings: Settings) -> bool:
    secret = (settings.whatsapp_app_secret or "").strip()
    if not secret:
        if settings.is_production:
            logger.error("whatsapp_webhook_signature_missing_secret")
            return False
        logger.info("whatsapp_webhook_signature_skipped")
        return True

    if not header_value or not header_value.startswith("sha256="):
        logger.info("whatsapp_webhook_signature_missing")
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = header_value.split("=", 1)[1].strip()
    valid = hmac.compare_digest(provided, expected)
    if not valid:
        logger.info("whatsapp_webhook_signature_rejected")
    return valid
