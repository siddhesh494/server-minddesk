from __future__ import annotations

from pydantic import BaseModel, Field


UNSUPPORTED_MESSAGE_REPLY = (
    "I can currently respond to text messages. Please send your question as text."
)
CHAT_FAILURE_REPLY = (
    "Sorry, I'm having trouble processing your request right now. Please try again shortly."
)
SUPPORTED_TEXT_TYPES = {"text"}
UNSUPPORTED_MESSAGE_TYPES = {
    "image",
    "audio",
    "video",
    "document",
    "sticker",
    "location",
    "contacts",
    "button",
    "interactive",
    "order",
    "system",
    "unknown",
    "reaction",
}


class WhatsAppIncomingMessage(BaseModel):
    phone_number_id: str
    customer_phone_number: str
    message_id: str
    message_type: str
    text: str | None = None

    @property
    def is_text(self) -> bool:
        return self.message_type in SUPPORTED_TEXT_TYPES and bool((self.text or "").strip())

    @property
    def is_unsupported(self) -> bool:
        return self.message_type not in SUPPORTED_TEXT_TYPES


class WhatsAppSendResult(BaseModel):
    ok: bool
    message_id: str | None = None
    status_code: int = 200


class WhatsAppConnectRequest(BaseModel):
    business_uuid: str = Field(..., min_length=8, max_length=64)
    phone_number_id: str = Field(..., min_length=3, max_length=64)
    business_account_id: str = Field(..., min_length=3, max_length=64)
    display_phone_number: str = Field(..., min_length=6, max_length=32)
    access_token: str | None = Field(default=None, max_length=4000)


class WhatsAppConnectResponse(BaseModel):
    success: bool = True
    business_uuid: str
    status: str


class WhatsAppStatusResponse(BaseModel):
    success: bool = True
    connected: bool
    status: str | None = None
    display_phone_number: str | None = None
    phone_number_id: str | None = None


class WhatsAppDisconnectResponse(BaseModel):
    success: bool = True
    business_uuid: str
    status: str = "inactive"


class WhatsAppTestResponse(BaseModel):
    success: bool = True
    message: str
