from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


BusinessStatus = Literal["indexing", "active", "failed"]


class IndexCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, examples=["ABC Electronics"])
    text: str = Field(..., min_length=1, max_length=400_000, examples=["ABC Electronics sells..."])
    editor_content: str | dict[str, Any] | None = None
    system_prompt: str | None = Field(default=None, max_length=20_000)


class IndexUpdateRequest(BaseModel):
    uuid: str = Field(..., min_length=8, max_length=64)
    text: str = Field(..., min_length=1, max_length=400_000)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    editor_content: str | dict[str, Any] | None = None
    system_prompt: str | None = Field(default=None, max_length=20_000)


class IndexCreateResponse(BaseModel):
    success: bool = True
    uuid: str
    version: int
    chunk_count: int
    namespace: str
    status: BusinessStatus
    message: str


class IndexUpdateResponse(BaseModel):
    success: bool = True
    uuid: str
    version: int
    chunk_count: int
    message: str


class BusinessResponse(BaseModel):
    uuid: str
    name: str
    editor_content: str | dict[str, Any] = ""
    plain_text: str = ""
    system_prompt: str = ""
    active_version: int
    active_namespace: str = ""
    chunk_count: int
    status: BusinessStatus
    created_at: datetime
    updated_at: datetime


class BusinessListResponse(BaseModel):
    success: bool = True
    items: list[BusinessResponse]


class BusinessDetailResponse(BusinessResponse):
    success: bool = True


class PublicBusinessResponse(BaseModel):
    success: bool = True
    uuid: str
    name: str
    status: BusinessStatus


class BusinessUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    editor_content: str | dict[str, Any] | None = None
    text: str | None = Field(default=None, min_length=1, max_length=400_000)
    system_prompt: str | None = Field(default=None, max_length=20_000)
