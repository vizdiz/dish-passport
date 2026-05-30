"""Manual integration smoke for Service 3 (Flavor + SVD) against real Postgres+pgvector.
Seeds a varied flavor catalog, runs the batch fit, and verifies persistence + that the
stored per-dish factors match an online re-projection. No API keys needed.

    docker compose up -d ; psql "$DP_DATABASE_URL" -f migrations/002_flavor_svd.sql
    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/smoke_svd.py
"""
from __future__ import annotations

import asyncio
import os

import asyncpg

from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.ports import NormalizedDish
from app.services.flavor_svd import project, recompute_svd

DIM = 1536

# umami spicy sour sweet bitter rich herb smoky ferm fresh
FLAVORS = {
    "Ceviche":   [0.5, 0.3, 0.9, 0.1, 0.1, 0.1, 0.4, 0.0, 0.2, 0.9],
    "Larb":      [0.6, 0.6, 0.7, 0.1, 0.2, 0.2, 0.6, 0.1, 0.3, 0.7],
    "Tonkotsu":  [0.9, 0.2, 0.1, 0.1, 0.2, 0.9, 0.1, 0.3, 0.5, 0.1],
    "Tiramisu":  [0.1, 0.0, 0.1, 0.9, 0.5, 0.8, 0.0, 0.1, 0.0, 0.1],
    "Kimchi":    [0.6, 0.7, 0.7, 0.2, 0.1, 0.2, 0.2, 0.1, 0.9, 0.4],
    "Guacamole": [0.3, 0.3, 0.5, 0.1, 0.1, 0.4, 0.6, 0.0, 0.1, 0.8],
}


def emb(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i % DIM] = 1.0
    return v


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=init_connection)
    repo = PgVectorRepository(pool)

    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE dish_flavor_factors, flavor_svd_model, impressions, logs, dishes, users "
            "RESTART IDENTITY CASCADE"
        )

    ids = []
    for i, (name, flavor) in enumerate(FLAVORS.items()):
        d = await repo.insert_dish(
            NormalizedDish(name=name, description=name.lower(), flavor=flavor), emb(i), "smoke-emb"
        )
        ids.append(d.id)
    print(f"seeded {len(ids)} dishes")

    model = await recompute_svd(repo)
    assert model is not None
    print(f"fit {model.version}")
    for i, (label, sv) in enumerate(zip(model.factor_labels, model.singular_values)):
        print(f"  factor {i}: {label:<26} (sv {sv:.3f})")

    reloaded = await repo.get_latest_svd_model()
    assert reloaded is not None and reloaded.version == model.version

    stored = await repo.get_dish_factors(ids[0])
    assert stored is not None
    factors, version = stored
    dish0 = await repo.get_dish(ids[0])
    reproj = project(dish0.flavor, reloaded)
    print(f"dish {ids[0]} stored factors={[round(x, 3) for x in factors]}  version={version}")
    assert all(abs(a - b) < 1e-6 for a, b in zip(factors, reproj)), "stored != reprojected"

    await pool.close()
    print("\nSVD SMOKE OK — fit, jsonb persistence, and online projection verified.")


if __name__ == "__main__":
    asyncio.run(main())
