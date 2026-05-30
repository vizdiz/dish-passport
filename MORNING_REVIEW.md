# Morning review — Dish Passport, Service 1 (Ingestion)

Built overnight, autonomously. **Scope: Service 1 only** (the dedup gate), per "Go! Service 1".
Stopped here on purpose — Services 2–5 and the frontend involve per-service decisions
(τ calibration, factor labeling, ALS hyperparameters, `n` defaults) that the spec says to
shape with you rather than guess. A concrete Service 2 plan is at the bottom.

**Remote:** https://github.com/vizdiz/dish-passport (private) · branch `main`, 2 commits.

---

## TL;DR — what's done

- ✅ Dedup gate: `dish_id` fast lane (zero LLM/embed) | normalize → embed description →
  nearest → **link** (cos ≥ τ, reuse flavor) or **mint** (cos < τ, scored flavor).
- ✅ Ports/adapters: gate depends only on `ports.py`; adapters for pgvector (asyncpg, `<=>`),
  in-memory, OpenAI embeddings, Anthropic one-call normalizer (SDKs imported lazily).
- ✅ Endpoints: `POST /logs`, `POST /impressions`, `GET /dishes/{id}` (+ `/health`).
- ✅ `migrations/001_init.sql`: users/dishes/logs/impressions + HNSW cosine index.
- ✅ **17 unit tests green** on in-memory fakes (no DB, no keys).
- ✅ **Verified end-to-end on a real Postgres+pgvector** (Docker): `<=>` cosine, log_count
  bump, impressions, and lifespan wiring over HTTP.

---

## Run it yourself

> ⚠️ **Environment note:** the Homebrew `python@3.12` on this machine has a broken `pyexpat`
> (`Symbol not found: _XML_SetAllocTrackerActivationThreshold`), which breaks `pip`/`ensurepip`
> inside venvs. I worked around it with a **uv-managed CPython 3.12** (clean, isolated). If you
> use plain `python3 -m venv`, you'll hit the same wall — use uv, or `brew reinstall python@3.12`.

### Tests (no DB, no keys)
```bash
cd backend
uv venv .venv --python 3.12 --python-preference only-managed   # or your own working 3.12
uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q                                   # 17 passed
```

### The app + real DB
```bash
# 5432 was taken on this machine (an unrelated timescaledb container), so I used 5433:
DP_DB_PORT=5433 docker compose up -d
export DP_DATABASE_URL=postgresql://dishport:dishport@localhost:5433/dishport
psql "$DP_DATABASE_URL" -f backend/migrations/001_init.sql

# integration smokes (deterministic vectors, no keys needed):
cd backend
DP_DATABASE_URL=$DP_DATABASE_URL PYTHONPATH=. .venv/bin/python scripts/smoke_pgvector.py
DP_DATABASE_URL=$DP_DATABASE_URL PYTHONPATH=. .venv/bin/python scripts/smoke_http.py

# real server (needs provider keys for the text/mint path; fast lane works without):
export DP_OPENAI_API_KEY=...  DP_ANTHROPIC_API_KEY=...
.venv/bin/uvicorn app.main:app --reload     # http://localhost:8000/docs
```

> **Heads up:** I left the Docker DB running on **port 5433** with smoke-test seed data
> (dishes 1 = Al Pastor, 2 = Miso Soup). Stop it with `docker compose down` (add `-v` to wipe
> `pgdata/`). The unrelated `correctness-bench-postgres-1` on 5432 was left untouched.

---

## Test results (captured)

```
17 passed in 0.02s
```

Dedup gate coverage (`tests/test_dedup_gate.py`):
- fast lane links with **zero** embedder/normalizer calls; unknown `dish_id` → `DishNotFound`
- empty catalog mints; paraphrase (cos 0.97) links; distinct (cos 0.20) mints
- **kindred cross-cuisine (al pastor ~ shawarma, cos 0.85) is NOT collapsed** — the headline guarantee
- τ boundary is inclusive (`>=`): cos == τ links, a hair below mints (uses the repo's own cosine to dodge float ambiguity)
- link reuses the **canonical** dish's flavor (discards the paraphrase's scored flavor)
- log_count bumps; sentiment/rating recorded; every decision (mint/link/fastlane) is logged with cosine + τ

Real pgvector smoke (`scripts/smoke_pgvector.py`, against Docker):
```
nearest(0.97·A) -> Al Pastor cosine=0.9700   (>= 0.90 τ => LINK)
nearest(0.85·A) -> Al Pastor cosine=0.8500   (<  0.90 τ => MINT — kindred stays distinct)
user 1 log_count = 2 ; impressions ingested = 2
```
HTTP smoke (`scripts/smoke_http.py`): `/health`, `GET /dishes/1`, fast-lane `POST /logs`,
`POST /impressions` all 200 with PgVectorRepository wired by the lifespan.

---

## Decisions made autonomously (please sanity-check)

1. **asyncpg + raw SQL**, not an ORM — two vector queries don't need one; keeps `<=>` explicit.
2. **One combined Anthropic call** (tool-use, forced structured output) returns
   `canonical_name + cuisine-blind description + ingredients + prep_method + flavor[10]`.
3. **Providers are real (OpenAI/Anthropic); test doubles live only in `tests/`.** No offline
   provider shim in `app/`. Running the mint path needs both keys; `pytest` needs neither.
4. **Lazy "unconfigured" providers** so the fast lane / reads work with only a DB wired (the
   "no LLM, no embed" promise holds at the DI layer too). Mint/link fails loudly if a key's missing.
5. **`repo_memory` is a first-class adapter**, not just a mock — it backs every test.
6. **Auth is stubbed:** `user_id` in the body stands in for the authenticated subject;
   `insert_log` upserts the user row. Not security-reviewed.
7. **Built a slightly larger suite than the spec's "13"** (17) — extra coverage on the τ
   boundary, flavor reuse, per-decision logging, and the no-provider fast lane.

## Assumptions worth a glance

- Repo name `dish-passport`, **private**, under `vizdiz`.
- Set a local `git config user.name "Vismay Ravikumar"` (global name was empty; email was set).
- Commits carry **no `Co-Authored-By` trailer** (per your instruction; saved to memory).

---

## QA checklist for our session

- [ ] Read `ARCHITECTURE.md` §3–4 — agree on the gate shape + the asyncpg/one-call decisions.
- [ ] Skim `app/services/ingestion.py` (the whole gate is ~90 lines) and `tests/test_dedup_gate.py`.
- [ ] Decide: wire **real** OpenAI + Claude and re-run the smokes to see actual cosines
      (the offline smokes use synthetic vectors; the cross-cuisine *quality* proof needs real embeddings).
- [ ] Confirm `DEDUP_TAU = 0.90` after we eyeball a real cosine distribution (that's what
      Service 2 is for — see plan below).
- [ ] Confirm the stubbed `user_id` auth is fine for the next couple of services.

## Open questions (also in ARCHITECTURE.md §7)

1. Wire real providers now, or stay on fakes until after this review?
2. Is the stubbed `user_id` acceptable through Services 2–3?
3. `DEDUP_TAU` = 0.90 — lock it, or calibrate from real data via Service 2 first?
4. On `link`, strictly reuse the canonical flavor (current) or blend (running average)?

---

## Recommended next: Service 2 — Similarity (ready to start)

Smallest, highest-signal next step; the spec says build it second to *see* the embedding
thesis hold and to **calibrate `DEDUP_TAU` empirically**.

- **Endpoint:** `GET /dishes/{id}/similar?n=` — pure pgvector cosine neighbors, **self excluded**,
  no CF, no flavor.
- **Repo:** add `DishRepository.similar(dish_id, n) -> list[Neighbor]`
  (`ORDER BY embedding <=> (SELECT embedding FROM dishes WHERE id=$1) WHERE id != $1 LIMIT n`);
  in-memory mirror for tests.
- **Tests:** self-exclusion; ordering by descending cosine; `n` cap; 404 on missing dish;
  a fixture that asserts a known kindred pair surfaces (ceviche ≈ larb) once real embeddings exist.
- **Calibration deliverable:** a small script that prints the cosine between seeded kindred
  pairs (al pastor/shawarma, ceviche/larb) so we can pick τ from data, not vibes.

Say the word (or hand me the Service 2 spec) and I'll build it the same way: propose the tiny
data/endpoint delta, then implement + test.
