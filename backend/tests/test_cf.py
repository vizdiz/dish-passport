"""Service 4 — CF/ALS: preference aggregation, ALS recovery, and the load-bearing
'disliked is not unseen' semantics."""
from __future__ import annotations

from app.services.cf import aggregate_preferences, retrain_als, train_als
from tests.fakes import axis0, flat_flavor

ALPHA = 40.0
C = 1.0 + ALPHA            # confidence for a strong (w=1) signal


def _score(X, Y, u, i):
    return float(X[u] @ Y[i])


# --------------------------------------------------------------------------- aggregation

def test_aggregate_preferences_mapping():
    logs = [
        (1, 10, "liked"), (1, 10, "liked"),   # repeated positive accumulates
        (1, 11, "neutral"),                    # weak positive
        (2, 10, "disliked"), (2, 10, "disliked"), (2, 10, "liked"),  # negative dominates
    ]
    prefs = aggregate_preferences(logs)
    assert prefs[(1, 10)] == (1.0, 2.0)
    assert prefs[(1, 11)] == (1.0, 0.1)
    assert prefs[(2, 10)] == (0.0, 2.0)        # disliked (p=0), high weight


# --------------------------------------------------------------------------- ALS recovery

def test_als_recovers_block_structure():
    # Users {0,1} like items {0,1}; users {2,3} like items {2,3}.
    user_obs = {
        0: [(0, C, 1.0), (1, C, 1.0)], 1: [(0, C, 1.0), (1, C, 1.0)],
        2: [(2, C, 1.0), (3, C, 1.0)], 3: [(2, C, 1.0), (3, C, 1.0)],
    }
    item_obs = {
        0: [(0, C, 1.0), (1, C, 1.0)], 1: [(0, C, 1.0), (1, C, 1.0)],
        2: [(2, C, 1.0), (3, C, 1.0)], 3: [(2, C, 1.0), (3, C, 1.0)],
    }
    X, Y = train_als(user_obs, item_obs, 4, 4, n_factors=2, reg=0.1, iters=30)

    assert _score(X, Y, 0, 0) > _score(X, Y, 0, 2)     # in-block beats cross-block
    assert _score(X, Y, 0, 1) > _score(X, Y, 0, 3)


def test_disliked_scores_below_unseen():
    """The whole reason disliked carries p=0 *with high confidence*: a dish someone disliked
    must score below the same dish merely unseen by a similar user."""
    # i0 and i1 co-occur (user 0 likes both). user 1 likes i0 but DISLIKES i1.
    # user 2 likes i0 and has never seen i1 (unseen).
    user_obs = {
        0: [(0, C, 1.0), (1, C, 1.0)],
        1: [(0, C, 1.0), (1, C, 0.0)],     # disliked i1: p=0, high confidence
        2: [(0, C, 1.0)],                  # i1 unseen
    }
    item_obs = {
        0: [(0, C, 1.0), (1, C, 1.0), (2, C, 1.0)],
        1: [(0, C, 1.0), (1, C, 0.0)],
    }
    X, Y = train_als(user_obs, item_obs, 3, 2, n_factors=2, reg=0.05, iters=60)

    disliked = _score(X, Y, 1, 1)
    unseen = _score(X, Y, 2, 1)
    assert disliked < unseen                  # known-zero pushed below the inherited positive
    assert _score(X, Y, 1, 0) > disliked      # the dish user 1 actually liked scores higher


# --------------------------------------------------------------------------- batch

async def test_retrain_als_persists_factors(repo):
    d0 = repo.seed_dish(name="D0", description="d0", flavor=flat_flavor(), embedding=axis0())
    d1 = repo.seed_dish(name="D1", description="d1", flavor=flat_flavor(), embedding=axis0())
    await repo.insert_log(user_id=1, dish_id=d0.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=1, dish_id=d1.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=2, dish_id=d0.id, sentiment="liked", rating=None, notes=None)
    await repo.insert_log(user_id=2, dish_id=d1.id, sentiment="disliked", rating=1, notes=None)
    await repo.insert_log(user_id=3, dish_id=d0.id, sentiment="liked", rating=None, notes=None)

    result = await retrain_als(repo, n_factors=8)

    assert result is not None and result.version.startswith("als-")
    assert result.n_users == 3 and result.n_items == 2 and result.n_factors == 2
    for user_id in (1, 2, 3):
        vec, version = await repo.get_cf_user_factors(user_id)
        assert len(vec) == 2 and version == result.version
    for dish_id in (d0.id, d1.id):
        vec, version = await repo.get_cf_item_factors(dish_id)
        assert len(vec) == 2 and version == result.version


async def test_retrain_als_no_logs_returns_none(repo):
    assert await retrain_als(repo) is None
