"""WhatsApp channel orchestration. Delegates conversations to ChatService."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import Settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import (
    WhatsAppBusinessNotFoundError,
    WhatsAppConflictError,
    WhatsAppSendError,
)
from app.core.logging import get_logger
from app.core.utils import mask_display_phone_number, mask_phone_number, normalize_phone_number
from app.integrations.whatsapp.schemas import (
    CHAT_FAILURE_REPLY,
    UNSUPPORTED_MESSAGE_REPLY,
    WhatsAppIncomingMessage,
    WhatsAppStatusResponse,
)
from app.models.whatsapp import WhatsAppIntegrationDocument
from app.repositories.whatsapp_repository import WhatsAppRepository
from app.services.business_service import BusinessService
from app.services.chat_service import ChatService

logger = get_logger(__name__)


class WhatsAppService:
    def __init__(
        self,
        *,
        repository: WhatsAppRepository,
        businesses: BusinessService,
        chat: ChatService,
        client,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.businesses = businesses
        self.chat = chat
        self.client = client
        self.settings = settings

    async def connect(
        self,
        *,
        owner_user_id: str,
        business_uuid: str,
        phone_number_id: str,
        business_account_id: str,
        display_phone_number: str,
        access_token: str | None = None,
    ) -> WhatsAppIntegrationDocument:
        business = await self.businesses.get_owned(business_uuid, owner_user_id)
        existing_phone = await self.repository.get_by_phone_number_id(phone_number_id)
        if existing_phone is not None and existing_phone.business_uuid != business.uuid:
            if existing_phone.status == "active":
                raise WhatsAppConflictError()
            await self.repository.release_phone_number_id(existing_phone.business_uuid)

        encrypted = encrypt_secret(access_token, self.settings)
        document = {
            "business_uuid": business.uuid,
            "phone_number_id": phone_number_id.strip(),
            "business_account_id": business_account_id.strip(),
            "display_phone_number": display_phone_number.strip(),
            "encrypted_access_token": encrypted,
            "status": "active",
        }
        integration = await self.repository.upsert_integration(document)
        logger.info("whatsapp_integration_connected", business_uuid=business.uuid)
        return integration

    async def get_status(self, *, owner_user_id: str, business_uuid: str) -> WhatsAppStatusResponse:
        business = await self.businesses.get_owned(business_uuid, owner_user_id)
        integration = await self.repository.get_by_business_uuid(business.uuid)
        if integration is None or integration.status != "active":
            return WhatsAppStatusResponse(connected=False, status=integration.status if integration else None)
        return WhatsAppStatusResponse(
            connected=True,
            status=integration.status,
            display_phone_number=mask_display_phone_number(integration.display_phone_number),
            phone_number_id=integration.phone_number_id,
        )

    async def disconnect(self, *, owner_user_id: str, business_uuid: str) -> WhatsAppIntegrationDocument:
        business = await self.businesses.get_owned(business_uuid, owner_user_id)
        integration = await self.repository.get_by_business_uuid(business.uuid)
        if integration is None:
            raise WhatsAppBusinessNotFoundError("WhatsApp is not connected for this business")
        updated = await self.repository.deactivate(business.uuid)
        assert updated is not None
        logger.info("whatsapp_integration_disconnected", business_uuid=business.uuid)
        return updated

    async def send_test_message(self, *, owner_user_id: str, business_uuid: str) -> None:
        business = await self.businesses.get_owned(business_uuid, owner_user_id)
        integration = await self.repository.get_by_business_uuid(business.uuid)
        if integration is None or integration.status != "active":
            raise WhatsAppBusinessNotFoundError("WhatsApp is not connected for this business")
        recipient = normalize_phone_number(integration.display_phone_number)
        await self._send(
            integration,
            recipient,
            "MindDesk WhatsApp is connected. Customers can now message this number.",
        )

    async def accept_incoming(self, message: WhatsAppIncomingMessage) -> bool:
        """Claim the WhatsApp message id so Meta retries do not run the agent twice."""
        claimed = await self.repository.claim_message(
            {
                "message_id": message.message_id,
                "phone_number_id": message.phone_number_id,
                "phone_number": normalize_phone_number(message.customer_phone_number),
                "status": "received",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        if not claimed:
            logger.info("whatsapp_duplicate_ignored", message_id=message.message_id)
        return claimed

    async def handle_incoming(self, message: WhatsAppIncomingMessage) -> None:
        logger.info(
            "whatsapp_chat_started",
            message_id=message.message_id,
            phone_number_id=message.phone_number_id,
            phone=mask_phone_number(message.customer_phone_number),
            channel="whatsapp",
        )
        await self.repository.mark_message_status(message.message_id, "processing")
        integration = await self.repository.get_active_by_phone_number_id(message.phone_number_id)
        if integration is None:
            logger.error(
                "whatsapp_business_not_found",
                message_id=message.message_id,
                phone_number_id=message.phone_number_id,
            )
            await self.repository.mark_message_status(message.message_id, "failed")
            return

        logger.info(
            "whatsapp_business_resolved",
            business_uuid=integration.business_uuid,
            message_id=message.message_id,
            channel="whatsapp",
        )
        await self.repository.mark_message_status(
            message.message_id,
            "processing",
            business_uuid=integration.business_uuid,
        )
        recipient = normalize_phone_number(message.customer_phone_number)

        if message.is_unsupported or not message.is_text:
            await self._send(integration, recipient, UNSUPPORTED_MESSAGE_REPLY)
            await self.repository.mark_message_status(message.message_id, "processed")
            return

        try:
            logger.info(
                "whatsapp_agent_started",
                business_uuid=integration.business_uuid,
                message_id=message.message_id,
                channel="whatsapp",
            )
            result = await self.chat.process_message(
                business_uuid=integration.business_uuid,
                phone_number=message.customer_phone_number,
                user_query=message.text or "",
                channel="whatsapp",
            )
            logger.info(
                "whatsapp_agent_completed",
                business_uuid=integration.business_uuid,
                message_id=message.message_id,
                channel="whatsapp",
            )
            await self._send(integration, recipient, result["answer"])
            await self.repository.mark_message_status(message.message_id, "processed")
        except WhatsAppSendError:
            logger.error(
                "whatsapp_send_failed",
                business_uuid=integration.business_uuid,
                message_id=message.message_id,
            )
            await self.repository.mark_message_status(message.message_id, "failed")
        except Exception:
            logger.error(
                "whatsapp_agent_failed",
                business_uuid=integration.business_uuid,
                message_id=message.message_id,
            )
            try:
                await self._send(integration, recipient, CHAT_FAILURE_REPLY)
            except WhatsAppSendError:
                logger.error("whatsapp_send_failed", message_id=message.message_id)
            await self.repository.mark_message_status(message.message_id, "failed")

    async def _send(self, integration: WhatsAppIntegrationDocument, recipient: str, text: str) -> None:
        token = decrypt_secret(integration.encrypted_access_token, self.settings)
        await self.client.send_text_message(
            integration.phone_number_id,
            recipient,
            text,
            access_token=token,
        )
