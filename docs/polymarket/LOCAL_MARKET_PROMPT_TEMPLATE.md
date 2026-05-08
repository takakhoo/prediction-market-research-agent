# Local Market Classification Prompt Template

Use this template for the **first-step market classifier** that decides whether a market has local-information edge.

## Goal

Given Polymarket market metadata and rules, output a strict JSON decision for:
1. whether to track,
2. why it is or is not local-edge,
3. what languages/regions/channels are likely useful.

## Recommended Model Behavior

1. Prefer **precision** over recall in v1.
2. Treat only markets with `active=true` and `closed=false` as trackable.
3. Do not infer unsupported facts. If unclear, mark uncertainty explicitly.
4. Focus on **information asymmetry**:
   - local witnesses,
   - local official channels,
   - local-language reporting lead time.

## Input Schema

```json
{
  "market_id": "string",
  "slug": "string",
  "question": "string",
  "description": "string|null",
  "rules_text": "string|null",
  "market_context": "string|null",
  "active": true,
  "closed": false,
  "archived": false,
  "end_date": "ISO8601|null",
  "outcomes": [
    {"index": 0, "label": "Yes", "price": 0.16},
    {"index": 1, "label": "No", "price": 0.84}
  ],
  "volume_usd": 218745.0,
  "liquidity_usd": 12345.0,
  "event_metadata": {
    "event_id": "string|null",
    "event_slug": "string|null",
    "category": "string|null"
  }
}
```

## Output Schema (Strict JSON)

```json
{
  "track_decision": "track_now|track_later|ignore",
  "is_local_candidate": true,
  "local_score": 0.0,
  "market_archetype": "binary_oneoff|binary_recurring|binary_deadline_series|categorical_group|scalar|unknown",
  "competition_flag": {
    "high_competition": false,
    "reason": "volume_below_threshold"
  },
  "price_flags": [
    {"outcome_index": 0, "label": "Yes", "probability": 0.16, "flag": "unlikely"},
    {"outcome_index": 1, "label": "No", "probability": 0.84, "flag": "likely"}
  ],
  "edge_hypothesis": "string",
  "priority_regions": ["string"],
  "priority_languages": ["ar", "he", "en", "fa", "es"],
  "channel_profiles_needed": [
    "official_military",
    "local_journalists",
    "community_alerts"
  ],
  "match_focus": {
    "must_include": ["string"],
    "must_exclude": ["string"],
    "time_window_notes": "string"
  },
  "reason_short": "string",
  "reason_detailed": ["string"]
}
```

## System Prompt Template

```text
You are a market-intelligence classifier for a speed-sensitive news pipeline.

Task:
1) Classify whether this market has local-information edge.
2) Classify market archetype.
3) Provide language/region/channel profile guidance.
4) Return STRICT JSON only following the provided output schema.

Rules:
- Prefer precision over recall.
- If active=false or closed=true -> track_decision must be "ignore".
- local_score must be between 0.0 and 1.0.
- price_flags must evaluate each outcome using:
  likely if probability >= 0.75
  unlikely if probability <= 0.25
  neutral otherwise
- high_competition true if volume_usd >= 5000000.
- Do not invent facts not present in market data.
- Keep reason_short concise (<= 160 chars).
```

## User Prompt Template

```text
Classify this market for local-edge tracking.

INPUT_JSON:
{{MARKET_JSON}}
```

## First-pass Rubric

Use this mental rubric when tuning:
1. Is outcome likely to be known first by local actors before global media?
2. Are there known local-language channels with faster signal flow?
3. Are rule conditions observable in near-real-time (vs slow institutional data)?
4. Is there enough rule clarity to build deterministic message matching?

## Notes For Your Tweaks

Start by tuning:
1. `track_decision` thresholds.
2. `local_score` interpretation bands.
3. `must_include` / `must_exclude` keyword discipline.
4. region/language expansion beyond `ar, he, en, fa, es`.
