from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings
from app.deps import get_repo, get_settings
from app.ports import DishRepository
from app.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password
from app.services.errors import UserExists

router = APIRouter(tags=["auth"])


def _token(user_id: int, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            user_id,
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            expires_minutes=settings.jwt_expire_minutes,
        ),
        user_id=user_id,
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    repo: DishRepository = Depends(get_repo),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        user_id = await repo.create_user(body.username, hash_password(body.password))
    except UserExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already taken") from exc
    return _token(user_id, settings)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    repo: DishRepository = Depends(get_repo),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    record = await repo.get_user_by_username(body.username)
    if record is None or not record[1] or not verify_password(body.password, record[1]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return _token(record[0], settings)
