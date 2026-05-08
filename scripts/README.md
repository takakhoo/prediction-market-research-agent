# Scripts

Operational scripts live here.

## Current Scripts

1. `telegram_preflight.sh`
   - Validates env for modes: `bot_api_only`, `bot_api_plus_tdlib_stub`, `tdlib_discovery_only`.
2. `telegram_session_bootstrap.py`
   - Performs one-time TDLib login bootstrap and writes local session marker for dashboard use.
3. `run_discovery_dashboard.sh`
   - Runs preflight, loads env file, and starts the dashboard server.
   - Usage: `bash scripts/run_discovery_dashboard.sh [env_file] [port]`
4. `telegram_readonly_probe.py`
   - Runs a safe read-only Telegram probe: search public channels, inspect recent messages, and fetch similar channels.
   - Usage: `python3 scripts/telegram_readonly_probe.py --env-file configs/sources/telegram_runtime.template.env --query "israel lebanon"`
5. `polymarket_markets.py`
   - Lists markets, shows market details, and reports action/trading readiness.
6. `polymarket_preflight.sh`
   - Validates Polymarket env for `read_only` or `trading` mode.
7. `run_polymarket_dashboard.sh`
   - Runs Polymarket read-only preflight, loads env file, and starts the Polymarket discovery dashboard.
   - Usage: `bash scripts/run_polymarket_dashboard.sh [env_file] [port]`
8. `run_workspace_dashboard.sh`
   - Runs Telegram + Polymarket preflight checks, loads both env files, and starts a tabbed workspace UI with both dashboards.
   - Usage: `bash scripts/run_workspace_dashboard.sh [telegram_env_file] [polymarket_env_file] [port] [host]`
   - Example (EC2/public bind): `bash scripts/run_workspace_dashboard.sh /etc/polymarket-news-agent/telegram.env /etc/polymarket-news-agent/.env 8020 0.0.0.0`
9. `init_supabase_schema.py`
   - Applies the Postgres schema migration to Supabase from SQL file.
   - Usage: `python3 scripts/init_supabase_schema.py --env-file .env --sql-file sql/001_init_market_intel_schema.sql`
10. `ingest_markets.py`
   - Pulls active/open markets from Gamma and upserts normalized market/outcome/snapshot rows into Postgres.
   - Usage:
     - One run: `python3 scripts/ingest_markets.py --env-file .env`
     - Watch mode: `python3 scripts/ingest_markets.py --env-file .env --watch --interval-seconds 60`
     - Bounded run (faster test): `python3 scripts/ingest_markets.py --env-file .env --page-limit 50 --max-pages 1`
     - URL-source run (scrape page event slugs, then ingest those events): `python3 scripts/ingest_markets.py --env-file .env --source-url https://polymarket.com/geopolitics --source-url https://polymarket.com/predictions/israel --source-url "https://polymarket.com/search?_q=iran"`
11. `analyze_markets.py`
   - Reads pending active/open markets from Postgres and writes local-edge classification rows into `market_analysis`.
   - Usage:
     - One run: `python3 scripts/analyze_markets.py --env-file .env --limit 100`
     - Watch mode: `python3 scripts/analyze_markets.py --env-file .env --watch --interval-seconds 60 --limit 100`
12. `discover_channels.py`
   - For `track_now` markets, runs Telegram discovery (search + similar) and upserts `telegram_channels` and `channel_market_map`.
   - Usage:
     - One run: `python3 scripts/discover_channels.py --env-file .env`
     - Watch mode: `python3 scripts/discover_channels.py --env-file .env --watch --interval-seconds 120`
13. `listen_telegram_messages.py`
   - Polls mapped Telegram channels, stores messages, evaluates market-rule matches, and writes first activation rows.
   - Usage:
     - One run: `python3 scripts/listen_telegram_messages.py --env-file .env`
     - Watch mode: `python3 scripts/listen_telegram_messages.py --env-file .env --watch --interval-seconds 8`
14. `run_telegram_market_agent.py`
   - Single-process Telegram agent that runs channel discovery and message listening on separate intervals while sharing one TDLib client/session.
   - Usage:
     - `python3 scripts/run_telegram_market_agent.py --env-file .env --env-file configs/sources/telegram_runtime.template.env`
     - Smoke test once: `python3 scripts/run_telegram_market_agent.py --env-file .env --env-file configs/sources/telegram_runtime.template.env --once`
     - Enable Google SERP official-channel bootstrap (requires `SERPER_API_KEY` or `SERPAPI_API_KEY`):
       `python3 scripts/run_telegram_market_agent.py --env-file .env --once --enable-google-serp --max-google-queries-per-market 8 --google-results-per-query 8`
   - Notes:
     - `AUTH_KEY_DUPLICATED` means the same TDLib auth key/session is active in another process/host.
     - Keep one owner per `TELEGRAM_SESSION_DIR` (or bootstrap separate session dirs per runtime).
15. `run_news_agent_stack.sh`
   - Starts market workers together (ingest, analysis, unified Telegram agent) and keeps them supervised in one terminal.
   - Usage:
     - `bash scripts/run_news_agent_stack.sh .env`
     - `bash scripts/run_news_agent_stack.sh .env configs/sources/telegram_runtime.template.env`
16. `ec2_prepare_host.sh`
   - Installs host dependencies, creates `.venv`, installs Python dependencies, and prepares runtime dirs on Amazon Linux 2023.
   - Usage: `bash scripts/ec2_prepare_host.sh`
17. `install_ec2_services.sh`
   - Installs/updates `systemd` services for always-on workers (ingest, analyze, telegram agent).
   - Usage:
     - `sudo bash scripts/install_ec2_services.sh <repo_dir> <run_user> <db_env_file> <telegram_env_file> [dashboard_port]`
   - Also installs `workspace-dashboard.service` (binds to `0.0.0.0:<dashboard_port>`).
18. `compact_market_storage.py`
   - Reclaims DB space by truncating `market_snapshots`, optionally truncating `market_outcomes`, and/or compacting `market_analysis` to latest-per-market.
   - Usage:
     - Dry run: `python3 scripts/compact_market_storage.py --env-file .env --truncate-snapshots`
     - Apply: `python3 scripts/compact_market_storage.py --env-file .env --truncate-snapshots --compact-analysis-latest --apply`

## Script Standards

Each new script should support:
1. `--help` (for Python scripts)
2. explicit input/output behavior
3. deterministic logging or error output
