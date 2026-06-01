"""Service 5 — the recommendation ensemble: weight ramp, cold vs warm, candidate
exclusion (logged + disliked), flavor-factor explanations, and the two endpoints."""
from __future__ import annotations

import asyncio

import pytest

from app.services.cf import retrain_als
from app.services.flavor_svd import recompute_svd
from app.services.recommend import _minmax, ramp, recommend
from app.services.taste import rebuild_taste_profiles
from tests.fakes import StubEmbedder, StubNormalizer, vec_cos_to_axis0

# 10 dishes laid out along a cosine gradient so neighbors are well-ordered.
N_DISHES = 10


def _flavor(i: int) -> list[float]:
    v = [0.2] * 10
    v[i % 10] = 0.9
    return v


async def _build_world(repo):
    """Seed a gradient catalog + a few users, then run all three batch jobs."""
    ids = [
        repo.seed_dish(name=f"D{i}", description=f"d{i}", flavor=_flavor(i),
                       embedding=vec_cos_to_axis0(1.0 - 0.07 * i)).id
        for i in range(N_DISHES)
    ]
    async def log(uid, idx, sentiment="liked"):
        await repo.insert_log(user_id=uid, dish_id=ids[idx], sentiment=sentiment,
                              rating=None, notes=None)

    for idx in range(5):           # user 1: warm (6 logs incl. a dislike)
        await log(1, idx)
    await log(1, 9, "disliked")
    for idx in range(3):           # user 2: shares likes with user 1 (CF overlap)
        await log(2, idx)
    for idx in range(2):           # user 4: cold (2 logs)
        await log(4, idx)

    await recompute_svd(repo)
    await retrain_als(repo, n_factors=8)
    await rebuild_taste_profiles(repo)
    return ids


# --------------------------------------------------------------------------- pure helpers

def test_ramp_endpoints_and_continuity():
    assert ramp(0) == (0.0, 0.0, 1.0)
    assert ramp(4) == (0.0, 0.0, 1.0)
    assert ramp(5) == pytest.approx((0.2, 0.3, 0.5))
    assert ramp(20) == (0.6, 0.3, 0.1)
    w = ramp(19)
    assert 0.45 < w[0] < 0.5 and w[1] == 0.3
    for lc in (0, 5, 12, 19, 20, 100):
        assert sum(ramp(lc)) == pytest.approx(1.0)


def test_minmax_normalizes_and_handles_flat():
    assert _minmax({1: 0.0, 2: 1.0, 3: 0.5}) == {1: 0.0, 2: 1.0, 3: 0.5}
    assert _minmax({1: 7.0, 2: 7.0}) == {1: 0.0, 2: 0.0}


# --------------------------------------------------------------------------- ensemble

async def test_warm_ensemble_excludes_logged_and_disliked(repo):
    ids = await _build_world(repo)
    logged_user1 = set(ids[:5]) | {ids[9]}

    result = await recommend(repo, user_id=1, n=5)

    assert result.cold_start is False
    rec_ids = [r.dish.id for r in result.recommendations]
    assert rec_ids and logged_user1.isdisjoint(rec_ids)         # nothing logged/disliked
    assert ids[9] not in rec_ids                                # the disliked dish, explicitly
    for r in result.recommendations:
        assert {"cf", "cb", "vec"} <= set(r.components)
        assert r.explanation.startswith("high")                 # from flavor factors


async def test_cold_start_is_pure_vector(repo):
    ids = await _build_world(repo)

    result = await recommend(repo, user_id=4, n=3)              # 2 logs -> cold

    assert result.cold_start is True
    rec_ids = [r.dish.id for r in result.recommendations]
    assert ids[0] not in rec_ids and ids[1] not in rec_ids      # logged dropped
    assert rec_ids[0] == ids[2]                                 # nearest unlogged to the centroid


async def test_brand_new_user_falls_back_to_popularity(repo):
    await _build_world(repo)

    result = await recommend(repo, user_id=999, n=5)           # never logged

    assert result.cold_start is True
    assert len(result.recommendations) > 0                      # popularity, not empty


# --------------------------------------------------------------------------- endpoints

def test_recommendations_endpoint(repo, make_client):
    asyncio.run(_build_world(repo))
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    resp = client.get("/recommendations?n=5")   # user_id comes from the auth token (== 1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cold_start"] is False
    assert len(body["recommendations"]) > 0
    first = body["recommendations"][0]
    assert {"dish", "score", "explanation", "components"} <= set(first)


def test_taste_profile_endpoint_and_404(repo, make_client):
    asyncio.run(_build_world(repo))
    client = make_client(repo, StubEmbedder(), StubNormalizer(), user=1)

    ok = client.get("/users/me/taste-profile")   # "me" == authenticated user 1
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["n_dishes"] > 0
    assert body["has_liked_centroid"] is True
    assert body["has_disliked_centroid"] is True               # user 1 disliked D9
    assert body["flavor_factor_pref"] is not None

    # A user with no profile yet -> 404 (authenticated as a never-logged user).
    stranger = make_client(repo, StubEmbedder(), StubNormalizer(), user=424242)
    assert stranger.get("/users/me/taste-profile").status_code == 404
