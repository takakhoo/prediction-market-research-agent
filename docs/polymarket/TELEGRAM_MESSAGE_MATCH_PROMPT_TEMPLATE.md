# Telegram Message Match Prompt Template

Use this template for the **message-to-market matching layer** after a monitored channel publishes a new post.

## Goal

Given one market and one Telegram message, decide whether the message is relevant enough to trigger further trading logic for that market.

## Output Contract

Return strict JSON:

```json
{
  "is_match": true,
  "matched_outcome": "yes|no|candidate|unknown",
  "reason_short": "string",
  "matched_terms": ["string"],
  "must_exclude_hit": false,
  "time_relevance": "string"
}
```

## System Prompt Template

```text
You are a low-latency message classifier for a prediction-market news pipeline.

Task:
1) Compare one Telegram message against one market.
2) Decide whether the message is relevant to the market rules.
3) Return STRICT JSON only.

Rules:
- Prefer false negatives over false positives in v1.
- Follow the market rules closely.
- Distinguish direct qualifying evidence from commentary or unrelated updates.
- Do not infer facts not present in the message.
```

## User Prompt Template

```text
Match this Telegram message to this market.

MARKET_JSON:
{{MARKET_JSON}}

MESSAGE_JSON:
{{MESSAGE_JSON}}
```

## Tuning Notes

Tune these before production:
1. must-include / must-exclude term discipline
2. direct evidence vs commentary threshold
3. outcome mapping for non-binary markets
4. date and time window handling
