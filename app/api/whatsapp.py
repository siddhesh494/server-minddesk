from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.integrations.whatsapp.schemas import (
    WhatsAppConnectRequest,
    WhatsAppConnectResponse,
    WhatsAppDisconnectResponse,
    WhatsAppStatusResponse,
    WhatsAppTestResponse,
)
from app.models.user import UserDocument
from app.repositories.business_repository import BusinessRepository
from app.repositories.whatsapp_repository import WhatsAppRepository
from app.services.business_service import BusinessService
from app.services.chat_service import ChatService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(tags=["WhatsApp"])


def _service(request: Request) -> WhatsAppService:
    return WhatsAppService(
        repository=WhatsAppRepository(request.app.state.db),
        businesses=BusinessService(BusinessRepository(request.app.state.db)),
        chat=ChatService(
            businesses=BusinessRepository(request.app.state.db),
            agent=request.app.state.agent,
        ),
        client=request.app.state.whatsapp_client,
        settings=request.app.state.settings,
    )


@router.post(
    "/whatsapp/connect",
    response_model=WhatsAppConnectResponse,
    summary="Connect a WhatsApp Business number to an owned MindDesk business",
)
async def connect_whatsapp(
    payload: WhatsAppConnectRequest,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> WhatsAppConnectResponse:
    integration = await _service(request).connect(
        owner_user_id=str(user.id),
        business_uuid=payload.business_uuid,
        phone_number_id=payload.phone_number_id,
        business_account_id=payload.business_account_id,
        display_phone_number=payload.display_phone_number,
        access_token=payload.access_token,
    )
    return WhatsAppConnectResponse(business_uuid=integration.business_uuid, status=integration.status)


@router.get(
    "/whatsapp/{business_uuid}",
    response_model=WhatsAppStatusResponse,
    summary="Get WhatsApp connection status for an owned business",
)
async def get_whatsapp_status(
    business_uuid: str,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> WhatsAppStatusResponse:
    return await _service(request).get_status(owner_user_id=str(user.id), business_uuid=business_uuid)


@router.delete(
    "/whatsapp/{business_uuid}",
    response_model=WhatsAppDisconnectResponse,
    summary="Disconnect WhatsApp without deleting business knowledge or memory",
)
async def disconnect_whatsapp(
    business_uuid: str,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> WhatsAppDisconnectResponse:
    integration = await _service(request).disconnect(owner_user_id=str(user.id), business_uuid=business_uuid)
    return WhatsAppDisconnectResponse(business_uuid=integration.business_uuid, status=integration.status)


@router.post(
    "/whatsapp/{business_uuid}/test",
    response_model=WhatsAppTestResponse,
    summary="Send a test WhatsApp message to the connected display number",
)
async def test_whatsapp(
    business_uuid: str,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> WhatsAppTestResponse:
    await _service(request).send_test_message(owner_user_id=str(user.id), business_uuid=business_uuid)
    return WhatsAppTestResponse(message="Test message sent to the connected WhatsApp number.")
