#!/usr/bin/env bash
set -euo pipefail

# Installs/updates systemd services for long-running workers.
#
# Usage:
#   sudo bash scripts/install_ec2_services.sh <repo_dir> <run_user> <db_env_file> <telegram_env_file> [dashboard_port]
#
# Example:
#   sudo bash scripts/install_ec2_services.sh /opt/polymarket-news-agent ec2-user /etc/polymarket-news-agent/.env /etc/polymarket-news-agent/telegram.env 8020

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (use sudo)."
  exit 1
fi

REPO_DIR="${1:-}"
RUN_USER="${2:-ec2-user}"
DB_ENV_FILE="${3:-/etc/polymarket-news-agent/.env}"
TELEGRAM_ENV_FILE="${4:-/etc/polymarket-news-agent/telegram.env}"
DASHBOARD_PORT="${5:-8020}"

if [[ -z "${REPO_DIR}" ]]; then
  echo "Usage: sudo bash scripts/install_ec2_services.sh <repo_dir> <run_user> <db_env_file> <telegram_env_file> [dashboard_port]"
  exit 1
fi

if [[ ! -d "${REPO_DIR}" ]]; then
  echo "Repo directory not found: ${REPO_DIR}"
  exit 1
fi

if [[ ! -f "${REPO_DIR}/.venv/bin/python" ]]; then
  echo "Python venv not found at ${REPO_DIR}/.venv/bin/python"
  echo "Run scripts/ec2_prepare_host.sh first."
  exit 1
fi

if [[ ! -f "${DB_ENV_FILE}" ]]; then
  echo "DB env file not found: ${DB_ENV_FILE}"
  exit 1
fi

if [[ ! -f "${TELEGRAM_ENV_FILE}" ]]; then
  echo "Telegram env file not found: ${TELEGRAM_ENV_FILE}"
  exit 1
fi

PYTHON_BIN="${REPO_DIR}/.venv/bin/python"

cat >/etc/systemd/system/polymarket-ingest.service <<EOF
[Unit]
Description=Polymarket Ingest Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${PYTHON_BIN} ${REPO_DIR}/scripts/ingest_markets.py --env-file ${DB_ENV_FILE} --watch --interval-seconds 60
Restart=always
RestartSec=5
TimeoutStopSec=30
StandardOutput=append:${REPO_DIR}/logs/worker_ingest.log
StandardError=append:${REPO_DIR}/logs/worker_ingest.log

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/polymarket-analyze.service <<EOF
[Unit]
Description=Polymarket Analysis Worker
After=network-online.target polymarket-ingest.service
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${PYTHON_BIN} ${REPO_DIR}/scripts/analyze_markets.py --env-file ${DB_ENV_FILE} --watch --interval-seconds 60 --limit 100
Restart=always
RestartSec=5
TimeoutStopSec=30
StandardOutput=append:${REPO_DIR}/logs/worker_analyze.log
StandardError=append:${REPO_DIR}/logs/worker_analyze.log

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/telegram-market-agent.service <<EOF
[Unit]
Description=Telegram Market Agent (Discovery + Listener)
After=network-online.target polymarket-analyze.service
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${PYTHON_BIN} ${REPO_DIR}/scripts/run_telegram_market_agent.py --env-file ${DB_ENV_FILE} --env-file ${TELEGRAM_ENV_FILE} --discover-interval-seconds 120 --listen-interval-seconds 8 --market-limit 30 --target-channels-per-market 25 --global-max-channels 500 --query-results-limit 20 --max-queries-per-market 6 --similar-per-seed 10 --similar-seed-channels 3 --channel-limit 500 --markets-per-channel 25 --history-limit 10 --concurrency 8 --max-new-messages 3000
Restart=always
RestartSec=5
TimeoutStopSec=30
StandardOutput=append:${REPO_DIR}/logs/worker_telegram_agent.log
StandardError=append:${REPO_DIR}/logs/worker_telegram_agent.log

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/workspace-dashboard.service <<EOF
[Unit]
Description=Workspace Dashboard (Telegram + Polymarket + Backtest)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/scripts/run_workspace_dashboard.sh ${TELEGRAM_ENV_FILE} ${DB_ENV_FILE} ${DASHBOARD_PORT} 0.0.0.0
Restart=always
RestartSec=5
TimeoutStopSec=30
StandardOutput=append:${REPO_DIR}/logs/workspace_dashboard.log
StandardError=append:${REPO_DIR}/logs/workspace_dashboard.log

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "${REPO_DIR}/logs"
chown -R "${RUN_USER}:${RUN_USER}" "${REPO_DIR}/logs"

systemctl daemon-reload
systemctl enable --now polymarket-ingest.service
systemctl enable --now polymarket-analyze.service
systemctl enable --now telegram-market-agent.service
systemctl enable --now workspace-dashboard.service

cat <<'EOF'
systemd services installed and started:
 - polymarket-ingest.service
 - polymarket-analyze.service
 - telegram-market-agent.service
 - workspace-dashboard.service

Useful commands:
  sudo systemctl status polymarket-ingest.service --no-pager
  sudo systemctl status polymarket-analyze.service --no-pager
  sudo systemctl status telegram-market-agent.service --no-pager
  sudo systemctl status workspace-dashboard.service --no-pager
  sudo journalctl -u telegram-market-agent.service -f
  sudo journalctl -u workspace-dashboard.service -f
EOF
