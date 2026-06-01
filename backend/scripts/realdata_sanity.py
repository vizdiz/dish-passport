"""Real-data sanity pass: run a handful of real dish entries through the ACTUAL gate
(OpenAI normalize + embed) and cross-check the thesis on real embeddings.

  - paraphrases should LINK (chicken tikka masala ~ murgh tikka masala)
  - kindred-but-distinct should stay apart (al pastor vs shawarma)
  - cross-cuisine kinship should surface (ceviche ~ larb) as a high pairwise cosine
  - prints the full pairwise cosine distribution to calibrate DEDUP_TAU from data

    DP_OPENAI_API_KEY=... DP_DATABASE_URL=... PYTHONPATH=. python scripts/realdata_sanity.py
"""
from __future__ import annotations

import asyncio
import itertools

import asyncpg

from app.adapters.embeddings_openai import OpenAIEmbedder
from app.adapters.llm_openai import OpenAINormalizer
from app.adapters.repo_pgvector import PgVectorRepository, init_connection
from app.config import Settings
from app.services.ingestion import log_dish

ENTRIES = [
    "ceviche",
    "larb",
    "tacos al pastor",
    "chicken shawarma",
    "chicken tikka masala",
    "murgh tikka masala",   # paraphrase of the previous -> should LINK
    "spaghetti carbonara",
    "miso soup",
    "tom yum goong soup",
    "guacamole",
]


async def main() -> None:
    s = Settings()
    if not s.openai_api_key:
        raise SystemExit("DP_OPENAI_API_KEY required")
    pool = await asyncpg.create_pool(dsn=s.database_url, init=init_connection)
    repo = PgVectorRepository(pool)
    embedder = OpenAIEmbedder(s.openai_api_key, s.embedding_model)
    normalizer = OpenAINormalizer(s.openai_api_key, s.flavor_model)

    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE user_taste_profiles, cf_user_factors, cf_item_factors, dish_flavor_factors, "
            "flavor_svd_model, impressions, logs, dishes, users RESTART IDENTITY CASCADE"
        )

    print(f"== running {len(ENTRIES)} entries through the real gate (tau={s.dedup_tau}) ==")
    for text in ENTRIES:
        res = await log_dish(repo=repo, embedder=embedder, normalizer=normalizer,
                             user_id=1, text=text, tau=s.dedup_tau)
        tag = "MINT" if res.is_new else "LINK"
        print(f"  [{tag}] {text!r:24} -> #{res.dish.id} {res.dish.name!r}")

    # Eyeball two canonical dishes' cuisine-blind description + top flavors.
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name, canonical_description, flavor FROM dishes ORDER BY id"
        )
    print("\n== cuisine-blind descriptions + flavor (sanity) ==")
    dims = ["umami", "spicy", "sour", "sweet", "bitter", "rich", "herbaceous", "smoky", "fermented", "fresh"]
    for r in rows[:4]:
        flavor = [float(x) for x in r["flavor"]]
        top = sorted(zip(dims, flavor), key=lambda x: x[1], reverse=True)[:3]
        print(f"  {r['name']}: {r['canonical_description']}")
        print(f"      top flavors: {', '.join(f'{d} {v:.2f}' for d, v in top)}")

    # Full pairwise cosine distribution (real embeddings) vs tau.
    async with pool.acquire() as conn:
        ids = [(r["id"], r["name"]) for r in await conn.fetch("SELECT id, name FROM dishes ORDER BY id")]
        pairs = []
        for (a, na), (b, nb) in itertools.combinations(ids, 2):
            cos = await conn.fetchval(
                "SELECT 1 - (d1.embedding <=> d2.embedding) FROM dishes d1, dishes d2 "
                "WHERE d1.id=$1 AND d2.id=$2", a, b)
            pairs.append((float(cos), na, nb))
    pairs.sort(reverse=True)
    print(f"\n== pairwise cosines (real text-embedding-3-small), tau={s.dedup_tau} ==")
    for cos, na, nb in pairs:
        flag = "LINK" if cos >= s.dedup_tau else "    "
        print(f"  {cos:.4f} [{flag}]  {na} ~ {nb}")
    above = sum(1 for c, _, _ in pairs if c >= s.dedup_tau)
    print(f"\n  {above}/{len(pairs)} distinct-dish pairs are >= tau ({s.dedup_tau}) "
          f"(want 0 — distinct dishes must NOT collapse)")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
