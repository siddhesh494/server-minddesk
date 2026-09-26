"""Convert Meta webhook JSON into MindDesk message models."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.integrations.whatsapp.schemas import WhatsAppIncomingMessage

logger = get_logger(__name__)


def parse_webhook_payload(payload: dict[str, Any] | None) -> list[WhatsAppIncomingMessage]:
    if not isinstance(payload, dict):
        return []
    object_type = payload.get("object")
    if object_type not in {None, "whatsapp_business_account", "whatsapp"}:
        logger.info("whatsapp_webhook_ignored", object_type=object_type)
        return []

    messages: list[WhatsAppIncomingMessage] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") not in {None, "messages"}:
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            raw_messages = value.get("messages") or []
            if not phone_number_id or not raw_messages:
                continue
            for item in raw_messages:
                parsed = _parse_message(phone_number_id, item)
                if parsed is not None:
                    messages.append(parsed)
    logger.info("whatsapp_message_parsed", message_count=len(messages))
    return messages


def _parse_message(phone_number_id: str, item: Any) -> WhatsAppIncomingMessage | None:
    if not isinstance(item, dict):
        return None
    message_id = str(item.get("id") or "").strip()
    customer_phone = str(item.get("from") or "").strip()
    message_type = str(item.get("type") or "unknown").strip() or "unknown"
    if not message_id or not customer_phone:
        return None

    text: str | None = None
    if message_type == "text":
        body = (item.get("text") or {}).get("body")
        text = str(body).strip() if body is not None else None

    return WhatsAppIncomingMessage(
        phone_number_id=phone_number_id,
        customer_phone_number=customer_phone,
        message_id=message_id,
        message_type=message_type,
        text=text,
    )
