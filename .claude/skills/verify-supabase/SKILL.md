---
name: verify-supabase
description: Verify the Dish Passport Supabase migration end-to-end — DB schema, the signup→profile trigger, ES256/JWKS auth on the worker, and an authenticated data round-trip. Use after changing the Supabase schema, auth, or the worker, or to confirm the stack is healthy against a live Supabase project. Reads creds from .supabase.env.
---

# Verify the Dish Passport Supabase stack

Drives the whole migrated stack against a **live Supabase project** and proves each hop:
Supabase Auth (ES256) → worker JWKS verification → UUID user → DB (profiles trigger,
schema, RLS) → the authenticated data path. All from the CLI.

## Prerequisites
- `.supabase.env` at the repo root (gitignored) with:
  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`
  (use the session-mode pooler URL — the direct `db.<ref>.supabase.co` host is IPv6-only),
  and optionally `SUPABASE_JWKS_URL` (else derived from `SUPABASE_URL`).
- `backend/.env` with `DP_OPENAI_API_KEY` (for the optional mint check).
- `psql`, and the backend venv at `backend/.venv` (`uv venv` + `requirements.txt`).

## What it does
1. **Connectivity** — `select 1` over the pooler.
2. **Schema** — applies `supabase/migrations/*.sql` only if `public.profiles` is missing
   (idempotent: skips when the schema is already there); verifies 9 tables + pgvector + the
   `on_auth_user_created` trigger + RLS.
3. **Worker** — boots `uvicorn` on :8010 against Supabase if not already up; waits for `/health`.
4. **Auth round-trip** — admin-creates a confirmed test user (bypasses email confirmation),
   signs in for an ES256 token, then asserts:
   - protected endpoint → **401** with no token and with a garbage token,
   - `/recommendations` → **200** with the valid token (worker verified it via JWKS),
   - the `profiles` row was created by the trigger.
5. **(Optional) mint** — with `--mint`, logs a dish through the OpenAI path and checks it
   persists under the UUID user.

## Run it
```bash
bash .claude/skills/verify-supabase/run.sh          # auth + schema round-trip
bash .claude/skills/verify-supabase/run.sh --mint   # also exercise the OpenAI mint path
```

## Pass criteria
All hops green: connectivity, schema present, worker healthy, 401s on bad auth, 200 on
`/recommendations` with a real token, and the trigger-created profile. Prints `PASS`/`FAIL`.

## Notes
- New-user *registration from the app* additionally needs email confirmations disabled in the
  Supabase dashboard (Auth → Providers → Email). This skill sidesteps that via the Admin API.
- The test user is `verify-<n>@dishport.app`; it's left in place (Supabase auth.users) for reuse.
