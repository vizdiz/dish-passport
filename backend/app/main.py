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
from app.routers import auth, dishes, impressions, logs, recommendations, uploads, users

logger = logging.getLogger("dishport")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = deps.get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    pool = None

    if settings.database_url:
        import asyncpg

        from app.adapters.repo_pgvector import PgVectorRepository, init_connection

        pool = await asyncpg.create_pool(dsn=settings.database_url, init=init_connection)
        repo = PgVectorRepository(pool)
        app.dependency_overrides[deps.get_repo] = lambda: repo
        logger.info("wired PgVectorRepository")
    else:
        logger.warning("DP_DATABASE_URL unset — no repository wired; /logs will 500.")

    if settings.openai_api_key:
        from app.adapters.embeddings_openai import OpenAIEmbedder
        from app.adapters.llm_openai import OpenAINormalizer

        embedder = OpenAIEmbedder(settings.openai_api_key, settings.embedding_model)
        normalizer = OpenAINormalizer(settings.openai_api_key, settings.flavor_model)
        app.dependency_overrides[deps.get_embedder] = lambda: embedder
        app.dependency_overrides[deps.get_normalizer] = lambda: normalizer
        logger.info(
            "wired OpenAI embedder (%s) + normalizer (%s)",
            settings.embedding_model, settings.flavor_model,
        )
    else:
        logger.warning("DP_OPENAI_API_KEY unset — embedder/normalizer not wired; mint path will fail.")

    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


app = FastAPI(title="Dish Passport — Ingestion", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(logs.router)
app.include_router(dishes.router)
app.include_router(impressions.router)
app.include_router(recommendations.router)
app.include_router(users.router)
app.include_router(uploads.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
