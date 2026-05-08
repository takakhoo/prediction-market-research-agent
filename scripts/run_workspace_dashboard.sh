#!/usr/bin/env bash
set -euo pipefail

TELEGRAM_ENV_FILE="${1:-configs/sources/telegram_runtime.template.env}"
POLYMARKET_ENV_FILE="${2:-configs/sources/polymarket_runtime.template.env}"
PORT="${3:-8020}"
HOST="${4:-127.0.0.1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOT_RELOAD="${HOT_RELOAD:-0}"

if [[ ! -f "${TELEGRAM_ENV_FILE}" ]]; then
  echo "Telegram env file not found: ${TELEGRAM_ENV_FILE}"
  exit 1
fi

if [[ ! -f "${POLYMARKET_ENV_FILE}" ]]; then
  echo "Polymarket env file not found: ${POLYMARKET_ENV_FILE}"
  exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

echo "[1/4] Telegram preflight..."
bash scripts/telegram_preflight.sh tdlib_discovery_only "${TELEGRAM_ENV_FILE}"

echo "[2/4] Polymarket preflight (read_only)..."
bash scripts/polymarket_preflight.sh read_only "${POLYMARKET_ENV_FILE}"

echo "[3/4] Loading environment files..."
set -a
# shellcheck disable=SC1090
source "${TELEGRAM_ENV_FILE}"
# shellcheck disable=SC1090
source "${POLYMARKET_ENV_FILE}"
set +a

UVICORN_ARGS=(src.workspace_dashboard.api:app --host "${HOST}" --port "${PORT}")
if [[ "${HOT_RELOAD}" == "1" || "${HOT_RELOAD}" == "true" ]]; then
  UVICORN_ARGS+=(--reload)
  echo "[4/4] Starting workspace dashboard with HOT_RELOAD on http://${HOST}:${PORT} (python: ${PYTHON_BIN})"
else
  echo "[4/4] Starting workspace dashboard with HOT_RELOAD off (recommended for TDLib stability) on http://${HOST}:${PORT} (python: ${PYTHON_BIN})"
fi
exec "${PYTHON_BIN}" -m uvicorn "${UVICORN_ARGS[@]}"
