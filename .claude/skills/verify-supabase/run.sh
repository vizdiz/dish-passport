#!/usr/bin/env bash
# Verify the Dish Passport Supabase stack end-to-end from the CLI.
# Auth (ES256/JWKS) -> worker -> UUID -> DB (trigger/schema/RLS) -> data path.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
WANT_MINT=0; [ "${1:-}" = "--mint" ] && WANT_MINT=1

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()  { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m[FAIL] %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$REPO_ROOT/.supabase.env" ] || die ".supabase.env not found at repo root"
set -a; . "$REPO_ROOT/.supabase.env"; set +a
: "${SUPABASE_URL:?}"; : "${SUPABASE_ANON_KEY:?}"; : "${SUPABASE_SERVICE_ROLE_KEY:?}"; : "${SUPABASE_DB_URL:?}"
PORT=8010; BASE="http://localhost:$PORT"
export PGCONNECT_TIMEOUT=8
jq_get() { python3 -c "import sys,json;print((json.load(sys.stdin) or {}).get('$1','') or '')" 2>/dev/null; }

# --- 1. connectivity ----------------------------------------------------------
say "1. DB connectivity"
psql "$SUPABASE_DB_URL" -tAc "select 1" >/dev/null 2>&1 || die "cannot reach Supabase DB (is SUPABASE_DB_URL the IPv4 pooler?)"
ok "connected"

# --- 2. schema (apply only if missing) ---------------------------------------
say "2. Schema"
HAS_PROFILES=$(psql "$SUPABASE_DB_URL" -tAc "select to_regclass('public.profiles') is not null" 2>/dev/null | tr -d '[:space:]')
if [ "$HAS_PROFILES" != "t" ]; then
  echo "  profiles missing — applying migrations"
  for f in "$REPO_ROOT"/supabase/migrations/*.sql; do
    psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$f" >/dev/null || die "migration failed: $f"
  done
fi
TABLES=$(psql "$SUPABASE_DB_URL" -tAc "select count(*) from pg_tables where schemaname='public'" | tr -d '[:space:]')
TRIG=$(psql "$SUPABASE_DB_URL" -tAc "select count(*) from pg_trigger where tgrelid='auth.users'::regclass and tgname='on_auth_user_created'" | tr -d '[:space:]')
RLS=$(psql "$SUPABASE_DB_URL" -tAc "select count(*) from pg_tables where schemaname='public' and rowsecurity" | tr -d '[:space:]')
VEC=$(psql "$SUPABASE_DB_URL" -tAc "select count(*) from pg_extension where extname='vector'" | tr -d '[:space:]')
[ "$TABLES" -ge 9 ] || die "expected >=9 public tables, found $TABLES"
[ "$TRIG" = "1" ]  || die "signup trigger on_auth_user_created missing"
[ "$VEC" = "1" ]   || die "pgvector not installed"
ok "$TABLES tables, trigger present, RLS on $RLS, pgvector on"

# --- 3. worker ----------------------------------------------------------------
say "3. Worker on :$PORT"
if ! curl -sf "$BASE/health" >/dev/null 2>&1; then
  echo "  booting worker"
  ( cd "$REPO_ROOT/backend" && set -a && . "$REPO_ROOT/.supabase.env" && set +a \
    && nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT" >/tmp/dishport-worker.log 2>&1 & )
  for _ in $(seq 1 30); do curl -sf "$BASE/health" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -sf "$BASE/health" >/dev/null 2>&1 || die "worker /health unreachable (see /tmp/dishport-worker.log)"
ok "healthy"

# --- 4. auth round-trip -------------------------------------------------------
say "4. Auth round-trip (ES256/JWKS)"
EMAIL="verify-1@dishport.app"; PASS="passw0rd1"
# admin-create a confirmed user (idempotent: ignore 'already registered')
curl -s -X POST "$SUPABASE_URL/auth/v1/admin/users" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"email_confirm\":true,\"user_metadata\":{\"username\":\"verify1\"}}" >/dev/null
SIGNIN=$(curl -s -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(echo "$SIGNIN" | jq_get access_token)
[ -n "$TOKEN" ] || die "sign-in returned no token: $(echo "$SIGNIN" | head -c 160)"
ALG=$(echo "$TOKEN" | cut -d. -f1 | python3 -c "import sys,base64,json;s=sys.stdin.read().strip();s+='='*(-len(s)%4);print(json.loads(base64.urlsafe_b64decode(s)).get('alg'))" 2>/dev/null)
ok "token minted (alg=$ALG)"

C_NONE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/users/me/taste-profile")
C_BAD=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer bad.token.here" "$BASE/users/me/taste-profile")
C_OK=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE/recommendations?n=3")
[ "$C_NONE" = "401" ] || die "no-token expected 401, got $C_NONE"
[ "$C_BAD" = "401" ]  || die "bad-token expected 401, got $C_BAD"
[ "$C_OK" = "200" ]   || die "valid-token on /recommendations expected 200, got $C_OK"
ok "no-token 401, bad-token 401, valid-token 200 (worker verified via JWKS)"

PROF=$(psql "$SUPABASE_DB_URL" -tAc "select username from public.profiles where username='verify1'" | tr -d '[:space:]')
[ "$PROF" = "verify1" ] || die "profiles row not created by trigger"
ok "signup trigger created profiles row"

# --- 5. optional mint ---------------------------------------------------------
if [ "$WANT_MINT" = "1" ]; then
  say "5. OpenAI mint path (--mint)"
  RESP=$(curl -s -w "\n%{http_code}" -m 40 -X POST "$BASE/logs" -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"text":"grilled halloumi with lemon and mint","sentiment":"liked","rating":5}')
  CODE=$(echo "$RESP" | tail -1)
  [ "$CODE" = "200" ] || die "POST /logs mint expected 200, got $CODE (needs DP_OPENAI_API_KEY in backend/.env): $(echo "$RESP" | sed '$d' | head -c 160)"
  ok "dish minted + persisted under the UUID user"
fi

say "PASS — Supabase stack verified end-to-end"
