from __future__ import annotations

from app.core.exceptions import BusinessNotActiveError, BusinessNotFoundError, InvalidRequestError
from app.core.logging import get_logger
from app.core.utils import build_thread_id, mask_phone_number, parse_uuid
from app.rag.agent import invoke_agent
from app.rag.prompts import resolve_system_prompt
from app.rag.tools import BusinessContext
from app.repositories.business_repository import BusinessRepository

logger = get_logger(__name__)


class ChatService:
    def __init__(self, *, businesses: BusinessRepository, agent) -> None:
        self.businesses = businesses
        self.agent = agent

    async def process_message(
        self,
        *,
        business_uuid: str,
        phone_number: str,
        user_query: str,
        channel: str = "api",
    ) -> dict[str, str]:
        """Channel-agnostic conversation entry used by REST chat and WhatsApp."""
        logger.info(
            "chat_request_started",
            channel=channel,
            phone=mask_phone_number(phone_number),
        )
        try:
            parsed_uuid = parse_uuid(business_uuid)
        except ValueError as exc:
            raise BusinessNotFoundError() from exc

        if not phone_number.strip():
            raise InvalidRequestError("A phone number is required")
        if not user_query.strip():
            raise InvalidRequestError("A query is required")

        business = await self.businesses.get_by_uuid(parsed_uuid)
        if business is None:
            raise BusinessNotFoundError()
        if business.status != "active" or not business.active_namespace:
            raise BusinessNotActiveError()

        logger.info("business_resolved", business_uuid=parsed_uuid, channel=channel)
        thread_id = build_thread_id(phone_number, parsed_uuid)
        logger.info("thread_id_created", channel=channel)

        context = BusinessContext(
            business_uuid=parsed_uuid,
            active_namespace=business.active_namespace,
            user_phone_number=phone_number,
            system_prompt=resolve_system_prompt(business.system_prompt),
        )
        answer = await invoke_agent(
            self.agent,
            query=user_query.strip(),
            thread_id=thread_id,
            context=context,
        )
        logger.info("chat_request_completed", business_uuid=parsed_uuid, channel=channel)
        return {
            "uuid": parsed_uuid,
            "thread_id": thread_id,
            "answer": answer,
        }

    async def chat(self, *, uuid: str, phone: str, query: str, channel: str = "api") -> dict[str, str]:
        return await self.process_message(
            business_uuid=uuid,
            phone_number=phone,
            user_query=query,
            channel=channel,
        )
