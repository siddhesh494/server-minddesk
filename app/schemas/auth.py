from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["Admin"])
    email: EmailStr = Field(..., examples=["admin@example.com"])
    password: str = Field(..., min_length=8, max_length=128, examples=["password"])


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., examples=["admin@example.com"])
    password: str = Field(..., min_length=1, max_length=128, examples=["password"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyTokenResponse(BaseModel):
    authenticated: bool = True


class RegisterResponse(BaseModel):
    success: bool = True
    id: str
    name: str
    email: EmailStr
