#!/usr/bin/env bash
set -euo pipefail

# Prepare a Linux host for running the Polymarket News Agent workers.
# Supported:
# - Amazon Linux 2023 (dnf)
# - Ubuntu 24.04+ (apt)
# Run this from the repo root as the deployment user.

if [[ ! -f "pyproject.toml" ]]; then
  echo "Run this script from the repository root (pyproject.toml not found)."
  exit 1
fi

echo "[1/4] Installing OS dependencies..."
if command -v dnf >/dev/null 2>&1; then
  sudo dnf update -y
  sudo dnf install -y \
    git \
    python3 \
    python3-pip \
    tmux \
    jq \
    htop \
    openssl \
    ca-certificates
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y \
    git \
    python3 \
    python3-venv \
    python3-pip \
    tmux \
    jq \
    htop \
    openssl \
    ca-certificates \
    libc++1 \
    libc++abi1 \
    libunwind8
else
  echo "Unsupported package manager. Expected dnf or apt-get."
  exit 1
fi

echo "[2/4] Creating virtual environment..."
python3 -m venv .venv

echo "[3/4] Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e .

echo "[4/4] Creating runtime directories..."
mkdir -p .runtime/telegram_session logs data/raw data/normalized data/derived

cat <<'EOF'
Host preparation complete.

Next steps:
1. Put runtime env files on the host (recommended):
   - /etc/polymarket-news-agent/.env
   - /etc/polymarket-news-agent/telegram.env
2. Bootstrap Telegram session once:
   .venv/bin/python scripts/telegram_session_bootstrap.py --env-file /etc/polymarket-news-agent/telegram.env
3. Install and start systemd services:
   sudo bash scripts/install_ec2_services.sh "$(pwd)" <run-user> /etc/polymarket-news-agent/.env /etc/polymarket-news-agent/telegram.env
EOF
