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

    async def chat(self, *, uuid: str, phone: str, query: str) -> dict[str, str]:
        logger.info("chat_request_started", phone=mask_phone_number(phone))
        try:
            business_uuid = parse_uuid(uuid)
        except ValueError as exc:
            raise BusinessNotFoundError() from exc

        if not phone.strip():
            raise InvalidRequestError("A phone number is required")
        if not query.strip():
            raise InvalidRequestError("A query is required")

        business = await self.businesses.get_by_uuid(business_uuid)
        if business is None:
            raise BusinessNotFoundError()
        if business.status != "active" or not business.active_namespace:
            raise BusinessNotActiveError()

        logger.info("business_resolved", business_uuid=business_uuid)
        thread_id = build_thread_id(phone, business_uuid)
        logger.info("thread_id_created")

        context = BusinessContext(
            business_uuid=business_uuid,
            active_namespace=business.active_namespace,
            user_phone_number=phone,
            system_prompt=resolve_system_prompt(business.system_prompt),
        )
        answer = await invoke_agent(
            self.agent,
            query=query.strip(),
            thread_id=thread_id,
            context=context,
        )
        logger.info("chat_request_completed", business_uuid=business_uuid)
        return {
            "uuid": business_uuid,
            "thread_id": thread_id,
            "answer": answer,
        }
