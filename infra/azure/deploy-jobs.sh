#!/usr/bin/env bash
# Deploy the three batch jobs as cron-scheduled Azure Container Apps Jobs (no Celery/Redis).
# Each job runs `python app/batch.py <name>` on the deployed image, against the DB.
#   bash infra/azure/deploy-jobs.sh
# Trigger one on demand:  az containerapp job start -g dishport-rg -n dishport-job-taste
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENVF="$ROOT/.azure-deploy.env"
val() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2-; }

RG=$(val AZ_RG)
ACR=$(val AZ_ACR)
ACR_LOGIN=$(val AZ_ACR_LOGIN)
CAENV=$(val AZ_CONTAINERAPP_ENV)
DBURL=$(val DP_DATABASE_URL)
IMG="$ACR_LOGIN/dishport-api:v1"
ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv)
log() { echo "[$(date +%H:%M:%S)] $*"; }

# name  cron(UTC)        task
#   taste profiles hourly · ALS nightly 03:00 · SVD weekly Sun 04:00
create_job() {
  local NAME=$1 CRON=$2 TASK=$3
  log "job $NAME  cron='$CRON'  task=$TASK"
  az containerapp job create -g "$RG" -n "$NAME" --environment "$CAENV" \
    --trigger-type Schedule --cron-expression "$CRON" \
    --image "$IMG" --cpu 0.5 --memory 1.0Gi \
    --registry-server "$ACR_LOGIN" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
    --replica-timeout 1800 --replica-retry-limit 1 --replica-completion-count 1 --parallelism 1 \
    --secrets db-url="$DBURL" \
    --env-vars DP_DATABASE_URL=secretref:db-url PYTHONPATH=/app \
    --command python --args "app/batch.py" "$TASK" \
    -o none || log "  WARN: $NAME create failed"
}

create_job dishport-job-taste "0 * * * *" taste
create_job dishport-job-als   "0 3 * * *" als
create_job dishport-job-svd   "0 4 * * 0" svd
log "done — list with: az containerapp job list -g $RG -o table"
