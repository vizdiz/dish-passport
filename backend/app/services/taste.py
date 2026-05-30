"""Service 5 (batch) — rebuild_taste_profiles.

Per user:
  * liked_centroid       = mean embedding of liked/neutral dishes
  * disliked_centroid    = weighted mean of disliked dishes (weight 1) + non-converted
                           impressions as *decaying* soft negatives (older = weaker)
  * flavor_factor_pref   = mean latent-factor vector over liked dishes
Disliked dishes are both filtered from recs (online) AND fed here as signal — both, not either.
BATCH only — never in a request.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

from app.ports import DishRepository, TasteProfile

logger = logging.getLogger("dishport.taste")

POSITIVE = {"liked", "neutral"}
SOFT_NEG_HALF_LIFE_DAYS = 14.0


def _mean(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    return np.mean(np.asarray(vectors, dtype=float), axis=0).tolist()


def _weighted_mean(pairs: list[tuple[list[float], float]]) -> list[float] | None:
    total = sum(w for _, w in pairs)
    if not pairs or total <= 0:
        return None
    acc = np.zeros(len(pairs[0][0]), dtype=float)
    for vec, weight in pairs:
        acc += np.asarray(vec, dtype=float) * weight
    return (acc / total).tolist()


async def rebuild_taste_profiles(
    repo: DishRepository,
    now: datetime | None = None,
    half_life_days: float = SOFT_NEG_HALF_LIFE_DAYS,
) -> int:
    now = now or datetime.now(timezone.utc)
    n = 0
    for user_id in await repo.all_user_ids():
        await repo.save_taste_profile(await _build_one(repo, user_id, now, half_life_days))
        n += 1
    logger.info("rebuild_taste_profiles: %d users", n)
    return n


async def _build_one(
    repo: DishRepository, user_id: int, now: datetime, half_life_days: float
) -> TasteProfile:
    logs = await repo.user_logs(user_id)
    liked_ids = [d for d, s in logs if s in POSITIVE]
    disliked_ids = [d for d, s in logs if s == "disliked"]
    impressions = await repo.user_impressions(user_id)

    needed = set(liked_ids) | set(disliked_ids) | {d for d, _, conv in impressions if not conv}
    emb = await repo.dish_embeddings(list(needed))

    liked_centroid = _mean([emb[d] for d in liked_ids if d in emb])

    neg_pairs: list[tuple[list[float], float]] = [(emb[d], 1.0) for d in disliked_ids if d in emb]
    for dish_id, shown_at, converted in impressions:
        if converted or dish_id not in emb:
            continue
        age_days = max(0.0, (now - _aware(shown_at)).total_seconds() / 86400.0)
        neg_pairs.append((emb[dish_id], 0.5 ** (age_days / half_life_days)))
    disliked_centroid = _weighted_mean(neg_pairs)

    factor_vecs: list[list[float]] = []
    for dish_id in liked_ids:
        factors = await repo.get_dish_factors(dish_id)
        if factors is not None:
            factor_vecs.append(factors[0])
    flavor_factor_pref = _mean(factor_vecs)

    return TasteProfile(
        user_id=user_id,
        liked_centroid=liked_centroid,
        disliked_centroid=disliked_centroid,
        flavor_factor_pref=flavor_factor_pref,
        n_dishes=len(set(liked_ids) | set(disliked_ids)),
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
