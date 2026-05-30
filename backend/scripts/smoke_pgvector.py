"""Manual integration smoke for the pgvector adapter (NOT part of the unit suite).

Exercises PgVectorRepository against a real Postgres+pgvector over asyncpg: insert_dish,
nearest (`<=>` cosine), get_dish, insert_log (user upsert + log_count bump), impressions.
Uses deterministic, controlled embeddings — no OpenAI/Anthropic needed.

    docker compose up -d
    export DP_DATABASE_URL=postgresql://dishport:dishport@localhost:5432/dishport
    psql "$DP_DATABASE_URL" -f migrations/001_init.sql
    python scripts/smoke_pgvector.py
"""
from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timezone

import asyncpg
from pgvector.asyncpg import register_vector

from app.adapters.repo_pgvector import PgVectorRepository
from app.ports import ImpressionRow, NormalizedDish

DIM = 1536


def axis0() -> list[float]:
    v = [0.0] * DIM
    v[0] = 1.0
    return v


def vec_cos(c: float) -> list[float]:
    v = [0.0] * DIM
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


async def main() -> None:
    dsn = os.environ["DP_DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn=dsn, init=register_vector)
    repo = PgVectorRepository(pool)

    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE impressions, logs, dishes, users RESTART IDENTITY CASCADE")

    a = await repo.insert_dish(
        NormalizedDish(
            name="Al Pastor",
            description="spit-roasted marinated pork shaved thin with pineapple",
            flavor=[0.6, 0.4, 0.3, 0.4, 0.1, 0.7, 0.2, 0.5, 0.1, 0.3],
            ingredients=["pork", "pineapple", "chili"],
            prep_method="grilled",
        ),
        axis0(),
        "smoke-emb",
    )
    b = await repo.insert_dish(
        NormalizedDish(name="Miso Soup", description="fermented soybean broth with tofu",
                       flavor=[0.8, 0.0, 0.1, 0.1, 0.1, 0.2, 0.1, 0.0, 0.9, 0.2]),
        vec_cos(0.2),
        "smoke-emb",
    )
    print(f"inserted dishes: a={a.id} ({a.name}), b={b.id} ({b.name})")

    near = await repo.nearest(vec_cos(0.97))
    print(f"nearest(0.97·A) -> {near.dish.name} cosine={near.cosine:.4f}  (expect Al Pastor ~0.97)")
    assert near.dish.id == a.id and abs(near.cosine - 0.97) < 1e-3

    kindred = await repo.nearest(vec_cos(0.85))
    print(f"nearest(0.85·A) -> {kindred.dish.name} cosine={kindred.cosine:.4f}  "
          f"(0.85 < 0.90 tau => would MINT)")
    assert abs(kindred.cosine - 0.85) < 1e-3

    # Service 2: a third dish, then similar(A) ranked by cosine, self excluded.
    c = await repo.insert_dish(
        NormalizedDish(name="Carnitas", description="slow-braised then crisped pork",
                       flavor=[0.6, 0.1, 0.1, 0.2, 0.1, 0.8, 0.1, 0.3, 0.0, 0.1]),
        vec_cos(0.50),
        "smoke-emb",
    )
    sim = await repo.similar(a.id, n=10)
    print(f"similar(A) -> {[(nb.dish.name, round(nb.cosine, 2)) for nb in sim]}  "
          f"(self excluded, ranked desc)")
    assert [nb.dish.id for nb in sim] == [c.id, b.id]       # Carnitas 0.50 > Miso 0.20
    assert a.id not in [nb.dish.id for nb in sim]
    assert [nb.dish.id for nb in await repo.similar(a.id, n=1)] == [c.id]

    got = await repo.get_dish(a.id)
    print(f"get_dish({a.id}) -> {got.name} ingredients={got.ingredients} "
          f"flavor[0:3]={[round(x,2) for x in got.flavor[:3]]}")
    assert got.ingredients == ["pork", "pineapple", "chili"]

    await repo.insert_log(user_id=1, dish_id=a.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=1, dish_id=b.id, sentiment="disliked", rating=2, notes="nope")
    async with pool.acquire() as conn:
        log_count = await conn.fetchval("SELECT log_count FROM users WHERE id = 1")
    print(f"user 1 log_count = {log_count}  (expect 2)")
    assert log_count == 2

    n = await repo.insert_impressions([
        ImpressionRow(user_id=1, dish_id=a.id, shown_at=datetime.now(timezone.utc),
                      context="feed", converted=True),
        ImpressionRow(user_id=1, dish_id=b.id, shown_at=datetime.now(timezone.utc),
                      context="recs", converted=False),
    ])
    print(f"impressions ingested = {n}  (expect 2)")
    assert n == 2

    await pool.close()
    print("\nSMOKE OK — pgvector adapter verified end-to-end.")


if __name__ == "__main__":
    asyncio.run(main())
