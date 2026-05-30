"""DEDUP_TAU calibration readout (Service 2's empirical purpose).

Computes every unique pairwise cosine in the `dishes` catalog (via the same pgvector
`similar` path the API uses) and prints them ranked, flagging which side of DEDUP_TAU each
falls on. Seed *real* dishes (real embeddings) first, then eyeball where kindred-but-distinct
pairs (al pastor/shawarma, ceviche/larb) land to choose tau from data rather than vibes.

    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/calibrate_tau.py
"""
from __future__ import annotations

import asyncio
import os
import statistics

import asyncpg
from pgvector.asyncpg import register_vector

from app.adapters.repo_pgvector import PgVectorRepository
from app.config import Settings

TOP = 30


async def main() -> None:
    tau = Settings().dedup_tau
    pool = await asyncpg.create_pool(dsn=os.environ["DP_DATABASE_URL"], init=register_vector)
    repo = PgVectorRepository(pool)

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name FROM dishes ORDER BY id")
    names = {r["id"]: r["name"] for r in rows}
    ids = list(names)
    if len(ids) < 2:
        print("Need >= 2 dishes in the catalog; seed real dishes first.")
        await pool.close()
        return

    seen: set[tuple[int, int]] = set()
    pairs: list[tuple[float, int, int]] = []
    for did in ids:
        for nb in await repo.similar(did, n=len(ids) - 1):
            key = (min(did, nb.dish.id), max(did, nb.dish.id))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((nb.cosine, key[0], key[1]))
    pairs.sort(reverse=True)

    print(f"{len(ids)} dishes, {len(pairs)} unique pairs. DEDUP_TAU = {tau:.2f}\n")
    for cos, a, b in pairs[:TOP]:
        flag = "LINK" if cos >= tau else "mint"
        print(f"  cos={cos:.4f} [{flag}]  {names[a]!r} <-> {names[b]!r}")

    cosines = [p[0] for p in pairs]
    print(f"\n  cosine  min={min(cosines):.4f}  median={statistics.median(cosines):.4f}  "
          f"max={max(cosines):.4f}")
    above = sum(1 for c in cosines if c >= tau)
    print(f"  {above}/{len(cosines)} pairs would LINK at tau={tau:.2f}")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
