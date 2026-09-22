from __future__ import annotations

from app.core.exceptions import BusinessAccessDeniedError, BusinessNotFoundError
from app.core.logging import get_logger
from app.core.utils import parse_uuid
from app.models.business import BusinessDocument
from app.repositories.business_repository import BusinessRepository

logger = get_logger(__name__)


class BusinessService:
    def __init__(self, businesses: BusinessRepository) -> None:
        self.businesses = businesses

    async def list_owned(self, owner_user_id: str) -> list[BusinessDocument]:
        return await self.businesses.list_by_owner(owner_user_id)

    async def get_owned(self, uuid: str, owner_user_id: str) -> BusinessDocument:
        try:
            parsed = parse_uuid(uuid)
        except ValueError as exc:
            raise BusinessNotFoundError() from exc
        business = await self.businesses.get_owned(parsed, owner_user_id)
        if business is None:
            # Distinguish missing vs unauthorized without leaking other tenants.
            existing = await self.businesses.get_by_uuid(parsed)
            if existing is None:
                raise BusinessNotFoundError()
            raise BusinessAccessDeniedError()
        return business

    async def get_public(self, uuid: str) -> BusinessDocument:
        try:
            parsed = parse_uuid(uuid)
        except ValueError as exc:
            raise BusinessNotFoundError() from exc
        business = await self.businesses.get_by_uuid(parsed)
        if business is None:
            raise BusinessNotFoundError()
        return business
