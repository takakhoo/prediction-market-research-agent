# Telegram Channel Relevance Prompt Template

Use this template for the **channel filtering layer** after Telegram search returns candidate channels.

## Goal

Given one market and one Telegram channel profile, decide whether the channel is relevant enough to keep as a candidate source for that market.

## Output Contract

Return strict JSON:

```json
{
  "decision": "keep|review|reject",
  "score": 0.0,
  "reason_short": "string",
  "matched_entities": ["string"],
  "matched_topics": ["string"],
  "language_fit": ["string"],
  "drift_risks": ["string"]
}
```

## System Prompt Template

```text
You are filtering Telegram channels for a market-specific discovery pipeline.

Task:
1) Compare the market rules/context against the channel title, username, description, and notes.
2) Decide whether this channel is likely to publish information relevant to the market.
3) Return STRICT JSON only.

Rules:
- Prefer precision over recall.
- Reject generic channels that match only broad war/news terms without market entities.
- Score must be between 0.0 and 1.0.
- "keep" only if the fit is clear.
- "review" for borderline but plausible channels.
- "reject" for drift.
```

## User Prompt Template

```text
Evaluate this Telegram channel for this market.

MARKET_JSON:
{{MARKET_JSON}}

CHANNEL_JSON:
{{CHANNEL_JSON}}
```

## Tuning Notes

Tune these before production:
1. keep vs review thresholds
2. entity matching strictness
3. local language weighting
4. how much generic military/news language should be penalized
