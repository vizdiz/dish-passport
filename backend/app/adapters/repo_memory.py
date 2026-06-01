"""In-memory DishRepository. First-class adapter: backs every test and gives a
keys-optional local path. Pure-python cosine, so no numpy dependency."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional, Sequence

from app.ports import (
    DishRecord,
    ImpressionRow,
    Neighbor,
    NormalizedDish,
    SvdModel,
    TasteProfile,
)
from app.services.errors import UserExists


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


class InMemoryDishRepository:
    def __init__(self) -> None:
        self._dishes: dict[int, tuple[DishRecord, list[float]]] = {}
        self._logs: list[dict] = []
        self._impressions: list[ImpressionRow] = []
        self._user_log_count: dict[int, int] = {}
        self._svd_model: SvdModel | None = None
        self._dish_factors: dict[int, tuple[list[float], str]] = {}
        self._cf_user: dict[int, tuple[list[float], str]] = {}
        self._cf_item: dict[int, tuple[list[float], str]] = {}
        self._taste: dict[int, TasteProfile] = {}
        self._users_by_name: dict[str, tuple[int, str]] = {}  # username -> (id, password_hash)
        self._next_dish = 1
        self._next_log = 1
        self._next_user = 1

    # ---- auth / users ----
    async def create_user(self, username: str, password_hash: str) -> int:
        if username in self._users_by_name:
            raise UserExists(username)
        user_id = self._next_user
        self._next_user += 1
        self._users_by_name[username] = (user_id, password_hash)
        self._user_log_count.setdefault(user_id, 0)
        return user_id

    async def get_user_by_username(self, username: str) -> Optional[tuple[int, str]]:
        return self._users_by_name.get(username)

    async def log_belongs_to(self, log_id: int, user_id: int) -> bool:
        return any(log["id"] == log_id and log["user_id"] == user_id for log in self._logs)

    # ---- DishRepository ----
    async def get_dish(self, dish_id: int) -> Optional[DishRecord]:
        rec = self._dishes.get(dish_id)
        return rec[0] if rec is not None else None

    async def nearest(self, embedding: Sequence[float]) -> Optional[Neighbor]:
        best: Optional[Neighbor] = None
        for rec, emb in self._dishes.values():
            cos = _cosine(embedding, emb)
            if best is None or cos > best.cosine:
                best = Neighbor(dish=rec, cosine=cos)
        return best

    async def similar(self, dish_id: int, n: int) -> list[Neighbor]:
        target = self._dishes.get(dish_id)
        if target is None:
            return []
        _, target_emb = target
        scored = [
            Neighbor(dish=rec, cosine=_cosine(target_emb, emb))
            for did, (rec, emb) in self._dishes.items()
            if did != dish_id
        ]
        scored.sort(key=lambda nb: nb.cosine, reverse=True)
        return scored[:n]

    async def insert_dish(
        self,
        normalized: NormalizedDish,
        embedding: Sequence[float],
        embedding_model_version: str,
    ) -> DishRecord:
        dish_id = self._next_dish
        self._next_dish += 1
        rec = DishRecord(
            id=dish_id,
            name=normalized.name,
            description=normalized.description,
            ingredients=list(normalized.ingredients),
            prep_method=normalized.prep_method,
            flavor=list(normalized.flavor),
            embedding_model_version=embedding_model_version,
            created_at=datetime.now(timezone.utc),
        )
        self._dishes[dish_id] = (rec, list(embedding))
        return rec

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
        log_id = self._next_log
        self._next_log += 1
        self._logs.append(
            {
                "id": log_id,
                "user_id": user_id,
                "dish_id": dish_id,
                "sentiment": sentiment,
                "rating": rating,
                "notes": notes,
                "photo_url": photo_url,
                "flavor_override": None,
            }
        )
        self._user_log_count[user_id] = self._user_log_count.get(user_id, 0) + 1
        return log_id

    async def insert_impressions(self, rows: Sequence[ImpressionRow]) -> int:
        self._impressions.extend(rows)
        return len(rows)

    # ---- flavor / SVD (Service 3) ----
    async def set_log_flavor_override(self, log_id: int, flavor: Sequence[float]) -> bool:
        for log in self._logs:
            if log["id"] == log_id:
                log["flavor_override"] = list(flavor)
                return True
        return False

    async def all_dish_flavors(self) -> list[tuple[int, list[float]]]:
        return [(rec.id, list(rec.flavor)) for rec, _ in self._dishes.values()]

    async def save_svd_model(self, model: SvdModel) -> None:
        self._svd_model = model

    async def get_latest_svd_model(self) -> Optional[SvdModel]:
        return self._svd_model

    async def save_dish_factors(
        self, factors: Sequence[tuple[int, list[float]]], svd_model_version: str
    ) -> None:
        for dish_id, vec in factors:
            self._dish_factors[dish_id] = (list(vec), svd_model_version)

    async def get_dish_factors(self, dish_id: int) -> Optional[tuple[list[float], str]]:
        return self._dish_factors.get(dish_id)

    # ---- collaborative filtering (Service 4) ----
    async def all_logs(self) -> list[tuple[int, int, str]]:
        return [(log["user_id"], log["dish_id"], log["sentiment"]) for log in self._logs]

    async def save_cf_factors(
        self,
        user_factors: Sequence[tuple[int, list[float]]],
        item_factors: Sequence[tuple[int, list[float]]],
        model_version: str,
    ) -> None:
        for user_id, vec in user_factors:
            self._cf_user[user_id] = (list(vec), model_version)
        for dish_id, vec in item_factors:
            self._cf_item[dish_id] = (list(vec), model_version)

    async def get_cf_user_factors(self, user_id: int) -> Optional[tuple[list[float], str]]:
        return self._cf_user.get(user_id)

    async def get_cf_item_factors(self, dish_id: int) -> Optional[tuple[list[float], str]]:
        return self._cf_item.get(dish_id)

    async def all_cf_item_factors(self) -> list[tuple[int, list[float]]]:
        return [(dish_id, list(vec)) for dish_id, (vec, _) in self._cf_item.items()]

    # ---- recommendation / taste profiles (Service 5) ----
    async def all_user_ids(self) -> list[int]:
        return sorted(self._user_log_count)

    async def user_logs(self, user_id: int) -> list[tuple[int, str]]:
        return [(log["dish_id"], log["sentiment"]) for log in self._logs
                if log["user_id"] == user_id]

    async def user_impressions(self, user_id: int):
        return [(imp.dish_id, imp.shown_at, imp.converted) for imp in self._impressions
                if imp.user_id == user_id]

    async def dish_embeddings(self, dish_ids: Sequence[int]) -> dict[int, list[float]]:
        out: dict[int, list[float]] = {}
        for dish_id in dish_ids:
            rec = self._dishes.get(dish_id)
            if rec is not None:
                out[dish_id] = list(rec[1])
        return out

    async def vector_topk(
        self, embedding: Sequence[float], k: int, exclude_ids: Sequence[int]
    ) -> list[Neighbor]:
        excluded = set(exclude_ids)
        scored = [
            Neighbor(dish=rec, cosine=_cosine(embedding, emb))
            for dish_id, (rec, emb) in self._dishes.items()
            if dish_id not in excluded
        ]
        scored.sort(key=lambda nb: nb.cosine, reverse=True)
        return scored[:k]

    async def centroid_cosines(
        self,
        dish_ids: Sequence[int],
        liked_centroid: Sequence[float],
        disliked_centroid: Optional[Sequence[float]],
    ) -> dict[int, tuple[float, float]]:
        out: dict[int, tuple[float, float]] = {}
        for dish_id in dish_ids:
            rec = self._dishes.get(dish_id)
            if rec is None:
                continue
            emb = rec[1]
            cos_liked = _cosine(emb, liked_centroid)
            cos_disliked = _cosine(emb, disliked_centroid) if disliked_centroid else 0.0
            out[dish_id] = (cos_liked, cos_disliked)
        return out

    async def popular_dishes(self, k: int, exclude_ids: Sequence[int]) -> list[int]:
        excluded = set(exclude_ids)
        counts: dict[int, int] = {}
        for log in self._logs:
            counts[log["dish_id"]] = counts.get(log["dish_id"], 0) + 1
        ranked = sorted(
            (d for d in counts if d not in excluded),
            key=lambda d: counts[d], reverse=True,
        )
        return ranked[:k]

    async def save_taste_profile(self, profile: TasteProfile) -> None:
        self._taste[profile.user_id] = profile

    async def get_taste_profile(self, user_id: int) -> Optional[TasteProfile]:
        return self._taste.get(user_id)

    # ---- test / local helpers (not part of the port) ----
    def seed_dish(
        self,
        *,
        name: str,
        description: str,
        flavor: list[float],
        embedding: list[float],
        ingredients: Optional[list[str]] = None,
        prep_method: Optional[str] = None,
        model_version: str = "seed",
    ) -> DishRecord:
        dish_id = self._next_dish
        self._next_dish += 1
        rec = DishRecord(
            id=dish_id,
            name=name,
            description=description,
            ingredients=list(ingredients or []),
            prep_method=prep_method,
            flavor=list(flavor),
            embedding_model_version=model_version,
            created_at=datetime.now(timezone.utc),
        )
        self._dishes[dish_id] = (rec, list(embedding))
        return rec

    @property
    def dish_count(self) -> int:
        return len(self._dishes)

    @property
    def logs(self) -> list[dict]:
        return list(self._logs)

    @property
    def impressions(self) -> list[ImpressionRow]:
        return list(self._impressions)

    def log_count(self, user_id: int) -> int:
        return self._user_log_count.get(user_id, 0)
