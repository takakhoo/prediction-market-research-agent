#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
ENV_FILE="${2:-configs/sources/telegram_runtime.template.env}"

if [[ -z "${MODE}" ]]; then
  echo "Usage: bash scripts/telegram_preflight.sh <bot_api_only|bot_api_plus_tdlib_stub|tdlib_discovery_only> [env_file]"
  exit 1
fi

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

if [[ "${MODE}" == "bot_api_only" || "${MODE}" == "bot_api_plus_tdlib_stub" ]]; then
  require_var "TELEGRAM_BOT_TOKEN"
fi

if [[ "${MODE}" == "bot_api_plus_tdlib_stub" || "${MODE}" == "tdlib_discovery_only" ]]; then
  require_var "TELEGRAM_API_ID"
  require_var "TELEGRAM_API_HASH"
  require_var "TELEGRAM_PHONE_NUMBER"
fi

if [[ "${MODE}" == "tdlib_discovery_only" ]]; then
  require_var "TELEGRAM_SESSION_DIR"
fi

if [[ "${MODE}" != "bot_api_only" && "${MODE}" != "bot_api_plus_tdlib_stub" && "${MODE}" != "tdlib_discovery_only" ]]; then
  echo "Invalid mode: ${MODE}"
  echo "Allowed: bot_api_only | bot_api_plus_tdlib_stub | tdlib_discovery_only"
  exit 1
fi

if [[ "${#missing[@]}" -gt 0 ]]; then
  echo "Preflight failed. Missing values:"
  printf ' - %s\n' "${missing[@]}"
  exit 1
fi

echo "Preflight OK for mode: ${MODE}"
echo "Env file: ${ENV_FILE}"
