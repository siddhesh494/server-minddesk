from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    uuid: str = Field(..., min_length=8, max_length=64, examples=["550e8400-e29b-41d4-a716-446655440000"])
    user_phone_number: str = Field(..., min_length=6, max_length=32, examples=["+919999999999"])
    user_query: str = Field(..., min_length=1, max_length=4000, examples=["What products do you sell?"])


class ChatResponse(BaseModel):
    success: bool = True
    uuid: str
    thread_id: str
    answer: str
