"""Postgres + pgvector DishRepository, on an asyncpg pool.

Cosine neighbor via the `<=>` operator (cosine distance); cosine similarity = 1 - distance.
Requires `pgvector.asyncpg.register_vector` to have run on each connection — wired as the
pool `init` in app/main.py, so list/array vectors encode straight into `vector` columns.
"""
from __future__ import annotations

from typing import Optional, Sequence

import asyncpg

from app.ports import DishRecord, ImpressionRow, Neighbor, NormalizedDish

_DISH_COLS = (
    "id, name, canonical_description, ingredients, prep_method, "
    "flavor, embedding_model_version, created_at"
)


def _to_record(row: asyncpg.Record) -> DishRecord:
    return DishRecord(
        id=row["id"],
        name=row["name"],
        description=row["canonical_description"],
        ingredients=list(row["ingredients"] or []),
        prep_method=row["prep_method"],
        flavor=[float(x) for x in row["flavor"]],
        embedding_model_version=row["embedding_model_version"],
        created_at=row["created_at"],
    )


class PgVectorRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_dish(self, dish_id: int) -> Optional[DishRecord]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_DISH_COLS} FROM dishes WHERE id = $1", dish_id
            )
        return _to_record(row) if row is not None else None

    async def nearest(self, embedding: Sequence[float]) -> Optional[Neighbor]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_DISH_COLS}, 1 - (embedding <=> $1) AS cosine "
                f"FROM dishes ORDER BY embedding <=> $1 LIMIT 1",
                list(embedding),
            )
        if row is None:
            return None
        return Neighbor(dish=_to_record(row), cosine=float(row["cosine"]))

    async def insert_dish(
        self,
        normalized: NormalizedDish,
        embedding: Sequence[float],
        embedding_model_version: str,
    ) -> DishRecord:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO dishes "
                "(name, canonical_description, ingredients, prep_method, "
                " embedding, embedding_model_version, flavor) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                f"RETURNING {_DISH_COLS}",
                normalized.name,
                normalized.description,
                list(normalized.ingredients),
                normalized.prep_method,
                list(embedding),
                embedding_model_version,
                list(normalized.flavor),
            )
        return _to_record(row)

    async def insert_log(
        self,
        *,
        user_id: int,
        dish_id: int,
        sentiment: str,
        rating: Optional[int],
        notes: Optional[str],
    ) -> int:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
                    user_id,
                )
                log_id = await conn.fetchval(
                    "INSERT INTO logs (user_id, dish_id, sentiment, rating, notes) "
                    "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                    user_id, dish_id, sentiment, rating, notes,
                )
                await conn.execute(
                    "UPDATE users SET log_count = log_count + 1 WHERE id = $1", user_id
                )
        return int(log_id)

    async def insert_impressions(self, rows: Sequence[ImpressionRow]) -> int:
        if not rows:
            return 0
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO impressions (user_id, dish_id, shown_at, context, converted) "
                "VALUES ($1, $2, $3, $4, $5)",
                [(r.user_id, r.dish_id, r.shown_at, r.context, r.converted) for r in rows],
            )
        return len(rows)
