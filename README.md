# Polymarket News Agent

An AI-assisted research system that finds prediction markets on [Polymarket](https://polymarket.com) where **local news sources** may provide relevant evidence, then monitors those sources for reviewable signals.

**How it works in plain English:** The agent scans Polymarket for markets that could be resolved by local or niche news (for example, city council votes, regional weather events, or local elections). It discovers relevant Telegram channels, listens for new messages, and uses AI plus deterministic rules to classify possible evidence for human review.

> **Safety and scope:** the current repository is a research and monitoring
> system. Automated trade execution is not implemented. Model outputs can be
> wrong; verify source authenticity and market rules independently. Nothing in
> this repository is financial advice.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone & Install](#2-clone--install)
3. [Set Up Your Environment Variables](#3-set-up-your-environment-variables)
4. [Set Up the Database (Supabase)](#4-set-up-the-database-supabase)
5. [Run the Polymarket Market Explorer](#5-run-the-polymarket-market-explorer)
6. [Set Up Telegram Discovery](#6-set-up-telegram-discovery)
7. [Run the Workspace Dashboard](#7-run-the-workspace-dashboard)
8. [Run the Real-Time Listener](#8-run-the-real-time-listener)
9. [Deploy to EC2 (Optional)](#9-deploy-to-ec2-optional)
10. [Architecture Overview](#10-architecture-overview)
11. [Project Roadmap](#11-project-roadmap)

---

## 1. Prerequisites

Before you start, make sure you have the following installed and accounts created:

| Requirement | What it's for | How to get it |
|---|---|---|
| **Python 3.9+** | Runs everything | [python.org](https://www.python.org/downloads/) |
| **Git** | Version control | [git-scm.com](https://git-scm.com/) |
| **Supabase account** | Postgres database for storing markets, channels, and signals | [supabase.com](https://supabase.com/) (free tier works) |
| **Telegram API credentials** | Discovering and listening to Telegram channels | [my.telegram.org](https://my.telegram.org/) - create an app to get `api_id` and `api_hash` |
| **OpenAI-compatible API key** | AI classification and matching | [OpenAI](https://platform.openai.com/), [OpenRouter](https://openrouter.ai/), or any compatible provider |

Optional (for specific features):

| Requirement | What it's for |
|---|---|
| **SerpAPI or Serper key** | Google search for discovering official Telegram channels |
| **Polymarket CLOB API keys** | Placing actual trades (Phase 5 -- not yet implemented) |

---

## 2. Clone & Install

```bash
# Clone this repo
git clone https://github.com/takakhoo/Polymarket_Agent.git
cd Polymarket_Agent

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the package and all dependencies
pip install -e ".[dev]"
```

**Verify the install worked:**

```bash
python -c "import src; print('Install OK')"
```

---

## 3. Set Up Your Environment Variables

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Open `.env` in your editor. Here are the **must-fill** fields grouped by priority:

### Required for basic market browsing

```env
# Supabase -- get these from your Supabase project dashboard > Settings > API
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_DB_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres
DATABASE_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres
DIRECT_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres
```

### Required for AI classification

```env
# Use OpenAI, OpenRouter, or any OpenAI-compatible provider
OPENAI_API_KEY=sk-your-key-here
# If using OpenRouter, uncomment and set:
# OPENAI_BASE_URL=https://openrouter.ai/api/v1
```

### Required for Telegram features

```env
# Get these from https://my.telegram.org
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your-api-hash
TELEGRAM_PHONE_NUMBER=+1234567890
TELEGRAM_2FA_PASSWORD=           # leave blank if you don't use 2FA
```

Everything else can stay at its default value to start.

---

## 4. Set Up the Database (Supabase)

This creates all the tables the agent needs to store markets, channels, messages, and match results.

```bash
# Apply the database schema (run all three in order)
python3 scripts/init_supabase_schema.py --env-file .env --sql-file sql/001_init_market_intel_schema.sql
python3 scripts/init_supabase_schema.py --env-file .env --sql-file sql/002_grouped_markets.sql
python3 scripts/init_supabase_schema.py --env-file .env --sql-file sql/003_handpicked_market_targets.sql
```

**What this creates:** 10+ tables including `markets`, `market_outcomes`, `market_snapshots`, `telegram_channels`, `telegram_messages`, `message_market_matches`, and `market_activations`.

---

## 5. Run the Polymarket Market Explorer

This is the fastest way to see the system in action. No Telegram setup needed.

### Step A: Ingest markets from Polymarket

```bash
python3 scripts/ingest_markets.py --env-file .env
```

This pulls active/open markets from Polymarket's public API and stores them in your database. It fetches up to 2,000 markets by default.

### Step B: Run AI analysis on ingested markets

```bash
python3 scripts/analyze_markets.py --env-file .env
```

This classifies each market as having "local news edge" potential using your configured AI model.

### Step C: Launch the Polymarket dashboard

```bash
bash scripts/run_polymarket_dashboard.sh .env 8010
```

Open [http://localhost:8010](http://localhost:8010) in your browser. You can browse markets, sample random ones for review, and see the AI classifications.

---

## 6. Set Up Telegram Discovery

This lets the agent find Telegram channels relevant to each market.

### Step A: Run the preflight check

```bash
bash scripts/telegram_preflight.sh tdlib_discovery_only
```

This verifies your Telegram credentials and TDLib installation are working.

### Step B: Bootstrap your Telegram session

```bash
python3 scripts/telegram_session_bootstrap.py --env-file .env
```

This will prompt you for a login code sent to your Telegram app. You only need to do this once -- the session is saved locally.

### Step C: Launch the discovery dashboard

```bash
bash scripts/run_discovery_dashboard.sh .env 8000
```

Open [http://localhost:8000](http://localhost:8000). From here you can:
- Search for Telegram channels by keyword
- Expand discovery with "similar channels"
- Review channel relevance with AI scoring

---

## 7. Run the Workspace Dashboard

This is the **main control panel** that combines everything into one tabbed interface.

```bash
bash scripts/run_workspace_dashboard.sh .env .env 8020
```

Open [http://localhost:8020](http://localhost:8020).

### Available tabs and pages

| URL | What it does |
|---|---|
| `/` | Main dashboard with Telegram, Polymarket, Backtest, and Prompts tabs |
| `/market-rail` | High-speed market classification view |
| `/agent-runtime` | Live worker status and event log |
| `/stored-markets` | Browse grouped/stored markets |
| `/handpicked-review` | Review and approve hand-selected markets |
| `/saved-channel-map` | View the channel-to-market mapping graph |
| `/telegram-live` | Monitor the real-time Telegram listener |

---

## 8. Run the Real-Time Listener

Once you have markets selected and channels mapped, start the live listener:

### Step A: Build the grouped market scope

```bash
python3 scripts/rebuild_grouped_markets.py
```

### Step B: Import your handpicked markets

Create a text file with market names (one per line), then import:

```bash
python3 scripts/import_handpicked_markets.py handpicked.txt --apply-migration --replace-source
```

### Step C: Map Telegram channels to your markets

```bash
python3 scripts/map_handpicked_channels.py --market-limit 83 --batch-size 28 --min-confidence 0.80
```

### Step D: Start the real-time listener

```bash
python3 scripts/run_realtime_telegram_listener.py --link-source ai_handpicked_batch_v1
```

### Step E: Watch it work

Open [http://localhost:8020/telegram-live](http://localhost:8020/telegram-live) to see messages coming in and being matched against markets in real time.

---

## 9. Deploy to EC2 (Optional)

For always-on monitoring, deploy the workers to an AWS EC2 instance.

```bash
# On your EC2 instance:
bash scripts/ec2_prepare_host.sh

# Install as systemd services:
sudo bash scripts/install_ec2_services.sh /path/to/repo ubuntu .env .env
```

See the full runbook at `docs/runbooks/EC2_DEPLOYMENT.md`.

---

## 10. Architecture Overview

```
                    Polymarket APIs
                         |
                    [Market Ingest]
                         |
                    [AI Classifier] --- "Does this market have a local news edge?"
                         |
                   [Query Planner] --- "What Telegram channels might cover this?"
                         |
              [Channel Discovery] --- Search + Google SERP + Similar expansion
                         |
               [AI Channel Review] --- "Is this channel actually relevant?"
                         |
              [Channel-Market Map] --- Stored in DB
                         |
             [Real-Time Listener] --- TDLib watches mapped channels
                         |
             [AI Message Matcher] --- "Does this message affect the market?"
                         |
              [Alert / Activation] --- Signal stored, ready for action
```

### Key components

| Component | Location | Purpose |
|---|---|---|
| Polymarket clients | `src/polymarket/gamma_client.py`, `clob_public_client.py` | Pull market data from Polymarket APIs |
| Market ingest | `src/polymarket/market_ingest.py` | Batch-import markets into the database |
| Market analysis | `src/polymarket/market_analysis.py` | AI-driven local-edge classification |
| Telegram pipeline | `src/polymarket/telegram_pipeline.py` | Channel discovery + message listening |
| Channel relevance | `src/polymarket/channel_relevance.py` | AI scoring of channel-market fit |
| Real-time listener | `src/polymarket/realtime_listener.py` | Live TDLib message handler |
| LLM runtime | `src/polymarket/llm_runtime.py` | Unified AI inference interface |
| Discovery service | `src/discovery/service.py` | TDLib-backed channel search |
| Workspace dashboard | `src/workspace_dashboard/api.py` | FastAPI web UI |
| AI prompts | `configs/prompts/` | All prompt templates (editable) |
| SQL migrations | `sql/` | Database schema files |

---

## 11. Project Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 0: Foundation | Done | Repo structure, docs, config templates |
| Phase 1: Discovery + Market Retrieval | Done | Telegram discovery dashboard, Polymarket API clients |
| Phase 2: Telegram Intake Pipeline | Active | Real-time listener, message persistence, AI matching |
| Phase 3: Reliability Scoring | Planned | Rank channels by precision and lead time |
| Phase 4: Rule-Grounded Decision Engine | Planned | Map claims to market resolution rules |
| Phase 5: Polymarket Action Integration | Planned | Authenticated trading via CLOB API |
| Phase 6: Execution Guardrails | Planned | Position limits, kill switch, slippage checks |

---

## Running Tests

```bash
pytest tests/
```

---

## Project Structure

```
Polymarket_Agent/
├── configs/
│   ├── prompts/          # AI prompt templates (editable)
│   ├── markets/          # Market configuration
│   ├── risk/             # Risk parameters
│   └── sources/          # Source/env templates
├── data/                 # Local data storage
├── docs/                 # Documentation and runbooks
├── logs/                 # Runtime logs
├── scripts/              # CLI tools and shell scripts
├── sql/                  # Database migrations
├── src/
│   ├── discovery/        # TDLib channel discovery backend
│   ├── discovery_dashboard/  # Discovery web UI
│   ├── polymarket/       # Core market + Telegram pipeline logic
│   ├── polymarket_dashboard/ # Market explorer web UI
│   └── workspace_dashboard/  # Main unified dashboard
└── tests/                # Test suite
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Make sure you ran `pip install -e ".[dev]"` inside your venv |
| Telegram auth fails | Re-run `scripts/telegram_session_bootstrap.py` -- your session may have expired |
| TDLib not found | Install TDLib for your OS: [tdlib.github.io](https://tdlib.github.io/td/build.html) |
| Supabase connection refused | Check your `DATABASE_URL` in `.env` -- make sure the password is URL-encoded |
| AI classification returns errors | Verify your `OPENAI_API_KEY` and `OPENAI_BASE_URL` are correct |
| Dashboard won't start | Check if the port is already in use: `lsof -i :8020` |

---

## License

This project is for educational and research purposes.

---

*Built with FastAPI, TDLib, Supabase, and OpenAI-compatible LLMs.*
