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

from app.config import Settings
from app.ports import DishNormalizer, DishRepository, Embedder, NormalizedDish


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_repo() -> DishRepository:  # pragma: no cover - overridden at startup / in tests
    raise RuntimeError(
        "DishRepository is not configured. Wire one via "
        "app.dependency_overrides[get_repo] (lifespan does this when DP_DATABASE_URL is set)."
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
            "DishNormalizer is not configured. Set DP_ANTHROPIC_API_KEY so lifespan can wire it, "
            "or override app.dependency_overrides[get_normalizer]."
        )


def get_embedder() -> Embedder:
    return _UnconfiguredEmbedder()


def get_normalizer() -> DishNormalizer:
    return _UnconfiguredNormalizer()
