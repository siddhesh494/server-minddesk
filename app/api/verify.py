from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.models.user import UserDocument
from app.schemas.auth import VerifyTokenResponse

router = APIRouter(tags=["Authentication"])


@router.get(
    "/verifyJWTToken",
    response_model=VerifyTokenResponse,
    summary="Validate the current JWT",
)
async def verify_jwt_token(_user: UserDocument = Depends(get_current_user)) -> VerifyTokenResponse:
    """Protected clients call this to decide whether to render authenticated UI."""
    return VerifyTokenResponse(authenticated=True)
