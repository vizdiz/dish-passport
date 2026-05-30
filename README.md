# Dish Passport

Log a dish. Get a dish recommendation. **Dishes only — no restaurants.**

A dish is a *shared, canonical* thing: many users, one dish. Every log points at a
canonical catalog entry, so the user×dish matrix overlaps and collaborative filtering
(later service) has something to chew on.

> **Build status:** **Backend complete — Services 1–5** (this repo): Ingestion, Similarity,
> Flavor+SVD, CF/ALS, Recommendation. Full API below, three batch jobs (`recompute_svd`,
> `retrain_als`, `rebuild_taste_profiles`), 45 tests green + every adapter verified on real
> Postgres+pgvector. Remaining: Celery Beat wiring and the React Native client.
> See [ARCHITECTURE.md](./ARCHITECTURE.md).

## Service 1 — Ingestion (the dedup gate)

Free text **or** `dish_id` → cuisine-blind canonical dish → embed → link-or-mint → log.

```
dish_id present ──────────────► validate + log it           (no LLM, no embed)
free text ─► normalize (1 LLM call: name + cuisine-blind description + 10-dim flavor)
          ─► embed(description)  (text-embedding-3-small, 1536d)
          ─► nearest dish in pgvector (cosine via `<=>`)
          ─► cosine ≥ DP_DEDUP_TAU (0.90)?  LINK existing (reuse flavor)
                                     else    MINT new (with scored flavor)
          ─► write log(sentiment); decision is logged for human audit
```

`DP_DEDUP_TAU` sits **above** kindred cross-cuisine similarity (al pastor ~ shawarma ≈ 0.85),
so distinct dishes don't collapse. The test suite asserts this directly.

### Architecture (ports / adapters)

- `app/ports.py` — `Embedder`, `DishNormalizer`, `DishRepository` protocols (+ dataclasses).
- `app/services/ingestion.py` — the gate. DB- and vendor-agnostic; depends only on ports.
- `app/adapters/` — `repo_pgvector` (asyncpg + pgvector), `repo_memory` (in-memory),
  `embeddings_openai`, `llm_anthropic`. Heavy SDKs are imported **lazily**.
- `app/main.py` — FastAPI; real adapters are wired in at startup via `app.dependency_overrides`.

## Run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose -f ../docker-compose.yml up -d            # Postgres + pgvector
export DP_DATABASE_URL=postgresql://dishport:dishport@localhost:5432/dishport
psql "$DP_DATABASE_URL" -f migrations/001_init.sql
psql "$DP_DATABASE_URL" -f migrations/002_flavor_svd.sql
export DP_OPENAI_API_KEY=...  DP_ANTHROPIC_API_KEY=...
uvicorn app.main:app --reload                            # http://localhost:8000/docs

# batch jobs — scheduler-triggered in prod; manual entry points for now:
psql "$DP_DATABASE_URL" -f migrations/003_cf.sql
psql "$DP_DATABASE_URL" -f migrations/004_taste_profiles.sql
PYTHONPATH=. python scripts/run_recompute_svd.py         # fit flavor SVD + per-dish factors
PYTHONPATH=. python scripts/run_retrain_als.py           # confidence-weighted ALS factors
PYTHONPATH=. python scripts/run_rebuild_taste_profiles.py  # centroids + factor prefs
```

## Test

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q          # dedup gate + endpoints, on in-memory fakes (no DB, no keys)
```

## Endpoints

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/logs` | `{user_id, text\|dish_id, sentiment?, rating?, notes?}` | `{dish, is_new, log_id}` |
| POST | `/impressions` | `[{user_id, dish_id, shown_at, context, converted}]` | `{ingested}` |
| GET | `/dishes/{id}` | — | dish detail + 4-factor projection (lets the optimistic client reconcile the canonical id) |
| GET | `/dishes/{id}/similar?n=` | — | pure big-vector cosine neighbors, self excluded (Service 2) |
| PATCH | `/logs/{id}/flavor` | `{flavor: {dim: 0..1}}` | user refines the 10 flavor dims (Service 3) |
| GET | `/recommendations?user_id=&n=` | — | the ensemble + per-item flavor-factor explanation (Service 5) |
| GET | `/users/{id}/taste-profile` | — | factor prefs + representative dishes (Service 5) |

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the system design and decisions, and
[MORNING_REVIEW.md](./MORNING_REVIEW.md) for the overnight build log + QA checklist.
