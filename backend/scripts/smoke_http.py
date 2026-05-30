"""Real-stack HTTP smoke: drives the FastAPI app (with its lifespan) against a live
Postgres+pgvector, no API keys. Verifies lifespan wiring of PgVectorRepository and the
fast-lane / read endpoints. Run scripts/smoke_pgvector.py first to seed dish id 1.

    DP_DATABASE_URL=postgresql://... PYTHONPATH=. python scripts/smoke_http.py
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as c:  # `with` runs the lifespan -> wires PgVectorRepository
    assert c.get("/health").json() == {"status": "ok"}

    d = c.get("/dishes/1")
    print(f"GET /dishes/1 -> {d.status_code} {d.json().get('name')!r}")
    assert d.status_code == 200

    r = c.post("/logs", json={"user_id": 9, "dish_id": 1})
    print(f"POST /logs (fast lane) -> {r.status_code} is_new={r.json()['is_new']} "
          f"dish={r.json()['dish']['name']!r}")
    assert r.status_code == 200 and r.json()["is_new"] is False

    imp = c.post("/impressions", json=[{
        "user_id": 9, "dish_id": 1, "shown_at": "2026-05-30T08:00:00Z",
        "context": "feed", "converted": True,
    }])
    print(f"POST /impressions -> {imp.status_code} {imp.json()}")
    assert imp.json() == {"ingested": 1}

print("\nHTTP SMOKE OK — lifespan-wired pgvector verified over HTTP.")
