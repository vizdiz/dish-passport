#!/usr/bin/env bash
# Deploy the Dish Passport API to Azure Container Apps. Idempotent (re-run to ship a new image).
# Reads resource names + DB/storage from ../../.azure-deploy.env and the OpenAI key from
# ../../backend/.env. Prereqs come from provision.sh; migrations are already applied to the DB.
#
#   bash infra/azure/deploy.sh
#
# Steps: (1) cloud-build the image in ACR, (2) create/update the container app with secrets +
# external ingress on :8000, (3) print the public URL. Batch jobs (Celery) are a separate
# deploy and are not included here.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENVF="$ROOT/.azure-deploy.env"
val() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2-; }

RG=$(val AZ_RG)
ACR=$(val AZ_ACR)
ACR_LOGIN=$(val AZ_ACR_LOGIN)
CAENV=$(val AZ_CONTAINERAPP_ENV)
DBURL=$(val DP_DATABASE_URL)
STCONN=$(val DP_AZURE_STORAGE_CONNECTION_STRING)
OPENAI=$(grep -E '^DP_OPENAI_API_KEY=' "$ROOT/backend/.env" | head -1 | cut -d= -f2-)
JWT=$(val AZ_JWT_SECRET)
if [ -z "$JWT" ]; then JWT=$(openssl rand -hex 32); echo "AZ_JWT_SECRET=$JWT" >> "$ENVF"; fi

APP=dishport-api
TAG=v1
IMG="$ACR_LOGIN/$APP:$TAG"
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "cloud-build $IMG"
az acr build -r "$ACR" -t "$APP:$TAG" "$ROOT/backend" -o none || { log "build FAILED"; exit 1; }

ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv)

ENV_VARS="DP_OPENAI_API_KEY=secretref:openai-key DP_DATABASE_URL=secretref:db-url \
DP_AZURE_STORAGE_CONNECTION_STRING=secretref:storage-conn DP_JWT_SECRET=secretref:jwt-secret \
DP_AZURE_STORAGE_CONTAINER=dishport-photos"

if az containerapp show -g "$RG" -n "$APP" -o none 2>/dev/null; then
  log "update existing app $APP"
  az containerapp secret set -g "$RG" -n "$APP" --secrets \
    openai-key="$OPENAI" db-url="$DBURL" storage-conn="$STCONN" jwt-secret="$JWT" -o none
  az containerapp update -g "$RG" -n "$APP" --image "$IMG" --set-env-vars $ENV_VARS -o none
else
  log "create app $APP"
  az containerapp create -g "$RG" -n "$APP" --environment "$CAENV" --image "$IMG" \
    --registry-server "$ACR_LOGIN" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
    --target-port 8000 --ingress external --min-replicas 0 --max-replicas 2 \
    --secrets openai-key="$OPENAI" db-url="$DBURL" storage-conn="$STCONN" jwt-secret="$JWT" \
    --env-vars $ENV_VARS -o none
fi

FQDN=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
log "DONE — https://$FQDN  (docs at /docs, health at /health)"
