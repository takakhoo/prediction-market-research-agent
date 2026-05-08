# Real-Time Listener Runtime

## Purpose

This runtime is the new narrow lane for validating live Telegram intake against a curated Polymarket scope.

It does not do broad market discovery.
It does not do real trading.
It does not use heuristic message matching in the live path.

The runtime only does this:

1. Start from a curated handpicked market set.
2. Map saved Telegram channels to that reduced market set.
3. Listen to linked channels in real time through TDLib updates.
4. Store every received text/caption message from watched channels.
5. Run AI-only message-to-market matching against the markets already linked to that channel.
6. Persist matches and activations for later paper-trading work.

## Current Data Model

### Scope-building tables

- `public.market_groups`
  - grouped market families built from curated Polymarket pages
- `public.market_group_members`
  - member markets inside each grouped family
- `public.handpicked_market_targets`
  - handpicked requested market names, resolution status, and chosen representative market/group

### Runtime tables

- `public.telegram_channels`
  - saved Telegram channel inventory
- `public.channel_market_map`
  - saved channel-to-market links
- `public.telegram_messages`
  - stored incoming Telegram messages
- `public.message_market_matches`
  - stored message-to-market decisions
- `public.market_activations`
  - stored market activation rows from positive matches
- `public.agent_runtime_status`
  - runtime heartbeat/status snapshot
- `public.agent_runtime_events`
  - runtime event log

## New Workflow

### 1. Curate market scope

Grouped market scope is created with:

```bash
python3 scripts/rebuild_grouped_markets.py
```

This writes:

- `public.market_groups`
- `public.market_group_members`

### 2. Import handpicked market names

Handpicked scope import uses:

```bash
python3 scripts/import_handpicked_markets.py handpicked.txt --apply-migration --replace-source
```

This writes:

- `public.handpicked_market_targets`

### 3. Review uncertain market resolutions

Review UI:

- `/handpicked-review`

This is where low-confidence and unmatched handpicked rows are inspected and corrected.

### 4. Map saved channels to approved handpicked markets

Batch AI mapping uses:

```bash
python3 scripts/map_handpicked_channels.py --market-limit 83 --batch-size 28 --min-confidence 0.80
```

This writes:

- `public.channel_market_map`

The main saved mapping source used right now is:

- `link_source = 'ai_handpicked_batch_v1'`

### 5. Run the real-time listener

Real-time listener uses TDLib update handlers, not history polling.

Runner:

```bash
python3 scripts/run_realtime_telegram_listener.py --link-source ai_handpicked_batch_v1
```

Core implementation:

- `src/polymarket/realtime_listener.py`

Important runtime behavior:

- watches only linked channels from the saved graph
- evaluates only the markets already linked to that channel
- stores messages first
- uses AI-only matching
- fail-closed on AI errors
- logs runtime events to `agent_runtime_events`

## Dashboard Pages

### Market and mapping review

- `/stored-markets`
  - grouped stored markets and their member markets
- `/handpicked-review`
  - review queue for low-confidence and unmatched handpicked rows
- `/saved-channel-map`
  - persisted channel-to-market graph from `channel_market_map`

### Live runtime validation

- `/telegram-live`
  - simple live page for recent messages, matches, activations, and listener heartbeat
- `/agent-runtime`
  - generic runtime telemetry page backed by `agent_runtime_status` and `agent_runtime_events`

## Prompt Files

### Channel mapping

- `configs/prompts/telegram_channel_mapper/system.txt`
- `configs/prompts/telegram_channel_mapper/user.txt`

### Live message matching

- `configs/prompts/telegram_live_message_matcher/system.txt`
- `configs/prompts/telegram_live_message_matcher/user.txt`

## Current Runtime Contract

The live listener is intentionally strict:

- runtime scope is the saved handpicked graph only
- AI failures do not create matches or activations
- every watched-channel text/caption message is stored
- only positive AI decisions create activation candidates

## Known Limitation As Of March 16, 2026

The listener process and dashboard are now in place, but live message flow is not fully proven yet.

Observed behavior:

- TDLib session exists and the listener can start
- the saved graph loads correctly
- runtime heartbeat is written correctly
- no fresh incoming channel message has yet been observed in `telegram_messages` during live validation

This means the remaining open question is operational, not architectural:

- either watched channels did not post during the validation window
- or this TDLib session is not receiving channel updates for those watched channels in real time

## Recommended Validation Sequence

1. Start the workspace dashboard.

```bash
python3 -m uvicorn src.workspace_dashboard.api:app --host 127.0.0.1 --port 8020
```

2. Start the listener worker.

```bash
AI_PROVIDER=openrouter \
OPENROUTER_API_KEY=... \
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1 \
OPENROUTER_MODEL=google/gemini-3-flash-preview \
python3 scripts/run_realtime_telegram_listener.py --link-source ai_handpicked_batch_v1
```

3. Open:

- `http://127.0.0.1:8020/telegram-live`

4. Compare the page against Telegram when one watched channel posts.

5. Confirm rows appear in:

- `public.telegram_messages`
- `public.message_market_matches`
- `public.market_activations`

## What Was Added In This Runtime Push

- grouped market storage
- handpicked market import + review layer
- saved channel-to-market graph visualization
- real-time TDLib listener path
- DB-backed live listener monitor
- OpenRouter-compatible AI mapping/matching path
