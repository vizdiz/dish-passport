# Deploying the Dish Passport worker to Fly.io

The worker is the FastAPI app in `app/` (ingestion + recommendations). It **verifies**
Supabase-issued JWTs and connects to **Supabase Postgres**; it does not mint tokens or manage
users. Identity lives in Supabase (`auth.users`); the worker only reads/writes rows keyed by the
user's UUID.

Config lives in `backend/fly.toml` (app `dishport-worker`, internal port `8000`, health check on
`GET /health`). Run all commands from `backend/`.

## Prerequisites
- `flyctl` installed and `fly auth login` done.
- A Supabase project: grab the **JWT secret** (Project Settings → API → JWT Secret) and a
  **service Postgres connection string** (Project Settings → Database → Connection string, using
  the service/`postgres` credentials — this bypasses RLS, which is what the worker needs).

## Required secrets
The app reads these env vars (see `app/config.py`):

| Env var              | What                                                                 |
|----------------------|---------------------------------------------------------------------|
| `SUPABASE_DB_URL`    | asyncpg DSN for Supabase Postgres. Use the **session-mode pooler** (IPv4): `postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres`. The direct `db.<ref>.supabase.co` host is IPv6-only. |
| `SUPABASE_URL`       | Project URL, e.g. `https://<ref>.supabase.co`. The worker derives the JWKS endpoint from it to verify **ES256** tokens (asymmetric — no shared secret). |
| `DP_OPENAI_API_KEY`  | OpenAI key — powers embeddings and the flavor/normalization call.    |

> Legacy fallback: set `SUPABASE_JWT_SECRET` instead of `SUPABASE_URL` only if your project
> still signs tokens with a shared HS256 secret. New projects use ES256/JWKS.

> Env naming: Supabase-shared vars use their **plain** names (`SUPABASE_*`); everything else
> keeps the historical **`DP_`** prefix (`DP_OPENAI_API_KEY`, `DP_LOG_LEVEL`,
> `DP_AZURE_STORAGE_CONNECTION_STRING`, …). Optional auth toggles: `DP_JWT_AUDIENCE`
> (default `authenticated`), `DP_JWT_VERIFY_AUDIENCE` (`false` to skip the `aud` check).

Photo uploads still use Azure Blob (`DP_AZURE_STORAGE_CONNECTION_STRING`,
`DP_AZURE_BLOB_PUBLIC_BASE`); set those too if the upload/presign path is in use.

## First deploy
```bash
cd backend

# 1. Create the app WITHOUT deploying yet (fly.toml already exists, so keep it).
fly launch --no-deploy --copy-config --name dishport-worker --region yul

# 2. Set secrets (staged; applied on next deploy).
fly secrets set \
  SUPABASE_DB_URL='postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres' \
  SUPABASE_URL='https://<ref>.supabase.co' \
  DP_OPENAI_API_KEY='<openai-key>'

# 3. Build + ship.
fly deploy
```

## Subsequent deploys
```bash
cd backend
fly deploy
```
Rotate a secret with `fly secrets set KEY=value` (triggers a rolling restart). Check health with
`fly status` and `curl https://dishport-worker.fly.dev/health`.

## Batch jobs (SVD / ALS / taste profiles)
`app/batch.py` runs one job synchronously and exits: `python app/batch.py {svd|als|taste}`.
It needs `SUPABASE_DB_URL` (and `DP_OPENAI_API_KEY` is not required by the batch bodies). Against
Supabase there are two straightforward options — not built here, documented for whoever wires it:

1. **Scheduled Fly Machine (recommended).** Create a separate scheduled machine from the same
   image that runs the batch entrypoint instead of uvicorn, e.g.:
   ```bash
   fly machine run . --schedule daily --entrypoint "python app/batch.py taste" \
     --app dishport-worker
   ```
   Fly supports `--schedule hourly|daily|weekly`. Use one machine per job with the cadence each
   needs (e.g. `als` weekly, `svd` daily, `taste` daily). Secrets are inherited from the app, so
   `SUPABASE_DB_URL` is already present. The machine starts on schedule, runs once, and stops.

2. **`pg_cron` inside Supabase.** Supabase ships `pg_cron`. If the batch math is re-expressed in
   SQL (or invoked via an Edge Function / `http` extension calling a worker endpoint), schedule it
   with `cron.schedule(...)` in the database. Heavier lift than option 1 since the current jobs are
   Python/numpy, so option 1 is the low-friction path.

The legacy Azure path (`infra/azure/deploy-jobs.sh`, Container Apps Jobs cron) is replaced by the
above; Celery/Redis is not needed when invoking the task bodies directly through `app/batch.py`.
