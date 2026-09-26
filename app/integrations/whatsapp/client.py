"""Async Meta WhatsApp Cloud API client. No RAG or business logic."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import WhatsAppSendError
from app.core.logging import get_logger
from app.core.utils import mask_phone_number
from app.integrations.whatsapp.schemas import WhatsAppSendResult

logger = get_logger(__name__)


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=settings.whatsapp_api_timeout_seconds)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def send_text_message(
        self,
        phone_number_id: str,
        recipient_phone_number: str,
        message: str,
        *,
        access_token: str | None = None,
    ) -> WhatsAppSendResult:
        token = (access_token or self.settings.whatsapp_access_token or "").strip()
        if not token:
            raise WhatsAppSendError("WhatsApp access token is not configured")
        if not phone_number_id or not recipient_phone_number or not message.strip():
            raise WhatsAppSendError("WhatsApp send request is incomplete")

        version = self.settings.whatsapp_api_version.strip() or "v21.0"
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone_number,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        logger.info(
            "whatsapp_response_sending",
            phone_number_id=phone_number_id,
            phone=mask_phone_number(recipient_phone_number),
            message_type="text",
        )
        try:
            response = await self._http.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.error("whatsapp_send_failed", phone_number_id=phone_number_id, error_type=type(exc).__name__)
            raise WhatsAppSendError("Unable to reach the WhatsApp Cloud API") from exc

        logger.info(
            "whatsapp_response_sent",
            phone_number_id=phone_number_id,
            status_code=response.status_code,
        )
        if response.status_code >= 400:
            raise WhatsAppSendError("The WhatsApp Cloud API rejected the message")

        body: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}
        messages = body.get("messages") or []
        outbound_id = None
        if messages and isinstance(messages[0], dict):
            outbound_id = messages[0].get("id")
        return WhatsAppSendResult(ok=True, message_id=outbound_id, status_code=response.status_code)


class FakeWhatsAppClient:
    """In-memory sender used by tests. Never calls Meta."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail = False

    async def aclose(self) -> None:
        return None

    async def send_text_message(
        self,
        phone_number_id: str,
        recipient_phone_number: str,
        message: str,
        *,
        access_token: str | None = None,
    ) -> WhatsAppSendResult:
        _ = access_token
        if self.fail:
            raise WhatsAppSendError("The WhatsApp Cloud API rejected the message")
        self.sent.append(
            {
                "phone_number_id": phone_number_id,
                "recipient_phone_number": recipient_phone_number,
                "message": message,
            }
        )
        return WhatsAppSendResult(ok=True, message_id="wamid.outbound-test", status_code=200)
