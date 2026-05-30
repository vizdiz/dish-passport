"""End-to-end integration smoke for Service 5 against real Postgres+pgvector.
Seeds a gradient catalog + users, runs all three batch jobs, then drives the recommend
ensemble — exercising vector_topk, centroid_cosines (two `<=>`), popular_dishes, and
nullable-vector taste profiles. No API keys.

    psql "$DP_DATABASE_URL" -f migrations/004_taste_profiles.sql
    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/smoke_recommend.py
"""
from __future__ import annotations

import asyncio
import math
import os

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.ports import NormalizedDish
from app.services.cf import retrain_als
from app.services.flavor_svd import recompute_svd
from app.services.recommend import recommend
from app.services.taste import rebuild_taste_profiles

DIM = 1536


def vec(c: float) -> list[float]:
    v = [0.0] * DIM
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


def flavor(i: int) -> list[float]:
    v = [0.2] * 10
    v[i % 10] = 0.9
    return v


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=init_connection)
    repo = PgVectorRepository(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE user_taste_profiles, cf_user_factors, cf_item_factors, dish_flavor_factors, "
            "flavor_svd_model, impressions, logs, dishes, users RESTART IDENTITY CASCADE"
        )

    ids = []
    for i in range(10):
        d = await repo.insert_dish(
            NormalizedDish(name=f"D{i}", description=f"d{i}", flavor=flavor(i)),
            vec(1.0 - 0.07 * i), "smoke-emb",
        )
        ids.append(d.id)

    async def log(uid, idx, sentiment="liked"):
        await repo.insert_log(user_id=uid, dish_id=ids[idx], sentiment=sentiment,
                              rating=None, notes=None)

    for idx in range(5):
        await log(1, idx)
    await log(1, 9, "disliked")
    for idx in range(3):
        await log(2, idx)

    await recompute_svd(repo)
    await retrain_als(repo, n_factors=8)
    n_profiles = await rebuild_taste_profiles(repo)
    print(f"batches done: {n_profiles} taste profiles")

    warm = await recommend(repo, user_id=1, n=5)
    rec_ids = [r.dish.id for r in warm.recommendations]
    print(f"recommend(user1) cold={warm.cold_start} -> "
          f"{[(r.dish.name, r.score, r.explanation) for r in warm.recommendations]}")
    logged = set(ids[:5]) | {ids[9]}
    assert warm.cold_start is False
    assert rec_ids and logged.isdisjoint(rec_ids), "logged/disliked leaked into recs"

    cold = await recommend(repo, user_id=999, n=5)             # brand-new -> popularity
    print(f"recommend(user999) cold={cold.cold_start} -> {[r.dish.name for r in cold.recommendations]}")
    assert cold.cold_start is True and len(cold.recommendations) > 0

    profile = await repo.get_taste_profile(1)
    print(f"user1 profile: n_dishes={profile.n_dishes} liked_centroid={profile.liked_centroid is not None} "
          f"disliked_centroid={profile.disliked_centroid is not None} "
          f"factor_pref={[round(x, 3) for x in profile.flavor_factor_pref]}")

    await pool.close()
    print("\nRECOMMEND SMOKE OK — ensemble, exclusions, and taste profiles verified end-to-end.")


if __name__ == "__main__":
    asyncio.run(main())
