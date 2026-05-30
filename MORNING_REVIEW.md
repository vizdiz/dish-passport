# Morning review — Dish Passport backend (Services 1–5 complete)

Built overnight, autonomously, down the spec's build order. **The entire backend is done:**
the dedup gate, similarity, flavor+SVD, CF/ALS, and the recommendation ensemble — full API,
three batch jobs, **45 unit tests green**, and **every adapter verified end-to-end on real
Postgres+pgvector**.

**Remote:** https://github.com/vizdiz/dish-passport (private) · `main` · 7 commits, one per service.

---

## What's built, service by service

| # | Service | Endpoints / jobs | Verified |
|---|---------|------------------|----------|
| 1 | **Ingestion** | `POST /logs`, `POST /impressions`, `GET /dishes/{id}` | dedup gate: paraphrase links, kindred al-pastor/shawarma (0.85) stays apart at τ=0.90, fast lane zero-LLM |
| 2 | **Similarity** | `GET /dishes/{id}/similar?n=` | pure big-vector neighbors, self excluded, cosine-ranked |
| 3 | **Flavor + SVD** | `PATCH /logs/{id}/flavor`, batch `recompute_svd`, factors on `GET /dishes/{id}` | data-derived labels (`sour+fresh ↔ rich+sweet`), online projection w/o refit |
| 4 | **CF / ALS** | batch `retrain_als` | confidence-weighted iALS; **disliked (−0.004) < unseen (+0.23)** on stored factors |
| 5 | **Recommendation** | `GET /recommendations`, `GET /users/{id}/taste-profile`, batch `rebuild_taste_profiles` | cold/warm ramp, drops logged+disliked, flavor-factor explanations |

Architecture is **ports/adapters**: every service depends only on `app/ports.py`; swapping
Postgres / OpenAI / Anthropic is an adapter change. `repo_memory` backs all tests; `repo_pgvector`
(asyncpg, cosine via `<=>`, jsonb codec) is the real one.

---

## Run it

> ⚠️ **The Homebrew `python@3.12` here is broken** (`pyexpat` symbol error → breaks pip/venv).
> I used a **uv-managed CPython 3.12**. Use uv, or `brew reinstall python@3.12`.

### Tests (no DB, no keys)
```bash
cd backend
uv venv .venv --python 3.12 --python-preference only-managed
uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q          # 45 passed
```

### Full stack + batch jobs + integration smokes
```bash
# 5432 was taken by an unrelated container, so I used 5433:
DP_DB_PORT=5433 docker compose up -d
export DP_DATABASE_URL=postgresql://dishport:dishport@localhost:5433/dishport
for m in 001_init 002_flavor_svd 003_cf 004_taste_profiles; do
  psql "$DP_DATABASE_URL" -f backend/migrations/$m.sql; done

cd backend
for s in smoke_pgvector smoke_svd smoke_cf smoke_recommend; do
  DP_DATABASE_URL=$DP_DATABASE_URL PYTHONPATH=. .venv/bin/python scripts/$s.py; done

# the API (fast lane / reads work with just a DB; mint path needs provider keys):
export DP_OPENAI_API_KEY=...  DP_ANTHROPIC_API_KEY=...
.venv/bin/uvicorn app.main:app --reload     # http://localhost:8000/docs
```

> I **left the Docker DB running on port 5433** with smoke seed data. `docker compose down`
> to stop (`-v` wipes `pgdata/`). The unrelated `correctness-bench-postgres-1` on 5432 is untouched.

---

## Evidence captured (real pgvector, no keys)

```
# Service 1/2 — dedup + similarity
nearest(0.97·A) -> Al Pastor 0.9700 [LINK]   nearest(0.85·A) -> 0.8500 [would MINT]
similar(A) -> [('Carnitas', 0.50), ('Miso Soup', 0.20)]   (self excluded, ranked)

# Service 3 — data-derived factor labels
factor 0: sour+fresh ↔ rich+sweet   factor 1: fermented+umami ↔ fresh+sweet  ...
stored factors == online re-projection ✓

# Service 4 — disliked is NOT unseen
score(user2 disliked d1) = -0.0040   score(user3 unseen d1) = +0.2297

# Service 5 — ensemble
recommend(user1) cold=False -> D5 'high rich+bitter', D6 'high herbaceous+smoky', ...
  (excludes logged D0-D4 and disliked D9)
recommend(user999) cold=True  -> D0..D4 (popularity)
```

---

## Decisions made autonomously (please sanity-check)

- **asyncpg + raw SQL** (no ORM); **one combined Anthropic tool-use call** (normalize + cuisine-blind
  description + 10-dim flavor); **dedup on the description** with a zero-LLM `dish_id` fast lane.
- **Providers are real (OpenAI/Anthropic); test doubles live only in `tests/`.** Lazy
  "unconfigured" providers so the fast lane / reads work with only a DB wired.
- **NumPy, not libraries**, for SVD (`linalg.svd`) and ALS (Hu/Koren/Volinsky closed form) —
  no fragile native deps, exact control over the confidence weighting.
- **Data-driven factor labels** (from loadings); **content-hash model versions**; deterministic
  SVD signs and seeded ALS init so versions/factors reproduce.
- **CF aggregation of repeat logs**: positive vs negative weight, ties go positive; `k` clamps to
  `min(#users, #items)`.
- **Recommend**: signals min-max normalized over the candidate set; β=0.4; soft-neg impression
  half-life 14d; explanations strictly from flavor factors.
- **Auth is stubbed** (`user_id` in the request = the subject; `insert_log` upserts the user).
- **One `DishRepository` port** grew to ~30 methods across services — pragmatic, but a candidate
  to split (DishRepo / FactorRepo / ProfileRepo) if you prefer.

---

## What's NOT done (next candidates)

1. **Celery Beat wiring.** The three batch jobs run today via `scripts/run_*.py`; they need a
   `celery_app` + beat schedule + Redis to be truly scheduler-triggered (spec §2). Redis is not
   in `docker-compose.yml` yet.
2. **Real provider keys.** The mint path and real embeddings need `DP_OPENAI_API_KEY` /
   `DP_ANTHROPIC_API_KEY`. Until then the cross-cuisine similarity *quality* proof (ceviche≈larb)
   can't be seen — only the gate mechanics are exercised (synthetic vectors).
3. **React Native client.** Nothing built yet — `tokens.ts` → primitives → DishCard /
   FlavorFingerprint / SentimentControl → Feed/Log/Taste. The impression seam is ready server-side.
4. **Auth**, photo→S3, and a `seed.py` of real dishes.

## QA checklist for our session

- [ ] Skim `app/services/{ingestion,recommend,cf,flavor_svd}.py` — the load-bearing logic.
- [ ] Run the 4 integration smokes (above) and eyeball the printed evidence.
- [ ] Decide whether to wire real keys + re-run `calibrate_tau.py` to lock `DEDUP_TAU` from data.
- [ ] Pick the next track: **Celery scheduler**, **frontend**, or **provider keys + real-data calibration**.
- [ ] Sanity-check the autonomous decisions above (esp. CF weighting, ramp priors, β, soft-neg half-life).

## Open questions

1. Wire real OpenAI + Claude now? (needed for the cross-cuisine similarity quality proof)
2. `DEDUP_TAU` = 0.90, β = 0.4, ALS α = 40 / k = 16, soft-neg half-life 14d — lock these or tune on real data?
3. Split the `DishRepository` god-port, or leave it?
4. Frontend next, or Celery/scheduler first?
