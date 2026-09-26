from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


WhatsAppIntegrationStatus = Literal["active", "inactive"]
WhatsAppMessageStatus = Literal["received", "processing", "processed", "failed"]


class WhatsAppIntegrationDocument(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    business_uuid: str
    phone_number_id: str
    business_account_id: str
    display_phone_number: str
    encrypted_access_token: str | None = None
    status: WhatsAppIntegrationStatus = "active"
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}

    @classmethod
    def from_mongo(cls, doc: dict[str, Any] | None) -> WhatsAppIntegrationDocument | None:
        if not doc:
            return None
        payload = dict(doc)
        if "_id" in payload:
            payload["_id"] = str(payload["_id"])
        return cls.model_validate(payload)


class WhatsAppMessageDocument(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    message_id: str
    business_uuid: str | None = None
    phone_number_id: str
    phone_number: str
    status: WhatsAppMessageStatus = "received"
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}

    @classmethod
    def from_mongo(cls, doc: dict[str, Any] | None) -> WhatsAppMessageDocument | None:
        if not doc:
            return None
        payload = dict(doc)
        if "_id" in payload:
            payload["_id"] = str(payload["_id"])
        return cls.model_validate(payload)
