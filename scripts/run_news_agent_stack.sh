#!/usr/bin/env bash
set -euo pipefail

DB_ENV_FILE="${1:-.env}"
TELEGRAM_ENV_FILE="${2:-configs/sources/telegram_runtime.template.env}"

if [[ ! -f "${DB_ENV_FILE}" ]]; then
  echo "DB env file not found: ${DB_ENV_FILE}"
  exit 1
fi

if [[ ! -f "${TELEGRAM_ENV_FILE}" ]]; then
  echo "Telegram env file not found: ${TELEGRAM_ENV_FILE}"
  exit 1
fi

mkdir -p logs

echo "Starting workers with:"
echo " - DB env: ${DB_ENV_FILE}"
echo " - Telegram env: ${TELEGRAM_ENV_FILE}"

python3 scripts/ingest_markets.py --env-file "${DB_ENV_FILE}" --watch --interval-seconds 60 \
  > logs/worker_ingest.log 2>&1 &
PID_INGEST=$!

python3 scripts/analyze_markets.py --env-file "${DB_ENV_FILE}" --watch --interval-seconds 60 --limit 100 \
  > logs/worker_analyze.log 2>&1 &
PID_ANALYZE=$!

python3 scripts/run_telegram_market_agent.py \
  --env-file "${DB_ENV_FILE}" \
  --env-file "${TELEGRAM_ENV_FILE}" \
  --discover-interval-seconds 120 \
  --listen-interval-seconds 8 \
  --market-limit 30 \
  --target-channels-per-market 25 \
  --global-max-channels 500 \
  --query-results-limit 20 \
  --max-queries-per-market 6 \
  --similar-per-seed 10 \
  --similar-seed-channels 3 \
  --channel-limit 500 \
  --markets-per-channel 25 \
  --history-limit 10 \
  --concurrency 8 \
  --max-new-messages 3000 \
  > logs/worker_telegram_agent.log 2>&1 &
PID_TELEGRAM_AGENT=$!

cleanup() {
  echo "Stopping workers..."
  kill "${PID_INGEST}" "${PID_ANALYZE}" "${PID_TELEGRAM_AGENT}" 2>/dev/null || true
  wait "${PID_INGEST}" "${PID_ANALYZE}" "${PID_TELEGRAM_AGENT}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Workers started:"
echo " - ingest:   ${PID_INGEST} (logs/worker_ingest.log)"
echo " - analyze:  ${PID_ANALYZE} (logs/worker_analyze.log)"
echo " - telegram_agent: ${PID_TELEGRAM_AGENT} (logs/worker_telegram_agent.log)"
echo
echo "Press Ctrl+C to stop all workers."

wait "${PID_INGEST}" "${PID_ANALYZE}" "${PID_TELEGRAM_AGENT}"
