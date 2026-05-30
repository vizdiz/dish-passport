"""Postgres + pgvector DishRepository, on an asyncpg pool.

Cosine neighbor via the `<=>` operator (cosine distance); cosine similarity = 1 - distance.
Requires `pgvector.asyncpg.register_vector` to have run on each connection — wired as the
pool `init` in app/main.py, so list/array vectors encode straight into `vector` columns.
"""
from __future__ import annotations

import json
from typing import Optional, Sequence

import asyncpg
from pgvector.asyncpg import register_vector

from app.ports import DishRecord, ImpressionRow, Neighbor, NormalizedDish, SvdModel

_DISH_COLS = (
    "id, name, canonical_description, ingredients, prep_method, "
    "flavor, embedding_model_version, created_at"
)


async def init_connection(conn: asyncpg.Connection) -> None:
    """Pool `init`: register pgvector codecs and a jsonb codec (for the SVD model)."""
    await register_vector(conn)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
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

    async def similar(self, dish_id: int, n: int) -> list[Neighbor]:
        """Top-n cosine neighbors of a dish, self excluded. Pure big-vector (Service 2)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_DISH_COLS}, 1 - (dishes.embedding <=> q.embedding) AS cosine "
                f"FROM dishes "
                f"CROSS JOIN (SELECT embedding FROM dishes WHERE id = $1) AS q "
                f"WHERE dishes.id <> $1 "
                f"ORDER BY dishes.embedding <=> q.embedding "
                f"LIMIT $2",
                dish_id, n,
            )
        return [Neighbor(dish=_to_record(row), cosine=float(row["cosine"])) for row in rows]

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

    # ---- flavor / SVD (Service 3) ----
    async def set_log_flavor_override(self, log_id: int, flavor: Sequence[float]) -> bool:
        async with self._pool.acquire() as conn:
            updated = await conn.fetchval(
                "UPDATE logs SET flavor_override = $2 WHERE id = $1 RETURNING id",
                log_id, list(flavor),
            )
        return updated is not None

    async def all_dish_flavors(self) -> list[tuple[int, list[float]]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, flavor FROM dishes ORDER BY id")
        return [(r["id"], [float(x) for x in r["flavor"]]) for r in rows]

    async def save_svd_model(self, model: SvdModel) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO flavor_svd_model "
                "(version, components, singular_values, mean, factor_labels) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (version) DO UPDATE SET "
                "components = EXCLUDED.components, singular_values = EXCLUDED.singular_values, "
                "mean = EXCLUDED.mean, factor_labels = EXCLUDED.factor_labels, created_at = now()",
                model.version, model.components, model.singular_values, model.mean,
                model.factor_labels,
            )

    async def get_latest_svd_model(self) -> Optional[SvdModel]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version, components, singular_values, mean, factor_labels "
                "FROM flavor_svd_model ORDER BY created_at DESC LIMIT 1"
            )
        if row is None:
            return None
        return SvdModel(
            version=row["version"],
            components=row["components"],
            singular_values=row["singular_values"],
            mean=row["mean"],
            factor_labels=row["factor_labels"],
        )

    async def save_dish_factors(
        self, factors: Sequence[tuple[int, list[float]]], svd_model_version: str
    ) -> None:
        if not factors:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO dish_flavor_factors (dish_id, factors, svd_model_version) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (dish_id) DO UPDATE SET "
                "factors = EXCLUDED.factors, svd_model_version = EXCLUDED.svd_model_version, "
                "updated_at = now()",
                [(dish_id, list(vec), svd_model_version) for dish_id, vec in factors],
            )

    async def get_dish_factors(self, dish_id: int) -> Optional[tuple[list[float], str]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT factors, svd_model_version FROM dish_flavor_factors WHERE dish_id = $1",
                dish_id,
            )
        if row is None:
            return None
        return ([float(x) for x in row["factors"]], row["svd_model_version"])
