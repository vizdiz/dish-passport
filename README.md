# Dish Passport

**A food app that learns your palate.** Log what you ate in plain words — Dish Passport
recognizes the *canonical* dish, learns your taste over time, and recommends new dishes, each
with a plain-English reason why. Dishes only, not restaurants.

📱 React Native (Expo) · ⚙️ FastAPI · 🐘 Postgres + pgvector · ☁️ Azure · 🤖 OpenAI

## What makes it tick

- **Shared, canonical dishes.** Your "chicken tikka" and someone else's "murgh tikka" resolve
  to one catalog entry — so the app learns across everyone, not just you.
- **Find with one lens, explain with another.** An opaque embedding finds *similar* dishes; a
  separate, readable flavor fingerprint (umami…fresh) explains *why* something is recommended.
- **Learns what you dislike, too.** A like / meh / not-for-me tap on each card is real signal;
  recommendations adapt and justify themselves ("high depth + intensity — matches your taste").

> **Status — full stack.** FastAPI backend (5 services + a Celery batch scheduler + Azure Blob
> photo uploads; 51 tests) and a React Native client (Feed / Log / Taste; 10 tests). Every
> backend adapter is verified against real Postgres+pgvector, Redis, and Azurite; the whole app
> bundles via Metro.

---

## How it works — the dedup gate

Free text **or** a known `dish_id` → cuisine-blind canonical dish → embed → link-or-mint → log.

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
  `embeddings_openai`, `llm_openai` (OpenAI powers both embeddings and the combined
  normalize+flavor call), `storage` (Azure Blob). Heavy SDKs are imported **lazily**.
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
export DP_OPENAI_API_KEY=...                             # powers embeddings + flavor scoring
uvicorn app.main:app --reload                            # http://localhost:8000/docs

psql "$DP_DATABASE_URL" -f migrations/003_cf.sql
psql "$DP_DATABASE_URL" -f migrations/004_taste_profiles.sql

# batch scheduler — Celery Beat + Redis (Redis is in docker compose):
celery -A app.celery_app.celery worker -l info           # runs the three batch tasks
celery -A app.celery_app.celery beat   -l info           # triggers them on schedule
#   taste profiles hourly · ALS nightly 03:00 · SVD weekly Sun 04:00 (tunable in celery_app.py)

# ...or trigger a batch job once, by hand:
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

## Frontend (React Native / Expo)

```bash
cd frontend
npm install
npx expo start            # open in Expo Go or a simulator
npm run typecheck         # tsc --noEmit
npm test                  # jest-expo + React Native Testing Library
```

Three tabs — **Feed** (recommendations with reasons + impression tracking), **Log** (free-text
or pick a dish, sentiment, optional photo), **Taste** (your flavor-factor profile). Design tokens
live in `src/theme/tokens.ts`; server state via TanStack Query, local state via Zustand. Photos
upload straight to Azure Blob via a presigned URL — the canonical `dish_id` reconciles when the
server's dedup response lands (optimistic logging).
