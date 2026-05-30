# Dish Passport — Architecture

> System vision + the concrete **Service 1 (Ingestion)** design built tonight.
> Anything marked **DECISION** or **ASSUMPTION** is fair game to revisit at review.

## 1. The rocks (non-negotiable invariants)

1. **Dish is a shared thing.** Many users, one canonical dish. Logs point at the catalog;
   we never mint a dish that already exists (the dedup gate). No sharing → the user×dish
   matrix never overlaps → CF dies.
2. **Two vectors, kept apart.** Big vector (1536d, opaque) *finds*. Flavor vector
   (10d → 4 latent via SVD, readable) *explains*. Never retrieve on flavor, never explain
   with the big vector. Different columns, different code paths.
3. **Online vs batch is a hard line.** Online = log, dedup, flavor score, embed, find similar,
   ensemble math. Batch = ALS fit, SVD fit, taste profiles. ALS never runs in a request.
4. **pgvector is truth. Pinecone sleeps.** All "vector neighbor" = pgvector cosine. No dual write.
5. **Negatives are real, but Rocchio first, no classifier yet.** (Later services.)
6. **Version everything.** `embedding_model_version`, `svd_model_version`, cf `model_version`.

## 2. Roadmap vs. this build

| # | Service | Status |
|---|---------|--------|
| **1** | **Ingestion** — dedup gate, log, impressions ingest | **✅ built tonight** |
| 2 | Similarity — `/dishes/{id}/similar`, pure big-vector | pending |
| 3 | Flavor + SVD — refine, fit, project, explain | pending |
| 4 | CF — ALS batch (confidence-weighted) | pending |
| 5 | Recommend — ensemble, ramp, filter disliked | pending |

The rest of this document describes Service 1 in detail; later sections sketch the system
the remaining services slot into.

## 3. Service 1 — Ingestion

### 3.1 The gate (`app/services/ingestion.py`)

```
log_dish(user_id, text|dish_id, sentiment, rating, notes, tau):
  1. dish_id present → repo.get_dish; 404 if missing; write log.    decision=fastlane  (no LLM, no embed)
  2. else:
       normalized = normalizer.normalize(text)        # ONE combined LLM call
       embedding  = embedder.embed(normalized.description)   # dedup key = the description
       neighbor   = repo.nearest(embedding)           # pgvector cosine via `<=>`
       if neighbor and neighbor.cosine >= tau:
           dish = neighbor.dish; reuse its flavor.     decision=link
       else:
           dish = repo.insert_dish(normalized, embedding, model_version).   decision=mint
  3. write log(sentiment); users.log_count += 1
  every decision logs: "dedup decision=<mint|link|fastlane> dish_id=… cosine=… tau=…"
```

- **Dedup key is the normalized, cuisine-blind description**, not the raw text. So "chicken
  tikka" and "murgh tikka" collapse, while genuinely different dishes stay apart.
- **`dish_id` fast lane is zero-LLM, zero-embed** — pairs with the optimistic mobile client,
  which already has a canonical id and just wants to record a log instantly.
- **`TAU` (0.90) sits above kindred cross-cuisine similarity** (al pastor ~ shawarma ≈ 0.85).
  Too low and distinct dishes collapse into one catalog row. Asserted by the test suite.
- **On `link` we reuse the existing dish's flavor** — the catalog entry is canonical; the new
  log doesn't get to rescore it. (User refinement is a later, explicit signal — Service 3.)

### 3.2 Ports / adapters (hexagonal)

```
app/ports.py         Embedder · DishNormalizer · DishRepository  (Protocols)
                     + NormalizedDish · DishRecord · Neighbor · ImpressionRow (dataclasses)
app/services/ingestion.py    the gate — depends ONLY on ports
app/adapters/
  repo_pgvector.py   asyncpg pool; nearest via `ORDER BY embedding <=> $1`, cosine = 1 - dist
  repo_memory.py     dict-backed; pure-python cosine; seed helpers (tests + local)
  embeddings_openai.py   text-embedding-3-small → 1536d   (SDK imported lazily)
  llm_anthropic.py   one tool-use call → name + cuisine-blind description + 10-dim flavor (lazy)
app/main.py          FastAPI; lifespan wires real adapters via app.dependency_overrides
```

The gate never imports a vendor SDK or a DB driver. Swapping Postgres for anything, or
OpenAI/Anthropic for anything, is an adapter change — the gate and its tests don't move.

### 3.3 Data (this service: `migrations/001_init.sql`)

```sql
users(id, created_at, log_count)                      -- log_count bumped on every log
dishes(id, name, canonical_description, ingredients text[], prep_method,
       embedding vector(1536), embedding_model_version, flavor vector(10), created_at)
logs(id, user_id, dish_id, logged_at,
     sentiment 'liked'|'neutral'|'disliked', rating int null, notes, flavor_override vector(10) null)
impressions(id, user_id, dish_id, shown_at, context 'feed'|'recs'|'similar', converted bool)
```

- HNSW index on `dishes.embedding` (`vector_cosine_ops`) — the dedup nearest-neighbor probe.
- `dish_flavor_factors`, `user_taste_profiles`, `cf_*_factors`, `flavor_svd_model` arrive in
  later migrations with their owning services.

### 3.4 Endpoints

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/logs` | `{user_id, text\|dish_id, sentiment?, rating?, notes?}` | `{dish, is_new, log_id}` |
| POST | `/impressions` | `[{user_id, dish_id, shown_at, context, converted}]` | `{ingested}` |
| GET | `/dishes/{id}` | — | dish detail |

`/impressions` is **write-only** here; soft negatives are derived later in
`rebuild_taste_profiles` (Service 5). This is the frontend↔backend seam — see §6.

## 4. Decisions made autonomously (review these)

- **DECISION — asyncpg + raw SQL, not an ORM.** The gate needs exactly two vector queries
  (`nearest`, `insert_dish`); raw SQL + `pgvector.asyncpg.register_vector` is the least
  machinery and keeps the `<=>` cosine explicit. (This supersedes the earlier
  SQLAlchemy/psycopg2 note from the pre-pivot scaffolding.)
- **DECISION — one combined LLM call** does normalize + cuisine-blind description + 10-dim
  flavor, via Anthropic tool-use (forced structured output). Cheaper and atomic vs. 2–3 calls.
- **DECISION — dedup on the description embedding**, with a zero-LLM `dish_id` fast lane.
- **DECISION — providers are real (OpenAI / Anthropic); test doubles live only in `tests/`.**
  No offline provider in `app/` this round — running the gate needs the two keys; `pytest`
  needs neither (in-memory fakes + deterministic controlled vectors).
- **DECISION — `repo_memory` is a first-class adapter**, not just a mock: it backs every test
  and gives a keys-optional local path for the non-LLM bits.
- **ASSUMPTION — auth is stubbed.** `user_id` in the request body stands in for the
  authenticated subject; `repo.insert_log` upserts the user row. Real token auth is a thin
  later layer (frontend already plans SecureStore). Not security-reviewed.
- **ASSUMPTION — repo is private**, name `dish-passport`, account `vizdiz`.

## 5. The system the later services slot into (sketch)

- **Recommend (5)** is retrieve-then-rank: cold start (`log_count < 5`) is pure big-vector;
  `≥5` unions pgvector + ALS + popularity candidates, drops logged+disliked, scores
  `w_cf·cf + w_cb·cb + w_vec·vec` with a weight ramp on `log_count`. Explanations come from
  flavor factors, never the big vector.
- **Negatives (4/5):** hard ("not for me"/low rating) → Rocchio disliked centroid + ALS pref 0
  high-confidence + filtered from output; soft (shown-not-logged impression) → decaying
  soft-neg; sample (random unlogged) → ALS train balance. ALS confidence `c = 1 + alpha·signal`.

## 6. Shared seam — impression contract (frozen)

```
POST /impressions
[ { user_id, dish_id, shown_at (ISO 8601), context: "feed"|"recs"|"similar", converted: bool } ]
```

Frontend emits on viewability (≥50% visible, ≥1s), batched + debounced on scroll-settle.
Backend stores raw (this service). Only `rebuild_taste_profiles` (Service 5) consumes it,
turning non-converted impressions into decaying soft negatives.

## 7. Open questions for the morning

1. Wire real OpenAI embeddings + Claude flavor now (needed for the cross-cuisine similarity
   *quality* proof), or stay on fakes until after we review Service 1's shape?
2. Auth: is the stubbed `user_id` fine through the next couple of services?
3. `DP_DEDUP_TAU` = 0.90 — comfortable, or want to see the cosine distribution on real
   embeddings before locking it?
4. Should `link` ever *blend* flavors (running average) instead of strictly reusing the
   canonical one? (Current: strict reuse.)
