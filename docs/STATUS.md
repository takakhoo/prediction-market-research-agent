# Status

## Current Phase

Phase 1: Telegram Discovery Dashboard MVP + Polymarket Market Retrieval Foundation

## Completed

1. Repository skeleton and standards docs.
2. Telegram reference docs and setup runbook.
3. Runtime env template expanded for `tdlib_discovery_only`.
4. Preflight script updated for discovery-only mode.
5. TDLib session bootstrap script added (`scripts/telegram_session_bootstrap.py`).
6. Discovery backend scaffold added:
   - `src/discovery/config.py`
   - `src/discovery/db.py`
   - `src/discovery/repository.py`
   - `src/discovery/tdlib_client.py`
   - `src/discovery/service.py`
   - `src/discovery/api.py`
7. Discovery dashboard templates added under `src/discovery_dashboard/templates/`.
8. API + repository + preflight tests added under `tests/`.
9. Discovery MVP runbook added (`docs/telegram/DISCOVERY_DASHBOARD_MVP.md`).
10. Polymarket retrieval code added:
    - `src/polymarket/config.py`
    - `src/polymarket/http.py`
    - `src/polymarket/gamma_client.py`
    - `src/polymarket/clob_public_client.py`
    - `src/polymarket/actions.py`
11. Polymarket operational scripts added:
    - `scripts/polymarket_markets.py`
    - `scripts/polymarket_preflight.sh`
12. Polymarket env template added (`configs/sources/polymarket_runtime.template.env`).
13. Polymarket docs added under `docs/polymarket/`.
14. Polymarket tests added:
    - `tests/test_polymarket_clients.py`
    - `tests/test_polymarket_preflight.py`
15. Polymarket discovery visualization added:
    - `src/polymarket/discovery_service.py`
    - `src/polymarket_dashboard/api.py`
    - `src/polymarket_dashboard/templates/`
    - `scripts/run_polymarket_dashboard.sh`
    - `tests/test_polymarket_discovery_service.py`
16. Telegram read-only safety and probe tooling added:
    - `TELEGRAM_READ_ONLY_MODE` support in discovery settings.
    - TDLib allowlist guard in `src/discovery/tdlib_client.py`.
    - Read-only probe script: `scripts/telegram_readonly_probe.py`.
    - Read-only guard tests: `tests/test_tdlib_readonly_guard.py`.
17. Unified tabbed workspace dashboard added:
    - `src/workspace_dashboard/api.py`
    - `src/workspace_dashboard/templates/dashboard.html`
    - `scripts/run_workspace_dashboard.sh`
    - Telegram and Polymarket templates updated to support mounted subpaths.
18. Supabase/Postgres market-intelligence schema scaffolding added:
    - `sql/001_init_market_intel_schema.sql`
    - `scripts/init_supabase_schema.py`
    - Prompt template: `docs/polymarket/LOCAL_MARKET_PROMPT_TEMPLATE.md`
19. Market ingest pipeline scaffold added:
    - `src/polymarket/market_intel_repository.py`
    - `src/polymarket/market_ingest.py`
    - `scripts/ingest_markets.py`
    - tests: `tests/test_market_ingest_service.py`
20. Live Supabase validation completed:
    - Schema applied to Supabase `public` (10 tables).
    - Ingest worker executed successfully against live Gamma data.
    - Verified row writes in `markets`, `market_outcomes`, and `market_snapshots`.
21. Market analysis pipeline scaffold added:
    - `src/polymarket/market_analysis.py`
    - repository methods for pending analysis fetch + analysis writes
    - `scripts/analyze_markets.py`
    - tests: `tests/test_market_analysis_service.py`
22. Telegram-to-market pipeline workers added:
    - `src/polymarket/telegram_pipeline.py`
    - repository methods for `telegram_channels`, `channel_market_map`, `telegram_messages`, `message_market_matches`, `market_activations`
    - `scripts/discover_channels.py`
    - `scripts/listen_telegram_messages.py`
    - `scripts/run_telegram_market_agent.py` (shared TDLib session for discovery + listener loops)
    - `scripts/run_news_agent_stack.sh`
    - tests: `tests/test_telegram_pipeline.py`
23. EC2 deployment runbook and automation scripts added:
    - `docs/runbooks/EC2_DEPLOYMENT.md`
    - `scripts/ec2_prepare_host.sh`
    - `scripts/install_ec2_services.sh`
24. AI runtime and prompt-config plumbing added across market analysis + Telegram discovery:
    - `src/polymarket/llm_runtime.py`
    - `src/polymarket/config.py` (`AI_*` env support)
    - prompt templates under `docs/polymarket/`
25. Channel relevance module and discovery gating added:
    - `src/polymarket/channel_relevance.py`
    - discovery + backtest integration in `src/polymarket/telegram_pipeline.py`
    - tests: `tests/test_channel_relevance.py`
26. Backtest and prompt management UI/pages added to workspace dashboard:
    - `src/workspace_dashboard/templates/backtest.html`
    - `src/workspace_dashboard/templates/prompt_lab.html`
    - API wiring in `src/workspace_dashboard/api.py`
    - tests: `tests/test_workspace_dashboard_api.py`
27. Stepwise Telegram backtest trace implemented:
    - local classifier prompt/output stage
    - query planner prompt/output stage
    - per-query and per-similar channel decision traces
    - per-channel AI review with recent-message context
28. Discovery workflow doc with Mermaid flow added:
    - `docs/telegram/CHANNEL_DISCOVERY_WORKFLOW.md`
29. Telegram backtest persistence added:
    - full backtest payload snapshots stored in `telegram_backtest_runs`
    - repository APIs for save/list/get run history
    - workspace API endpoints:
      - `GET /api/intel/telegram-backtest/runs`
      - `GET /api/intel/telegram-backtest/runs/{run_id}`
30. Runtime prompt files are now source-of-truth under `configs/prompts/*`:
    - local market classifier
    - telegram query planner
    - telegram channel reviewer
    - telegram message matcher
31. Google SERP bootstrap path integrated for official Telegram channel harvesting:
    - `src/polymarket/google_serp.py`
    - `run_telegram_market_agent.py --enable-google-serp ...`
    - planner now emits `site:t.me` query set consumed by runtime discovery.
32. Workspace dashboard expansion:
    - market rail view (`/market-rail`) for high-speed manual classification
    - agent runtime page (`/agent-runtime`) for live worker status + event log
    - richer backtest UI components under `src/workspace_dashboard/templates/backtest/`
33. Telegram agent runtime telemetry persisted to DB:
    - heartbeat/status snapshots via `agent_runtime_status`
    - structured runtime events via `agent_runtime_events`
    - used by dashboard live status pages.
34. Storage controls added to reduce DB pressure:
    - `MARKET_STORE_SNAPSHOTS` defaults false in runtime templates
    - `scripts/compact_market_storage.py` for controlled cleanup (snapshots/outcomes/analysis history).
35. Optional AI message matcher added for listener pipeline:
    - `MarketMessageMatcher` now supports prompt-driven JSON inference
    - dedicated runtime prompts under `configs/prompts/telegram_message_matcher/`
    - feature flag: `AI_ENABLE_MESSAGE_MATCHER` (fallback to heuristic remains default-safe)
    - OpenRouter-compatible endpoint/header env support for matcher-specific provider config.
36. Grouped market scope and handpicked review workflow added:
    - `sql/002_grouped_markets.sql`
    - `sql/003_handpicked_market_targets.sql`
    - `scripts/rebuild_grouped_markets.py`
    - `scripts/import_handpicked_markets.py`
    - grouped market review pages:
      - `src/workspace_dashboard/templates/stored_markets.html`
      - `src/workspace_dashboard/templates/handpicked_review.html`
37. Saved channel-to-market graph workflow added for approved handpicked markets:
    - `scripts/map_handpicked_channels.py`
    - channel mapping prompts under `configs/prompts/telegram_channel_mapper/`
    - saved graph page:
      - `src/workspace_dashboard/templates/saved_channel_map.html`
38. Workspace dashboard expanded with stored-market, saved-graph, and handpicked review views:
    - `src/workspace_dashboard/templates/pipeline_map.html`
    - `src/workspace_dashboard/templates/stored_markets.html`
    - `src/workspace_dashboard/templates/saved_channel_map.html`
    - `src/workspace_dashboard/templates/handpicked_review.html`
    - API wiring in `src/workspace_dashboard/api.py`
39. Real-time Telegram listener path added on top of saved handpicked links:
    - `src/polymarket/realtime_listener.py`
    - `scripts/run_realtime_telegram_listener.py`
    - prompt files under `configs/prompts/telegram_live_message_matcher/`
    - TDLib event-handler wrappers added to `src/discovery/tdlib_client.py`
40. Live listener monitor page added:
    - `src/workspace_dashboard/templates/telegram_live.html`
    - `/api/intel/telegram-live`
    - DB-backed view over `telegram_messages`, `message_market_matches`, `market_activations`, and runtime telemetry

## In Progress

1. First live end-to-end verification that `updateNewMessage` events from watched channels are landing in `telegram_messages`.
2. Runtime hardening for the new real-time listener process lifecycle.
3. Prompt tuning and calibration for local-edge classification, channel mapping, and live message match quality.
4. End-to-end production validation for the narrowed handpicked runtime instead of the old broad market universe.

## Next Actions

1. Confirm the real-time listener receives at least one live watched-channel post and persists it end to end.
2. Distinguish whether empty live flow is caused by low posting frequency or TDLib session/update-delivery issues.
3. Add stronger stale-runtime signaling so an old heartbeat is never mistaken for a healthy worker.
4. After live intake is proven, tune message-match precision on real traffic.
5. Use the saved handpicked graph as the paper-trading input funnel.
6. Implement Polymarket authenticated action client (order placement/cancel/status) after key provisioning.
