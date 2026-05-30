"""Service 2 — Similarity. Pure big-vector neighbors; no CF, no flavor.

This is the layer that surfaces cross-cuisine kinship (ceviche ~ larb) straight from the
opaque embedding, and the empirical instrument for calibrating DEDUP_TAU.
"""
from __future__ import annotations

from app.ports import DishRepository, Neighbor
from app.services.errors import DishNotFound


async def similar_dishes(repo: DishRepository, dish_id: int, n: int) -> list[Neighbor]:
    """Top-n cosine neighbors of `dish_id`, self excluded. Raises DishNotFound if missing."""
    dish = await repo.get_dish(dish_id)
    if dish is None:
        raise DishNotFound(dish_id)
    return await repo.similar(dish_id, n)
