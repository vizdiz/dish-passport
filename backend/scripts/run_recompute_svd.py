"""Manual trigger for the batch `recompute_svd` (Service 3).

Batch jobs are scheduler-triggered (Celery Beat) and never public endpoints; this script is
the manual/ops entry point until the scheduler is wired.

    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/run_recompute_svd.py
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.services.flavor_svd import recompute_svd


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=init_connection)
    repo = PgVectorRepository(pool)
    model = await recompute_svd(repo)
    if model is None:
        print("recompute_svd skipped (not enough dishes).")
    else:
        print(f"recompute_svd OK — version {model.version}")
        for i, (label, sv) in enumerate(zip(model.factor_labels, model.singular_values)):
            print(f"  factor {i}: {label:<28} (singular value {sv:.3f})")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
