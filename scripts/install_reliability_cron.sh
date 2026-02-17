#!/usr/bin/env bash
set -euo pipefail

# Installs daily + weekly reliability jobs into user crontab.
# Usage:
#   AGENT_ID=<agent_uuid> ./scripts/install_reliability_cron.sh
# Optional:
#   COMPOSE_FILE=docker-compose.prod.yml
#   ENV_FILE=.env.production
#   REPORTS_DIR=/app/tenants/_ops_reports

if [[ -z "${AGENT_ID:-}" ]]; then
  echo "ERROR: AGENT_ID is required" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
REPORTS_DIR="${REPORTS_DIR:-/app/tenants/_ops_reports}"

mkdir -p "$ROOT_DIR/ops/reports"

if [[ ! -f "$ROOT_DIR/$COMPOSE_FILE" ]]; then
  echo "ERROR: compose file not found: $ROOT_DIR/$COMPOSE_FILE" >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ROOT_DIR/$ENV_FILE" >&2
  exit 1
fi

BEGIN="# AGENTBOX_RELIABILITY_AUTOMATION_BEGIN"
END="# AGENTBOX_RELIABILITY_AUTOMATION_END"

CRON_TMP="$(mktemp)"
{ crontab -l 2>/dev/null || true; } > "$CRON_TMP"

# Remove previous block if exists
awk -v b="$BEGIN" -v e="$END" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
' "$CRON_TMP" > "$CRON_TMP.new"
mv "$CRON_TMP.new" "$CRON_TMP"

cat >> "$CRON_TMP" <<EOF
$BEGIN
# Daily KPI report at 09:05 UTC
5 9 * * * cd $ROOT_DIR && docker compose -f $COMPOSE_FILE --env-file $ENV_FILE exec -T app env AGENT_ID=$AGENT_ID python3 /app/scripts/reliability_cycle.py --mode daily --agent-id $AGENT_ID --out-dir $REPORTS_DIR >> $ROOT_DIR/ops/reports/cron.log 2>&1
# Weekly review snapshot at Monday 09:15 UTC
15 9 * * 1 cd $ROOT_DIR && docker compose -f $COMPOSE_FILE --env-file $ENV_FILE exec -T app env AGENT_ID=$AGENT_ID python3 /app/scripts/reliability_cycle.py --mode weekly --agent-id $AGENT_ID --out-dir $REPORTS_DIR >> $ROOT_DIR/ops/reports/cron.log 2>&1
$END
EOF

crontab "$CRON_TMP"
rm -f "$CRON_TMP"

echo "Installed reliability automation cron jobs for AGENT_ID=$AGENT_ID"
