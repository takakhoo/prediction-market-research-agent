# Discovery Dashboard MVP

## Goal

Provide a real TDLib-backed dashboard to discover Telegram channels, preview recent posts, expand similar channels, and seed a watchlist with manual trust weights.

## UX Design Goals

1. Fast operator flow: search -> preview -> expand -> save.
2. Visible system readiness: clear TDLib/session status on page load.
3. Low setup friction: one script to launch after bootstrap.
4. Safe failure messaging: explicit recovery steps when auth/session is missing.

## Stack

1. Backend: FastAPI (`src/discovery/api.py`)
2. Telegram layer: TDLib via `aiotdlib` (`src/discovery/tdlib_client.py`)
3. Database: SQLite (`data/derived/discovery.db`)
4. UI: Jinja + HTMX (`src/discovery_dashboard/templates/`)

## Required Environment

Minimum values:
1. `TELEGRAM_MODE=tdlib_discovery_only`
2. `TELEGRAM_API_ID`
3. `TELEGRAM_API_HASH`
4. `TELEGRAM_PHONE_NUMBER`
5. `TELEGRAM_SESSION_DIR=.runtime/telegram_session`
6. `DISCOVERY_DB_PATH=data/derived/discovery.db`

Optional:
1. `TELEGRAM_2FA_PASSWORD`
2. `TELEGRAM_REQUEST_TIMEOUT_SECONDS`
3. `DISCOVERY_SEARCH_LIMIT`
4. `DISCOVERY_SIMILAR_DEPTH`
5. `DISCOVERY_SIMILAR_PER_NODE`
6. `DISCOVERY_SIMILAR_MAX_NODES`
7. `DISCOVERY_MESSAGE_PREVIEW_LIMIT`

## Setup Flow

1. Preflight:
```bash
bash scripts/telegram_preflight.sh tdlib_discovery_only
```

2. Session bootstrap:
```bash
python3 scripts/telegram_session_bootstrap.py --env-file configs/sources/telegram_runtime.template.env
```

3. Start dashboard (recommended):
```bash
bash scripts/run_discovery_dashboard.sh configs/sources/telegram_runtime.template.env 8000
```

4. Open:
`http://127.0.0.1:8000`

## API Endpoints

1. `GET /api/health`
2. `POST /api/search` with `{ "query": "...", "limit": 50 }`
3. `GET /api/channels/{chat_id}/messages?limit=30`
4. `POST /api/channels/{chat_id}/expand-similar` with `{ "depth": 2, "per_node": 20, "max_nodes": 120 }`
5. `GET /api/watchlist`
6. `POST /api/watchlist` with `{ "chat_id": 123, "trust_weight": 0.7, "tags": ["region"], "notes": "..." }`
7. `PATCH /api/watchlist/{chat_id}`

## UI Endpoints

1. `GET /ui/health`
2. `POST /ui/search`
3. `GET /ui/channels/{chat_id}/messages`
4. `POST /ui/channels/{chat_id}/expand-similar`
5. `GET /ui/watchlist`
6. `GET /ui/channels/{chat_id}/watchlist-form`
7. `POST /ui/watchlist`
8. `PATCH /ui/watchlist/{chat_id}`

## Database Tables

1. `channels`
2. `channel_messages`
3. `watchlist`
4. `discovery_runs`
5. `similar_edges`

## Failure Behavior

If session is not ready:
1. API returns structured error with docs hint.
2. UI renders an error card with concrete recovery commands.
3. Status panel explains exactly what step is missing.

## Test Commands

```bash
python3 -m pytest -q
```

Preflight-only quick check:
```bash
python3 -m pytest -q tests/test_preflight_script.py
```
