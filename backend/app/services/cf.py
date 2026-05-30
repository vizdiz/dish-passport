"""Service 4 — Collaborative filtering (implicit, confidence-weighted ALS).

Hu/Koren/Volinsky (2008). Each user×dish cell has a preference p ∈ {0,1} and a confidence
c = 1 + α·w. The whole point of *implicit* ALS is the closed-form trick that lets unobserved
cells (p=0, c=1) stay implicit while observed cells get their real confidence:

    A_u = YᵀY + Yₒᵀ·diag(cₒ − 1)·Yₒ + λI        (only observed rows perturb YᵀY)
    b_u = Yₒᵀ·(cₒ · pₒ)
    x_u = A_u⁻¹ b_u

Signal mapping (the load-bearing distinction — disliked is NOT unseen):
    liked    → p=1, w=1.0   (strong positive)
    neutral  → p=1, w=0.1   (weak positive)
    disliked → p=0, w=1.0   (strong *known-zero* — high confidence the preference is 0)
    unseen   → p=0, c=1      (implicit; low confidence)

This is BATCH. Never call retrain_als inside a request. At inference (Service 5) the CF score
is just xᵤ·yᵢ over the precomputed factors — a read, never a train.
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from app.ports import DishRepository

logger = logging.getLogger("dishport.cf")

DEFAULT_FACTORS = 16
DEFAULT_ALPHA = 40.0
DEFAULT_REG = 0.1
DEFAULT_ITERS = 15

_WEIGHT = {"liked": (1.0, 0.0), "neutral": (0.1, 0.0), "disliked": (0.0, 1.0)}


@dataclass(frozen=True)
class CfResult:
    version: str
    n_users: int
    n_items: int
    n_factors: int


def aggregate_preferences(
    logs: list[tuple[int, int, str]],
) -> dict[tuple[int, int], tuple[float, float]]:
    """Collapse a user's possibly-many logs of a dish into one (preference, weight).

    Positive evidence (liked/neutral) and negative evidence (disliked) accumulate; whichever
    side is heavier wins, ties go positive. Returns {(user_id, dish_id): (preference, weight)}.
    """
    acc: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for user_id, dish_id, sentiment in logs:
        pos, neg = _WEIGHT.get(sentiment, (0.0, 0.0))
        cell = acc[(user_id, dish_id)]
        cell[0] += pos
        cell[1] += neg

    out: dict[tuple[int, int], tuple[float, float]] = {}
    for key, (pos_w, neg_w) in acc.items():
        if neg_w > pos_w:
            out[key] = (0.0, neg_w)        # disliked dominates: known-zero, high confidence
        elif pos_w > 0.0:
            out[key] = (1.0, pos_w)        # positive
        # both zero -> not an observation
    return out


def train_als(
    user_obs: dict[int, list[tuple[int, float, float]]],
    item_obs: dict[int, list[tuple[int, float, float]]],
    n_users: int,
    n_items: int,
    n_factors: int,
    reg: float = DEFAULT_REG,
    iters: int = DEFAULT_ITERS,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Alternating least squares. `*_obs[row] = [(col, confidence, preference), ...]`."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_users, n_factors)) * 0.01
    Y = rng.standard_normal((n_items, n_factors)) * 0.01
    eye = np.eye(n_factors)
    for _ in range(iters):
        X = _solve_factors(user_obs, Y, n_users, reg, eye)
        Y = _solve_factors(item_obs, X, n_items, reg, eye)
    return X, Y


def _solve_factors(
    obs_by_row: dict[int, list[tuple[int, float, float]]],
    other: np.ndarray,
    n_rows: int,
    reg: float,
    eye: np.ndarray,
) -> np.ndarray:
    gram = other.T @ other                          # YᵀY (or XᵀX), reused across rows
    reg_eye = reg * eye
    out = np.zeros((n_rows, other.shape[1]))
    for row in range(n_rows):
        obs = obs_by_row.get(row)
        if not obs:
            continue                                # cold row stays at zero
        idx = np.fromiter((c for c, _, _ in obs), dtype=int, count=len(obs))
        conf = np.fromiter((cc for _, cc, _ in obs), dtype=float, count=len(obs))
        pref = np.fromiter((pp for _, _, pp in obs), dtype=float, count=len(obs))
        factors_obs = other[idx]                    # (n_obs, k)
        a = gram + (factors_obs * (conf - 1.0)[:, None]).T @ factors_obs + reg_eye
        b = factors_obs.T @ (conf * pref)
        out[row] = np.linalg.solve(a, b)
    return out


async def retrain_als(
    repo: DishRepository,
    n_factors: int = DEFAULT_FACTORS,
    alpha: float = DEFAULT_ALPHA,
    reg: float = DEFAULT_REG,
    iters: int = DEFAULT_ITERS,
) -> CfResult | None:
    """BATCH. Factorize the confidence-weighted interaction matrix; persist user/item factors."""
    prefs = aggregate_preferences(await repo.all_logs())
    if not prefs:
        logger.warning("retrain_als skipped: no interactions")
        return None

    users = sorted({u for u, _ in prefs})
    items = sorted({d for _, d in prefs})
    uix = {u: i for i, u in enumerate(users)}
    iix = {d: i for i, d in enumerate(items)}

    # Clamp factors to the rank the data can support (avoids singular/over-parameterized fits).
    k = max(1, min(n_factors, len(users), len(items)))

    user_obs: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    item_obs: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for (user_id, dish_id), (pref, weight) in prefs.items():
        conf = 1.0 + alpha * weight
        u, d = uix[user_id], iix[dish_id]
        user_obs[u].append((d, conf, pref))
        item_obs[d].append((u, conf, pref))

    X, Y = train_als(user_obs, item_obs, len(users), len(items), k, reg=reg, iters=iters)
    version = _version(prefs, k, alpha, reg, iters)

    await repo.save_cf_factors(
        [(u, X[uix[u]].tolist()) for u in users],
        [(d, Y[iix[d]].tolist()) for d in items],
        version,
    )
    logger.info("retrain_als: %s — %d users × %d items, k=%d", version, len(users), len(items), k)
    return CfResult(version=version, n_users=len(users), n_items=len(items), n_factors=k)


def _version(prefs: dict, k: int, alpha: float, reg: float, iters: int) -> str:
    payload = repr((sorted(prefs.items()), k, alpha, reg, iters)).encode()
    return "als-" + hashlib.sha1(payload).hexdigest()[:10]
