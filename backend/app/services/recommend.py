"""Service 5 (online) — the recommendation ensemble. Retrieve-then-rank; never score the
whole catalog. Reads batch artifacts (taste profiles, CF factors, SVD model); trains nothing.

Cold start (log_count < 5 or no liked centroid): pure vector retrieval.
Warm: candidate union (vector ∪ ALS ∪ a little popularity), drop logged + disliked, then
    score = w_cf·cf + w_cb·cb + w_vec·vec     (each signal min-max normalized over candidates)
    cb (Rocchio) = cos(dish, liked_centroid) − β·cos(dish, disliked_centroid),  β = 0.4
Weights ramp on log_count. Explanations come from flavor factors, never the embedding.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.ports import FLAVOR_DIMS, DishRecord, DishRepository, Neighbor, SvdModel, TasteProfile
from app.services.flavor_svd import project

BETA = 0.4                     # Rocchio disliked-centroid penalty
CANDIDATES_PER_SOURCE = 50


@dataclass(frozen=True)
class Recommendation:
    dish: DishRecord
    score: float
    explanation: str
    components: dict[str, float]


@dataclass(frozen=True)
class RecommendResult:
    cold_start: bool
    recommendations: list[Recommendation]


def ramp(log_count: int) -> tuple[float, float, float]:
    """(w_cf, w_cb, w_vec) priors that ramp with experience."""
    if log_count < 5:
        return (0.0, 0.0, 1.0)
    if log_count >= 20:
        return (0.6, 0.3, 0.1)
    t = (log_count - 5) / (20 - 5)          # 0 at 5, ~0.93 at 19
    w_cf = 0.2 + (0.5 - 0.2) * t
    w_cb = 0.3
    return (w_cf, w_cb, max(0.0, 1.0 - w_cf - w_cb))


def _minmax(raw: dict[int, float]) -> dict[int, float]:
    if not raw:
        return {}
    lo, hi = min(raw.values()), max(raw.values())
    if hi - lo < 1e-12:
        return {k: 0.0 for k in raw}        # no spread => no signal
    return {k: (v - lo) / (hi - lo) for k, v in raw.items()}


async def recommend(repo: DishRepository, user_id: int, n: int) -> RecommendResult:
    logs = await repo.user_logs(user_id)
    log_count = len(logs)
    exclude = [d for d, _ in logs]          # drop everything already logged (incl. disliked)

    profile = await repo.get_taste_profile(user_id)
    liked_centroid = profile.liked_centroid if profile else None
    disliked_centroid = profile.disliked_centroid if profile else None
    svd_model = await repo.get_latest_svd_model()

    cold = log_count < 5 or not liked_centroid
    k = max(CANDIDATES_PER_SOURCE, n * 3)

    if cold:
        cands = await _cold_candidates(repo, liked_centroid, exclude, k)
        ranked = sorted(cands, key=lambda nb: nb.cosine, reverse=True)[:n]
        recs = [
            Recommendation(nb.dish, round(nb.cosine, 4),
                           _explain(nb.dish, svd_model, profile), {"vec": round(nb.cosine, 4)})
            for nb in ranked
        ]
        return RecommendResult(cold_start=True, recommendations=recs)

    # ---- warm: union candidates from vector, ALS, popularity ----
    dishes: dict[int, DishRecord] = {}
    for nb in await repo.vector_topk(liked_centroid, k, exclude):
        dishes[nb.dish.id] = nb.dish
    for dish_id, rec in await _als_topk(repo, user_id, k, set(exclude)):
        dishes[dish_id] = rec
    for dish_id in await repo.popular_dishes(max(5, n), exclude):
        if dish_id not in dishes:
            rec = await repo.get_dish(dish_id)
            if rec is not None:
                dishes[dish_id] = rec

    cand_ids = list(dishes)
    if not cand_ids:
        return RecommendResult(cold_start=False, recommendations=[])

    cos = await repo.centroid_cosines(cand_ids, liked_centroid, disliked_centroid)
    user_factors = await repo.get_cf_user_factors(user_id)
    uf = np.asarray(user_factors[0], dtype=float) if user_factors else None

    cf_raw, vec_raw, cb_raw = {}, {}, {}
    for dish_id in cand_ids:
        cos_liked, cos_disliked = cos.get(dish_id, (0.0, 0.0))
        vec_raw[dish_id] = cos_liked
        cb_raw[dish_id] = cos_liked - BETA * cos_disliked
        item = await repo.get_cf_item_factors(dish_id)
        if item is not None and uf is not None and len(item[0]) == len(uf):
            cf_raw[dish_id] = float(np.dot(uf, np.asarray(item[0], dtype=float)))
        else:
            cf_raw[dish_id] = 0.0

    cf_n, cb_n, vec_n = _minmax(cf_raw), _minmax(cb_raw), _minmax(vec_raw)
    w_cf, w_cb, w_vec = ramp(log_count)

    scored = []
    for dish_id in cand_ids:
        score = w_cf * cf_n[dish_id] + w_cb * cb_n[dish_id] + w_vec * vec_n[dish_id]
        scored.append((dish_id, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    recs = []
    for dish_id, score in scored[:n]:
        rec = dishes[dish_id]
        recs.append(Recommendation(
            dish=rec,
            score=round(score, 4),
            explanation=_explain(rec, svd_model, profile),
            components={"cf": round(cf_n[dish_id], 3), "cb": round(cb_n[dish_id], 3),
                        "vec": round(vec_n[dish_id], 3)},
        ))
    return RecommendResult(cold_start=False, recommendations=recs)


async def _cold_candidates(
    repo: DishRepository, liked_centroid, exclude: list[int], k: int
) -> list[Neighbor]:
    if liked_centroid:
        return await repo.vector_topk(liked_centroid, k, exclude)
    if exclude:                                          # has logs but no centroid yet
        best: dict[int, Neighbor] = {}
        for dish_id in list(reversed(exclude))[:3]:      # union similar() of last few logged
            for nb in await repo.similar(dish_id, k):
                if nb.dish.id in exclude:
                    continue
                if nb.dish.id not in best or nb.cosine > best[nb.dish.id].cosine:
                    best[nb.dish.id] = nb
        return list(best.values())
    # brand-new user: popularity, no vector signal
    out = []
    for dish_id in await repo.popular_dishes(k, exclude):
        rec = await repo.get_dish(dish_id)
        if rec is not None:
            out.append(Neighbor(dish=rec, cosine=0.0))
    return out


async def _als_topk(
    repo: DishRepository, user_id: int, k: int, exclude: set[int]
) -> list[tuple[int, DishRecord]]:
    user_factors = await repo.get_cf_user_factors(user_id)
    if not user_factors:
        return []
    uf = np.asarray(user_factors[0], dtype=float)
    scored = []
    for dish_id, vec in await repo.all_cf_item_factors():
        if dish_id in exclude or len(vec) != len(uf):
            continue
        scored.append((dish_id, float(np.dot(uf, np.asarray(vec, dtype=float)))))
    scored.sort(key=lambda x: x[1], reverse=True)
    out = []
    for dish_id, _ in scored[:k]:
        rec = await repo.get_dish(dish_id)
        if rec is not None:
            out.append((dish_id, rec))
    return out


def _explain(dish: DishRecord, svd_model: SvdModel | None, profile: TasteProfile | None) -> str:
    """Explain from flavor factors (never the embedding). Falls back to raw flavor dims."""
    if svd_model is None:
        top = sorted(zip(FLAVOR_DIMS, dish.flavor), key=lambda x: x[1], reverse=True)[:2]
        return "high " + " + ".join(dim for dim, _ in top)

    factors = project(dish.flavor, svd_model)
    idx = max(range(len(factors)), key=lambda i: abs(factors[i]))
    sides = svd_model.factor_labels[idx].split("↔")
    side = (sides[0] if factors[idx] >= 0 else sides[-1]).strip()
    message = f"high {side}"
    pref = profile.flavor_factor_pref if profile else None
    if pref and idx < len(pref) and pref[idx] * factors[idx] > 0:
        message += " — matches your taste"
    return message
