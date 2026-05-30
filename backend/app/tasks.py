"""Celery tasks: the three batch jobs, scheduler-triggered (never public endpoints).

Each task opens a short-lived asyncpg pool, runs the async batch service against a
PgVectorRepository, and returns a JSON-serializable summary. A fresh pool per run keeps the
asyncpg pool bound to the per-call event loop (asyncio.run), which is correct under Celery's
prefork worker — and the per-run pool overhead is negligible for hourly/nightly/weekly jobs.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.celery_app import celery
from app.config import Settings
from app.ports import DishRepository
from app.services.cf import retrain_als
from app.services.flavor_svd import recompute_svd
from app.services.taste import rebuild_taste_profiles

T = TypeVar("T")


async def _with_repo(fn: Callable[[DishRepository], Awaitable[T]]) -> T:
    settings = Settings()
    if not settings.database_url:
        raise RuntimeError("DP_DATABASE_URL is required for batch tasks")
    pool = await asyncpg.create_pool(dsn=settings.database_url, init=init_connection)
    try:
        return await fn(PgVectorRepository(pool))
    finally:
        await pool.close()


@celery.task(name="dishport.recompute_svd")
def recompute_svd_task() -> dict:
    model = asyncio.run(_with_repo(recompute_svd))
    if model is None:
        return {"status": "skipped"}
    return {"status": "ok", "version": model.version, "factor_labels": model.factor_labels}


@celery.task(name="dishport.retrain_als")
def retrain_als_task() -> dict:
    result = asyncio.run(_with_repo(retrain_als))
    if result is None:
        return {"status": "skipped"}
    return {
        "status": "ok",
        "version": result.version,
        "n_users": result.n_users,
        "n_items": result.n_items,
        "n_factors": result.n_factors,
    }


@celery.task(name="dishport.rebuild_taste_profiles")
def rebuild_taste_profiles_task() -> dict:
    n = asyncio.run(_with_repo(rebuild_taste_profiles))
    return {"status": "ok", "profiles": n}
