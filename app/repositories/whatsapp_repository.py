from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.models.whatsapp import WhatsAppIntegrationDocument, WhatsAppMessageDocument


class WhatsAppRepository:
    def __init__(self, db: Any) -> None:
        self.integrations = db["whatsapp_integrations"]
        self.messages = db["whatsapp_messages"]

    async def get_by_business_uuid(self, business_uuid: str) -> WhatsAppIntegrationDocument | None:
        doc = await self.integrations.find_one({"business_uuid": business_uuid})
        return WhatsAppIntegrationDocument.from_mongo(doc)

    async def get_by_phone_number_id(self, phone_number_id: str) -> WhatsAppIntegrationDocument | None:
        doc = await self.integrations.find_one({"phone_number_id": phone_number_id})
        return WhatsAppIntegrationDocument.from_mongo(doc)

    async def get_active_by_phone_number_id(self, phone_number_id: str) -> WhatsAppIntegrationDocument | None:
        doc = await self.integrations.find_one({"phone_number_id": phone_number_id, "status": "active"})
        return WhatsAppIntegrationDocument.from_mongo(doc)

    async def upsert_integration(self, document: dict[str, Any]) -> WhatsAppIntegrationDocument:
        now = datetime.now(timezone.utc)
        existing = await self.get_by_business_uuid(document["business_uuid"])
        payload = dict(document)
        payload["updated_at"] = now
        if existing is None:
            payload.setdefault("created_at", now)
            await self.integrations.insert_one(payload)
        else:
            await self.integrations.update_one(
                {"business_uuid": document["business_uuid"]},
                {"$set": payload},
            )
        stored = await self.get_by_business_uuid(document["business_uuid"])
        assert stored is not None
        return stored

    async def release_phone_number_id(self, business_uuid: str) -> None:
        existing = await self.get_by_business_uuid(business_uuid)
        if existing is None:
            return
        await self.integrations.update_one(
            {"business_uuid": business_uuid},
            {
                "$set": {
                    "phone_number_id": f"released:{existing.phone_number_id}:{business_uuid}",
                    "status": "inactive",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def deactivate(self, business_uuid: str) -> WhatsAppIntegrationDocument | None:
        await self.integrations.update_one(
            {"business_uuid": business_uuid},
            {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc)}},
        )
        return await self.get_by_business_uuid(business_uuid)

    async def claim_message(self, document: dict[str, Any]) -> bool:
        """Insert a processed-message lock. False means Meta already delivered this id."""
        payload = dict(document)
        now = datetime.now(timezone.utc)
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        try:
            await self.messages.insert_one(payload)
        except DuplicateKeyError:
            return False
        return True

    async def mark_message_status(
        self,
        message_id: str,
        status: str,
        *,
        business_uuid: str | None = None,
    ) -> None:
        fields: dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if business_uuid is not None:
            fields["business_uuid"] = business_uuid
        await self.messages.update_one({"message_id": message_id}, {"$set": fields})

    async def get_message(self, message_id: str) -> WhatsAppMessageDocument | None:
        doc = await self.messages.find_one({"message_id": message_id})
        return WhatsAppMessageDocument.from_mongo(doc)
