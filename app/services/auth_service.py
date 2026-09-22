from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import InvalidRequestError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import UserDocument
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class AuthService:
    def __init__(self, users: UserRepository, settings: Settings) -> None:
        self.users = users
        self.settings = settings

    async def register(self, *, name: str, email: str, password: str) -> UserDocument:
        existing = await self.users.get_by_email(email)
        if existing:
            raise InvalidRequestError("An account with this email already exists")
        user = await self.users.create(
            name=name,
            email=email,
            password_hash=hash_password(password),
        )
        logger.info("user_registered", user_id=user.id, email=user.email)
        return user

    async def login(self, *, email: str, password: str) -> str:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            logger.info("login_failed", email=email.lower())
            raise InvalidRequestError("Invalid email or password")
        token = create_access_token(user_id=str(user.id), email=user.email, settings=self.settings)
        logger.info("login_succeeded", user_id=user.id)
        return token
