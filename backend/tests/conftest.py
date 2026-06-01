from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import deps
from app.adapters.repo_memory import InMemoryDishRepository
from app.config import Settings
from app.main import app
from tests.fakes import StubEmbedder, StubNormalizer


@pytest.fixture
def repo() -> InMemoryDishRepository:
    return InMemoryDishRepository()


@pytest.fixture
def make_client():
    """Factory: wire in-memory repo + stub providers via dependency_overrides and return
    a TestClient. Used without the lifespan context, so no real adapters are constructed."""
    created: list[TestClient] = []

    def _make(repo, embedder, normalizer, tau: float = 0.90, user: int = 1) -> TestClient:
        app.dependency_overrides[deps.get_repo] = lambda: repo
        app.dependency_overrides[deps.get_embedder] = lambda: embedder
        app.dependency_overrides[deps.get_normalizer] = lambda: normalizer
        app.dependency_overrides[deps.get_current_user] = lambda: user
        app.dependency_overrides[deps.get_settings] = lambda: Settings(
            dedup_tau=tau, database_url=None, openai_api_key=None
        )
        client = TestClient(app)
        created.append(client)
        return client

    yield _make

    for client in created:
        client.close()
    app.dependency_overrides.clear()
