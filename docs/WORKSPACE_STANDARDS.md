# Workspace Standards

## Goal

Keep the project operationally clean while building fast.

## Folder Responsibilities

- `docs/`: decisions, plans, setup notes, runbooks.
- `configs/`: source lists, market definitions, risk limits, templates.
- `src/`: code only (ingestion, discovery, scoring, execution).
- `scripts/`: runnable entrypoints and maintenance utilities.
- `data/raw/`: immutable ingested payloads.
- `data/normalized/`: translated/parsed records.
- `data/derived/`: analytics outputs (scores, backtests, reports).
- `logs/`: runtime logs and job traces.

## Naming and Versioning

1. Use snake_case for filenames.
2. Prefer one responsibility per file.
3. Keep templates in `configs/*/*.template.yaml`.
4. Do not store secrets in repo; use environment variables.

## Change Protocol

For each task:
1. Add/update relevant config template.
2. Implement code.
3. Record status update in `docs/STATUS.md`.
4. If architecture changed, document it in `docs/ROADMAP.md`.

## Non-Negotiables

1. No direct execution from model outputs without deterministic gates.
2. No silent schema changes in data files.
3. No new top-level folders unless documented here first.
