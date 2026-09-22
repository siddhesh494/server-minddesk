from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


BusinessStatus = Literal["indexing", "active", "failed"]


class BusinessDocument(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    uuid: str
    name: str
    editor_content: str | dict[str, Any] = ""
    plain_text: str
    system_prompt: str = ""
    active_version: int = 0
    active_namespace: str = ""
    chunk_count: int = 0
    status: BusinessStatus = "indexing"
    owner_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}

    @classmethod
    def from_mongo(cls, doc: dict[str, Any] | None) -> BusinessDocument | None:
        if not doc:
            return None
        payload = dict(doc)
        if "_id" in payload:
            payload["_id"] = str(payload["_id"])
        if "owner_user_id" in payload:
            payload["owner_user_id"] = str(payload["owner_user_id"])
        return cls.model_validate(payload)
