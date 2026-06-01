"""Photo upload: presign endpoint (on a stub storage) + photo_url persisted on a log."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import deps
from app.main import app
from app.ports import PresignedUpload
from tests.fakes import StubEmbedder, StubNormalizer, axis0, flat_flavor


class StubStorage:
    def presign_put(self, key: str, content_type: str, expires: int = 3600) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://put.local/{key}?ct={content_type}",
            headers={"x-ms-blob-type": "BlockBlob", "Content-Type": content_type},
        )

    def public_url(self, key: str) -> str:
        return f"https://cdn.local/{key}"


def _with_stub_storage() -> TestClient:
    app.dependency_overrides[deps.get_storage] = lambda: StubStorage()
    app.dependency_overrides[deps.get_current_user] = lambda: 1
    return TestClient(app)


def test_presign_returns_key_and_urls():
    client = _with_stub_storage()
    try:
        resp = client.post("/uploads/presign", json={"content_type": "image/jpeg"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["key"].startswith("photos/") and body["key"].endswith(".jpg")
        assert body["key"] in body["public_url"]
        assert body["upload_url"].startswith("https://put.local/")
        assert body["headers"]["x-ms-blob-type"] == "BlockBlob"   # provider-specific header in response
    finally:
        app.dependency_overrides.clear()


def test_presign_rejects_unsupported_content_type():
    client = _with_stub_storage()
    try:
        resp = client.post("/uploads/presign", json={"content_type": "application/pdf"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_photo_url_persisted_on_log(repo, make_client):
    dish = repo.seed_dish(name="X", description="x", flavor=flat_flavor(), embedding=axis0())
    client = make_client(repo, StubEmbedder(), StubNormalizer())
    url = "https://cdn.local/photos/abc.jpg"

    resp = client.post("/logs", json={"user_id": 1, "dish_id": dish.id, "photo_url": url})

    assert resp.status_code == 200, resp.text
    assert repo.logs[-1]["photo_url"] == url
