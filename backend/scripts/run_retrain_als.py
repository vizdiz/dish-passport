"""Manual trigger for the batch `retrain_als` (Service 4). Scheduler-triggered in prod.

    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/run_retrain_als.py
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.services.cf import retrain_als


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=init_connection)
    repo = PgVectorRepository(pool)
    result = await retrain_als(repo)
    if result is None:
        print("retrain_als skipped (no interactions).")
    else:
        print(f"retrain_als OK — {result.version}: "
              f"{result.n_users} users × {result.n_items} items, k={result.n_factors}")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
