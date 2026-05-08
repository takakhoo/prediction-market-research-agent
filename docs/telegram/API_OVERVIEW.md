# Telegram API Overview for This Project

## Why This Matters

Discovery is the bottleneck for this project. If you want to find channels programmatically, you need client API capabilities.

## Option A: Bot API

Use when:
1. You already know channels.
2. Channels can add your bot.
3. You only need controlled monitoring.

Pros:
1. Fast setup.
2. Simple auth.
3. Lower operational complexity.

Limits:
1. Weak discovery capabilities.
2. Not suitable for broad public-channel discovery.

## Option B: MTProto/TDLib Client

Use when:
1. You need public search/discovery workflows.
2. You want similar-channel graph expansion.
3. You can manage local session/auth state.

Pros:
1. Supports discovery endpoints.
2. Supports message preview and richer chat metadata.

Limits:
1. More setup complexity.
2. Session lifecycle management required.

## Current MVP Decision

Phase 1 discovery dashboard uses:
1. `tdlib_discovery_only`
2. FastAPI + Jinja/HTMX UI
3. SQLite watchlist and discovery run persistence

Core methods used:
1. `searchPublicChats`
2. `searchPublicChat`
3. `getChatHistory`
4. `getChatSimilarChats`

## Data Contracts (MVP)

Persisted tables:
1. `channels`
2. `channel_messages`
3. `watchlist`
4. `discovery_runs`
5. `similar_edges`

See `docs/telegram/DISCOVERY_DASHBOARD_MVP.md` for endpoint-level details.
