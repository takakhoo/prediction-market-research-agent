# Prompt Runtime Files

Runtime prompts are now loaded from editable files under:

- `configs/prompts/local_market/`
- `configs/prompts/telegram_query_planner/`
- `configs/prompts/telegram_channel_reviewer/`
- `configs/prompts/telegram_message_matcher/`

## Files

1. `configs/prompts/local_market/system.txt`
2. `configs/prompts/local_market/user.txt`
3. `configs/prompts/telegram_query_planner/system.txt`
4. `configs/prompts/telegram_query_planner/user.txt`
5. `configs/prompts/telegram_channel_reviewer/system.txt`
6. `configs/prompts/telegram_channel_reviewer/user.txt`
7. `configs/prompts/telegram_message_matcher/system.txt`
8. `configs/prompts/telegram_message_matcher/user.txt`

## Placeholders

- `{{MARKET_JSON}}` for market classifier + query planner user prompts
- `{{MAX_QUERIES}}` for query planner user prompt
- `{{INPUT_JSON}}` for channel reviewer user prompt
- `{{MARKET_ID}}`, `{{MARKET_ARCHETYPE}}`, `{{QUESTION}}`, `{{RULES_TEXT}}`, `{{MARKET_CONTEXT}}`, `{{MESSAGE_TEXT}}` for message matcher prompt

## Optional Override

Set `PROMPTS_DIR` in env if you want prompts loaded from a different directory.

Example:

```bash
PROMPTS_DIR=configs/prompts
```

## Message Matcher Runtime Toggle

Telegram message matching now supports prompt-driven AI classification (optional) with a safe fallback:

- `AI_ENABLE_MESSAGE_MATCHER=true` enables AI matching.
- `AI_TELEGRAM_MESSAGE_MATCHER_MODEL` selects the model.
- If AI is unavailable, runtime falls back to deterministic heuristic matching (no listener crash).

OpenRouter-compatible settings are supported via:

- `AI_MESSAGE_MATCHER_API_KEY`
- `AI_MESSAGE_MATCHER_BASE_URL`
- `AI_MESSAGE_MATCHER_HTTP_REFERER`
- `AI_MESSAGE_MATCHER_APP_NAME`
