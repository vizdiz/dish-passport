# Dish Passport

**A food app that learns your palate.** Log what you ate in plain words - Dish Passport
recognizes the *canonical* dish, learns your taste over time, and recommends new dishes, each
with a plain-English reason why. Dishes only, not restaurants.

📱 React Native (Expo) · ⚙️ FastAPI · 🐘 Postgres + pgvector · ☁️ Azure · 🤖 OpenAI

## What makes it tick

- **Shared, canonical dishes.** Your "chicken tikka" and someone else's "murgh tikka" resolve
  to one catalog entry - so the app learns across everyone, not just you.
- **Find with one lens, explain with another.** An opaque embedding finds *similar* dishes; a
  separate, readable flavor fingerprint (umami…fresh) explains *why* something is recommended.
- **Learns what you dislike, too.** A like / meh / not-for-me tap on each card is real signal;
  recommendations adapt and justify themselves ("high depth + intensity - matches your taste").

> **Status - full stack.** FastAPI backend (5 services + JWT auth + a Celery batch scheduler +
> Azure Blob photo uploads; 53 tests) and a React Native client (Feed / Log / Taste; 10 tests). Every
> backend adapter is verified against real Postgres+pgvector, Redis, and Azurite; the whole app
> bundles via Metro.

---

## How it works - the dedup gate

Free text **or** a known `dish_id` → cuisine-blind canonical dish → embed → link-or-mint → log.

```
dish_id present ──────────────► validate + log it           (no LLM, no embed)
free text ─► normalize (1 LLM call: name + cuisine-blind description + 10-dim flavor)
          ─► embed(name + description + ingredients)  (text-embedding-3-small, 1536d)
          ─► nearest dish in pgvector (cosine via `<=>`)
          ─► cosine ≥ DP_DEDUP_TAU (0.80)?  LINK existing (reuse flavor)
                                     else    MINT new (with scored flavor)
          ─► write log(sentiment); decision is logged for human audit
```

`DP_DEDUP_TAU` (**0.80**) was calibrated on real `text-embedding-3-small` cosines over the
enriched embedding text (`scripts/calibrate_dedup.py`): true paraphrases of one dish land
0.80-0.99 (e.g. chicken tikka masala ~ murgh tikka masala ≈ 0.97), while distinct dishes stay
≤ ~0.73, so they don't collapse.

### Architecture (ports / adapters)

- `app/ports.py` - `Embedder`, `DishNormalizer`, `DishRepository` protocols (+ dataclasses).
- `app/services/ingestion.py` - the gate. DB- and vendor-agnostic; depends only on ports.
- `app/adapters/` - `repo_pgvector` (asyncpg + pgvector), `repo_memory` (in-memory),
  `embeddings_openai`, `llm_openai` (OpenAI powers both embeddings and the combined
  normalize+flavor call), `storage` (Azure Blob). Heavy SDKs are imported **lazily**.
- `app/main.py` - FastAPI; real adapters are wired in at startup via `app.dependency_overrides`.

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

# batch scheduler - Celery Beat + Redis (Redis is in docker compose):
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

`/auth/register` and `/auth/login` return a JWT; every other endpoint requires
`Authorization: Bearer <token>` and derives the user from it (no `user_id` in requests).

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/auth/register` · `/auth/login` | `{username, password}` | `{access_token, user_id}` |
| POST | `/logs` | `{text\|dish_id, sentiment?, rating?, notes?, photo_url?}` | `{dish, is_new, log_id}` |
| POST | `/impressions` | `[{dish_id, shown_at, context, converted}]` | `{ingested}` |
| GET | `/dishes/{id}` | - | dish detail + 4-factor projection |
| GET | `/dishes/{id}/similar?n=` | - | pure big-vector cosine neighbors, self excluded |
| PATCH | `/logs/{id}/flavor` | `{flavor: {dim: 0..1}}` | refine the 10 flavor dims (your own log) |
| GET | `/recommendations?n=` | - | the ensemble + per-item flavor-factor explanation |
| GET | `/users/me/taste-profile` | - | factor prefs + representative dishes |
| POST | `/uploads/presign` | `{content_type}` | `{upload_url, public_url, key, headers}` |

## Frontend (React Native / Expo)

```bash
cd frontend
npm install
npm run typecheck         # tsc --noEmit
npm test                  # jest-expo + React Native Testing Library
npx expo start            # dev server (uses a dev build — see below, not plain Expo Go)

# native builds via EAS (eas.json wires EXPO_PUBLIC_API_URL to the deployed API):
eas login && eas init                 # one-time: link an Expo project
eas build -p ios --profile preview    # simulator build  (or -p android for an APK)
eas build -p all --profile production # store builds
```

This app uses native modules (secure-store, image-picker, file-system), so it needs a
**development build** (`eas build --profile development` + `expo-dev-client`) or
`expo run:ios|android` — not plain Expo Go. Builds talk to the deployed API by default
(`EXPO_PUBLIC_API_URL` in `eas.json`); for local dev against your own backend, set
`EXPO_PUBLIC_API_URL` before `expo start`.

Three tabs - **Feed** (recommendations with reasons + impression tracking), **Log** (free-text
or pick a dish, sentiment, optional photo), **Taste** (your flavor-factor profile). Design tokens
live in `src/theme/tokens.ts`; server state via TanStack Query, local state via Zustand. Photos
upload straight to Azure Blob via a presigned URL - the canonical `dish_id` reconciles when the
server's dedup response lands (optimistic logging).
