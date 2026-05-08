# Polymarket Setup Steps

This runbook covers market retrieval and action-readiness checks.

## 1) Configure environment

1. Copy `configs/sources/polymarket_runtime.template.env` to your local runtime env file.
2. For read-only market discovery, no private key is required.

## 2) Preflight

Read-only:
```bash
bash scripts/polymarket_preflight.sh read_only configs/sources/polymarket_runtime.template.env
```

Trading readiness:
```bash
bash scripts/polymarket_preflight.sh trading configs/sources/polymarket_runtime.template.env
```

## 3) Retrieve markets

```bash
python3 scripts/polymarket_markets.py --env-file configs/sources/polymarket_runtime.template.env list --limit 25
```

## 4) Show one market

By id:
```bash
python3 scripts/polymarket_markets.py --env-file configs/sources/polymarket_runtime.template.env show --market-id <market_id>
```

By slug:
```bash
python3 scripts/polymarket_markets.py --env-file configs/sources/polymarket_runtime.template.env show --slug <slug>
```

## 5) Check action/trading requirements

```bash
python3 scripts/polymarket_markets.py --env-file configs/sources/polymarket_runtime.template.env actions
```

## 6) Visualize market discovery step

Start dashboard:
```bash
bash scripts/run_polymarket_dashboard.sh configs/sources/polymarket_runtime.template.env 8010
```

Open:
`http://127.0.0.1:8010`

In UI:
1. Step A: load market JSON and inspect table + raw payload.
2. Step B: sample random markets (default 10) from a selected pool size.

## 7) Initialize Supabase schema (market intelligence pipeline)

Apply the Postgres schema migration (10 core tables):

```bash
python3 scripts/init_supabase_schema.py --env-file .env --sql-file sql/001_init_market_intel_schema.sql
```

Notes:
1. Use direct DB URL for migrations (`SUPABASE_DIRECT_DB_URL` or `DIRECT_URL`).
2. If you must run via pooler URL, use `--pooled`.

## 8) Ingest active/open markets into Postgres

One run:
```bash
python3 scripts/ingest_markets.py --env-file .env
```

Faster smoke test:
```bash
python3 scripts/ingest_markets.py --env-file .env --page-limit 50 --max-pages 1
```

Continuous polling:
```bash
python3 scripts/ingest_markets.py --env-file .env --watch --interval-seconds 60
```

Behavior:
1. Pulls only `active=true` and `closed=false` markets.
2. Upserts market metadata + outcomes.
3. Appends market snapshots for time-series analysis.
4. Flags likely/unlikely outcomes and high-competition markets.

## 9) Analyze local-edge candidates and write `market_analysis`

One run:
```bash
python3 scripts/analyze_markets.py --env-file .env --limit 100
```

Continuous polling:
```bash
python3 scripts/analyze_markets.py --env-file .env --watch --interval-seconds 60 --limit 100
```

Behavior:
1. Reads only active/open markets that have no analysis yet or changed `rules_hash`.
2. Computes a deterministic local-edge classification (`track_now|track_later|ignore`).
3. Writes analysis rows into `market_analysis`.
4. Updates `markets.is_local_candidate`, `markets.local_score`, and `markets.local_reason_json`.

## 10) Discover Telegram channels for `track_now` markets

One run:
```bash
python3 scripts/discover_channels.py \
  --env-file .env \
  --env-file configs/sources/telegram_runtime.template.env
```

Continuous polling:
```bash
python3 scripts/run_telegram_market_agent.py \
  --env-file .env \
  --env-file configs/sources/telegram_runtime.template.env \
  --discover-interval-seconds 120 \
  --listen-interval-seconds 8
```

## 11) Listen to mapped Telegram channels and evaluate matches

One run:
```bash
python3 scripts/listen_telegram_messages.py \
  --env-file .env \
  --env-file configs/sources/telegram_runtime.template.env
```

Note:
For continuous operation, prefer `run_telegram_market_agent.py` so discovery and listener reuse one TDLib session.
