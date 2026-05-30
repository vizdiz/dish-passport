"""Manual trigger for the batch `rebuild_taste_profiles` (Service 5). Scheduler-triggered in prod.

    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/run_rebuild_taste_profiles.py
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.services.taste import rebuild_taste_profiles


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=init_connection)
    repo = PgVectorRepository(pool)
    n = await rebuild_taste_profiles(repo)
    print(f"rebuild_taste_profiles OK — {n} profiles")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
