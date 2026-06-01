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

from app.ports import (
    DishRecord,
    ImpressionRow,
    Neighbor,
    NormalizedDish,
    SvdModel,
    TasteProfile,
)
from app.services.errors import UserExists

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


def _vec_or_none(v) -> Optional[list[float]]:
    return [float(x) for x in v] if v is not None else None


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

    # ---- auth / users ----
    async def create_user(self, username: str, password_hash: str) -> int:
        async with self._pool.acquire() as conn:
            try:
                return await conn.fetchval(
                    "INSERT INTO users (username, password_hash) VALUES ($1, $2) RETURNING id",
                    username, password_hash,
                )
            except asyncpg.UniqueViolationError as exc:
                raise UserExists(username) from exc

    async def get_user_by_username(self, username: str) -> Optional[tuple[int, str]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, password_hash FROM users WHERE username = $1", username
            )
        return (row["id"], row["password_hash"]) if row is not None else None

    async def log_belongs_to(self, log_id: int, user_id: int) -> bool:
        async with self._pool.acquire() as conn:
            found = await conn.fetchval(
                "SELECT 1 FROM logs WHERE id = $1 AND user_id = $2", log_id, user_id
            )
        return found is not None

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
        photo_url: Optional[str] = None,
    ) -> int:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
                    user_id,
                )
                log_id = await conn.fetchval(
                    "INSERT INTO logs (user_id, dish_id, sentiment, rating, notes, photo_url) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                    user_id, dish_id, sentiment, rating, notes, photo_url,
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

    # ---- collaborative filtering (Service 4) ----
    async def all_logs(self) -> list[tuple[int, int, str]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, dish_id, sentiment FROM logs")
        return [(r["user_id"], r["dish_id"], r["sentiment"]) for r in rows]

    async def save_cf_factors(
        self,
        user_factors: Sequence[tuple[int, list[float]]],
        item_factors: Sequence[tuple[int, list[float]]],
        model_version: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if user_factors:
                    await conn.executemany(
                        "INSERT INTO cf_user_factors (user_id, factors, model_version) "
                        "VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET "
                        "factors = EXCLUDED.factors, model_version = EXCLUDED.model_version, "
                        "computed_at = now()",
                        [(uid, [float(x) for x in vec], model_version) for uid, vec in user_factors],
                    )
                if item_factors:
                    await conn.executemany(
                        "INSERT INTO cf_item_factors (dish_id, factors, model_version) "
                        "VALUES ($1, $2, $3) ON CONFLICT (dish_id) DO UPDATE SET "
                        "factors = EXCLUDED.factors, model_version = EXCLUDED.model_version, "
                        "computed_at = now()",
                        [(did, [float(x) for x in vec], model_version) for did, vec in item_factors],
                    )

    async def get_cf_user_factors(self, user_id: int) -> Optional[tuple[list[float], str]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT factors, model_version FROM cf_user_factors WHERE user_id = $1", user_id
            )
        if row is None:
            return None
        return ([float(x) for x in row["factors"]], row["model_version"])

    async def get_cf_item_factors(self, dish_id: int) -> Optional[tuple[list[float], str]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT factors, model_version FROM cf_item_factors WHERE dish_id = $1", dish_id
            )
        if row is None:
            return None
        return ([float(x) for x in row["factors"]], row["model_version"])

    async def all_cf_item_factors(self) -> list[tuple[int, list[float]]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT dish_id, factors FROM cf_item_factors")
        return [(r["dish_id"], [float(x) for x in r["factors"]]) for r in rows]

    # ---- recommendation / taste profiles (Service 5) ----
    async def all_user_ids(self) -> list[int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM users ORDER BY id")
        return [r["id"] for r in rows]

    async def user_logs(self, user_id: int) -> list[tuple[int, str]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT dish_id, sentiment FROM logs WHERE user_id = $1 ORDER BY id", user_id
            )
        return [(r["dish_id"], r["sentiment"]) for r in rows]

    async def user_impressions(self, user_id: int):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT dish_id, shown_at, converted FROM impressions WHERE user_id = $1", user_id
            )
        return [(r["dish_id"], r["shown_at"], r["converted"]) for r in rows]

    async def dish_embeddings(self, dish_ids: Sequence[int]) -> dict[int, list[float]]:
        if not dish_ids:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, embedding FROM dishes WHERE id = ANY($1::bigint[])", list(dish_ids)
            )
        return {r["id"]: [float(x) for x in r["embedding"]] for r in rows}

    async def vector_topk(
        self, embedding: Sequence[float], k: int, exclude_ids: Sequence[int]
    ) -> list[Neighbor]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_DISH_COLS}, 1 - (embedding <=> $1) AS cosine "
                f"FROM dishes WHERE id <> ALL($2::bigint[]) "
                f"ORDER BY embedding <=> $1 LIMIT $3",
                list(embedding), list(exclude_ids), k,
            )
        return [Neighbor(dish=_to_record(row), cosine=float(row["cosine"])) for row in rows]

    async def centroid_cosines(
        self,
        dish_ids: Sequence[int],
        liked_centroid: Sequence[float],
        disliked_centroid: Optional[Sequence[float]],
    ) -> dict[int, tuple[float, float]]:
        if not dish_ids:
            return {}
        async with self._pool.acquire() as conn:
            if disliked_centroid is None:
                rows = await conn.fetch(
                    "SELECT id, 1 - (embedding <=> $1) AS cl FROM dishes "
                    "WHERE id = ANY($2::bigint[])",
                    list(liked_centroid), list(dish_ids),
                )
                return {r["id"]: (float(r["cl"]), 0.0) for r in rows}
            rows = await conn.fetch(
                "SELECT id, 1 - (embedding <=> $1) AS cl, 1 - (embedding <=> $3) AS cd "
                "FROM dishes WHERE id = ANY($2::bigint[])",
                list(liked_centroid), list(dish_ids), list(disliked_centroid),
            )
        return {r["id"]: (float(r["cl"]), float(r["cd"])) for r in rows}

    async def popular_dishes(self, k: int, exclude_ids: Sequence[int]) -> list[int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT dish_id, count(*) AS c FROM logs WHERE dish_id <> ALL($1::bigint[]) "
                "GROUP BY dish_id ORDER BY c DESC, dish_id LIMIT $2",
                list(exclude_ids), k,
            )
        return [r["dish_id"] for r in rows]

    async def save_taste_profile(self, profile: TasteProfile) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_taste_profiles "
                "(user_id, liked_centroid, disliked_centroid, flavor_factor_pref, n_dishes, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, now()) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "liked_centroid = EXCLUDED.liked_centroid, "
                "disliked_centroid = EXCLUDED.disliked_centroid, "
                "flavor_factor_pref = EXCLUDED.flavor_factor_pref, "
                "n_dishes = EXCLUDED.n_dishes, updated_at = now()",
                profile.user_id,
                list(profile.liked_centroid) if profile.liked_centroid is not None else None,
                list(profile.disliked_centroid) if profile.disliked_centroid is not None else None,
                list(profile.flavor_factor_pref) if profile.flavor_factor_pref is not None else None,
                profile.n_dishes,
            )

    async def get_taste_profile(self, user_id: int) -> Optional[TasteProfile]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, liked_centroid, disliked_centroid, flavor_factor_pref, n_dishes "
                "FROM user_taste_profiles WHERE user_id = $1",
                user_id,
            )
        if row is None:
            return None
        return TasteProfile(
            user_id=row["user_id"],
            liked_centroid=_vec_or_none(row["liked_centroid"]),
            disliked_centroid=_vec_or_none(row["disliked_centroid"]),
            flavor_factor_pref=_vec_or_none(row["flavor_factor_pref"]),
            n_dishes=row["n_dishes"],
        )
