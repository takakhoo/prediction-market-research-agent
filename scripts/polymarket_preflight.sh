#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-read_only}"
ENV_FILE="${2:-configs/sources/polymarket_runtime.template.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

missing=()

require_var() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "${value}" || "${value}" == "replace_me" ]]; then
    missing+=("${name}")
  fi
}

if [[ "${MODE}" == "trading" ]]; then
  require_var "POLYMARKET_PRIVATE_KEY"
  require_var "POLYMARKET_FUNDER_ADDRESS"
fi

if [[ "${MODE}" != "read_only" && "${MODE}" != "trading" ]]; then
  echo "Invalid mode: ${MODE}"
  echo "Allowed: read_only | trading"
  exit 1
fi

if [[ "${#missing[@]}" -gt 0 ]]; then
  echo "Preflight failed. Missing values:"
  printf ' - %s\n' "${missing[@]}"
  exit 1
fi

echo "Preflight OK for mode: ${MODE}"
echo "Env file: ${ENV_FILE}"
