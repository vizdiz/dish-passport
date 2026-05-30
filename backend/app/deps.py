"""Overridable dependencies.

In production, `app/main.py`'s lifespan wires real adapters into
`app.dependency_overrides[...]`. In tests, the fixtures do the same with in-memory fakes.
Unconfigured, the provider getters raise a clear error rather than guessing.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import Settings
from app.ports import DishNormalizer, DishRepository, Embedder


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_repo() -> DishRepository:  # pragma: no cover - overridden at startup / in tests
    raise RuntimeError(
        "DishRepository is not configured. Wire one via "
        "app.dependency_overrides[get_repo] (lifespan does this when DP_DATABASE_URL is set)."
    )


def get_embedder() -> Embedder:  # pragma: no cover - overridden at startup / in tests
    raise RuntimeError(
        "Embedder is not configured. Set DP_OPENAI_API_KEY so lifespan can wire it, "
        "or override app.dependency_overrides[get_embedder]."
    )


def get_normalizer() -> DishNormalizer:  # pragma: no cover - overridden at startup / in tests
    raise RuntimeError(
        "DishNormalizer is not configured. Set DP_ANTHROPIC_API_KEY so lifespan can wire it, "
        "or override app.dependency_overrides[get_normalizer]."
    )
