from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.models.user import UserDocument
from app.repositories.business_repository import BusinessRepository
from app.schemas.business import (
    BusinessDetailResponse,
    BusinessListResponse,
    BusinessResponse,
    PublicBusinessResponse,
)
from app.services.business_service import BusinessService

router = APIRouter(tags=["Businesses"])


def _service(request: Request) -> BusinessService:
    return BusinessService(BusinessRepository(request.app.state.db))


@router.get(
    "/businesses",
    response_model=BusinessListResponse,
    summary="List businesses owned by the authenticated user",
)
async def list_businesses(
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> BusinessListResponse:
    items = await _service(request).list_owned(str(user.id))
    return BusinessListResponse(items=[BusinessResponse.model_validate(item.model_dump()) for item in items])


@router.get(
    "/public/businesses/{uuid}",
    response_model=PublicBusinessResponse,
    summary="Public demo lookup for a business UUID",
)
async def get_public_business(uuid: str, request: Request) -> PublicBusinessResponse:
    business = await _service(request).get_public(uuid)
    return PublicBusinessResponse(uuid=business.uuid, name=business.name, status=business.status)


@router.get(
    "/businesses/{uuid}",
    response_model=BusinessDetailResponse,
    summary="Get a business owned by the authenticated user",
)
async def get_business(
    uuid: str,
    request: Request,
    user: UserDocument = Depends(get_current_user),
) -> BusinessDetailResponse:
    business = await _service(request).get_owned(uuid, str(user.id))
    return BusinessDetailResponse(**business.model_dump(), success=True)
