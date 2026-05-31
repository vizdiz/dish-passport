"""The dedup gate. Free text or dish_id -> canonical dish -> log.

This module is the riskiest part of the system and the most heavily tested. It depends
only on ports (Embedder, DishNormalizer, DishRepository) so it is DB- and vendor-agnostic.

Three decision paths, every one logged for human audit:
  * fastlane — dish_id supplied; validate + log. No LLM, no embed.
  * link     — novel text, but its description embeds within DEDUP_TAU of an existing dish.
  * mint     — novel text, far from everything; create a new canonical dish.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ports import DishNormalizer, DishRecord, DishRepository, Embedder
from app.services.errors import DishNotFound  # re-exported for callers/tests

logger = logging.getLogger("dishport.ingestion")

__all__ = ["DishNotFound", "LogResult", "log_dish"]


@dataclass(frozen=True)
class LogResult:
    dish: DishRecord
    is_new: bool
    log_id: int


async def log_dish(
    *,
    repo: DishRepository,
    embedder: Embedder,
    normalizer: DishNormalizer,
    user_id: int,
    text: str | None = None,
    dish_id: int | None = None,
    sentiment: str = "liked",
    rating: int | None = None,
    notes: str | None = None,
    photo_url: str | None = None,
    tau: float,
) -> LogResult:
    """Run the gate and write a log. Returns the canonical dish, is_new, and log id."""
    if (text is None) == (dish_id is None):
        raise ValueError("exactly one of `text` or `dish_id` is required")

    # ---- Fast lane: dish_id is already canonical. No LLM, no embed. ----
    if dish_id is not None:
        dish = await repo.get_dish(dish_id)
        if dish is None:
            raise DishNotFound(dish_id)
        log_id = await _write_log(repo, user_id, dish.id, sentiment, rating, notes, photo_url)
        logger.info(
            "dedup decision=fastlane dish_id=%s user_id=%s log_id=%s",
            dish.id, user_id, log_id,
        )
        return LogResult(dish=dish, is_new=False, log_id=log_id)

    # ---- Novel free text: normalize (1 LLM call) -> embed description -> nearest. ----
    assert text is not None
    normalized = await normalizer.normalize(text)
    embedding = await embedder.embed(normalized.description)
    neighbor = await repo.nearest(embedding)

    if neighbor is not None and neighbor.cosine >= tau:
        dish = neighbor.dish              # link: reuse the canonical dish's flavor
        is_new = False
        logger.info(
            "dedup decision=link dish_id=%s name=%r cosine=%.4f tau=%.2f input=%r",
            dish.id, dish.name, neighbor.cosine, tau, text,
        )
    else:
        dish = await repo.insert_dish(normalized, embedding, embedder.model_version)
        is_new = True
        cosine_str = f"{neighbor.cosine:.4f}" if neighbor is not None else "none"
        logger.info(
            "dedup decision=mint dish_id=%s name=%r cosine=%s tau=%.2f input=%r",
            dish.id, dish.name, cosine_str, tau, text,
        )

    log_id = await _write_log(repo, user_id, dish.id, sentiment, rating, notes, photo_url)
    return LogResult(dish=dish, is_new=is_new, log_id=log_id)


async def _write_log(
    repo: DishRepository,
    user_id: int,
    dish_id: int,
    sentiment: str,
    rating: int | None,
    notes: str | None,
    photo_url: str | None,
) -> int:
    return await repo.insert_log(
        user_id=user_id, dish_id=dish_id, sentiment=sentiment, rating=rating, notes=notes,
        photo_url=photo_url,
    )
