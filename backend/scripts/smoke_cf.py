"""Manual integration smoke for Service 4 (CF/ALS) against real Postgres+pgvector.
Seeds an interaction matrix with a disliked and an unseen cell, runs the batch fit, and
checks the persisted factors reproduce the 'disliked < unseen' ordering. No API keys.

    psql "$DP_DATABASE_URL" -f migrations/003_cf.sql
    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/smoke_cf.py
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.ports import NormalizedDish
from app.services.cf import retrain_als

DIM = 1536


def emb(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i % DIM] = 1.0
    return v


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=init_connection)
    repo = PgVectorRepository(pool)

    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE cf_user_factors, cf_item_factors, dish_flavor_factors, flavor_svd_model, "
            "impressions, logs, dishes, users RESTART IDENTITY CASCADE"
        )

    d0 = await repo.insert_dish(NormalizedDish(name="D0", description="d0", flavor=[0.5] * 10),
                                emb(0), "smoke-emb")
    d1 = await repo.insert_dish(NormalizedDish(name="D1", description="d1", flavor=[0.5] * 10),
                                emb(1), "smoke-emb")
    # user1 likes both (couples d0~d1); user2 likes d0, DISLIKES d1; user3 likes d0 (d1 unseen)
    await repo.insert_log(user_id=1, dish_id=d0.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=1, dish_id=d1.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=2, dish_id=d0.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=2, dish_id=d1.id, sentiment="disliked", rating=1, notes=None)
    await repo.insert_log(user_id=3, dish_id=d0.id, sentiment="liked", rating=None, notes=None)

    result = await retrain_als(repo, n_factors=8)
    assert result is not None
    print(f"fit {result.version} — {result.n_users} users × {result.n_items} items, k={result.n_factors}")

    u2, _ = await repo.get_cf_user_factors(2)   # disliked d1
    u3, _ = await repo.get_cf_user_factors(3)   # d1 unseen
    i1, _ = await repo.get_cf_item_factors(d1.id)
    s_disliked, s_unseen = dot(u2, i1), dot(u3, i1)
    print(f"score(user2 disliked d1) = {s_disliked:.4f}")
    print(f"score(user3 unseen  d1) = {s_unseen:.4f}")
    assert s_disliked < s_unseen, "disliked should score below unseen"

    await pool.close()
    print("\nCF SMOKE OK — ALS persisted; disliked < unseen holds on stored factors.")


if __name__ == "__main__":
    asyncio.run(main())
