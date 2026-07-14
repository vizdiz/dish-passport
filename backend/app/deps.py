"""Overridable dependencies.

In production, `app/main.py`'s lifespan wires real adapters into
`app.dependency_overrides[...]` when the matching env var is present. In tests, fixtures do
the same with in-memory fakes.

The embedder/normalizer getters return *lazy unconfigured* providers rather than raising at
dependency-resolution time. That keeps the dish_id fast lane (and GET /dishes, /impressions)
working with only a database wired — they never touch a provider — while the mint/link path
fails loudly and clearly the moment it actually needs to embed or normalize.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.ports import DishNormalizer, DishRepository, Embedder, NormalizedDish, Storage


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_storage() -> Storage:
    from app.services.storage import AzureBlobStorage

    return AzureBlobStorage(get_settings())


def get_repo() -> DishRepository:  # pragma: no cover - overridden at startup / in tests
    raise RuntimeError(
        "DishRepository is not configured. Wire one via "
        "app.dependency_overrides[get_repo] (lifespan does this when SUPABASE_DB_URL is set)."
    )


class _UnconfiguredEmbedder:
    """Resolves fine as a dependency; raises only if something tries to embed."""

    @property
    def model_version(self) -> str:  # pragma: no cover - trivial
        return "unconfigured"

    async def embed(self, text: str) -> list[float]:
        raise RuntimeError(
            "Embedder is not configured. Set DP_OPENAI_API_KEY so lifespan can wire it, "
            "or override app.dependency_overrides[get_embedder]."
        )


class _UnconfiguredNormalizer:
    async def normalize(self, text: str) -> NormalizedDish:
        raise RuntimeError(
            "DishNormalizer is not configured. Set DP_OPENAI_API_KEY so lifespan can wire it, "
            "or override app.dependency_overrides[get_normalizer]."
        )


def get_embedder() -> Embedder:
    return _UnconfiguredEmbedder()


def get_normalizer() -> DishNormalizer:
    return _UnconfiguredNormalizer()


_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(url: str):
    """Cached PyJWKClient — fetches/caches the project public keys and refetches on rotation."""
    from jwt import PyJWKClient

    return PyJWKClient(url)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """Resolve the authenticated user id (a UUID string) from a Supabase-issued JWT.

    Modern Supabase projects sign access tokens ES256 with a private key; we verify with the
    public key from the project JWKS endpoint (`settings.jwks_url`). Legacy HS256 shared-secret
    projects are supported as a fallback (`supabase_jwt_secret`). `sub` is the user's auth.users
    UUID and `aud` is "authenticated". We only verify — the worker never mints tokens. 401 if the
    header is missing or the token fails verification/expiry.
    """
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")

    import jwt

    options = {} if settings.jwt_verify_audience else {"verify_aud": False}
    aud = settings.jwt_audience if settings.jwt_verify_audience else None
    token = creds.credentials
    try:
        jwks_url = settings.jwks_url
        if jwks_url:
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"], audience=aud, options=options)
        elif settings.supabase_jwt_secret:
            claims = jwt.decode(
                token, settings.supabase_jwt_secret, algorithms=["HS256"], audience=aud, options=options
            )
        else:
            raise RuntimeError(
                "No JWT verification configured: set SUPABASE_URL/SUPABASE_JWKS_URL (ES256) "
                "or SUPABASE_JWT_SECRET (HS256)."
            )
        sub = claims["sub"]
    except Exception as exc:  # noqa: BLE001 - any decode/verify failure is an auth failure
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        ) from exc

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        )
    return str(sub)
