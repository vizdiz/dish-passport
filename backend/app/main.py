"""FastAPI app. Real adapters are wired in at startup via app.dependency_overrides.

Nothing here imports a vendor SDK at module load — adapters import lazily, and we only
touch them inside the lifespan when the corresponding env var is present. So the module
imports cleanly with no keys and no DB (which is what the test suite relies on).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import deps
from app.routers import dishes, impressions, logs

logger = logging.getLogger("dishport")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = deps.get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    pool = None

    if settings.database_url:
        import asyncpg
        from pgvector.asyncpg import register_vector

        from app.adapters.repo_pgvector import PgVectorRepository

        pool = await asyncpg.create_pool(dsn=settings.database_url, init=register_vector)
        repo = PgVectorRepository(pool)
        app.dependency_overrides[deps.get_repo] = lambda: repo
        logger.info("wired PgVectorRepository")
    else:
        logger.warning("DP_DATABASE_URL unset — no repository wired; /logs will 500.")

    if settings.openai_api_key:
        from app.adapters.embeddings_openai import OpenAIEmbedder

        embedder = OpenAIEmbedder(settings.openai_api_key, settings.embedding_model)
        app.dependency_overrides[deps.get_embedder] = lambda: embedder
        logger.info("wired OpenAIEmbedder (%s)", settings.embedding_model)

    if settings.anthropic_api_key:
        from app.adapters.llm_anthropic import AnthropicNormalizer

        normalizer = AnthropicNormalizer(settings.anthropic_api_key, settings.flavor_model)
        app.dependency_overrides[deps.get_normalizer] = lambda: normalizer
        logger.info("wired AnthropicNormalizer (%s)", settings.flavor_model)

    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


app = FastAPI(title="Dish Passport — Ingestion", version="0.1.0", lifespan=lifespan)
app.include_router(logs.router)
app.include_router(dishes.router)
app.include_router(impressions.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
