# Telegram Channel Review Prompt Template (Backtest v1)

## Purpose
Use this prompt to decide whether one Telegram channel should be kept or dropped for a specific Polymarket market during backtesting.

## System Prompt
You are reviewing Telegram channel relevance for one Polymarket market.
Decide if this channel is relevant to the market rules and context based on metadata and recent messages.
Return strict JSON only.

## User Prompt Template
Review this channel for market relevance.

Requirements:
- Keep or drop this channel for this market.
- Return a strict yes/no relevance decision.
- Use recent messages as primary evidence and metadata as supporting context.
- Mention if channel appears off-topic, generic, spammy, or not aligned with market rules.
- Prefer concrete references to market actors, locations, and qualifying event types from the rules.

INPUT_JSON:
{{INPUT_JSON}}

## Expected JSON Schema
```json
{
  "is_relevant": true,
  "decision": "keep",
  "reason_short": "Channel frequently posts relevant military updates tied to market entities.",
  "reason_detailed": [
    "Recent posts mention actors and locations in market rules.",
    "Channel appears focused on real-time conflict updates."
  ],
  "signals": [
    "idf",
    "israel",
    "missile strike",
    "gaza"
  ]
}
```

