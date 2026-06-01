"""Service 3 — Flavor + SVD: fit/project/label, the batch job, PATCH override, and the
4-factor projection surfacing on dish detail."""
from __future__ import annotations

import asyncio

import pytest

from app.ports import FLAVOR_DIMS
from app.services.flavor_svd import fit_svd, project, recompute_svd
from tests.fakes import StubEmbedder, StubNormalizer, axis0


def _varied_flavors() -> list[list[float]]:
    """6 dishes whose variance lives almost entirely on the 'rich' dimension (index 5)."""
    rich_idx = FLAVOR_DIMS.index("rich")
    out = []
    for r in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        v = [0.5] * 10
        v[rich_idx] = r
        out.append(v)
    return out


def _seed_varied(repo) -> list[int]:
    return [
        repo.seed_dish(name=f"D{i}", description=str(i), flavor=f, embedding=axis0()).id
        for i, f in enumerate(_varied_flavors())
    ]


# --------------------------------------------------------------------------- fit / project

def test_fit_svd_shapes_and_labels():
    model = fit_svd(_varied_flavors())
    assert len(model.components) == 4 and all(len(c) == 10 for c in model.components)
    assert len(model.singular_values) == 4
    assert len(model.mean) == 10
    assert len(model.factor_labels) == 4


def test_first_factor_tracks_dominant_variance():
    model = fit_svd(_varied_flavors())
    comp0 = model.components[0]
    dominant = FLAVOR_DIMS[max(range(10), key=lambda i: abs(comp0[i]))]
    assert dominant == "rich"
    assert "rich" in model.factor_labels[0]


def test_projecting_the_mean_is_zero():
    model = fit_svd(_varied_flavors())
    assert all(abs(v) < 1e-9 for v in project(model.mean, model))


def test_fit_requires_enough_dishes():
    with pytest.raises(ValueError):
        fit_svd([[0.5] * 10, [0.4] * 10])      # only 2 < 4 factors


def test_version_is_deterministic():
    a = fit_svd(_varied_flavors())
    b = fit_svd(_varied_flavors())
    assert a.version == b.version


# --------------------------------------------------------------------------- batch

async def test_recompute_svd_persists_model_and_factors(repo):
    ids = _seed_varied(repo)
    model = await recompute_svd(repo)

    assert model is not None
    assert (await repo.get_latest_svd_model()).version == model.version
    for dish_id in ids:
        stored = await repo.get_dish_factors(dish_id)
        assert stored is not None
        factors, version = stored
        assert len(factors) == 4 and version == model.version


async def test_recompute_svd_skips_when_too_few(repo):
    repo.seed_dish(name="solo", description="x", flavor=[0.5] * 10, embedding=axis0())
    assert await recompute_svd(repo) is None
    assert await repo.get_latest_svd_model() is None


# --------------------------------------------------------------------------- PATCH override

def test_patch_log_flavor_override(repo, make_client):
    dish = repo.seed_dish(name="Tonkotsu", description="rich pork broth ramen",
                          flavor=[0.5] * 10, embedding=axis0())
    client = make_client(repo, StubEmbedder(), StubNormalizer())
    log_id = client.post("/logs", json={"dish_id": dish.id}).json()["log_id"]

    new_flavor = {dim: 0.3 for dim in FLAVOR_DIMS}
    new_flavor["umami"] = 0.95
    resp = client.patch(f"/logs/{log_id}/flavor", json={"flavor": new_flavor})

    assert resp.status_code == 200, resp.text
    assert resp.json()["flavor_override"]["umami"] == 0.95
    assert repo.logs[-1]["flavor_override"][FLAVOR_DIMS.index("umami")] == 0.95


def test_patch_log_flavor_validation(repo, make_client):
    dish = repo.seed_dish(name="x", description="x", flavor=[0.5] * 10, embedding=axis0())
    client = make_client(repo, StubEmbedder(), StubNormalizer())
    log_id = client.post("/logs", json={"dish_id": dish.id}).json()["log_id"]

    bad_keys = client.patch(f"/logs/{log_id}/flavor", json={"flavor": {"umami": 0.5}})
    assert bad_keys.status_code == 422

    out_of_range = {dim: 0.5 for dim in FLAVOR_DIMS}
    out_of_range["spicy"] = 1.5
    assert client.patch(f"/logs/{log_id}/flavor",
                        json={"flavor": out_of_range}).status_code == 422

    full = {dim: 0.5 for dim in FLAVOR_DIMS}
    assert client.patch("/logs/99999/flavor", json={"flavor": full}).status_code == 404


# --------------------------------------------------------------------------- dish detail

def test_get_dish_surfaces_factors_after_svd(repo, make_client):
    ids = _seed_varied(repo)
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    before = client.get(f"/dishes/{ids[0]}").json()
    assert before["factors"] is None and before["svd_model_version"] is None

    asyncio.run(recompute_svd(repo))

    after = client.get(f"/dishes/{ids[0]}").json()
    assert after["svd_model_version"] is not None
    assert len(after["factors"]) == 4
    assert all({"label", "value"} <= set(f) for f in after["factors"])
