"""Endpoint tests via FastAPI TestClient, wired to the in-memory repo + stub providers."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import deps
from app.config import Settings
from app.main import app
from tests.fakes import StubEmbedder, StubNormalizer, axis0, flat_flavor


def _seed(repo, name="Pho", description="aromatic beef noodle broth"):
    return repo.seed_dish(
        name=name, description=description, flavor=flat_flavor(),
        embedding=axis0(), ingredients=["beef", "rice noodles"], prep_method="simmered",
    )


def test_post_logs_text_mints(repo, make_client):
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    resp = client.post("/logs", json={"text": "green papaya salad"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_new"] is True
    assert isinstance(body["log_id"], int)
    assert len(body["dish"]["flavor"]) == 10
    assert set(body["dish"]["flavor"]) >= {"umami", "spicy", "fresh"}


def test_post_logs_requires_text_xor_dish_id(repo, make_client):
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    both = client.post("/logs", json={"text": "x", "dish_id": 1})
    neither = client.post("/logs", json={})

    assert both.status_code == 422
    assert neither.status_code == 422


def test_post_logs_dish_id_fastlane(repo, make_client):
    dish = _seed(repo)
    embedder, normalizer = StubEmbedder(), StubNormalizer()
    client = make_client(repo, embedder, normalizer)

    resp = client.post("/logs", json={"dish_id": dish.id})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_new"] is False
    assert body["dish"]["id"] == dish.id
    assert embedder.calls == 0 and normalizer.calls == 0   # fast lane touched no provider


def test_get_dish_detail_and_404(repo, make_client):
    dish = _seed(repo)
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    ok = client.get(f"/dishes/{dish.id}")
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "Pho"
    assert ok.json()["ingredients"] == ["beef", "rice noodles"]

    missing = client.get("/dishes/424242")
    assert missing.status_code == 404


def test_post_impressions_ingest(repo, make_client):
    client = make_client(repo, StubEmbedder(), StubNormalizer())

    payload = [
        {"dish_id": 10, "shown_at": "2026-05-30T08:00:00Z", "context": "feed", "converted": False},
        {"dish_id": 11, "shown_at": "2026-05-30T08:00:01Z", "context": "recs", "converted": True},
    ]
    resp = client.post("/impressions", json=payload)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ingested": 2}
    assert len(repo.impressions) == 2


def test_fastlane_works_with_only_repo_wired(repo):
    """Fast lane (and read endpoints) must work with no provider configured — proving the
    'no LLM, no embed' promise holds at the DI layer. The text path then fails clearly."""
    dish = _seed(repo)
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_current_user] = lambda: 1
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        dedup_tau=0.90, database_url=None, openai_api_key=None
    )
    # Deliberately do NOT override get_embedder / get_normalizer -> lazy unconfigured providers.
    try:
        client = TestClient(app, raise_server_exceptions=False)

        fastlane = client.post("/logs", json={"dish_id": dish.id})
        assert fastlane.status_code == 200, fastlane.text
        assert fastlane.json()["is_new"] is False

        assert client.get(f"/dishes/{dish.id}").status_code == 200

        text_path = client.post("/logs", json={"text": "needs an embedder"})
        assert text_path.status_code == 500   # raised only when it actually tries to embed
    finally:
        app.dependency_overrides.clear()
