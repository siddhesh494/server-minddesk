from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import InvalidRequestError
from app.models.user import UserDocument


class UserRepository:
    def __init__(self, db: Any) -> None:
        self.collection = db["users"]

    async def create(self, *, name: str, email: str, password_hash: str) -> UserDocument:
        now = datetime.now(timezone.utc)
        document = {
            "name": name.strip(),
            "email": email.lower().strip(),
            "password_hash": password_hash,
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise InvalidRequestError("An account with this email already exists") from exc
        document["_id"] = result.inserted_id
        user = UserDocument.from_mongo(document)
        assert user is not None
        return user

    async def get_by_email(self, email: str) -> UserDocument | None:
        doc = await self.collection.find_one({"email": email.lower().strip()})
        return UserDocument.from_mongo(doc)

    async def get_by_id(self, user_id: str) -> UserDocument | None:
        if not ObjectId.is_valid(user_id):
            return None
        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        return UserDocument.from_mongo(doc)
