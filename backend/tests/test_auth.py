"""Real auth: register/login mint JWTs, and protected endpoints require a valid token.
(These tests do NOT override get_current_user — they exercise the real token path.)"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import deps
from app.config import Settings
from app.main import app
from app.ports import FLAVOR_DIMS
from tests.fakes import StubEmbedder, StubNormalizer, axis0, flat_flavor


def _client(repo) -> TestClient:
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_embedder] = lambda: StubEmbedder()
    app.dependency_overrides[deps.get_normalizer] = lambda: StubNormalizer()
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        dedup_tau=0.90, database_url=None, openai_api_key=None, jwt_secret="test-secret"
    )
    return TestClient(app)


def test_register_login_and_protected_access(repo):
    client = _client(repo)
    try:
        reg = client.post("/auth/register", json={"username": "alice", "password": "hunter2pw"})
        assert reg.status_code == 201, reg.text
        token, user_id = reg.json()["access_token"], reg.json()["user_id"]
        assert token and isinstance(user_id, int)

        # protected endpoint without a token -> 401
        assert client.post("/logs", json={"text": "ramen"}).status_code == 401

        # with the token -> 200
        auth = {"Authorization": f"Bearer {token}"}
        logged = client.post("/logs", json={"text": "ramen"}, headers=auth)
        assert logged.status_code == 200, logged.text

        # login returns a working token for the same user
        login = client.post("/auth/login", json={"username": "alice", "password": "hunter2pw"})
        assert login.status_code == 200 and login.json()["user_id"] == user_id

        # wrong password -> 401 ; duplicate username -> 409 ; garbage token -> 401
        assert client.post("/auth/login",
                           json={"username": "alice", "password": "wrong"}).status_code == 401
        assert client.post("/auth/register",
                           json={"username": "alice", "password": "another1"}).status_code == 409
        assert client.get("/dishes/1",
                          headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_flavor_refine_rejects_other_users_log(repo, make_client):
    """Ownership: a user can't refine a log that isn't theirs."""
    from tests.fakes import axis0, flat_flavor

    dish = repo.seed_dish(name="X", description="x", flavor=flat_flavor(), embedding=axis0())
    owner = make_client(repo, StubEmbedder(), StubNormalizer(), user=1)
    log_id = owner.post("/logs", json={"dish_id": dish.id}).json()["log_id"]

    full = {dim: 0.5 for dim in __import__("app.ports", fromlist=["FLAVOR_DIMS"]).FLAVOR_DIMS}
    stranger = make_client(repo, StubEmbedder(), StubNormalizer(), user=2)
    assert stranger.patch(f"/logs/{log_id}/flavor", json={"flavor": full}).status_code == 404
