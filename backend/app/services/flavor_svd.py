"""Service 3 — Flavor + SVD (the explainability layer).

Batch `recompute_svd` fits a 10->n_factors SVD on the dish flavor matrix and stores the
components + singular values + mean, so any dish (including ones minted after the fit)
projects into factor space online without a refit. Factor labels are derived from the
strongest loadings *after* fitting — the data names the axes, not us.

These factors are explainability only. They are NEVER used for retrieval (that's the big
vector). This module uses numpy; projecting one dish is a cheap matrix-vector product and is
fine on the request path. Fitting is batch — never call `recompute_svd` inside a request.
"""
from __future__ import annotations

import hashlib
import logging

import numpy as np

from app.ports import FLAVOR_DIMS, DishRepository, SvdModel

logger = logging.getLogger("dishport.flavor_svd")

N_FACTORS = 4
_LOADING_THRESHOLD = 0.15   # minimum |loading| to mention a dimension in a factor label


def fit_svd(flavors: list[list[float]], n_factors: int = N_FACTORS,
            version: str | None = None) -> SvdModel:
    """Mean-center the N×10 flavor matrix, SVD, keep the top `n_factors` components."""
    X = np.asarray(flavors, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(FLAVOR_DIMS):
        raise ValueError(f"expected an N×{len(FLAVOR_DIMS)} flavor matrix, got {X.shape}")
    if X.shape[0] < n_factors:
        raise ValueError(f"need >= {n_factors} dishes to fit {n_factors} factors, "
                         f"got {X.shape[0]}")

    mean = X.mean(axis=0)
    Xc = X - mean
    _, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    comps = Vt[:n_factors].copy()
    sv = S[:n_factors]

    # SVD signs are arbitrary; fix each component's sign so its largest-magnitude loading is
    # positive. Makes labels and projections deterministic across runs.
    for i in range(comps.shape[0]):
        j = int(np.argmax(np.abs(comps[i])))
        if comps[i, j] < 0:
            comps[i] = -comps[i]

    components = comps.tolist()
    mean_list = mean.tolist()
    labels = [_label_factor(comp) for comp in comps]
    if version is None:
        version = _content_version(components, mean_list)
    return SvdModel(
        version=version,
        components=components,
        singular_values=sv.tolist(),
        mean=mean_list,
        factor_labels=labels,
    )


def project(flavor: list[float], model: SvdModel) -> list[float]:
    """Project one flavor vector into the model's factor space: components @ (flavor - mean)."""
    x = np.asarray(flavor, dtype=float) - np.asarray(model.mean, dtype=float)
    comps = np.asarray(model.components, dtype=float)
    return [round(float(v), 6) for v in (comps @ x)]


def _label_factor(comp: np.ndarray, k: int = 2) -> str:
    """Name a factor from its strongest ± loadings, e.g. 'rich+umami ↔ fresh+sour'."""
    order = np.argsort(comp)                      # ascending
    pos = [FLAVOR_DIMS[i] for i in reversed(order) if comp[i] >= _LOADING_THRESHOLD][:k]
    neg = [FLAVOR_DIMS[i] for i in order if comp[i] <= -_LOADING_THRESHOLD][:k]
    left = "+".join(pos) or "·"
    right = "+".join(neg) or "·"
    return f"{left} ↔ {right}"


def _content_version(components: list[list[float]], mean: list[float]) -> str:
    payload = repr((components, mean)).encode()
    return "svd-" + hashlib.sha1(payload).hexdigest()[:10]


async def recompute_svd(repo: DishRepository, n_factors: int = N_FACTORS) -> SvdModel | None:
    """BATCH. Fit the SVD over all dish flavors, persist the model + per-dish factors."""
    rows = await repo.all_dish_flavors()
    if len(rows) < n_factors:
        logger.warning("recompute_svd skipped: only %d dishes (< %d factors)",
                       len(rows), n_factors)
        return None

    model = fit_svd([flavor for _, flavor in rows], n_factors=n_factors)
    await repo.save_svd_model(model)
    await repo.save_dish_factors(
        [(dish_id, project(flavor, model)) for dish_id, flavor in rows],
        model.version,
    )
    logger.info("recompute_svd: fit %s over %d dishes; labels=%s",
                model.version, len(rows), model.factor_labels)
    return model
