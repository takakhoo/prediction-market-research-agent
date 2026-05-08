#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-configs/sources/telegram_runtime.template.env}"
PORT="${2:-8000}"
POLYMARKET_ENV_FILE="${3:-configs/sources/polymarket_runtime.template.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOT_RELOAD="${HOT_RELOAD:-0}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}"
  exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

echo "[1/3] Running preflight..."
bash scripts/telegram_preflight.sh tdlib_discovery_only "${ENV_FILE}"

echo "[2/3] Loading environment from ${ENV_FILE}..."
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [[ -f "${POLYMARKET_ENV_FILE}" ]]; then
  echo "[3/4] Running Polymarket preflight (read_only)..."
  bash scripts/polymarket_preflight.sh read_only "${POLYMARKET_ENV_FILE}"
  echo "[4/4] Loading Polymarket env from ${POLYMARKET_ENV_FILE}..."
  set -a
  # shellcheck disable=SC1090
  source "${POLYMARKET_ENV_FILE}"
  set +a
else
  echo "[3/4] Polymarket env file not found, continuing without it: ${POLYMARKET_ENV_FILE}"
fi

UVICORN_ARGS=(src.workspace_dashboard.api:app --port "${PORT}")
if [[ "${HOT_RELOAD}" == "1" || "${HOT_RELOAD}" == "true" ]]; then
  UVICORN_ARGS+=(--reload)
  echo "Starting tabbed workspace dashboard with HOT_RELOAD on http://127.0.0.1:${PORT} (python: ${PYTHON_BIN})"
else
  echo "Starting tabbed workspace dashboard with HOT_RELOAD off (recommended for TDLib stability) on http://127.0.0.1:${PORT} (python: ${PYTHON_BIN})"
fi
exec "${PYTHON_BIN}" -m uvicorn "${UVICORN_ARGS[@]}"
