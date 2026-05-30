"""In-memory DishRepository. First-class adapter: backs every test and gives a
keys-optional local path. Pure-python cosine, so no numpy dependency."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional, Sequence

from app.ports import DishRecord, ImpressionRow, Neighbor, NormalizedDish, SvdModel


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
        self._next_dish = 1
        self._next_log = 1

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
