# Dish Passport — Supabase

Fresh-start Supabase Postgres for Dish Passport. Supabase Auth owns identity
(`auth.users`, UUID ids); the schema here is UUID-native. No data is migrated from
the old Azure Postgres.

## Layout

```
supabase/
  config.toml                 # Supabase CLI project config (project_id = "dishport")
  migrations/
    0001_extensions.sql       # create extension vector (pgvector)
    0002_profiles.sql         # public.profiles + handle_new_user() trigger on auth.users
    0003_schema.sql           # dishes, logs, impressions, flavor/svd, cf, taste_profiles
    0004_rls.sql              # Row Level Security enable + policies
```

The migrations are ordered and idempotent-ish; run them **top to bottom** on a fresh
project. `0002` and `0004` reference `auth.users`, which exists on any Supabase project.

## Applying the schema

### Option A — Dashboard SQL editor

1. Open your project → **SQL Editor**.
2. Paste and run each file **in numeric order**: `0001` → `0002` → `0003` → `0004`.
   (Run them as separate statements/queries so an early failure is obvious.)

### Option B — Supabase CLI

```bash
# from the repo root
supabase link --project-ref <your-project-ref>   # one-time, links to the hosted project
supabase db push                                  # applies everything in supabase/migrations
```

For a fully local stack instead: `supabase start` then `supabase db reset` (applies all
migrations against the local containers).

## What the project exposes (env vars)

Set these where the backend worker / frontend read them (e.g. `.env`). The Python worker
uses the **service_role** key and therefore **bypasses RLS**.

| Env var                     | What it is                                  | Where in the dashboard                          |
|-----------------------------|---------------------------------------------|-------------------------------------------------|
| `SUPABASE_URL`              | Project REST/Auth base URL                  | Project Settings → **API** → Project URL        |
| `SUPABASE_ANON_KEY`         | Public client key (RLS enforced)            | Project Settings → **API** → Project API keys → `anon` `public` |
| `SUPABASE_SERVICE_ROLE_KEY` | Server key, **bypasses RLS** — worker only  | Project Settings → **API** → Project API keys → `service_role` `secret` |
| `SUPABASE_JWT_SECRET`       | Secret used to sign/verify auth JWTs        | Project Settings → **API** → **JWT Settings** → JWT Secret |
| `SUPABASE_DB_URL`           | Direct Postgres connection string           | Project Settings → **Database** → Connection string (URI) |

> Never commit the `service_role` key or the DB URL. They are server-side secrets.

## Auth model / conventions

- Sign-up creates an `auth.users` row; the `handle_new_user()` trigger
  (`SECURITY DEFINER`) mirrors it into `public.profiles`, taking `username` from
  `raw_user_meta_data->>'username'` (falling back to the email local-part).
- Email confirmations are **disabled** (`config.toml`), so `username@users.dishport.app`
  pseudo-emails let users register/log in without a real inbox.
- Every user-owned table keys off `user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE`.
  RLS restricts clients to their own rows; global tables (`dishes`, `flavor_svd_model`,
  `dish_flavor_factors`, `cf_item_factors`) are readable by any authenticated user and
  writable only by `service_role`.
