from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import InvalidRequestError
from app.models.business import BusinessDocument


class BusinessRepository:
    def __init__(self, db: Any) -> None:
        self.collection = db["businesses"]

    async def create(self, document: dict[str, Any]) -> BusinessDocument:
        try:
            result = await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise InvalidRequestError("A business with this UUID already exists") from exc
        document["_id"] = result.inserted_id
        business = BusinessDocument.from_mongo(document)
        assert business is not None
        return business

    async def get_by_uuid(self, uuid: str) -> BusinessDocument | None:
        doc = await self.collection.find_one({"uuid": uuid})
        return BusinessDocument.from_mongo(doc)

    async def get_owned(self, uuid: str, owner_user_id: str) -> BusinessDocument | None:
        query: dict[str, Any] = {"uuid": uuid}
        if ObjectId.is_valid(owner_user_id):
            query["owner_user_id"] = {"$in": [owner_user_id, ObjectId(owner_user_id)]}
        else:
            query["owner_user_id"] = owner_user_id
        doc = await self.collection.find_one(query)
        return BusinessDocument.from_mongo(doc)

    async def list_by_owner(self, owner_user_id: str) -> list[BusinessDocument]:
        query: dict[str, Any]
        if ObjectId.is_valid(owner_user_id):
            query = {"owner_user_id": {"$in": [owner_user_id, ObjectId(owner_user_id)]}}
        else:
            query = {"owner_user_id": owner_user_id}
        cursor = self.collection.find(query).sort("updated_at", -1)
        items: list[BusinessDocument] = []
        async for doc in cursor:
            business = BusinessDocument.from_mongo(doc)
            if business:
                items.append(business)
        return items

    async def update_fields(self, uuid: str, fields: dict[str, Any]) -> BusinessDocument | None:
        payload = dict(fields)
        payload["updated_at"] = datetime.now(timezone.utc)
        await self.collection.update_one({"uuid": uuid}, {"$set": payload})
        return await self.get_by_uuid(uuid)
