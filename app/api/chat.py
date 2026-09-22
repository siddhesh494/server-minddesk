from fastapi import APIRouter, Request

from app.repositories.business_repository import BusinessRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Public multi-tenant chat endpoint",
)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """WhatsApp and demo clients send uuid + phone + query. No JWT required."""
    service = ChatService(
        businesses=BusinessRepository(request.app.state.db),
        agent=request.app.state.agent,
    )
    result = await service.chat(
        uuid=payload.uuid,
        phone=payload.user_phone_number,
        query=payload.user_query,
    )
    return ChatResponse(**result)
