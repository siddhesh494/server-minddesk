from fastapi import APIRouter, Request

from app.core.config import Settings
from app.dependencies.auth import get_settings_dep
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(tags=["Authentication"])


def _service(request: Request) -> AuthService:
    settings: Settings = get_settings_dep(request)
    return AuthService(UserRepository(request.app.state.db), settings)


@router.post(
    "/register",
    response_model=RegisterResponse,
    summary="Register a platform administrator",
)
async def register(payload: RegisterRequest, request: Request) -> RegisterResponse:
    """Create an admin account. Passwords are hashed before storage."""
    user = await _service(request).register(
        name=payload.name,
        email=str(payload.email),
        password=payload.password,
    )
    return RegisterResponse(id=str(user.id), name=user.name, email=user.email)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT",
)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    """Validate credentials and return a bearer token."""
    token = await _service(request).login(email=str(payload.email), password=payload.password)
    return TokenResponse(access_token=token)
