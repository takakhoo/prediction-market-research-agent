# Roadmap

## Phase 0: Foundation (completed)

Objective: enforce organization, docs, and configuration scaffolding.

Deliverables:
1. Workspace structure and standards.
2. Telegram API decision doc.
3. Seed/source and risk config templates.

## Phase 1: Discovery + Market Retrieval Foundation (current)

Objective: establish reliable source discovery and market visibility.

Deliverables:
1. TDLib-backed channel discovery dashboard.
2. Similar-channel expansion workflow.
3. Local watchlist with trust/tags/notes.
4. Polymarket market retrieval client and scripts.
5. Polymarket action-readiness/preflight checks.

## Phase 2: Telegram Intake Pipeline (active)

Objective: ingest monitored channels continuously with normalized event output.

Deliverables:
1. Saved-graph scoped Telegram listener.
2. Real-time message persistence into DB.
3. AI-only message-to-market matching on linked markets.
4. Simple runtime monitor for live validation.

## Phase 3: Reliability Scoring

Objective: rank channels by precision, lead time, and noise.

Deliverables:
1. Candidate promotion thresholds.
2. Reliability score computation.
3. Derived analytics persisted to `data/derived/`.

## Phase 4: Rule-Grounded Decision Engine

Objective: map incoming claims to market resolution rules.

Deliverables:
1. Market context pack schema.
2. Structured classification output.
3. Alert-only workflow.

## Phase 5: Polymarket Action Integration

Objective: authenticated market actions via CLOB client layer.

Deliverables:
1. L1/L2 auth handling.
2. Order placement/cancel/status wrappers.
3. Deterministic safety gates before live actions.

## Phase 6: Execution Guardrails

Objective: deterministic risk-gated execution.

Deliverables:
1. Position limits and kill switch.
2. Slippage and liquidity checks.
3. Small-size auto execution policy.
