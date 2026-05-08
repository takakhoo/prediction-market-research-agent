# Telegram Setup Steps

This runbook is for the discovery dashboard MVP.

## 1) Choose mode

Modes:
1. `tdlib_discovery_only` (default for discovery MVP)
2. `bot_api_only`
3. `bot_api_plus_tdlib_stub`

## 2) Create credentials

### Telegram app credentials (required for TDLib discovery)
1. Log in to `https://my.telegram.org`.
2. Create an application.
3. Save `api_id` and `api_hash`.

### Bot API token (not required for discovery)
Only needed for bot modes.

## 3) Configure environment

1. Copy `configs/sources/telegram_runtime.template.env` into your local runtime env file.
2. Fill values for chosen mode.
3. For discovery mode, you must set:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `TELEGRAM_PHONE_NUMBER`
   - `TELEGRAM_SESSION_DIR`
   - `TELEGRAM_READ_ONLY_MODE=true` (recommended safety default)

## 4) Run preflight checks

```bash
bash scripts/telegram_preflight.sh tdlib_discovery_only
```

## 5) Bootstrap TDLib session once

```bash
python3 scripts/telegram_session_bootstrap.py --env-file configs/sources/telegram_runtime.template.env
```

This creates the local TDLib session and marker under `.runtime/telegram_session`.

## 6) Start the dashboard

Preferred:
```bash
bash scripts/run_discovery_dashboard.sh configs/sources/telegram_runtime.template.env 8000
```

Manual alternative:
```bash
uvicorn src.discovery.api:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

## 7) Optional read-only probe

Use this after bootstrap to test discovery calls without write actions:
```bash
python3 scripts/telegram_readonly_probe.py --env-file configs/sources/telegram_runtime.template.env --query "israel lebanon"
```

## 8) Record progress

Update `docs/STATUS.md` with:
1. selected mode
2. session bootstrap status
3. dashboard verification notes

## 9) Run Telegram market workers (Postgres-backed)

These workers connect Telegram discovery to analyzed Polymarket markets.

Discover channels for `track_now` markets:
```bash
python3 scripts/discover_channels.py \
  --env-file .env \
  --env-file configs/sources/telegram_runtime.template.env
```

Listen and evaluate incoming messages:
```bash
python3 scripts/listen_telegram_messages.py \
  --env-file .env \
  --env-file configs/sources/telegram_runtime.template.env
```

Continuous mode:
```bash
python3 scripts/run_telegram_market_agent.py \
  --env-file .env \
  --env-file configs/sources/telegram_runtime.template.env \
  --discover-interval-seconds 120 \
  --listen-interval-seconds 8
```

Note:
Run discovery and listener together through `run_telegram_market_agent.py` so both tasks share one TDLib session.

All workers in one shell:
```bash
bash scripts/run_news_agent_stack.sh .env configs/sources/telegram_runtime.template.env
```
