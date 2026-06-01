#!/usr/bin/env bash
# Provision Dish Passport's Azure prerequisites (no app deploy — that happens later).
# Idempotent enough for a one-shot run; generates a unique suffix and writes all names +
# secrets + connection strings to ../../.azure-deploy.env (gitignored).
#
#   az login   # (service principal already logged in here)
#   bash infra/azure/provision.sh
#
# Creates: resource group, ACR (Basic), Postgres Flexible Server (B1ms, pgvector),
# Storage account + blob container, Container Apps environment. (Redis intentionally skipped.)
set -uo pipefail

RG=dishport-rg
LOC=eastus
# Postgres Flexible Server may be region-restricted on credit subscriptions (eastus was, for
# this one). Keep its region separate; westus3 was allowed. Override with PG_LOC=... if needed.
PG_LOC="${PG_LOC:-westus3}"
SFX=$(openssl rand -hex 3)
ACR=dishportacr${SFX}
PG=dishport-pg-${SFX}
ST=dishportst${SFX}
ENVNAME=dishport-env
PGADMIN=dishport
PGDB=dishport
PGPASS=$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 28)
OUT="$(cd "$(dirname "$0")/../.." && pwd)/.azure-deploy.env"

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "resource group ${RG} @ ${LOC}"
az group create -n "$RG" -l "$LOC" -o none || { log "FAILED: group create"; exit 1; }

log "ACR ${ACR} (Basic, admin enabled)"
az acr create -g "$RG" -n "$ACR" --sku Basic --admin-enabled true -o none || log "WARN: acr create"
ACR_LOGIN=$(az acr show -g "$RG" -n "$ACR" --query loginServer -o tsv 2>/dev/null)

log "storage ${ST} (+ public blob container dishport-photos)"
az storage account create -g "$RG" -n "$ST" -l "$LOC" --sku Standard_LRS --kind StorageV2 \
  --allow-blob-public-access true -o none || log "WARN: storage create"
ST_CONN=$(az storage account show-connection-string -g "$RG" -n "$ST" --query connectionString -o tsv 2>/dev/null)
az storage container create --name dishport-photos --connection-string "$ST_CONN" \
  --public-access blob -o none || log "WARN: container create"

log "postgres flexible server ${PG} (B1ms, pg16) @ ${PG_LOC} — slow (~5-10 min)"
az postgres flexible-server create -g "$RG" -n "$PG" -l "$PG_LOC" \
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 \
  --admin-user "$PGADMIN" --admin-password "$PGPASS" \
  --public-access 0.0.0.0 --yes -o none || log "WARN: postgres create"
log "create database ${PGDB} + allowlist pgvector"
az postgres flexible-server db create -g "$RG" -s "$PG" -d "$PGDB" -o none || log "WARN: db create"
az postgres flexible-server parameter set -g "$RG" -s "$PG" --name azure.extensions --value vector -o none || log "WARN: pgvector param"
MYIP=$(curl -4 -fsS ifconfig.me 2>/dev/null || true)
if [ -n "$MYIP" ]; then
  log "firewall: allow dev machine ${MYIP}"
  az postgres flexible-server firewall-rule create -g "$RG" -n "$PG" \
    --rule-name devmachine --start-ip-address "$MYIP" --end-ip-address "$MYIP" -o none || log "WARN: fw rule"
fi
PG_HOST=$(az postgres flexible-server show -g "$RG" -n "$PG" --query fullyQualifiedDomainName -o tsv 2>/dev/null)

log "container apps environment ${ENVNAME} — slow (~3-5 min)"
az containerapp env create -g "$RG" -n "$ENVNAME" -l "$LOC" -o none || log "WARN: env create"

log "writing ${OUT}"
cat > "$OUT" <<EOF
# Azure deploy config — GITIGNORED. Generated $(date -u +%Y-%m-%dT%H:%M:%SZ).
AZ_RG=${RG}
AZ_LOC=${LOC}
AZ_PG_LOC=${PG_LOC}
AZ_ACR=${ACR}
AZ_ACR_LOGIN=${ACR_LOGIN}
AZ_PG=${PG}
AZ_PG_HOST=${PG_HOST}
AZ_PG_DB=${PGDB}
AZ_PG_USER=${PGADMIN}
AZ_PG_PASSWORD=${PGPASS}
AZ_STORAGE_ACCOUNT=${ST}
AZ_STORAGE_CONN=${ST_CONN}
AZ_CONTAINERAPP_ENV=${ENVNAME}

# Backend runtime env for the container app (overnight deploy reads these):
DP_DATABASE_URL=postgresql://${PGADMIN}:${PGPASS}@${PG_HOST}:5432/${PGDB}?sslmode=require
DP_AZURE_STORAGE_CONNECTION_STRING=${ST_CONN}
DP_AZURE_STORAGE_CONTAINER=dishport-photos
EOF
chmod 600 "$OUT"
log "DONE — resources in ${RG} (suffix ${SFX}). Secrets in .azure-deploy.env"
