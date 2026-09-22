from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserDocument(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    name: str
    email: EmailStr
    password_hash: str
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}

    @classmethod
    def from_mongo(cls, doc: dict[str, Any] | None) -> UserDocument | None:
        if not doc:
            return None
        payload = dict(doc)
        if "_id" in payload:
            payload["_id"] = str(payload["_id"])
        return cls.model_validate(payload)
