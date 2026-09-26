from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse

from app.core.exceptions import InvalidRequestError, WhatsAppWebhookForbiddenError
from app.core.logging import get_logger
from app.integrations.whatsapp.parser import parse_webhook_payload
from app.integrations.whatsapp.webhook import verify_signature, verify_subscription
from app.repositories.business_repository import BusinessRepository
from app.repositories.whatsapp_repository import WhatsAppRepository
from app.services.business_service import BusinessService
from app.services.chat_service import ChatService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(tags=["WhatsApp Webhooks"])
logger = get_logger(__name__)


def _whatsapp_service(request: Request) -> WhatsAppService:
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


@router.get(
    "/webhooks/whatsapp",
    summary="Meta WhatsApp webhook verification",
    response_class=PlainTextResponse,
)
async def verify_whatsapp_webhook(request: Request) -> PlainTextResponse:
    """Respond to Meta's hub.challenge handshake using WHATSAPP_VERIFY_TOKEN."""
    challenge = verify_subscription(
        request.query_params.get("hub.mode"),
        request.query_params.get("hub.verify_token"),
        request.query_params.get("hub.challenge"),
        request.app.state.settings,
    )
    if challenge is None:
        raise WhatsAppWebhookForbiddenError()
    return PlainTextResponse(content=challenge, status_code=200)


@router.post(
    "/webhooks/whatsapp",
    summary="Receive WhatsApp Cloud API events",
)
async def receive_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, bool]:
    """Acknowledge quickly, then process claimed messages in a background task."""
    raw_body = await request.body()
    if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"), request.app.state.settings):
        raise WhatsAppWebhookForbiddenError("Invalid WhatsApp webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("whatsapp_webhook_parse_failed")
        raise InvalidRequestError("WhatsApp webhook payload is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise InvalidRequestError("WhatsApp webhook payload is invalid")

    logger.info("whatsapp_webhook_received")
    try:
        messages = parse_webhook_payload(payload)
    except Exception as exc:
        logger.error("whatsapp_webhook_parse_failed")
        raise InvalidRequestError("WhatsApp webhook payload could not be parsed") from exc

    service = _whatsapp_service(request)
    for message in messages:
        if await service.accept_incoming(message):
            background_tasks.add_task(service.handle_incoming, message)
    return {"success": True}
