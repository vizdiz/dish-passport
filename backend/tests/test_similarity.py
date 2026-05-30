"""Service 2 — Similarity: pure big-vector neighbors, self excluded, ranked by cosine."""
from __future__ import annotations

import pytest

from app.services.errors import DishNotFound
from app.services.similarity import similar_dishes
from tests.fakes import StubEmbedder, StubNormalizer, axis0, flat_flavor, vec_cos_to_axis0


def _seed_field(repo):
    """Anchor A at axis0, plus neighbors at known cosines to A."""
    a = repo.seed_dish(name="A", description="a", flavor=flat_flavor(), embedding=axis0())
    b = repo.seed_dish(name="B", description="b", flavor=flat_flavor(), embedding=vec_cos_to_axis0(0.95))
    c = repo.seed_dish(name="C", description="c", flavor=flat_flavor(), embedding=vec_cos_to_axis0(0.80))
    d = repo.seed_dish(name="D", description="d", flavor=flat_flavor(), embedding=vec_cos_to_axis0(0.30))
    return a, b, c, d


# --------------------------------------------------------------------------- service

async def test_similar_excludes_self_and_ranks_by_cosine(repo):
    a, b, c, d = _seed_field(repo)
    result = await similar_dishes(repo, a.id, n=10)

    assert [nb.dish.name for nb in result] == ["B", "C", "D"]      # self A dropped, ranked desc
    assert result[0].cosine > result[1].cosine > result[2].cosine
    assert result[0].cosine == pytest.approx(0.95, abs=1e-6)


async def test_similar_respects_n(repo):
    a, *_ = _seed_field(repo)
    result = await similar_dishes(repo, a.id, n=2)
    assert [nb.dish.name for nb in result] == ["B", "C"]


async def test_similar_missing_dish_raises(repo):
    with pytest.raises(DishNotFound):
        await similar_dishes(repo, 999, n=5)


async def test_similar_alone_returns_empty(repo):
    a = repo.seed_dish(name="A", description="a", flavor=flat_flavor(), embedding=axis0())
    assert await similar_dishes(repo, a.id, n=5) == []


# --------------------------------------------------------------------------- endpoint

def test_get_similar_endpoint(repo, make_client):
    a, b, c, d = _seed_field(repo)
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    resp = client.get(f"/dishes/{a.id}/similar")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dish_id"] == a.id
    names = [nb["dish"]["name"] for nb in body["neighbors"]]
    assert names == ["B", "C", "D"]
    assert a.id not in [nb["dish"]["id"] for nb in body["neighbors"]]
    assert body["neighbors"][0]["cosine"] == pytest.approx(0.95, abs=1e-4)


def test_get_similar_n_param_and_validation(repo, make_client):
    a, *_ = _seed_field(repo)
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    assert len(client.get(f"/dishes/{a.id}/similar?n=1").json()["neighbors"]) == 1
    assert client.get(f"/dishes/{a.id}/similar?n=0").status_code == 422
    assert client.get(f"/dishes/{a.id}/similar?n=999").status_code == 422
    assert client.get("/dishes/4242/similar").status_code == 404
