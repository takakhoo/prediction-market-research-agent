#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-configs/sources/polymarket_runtime.template.env}"
PORT="${2:-8010}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}"
  exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

echo "[1/3] Running Polymarket preflight (read_only)..."
bash scripts/polymarket_preflight.sh read_only "${ENV_FILE}"

echo "[2/3] Loading environment from ${ENV_FILE}..."
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

echo "[3/3] Starting Polymarket dashboard on http://127.0.0.1:${PORT} (python: ${PYTHON_BIN})"
exec "${PYTHON_BIN}" -m uvicorn src.polymarket_dashboard.api:app --reload --port "${PORT}"
