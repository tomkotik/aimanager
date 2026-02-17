#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   AGENT_ID=<uuid> DATABASE_URL=<postgresql+asyncpg://...> ./scripts/release_gate.sh

if [[ -z "${AGENT_ID:-}" ]]; then
  echo "ERROR: AGENT_ID is required" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is required" >&2
  exit 1
fi

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

python3 scripts/regression_matrix.py \
  --base-url "$BASE_URL" \
  --agent-id "$AGENT_ID" \
  --db-url "$DATABASE_URL"

echo "Release gate passed."
