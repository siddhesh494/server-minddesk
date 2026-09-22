from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.exceptions import AuthRequiredError, InvalidTokenError
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.models.user import UserDocument
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings_dep),
) -> UserDocument:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthRequiredError()

    payload = decode_access_token(credentials.credentials, settings)
    users = UserRepository(request.app.state.db)
    user = await users.get_by_id(str(payload["sub"]))
    if user is None:
        raise InvalidTokenError("The access token does not match a user")
    logger.info("jwt_validated", user_id=user.id)
    return user
