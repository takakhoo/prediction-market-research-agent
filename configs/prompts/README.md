# Runtime Prompts

This folder is the editable source of truth for AI runtime prompts used by:

- market local classifier
- Telegram query planner
- Telegram backtest channel reviewer

You can edit these files directly without changing Python code.

## Structure

- `local_market/system.txt`
- `local_market/user.txt`
- `telegram_query_planner/system.txt`
- `telegram_query_planner/user.txt`
- `telegram_channel_reviewer/system.txt`
- `telegram_channel_reviewer/user.txt`

## Template Placeholders

- `{{MARKET_JSON}}`
- `{{MAX_QUERIES}}`
- `{{INPUT_JSON}}`

If `PROMPTS_DIR` is set in env, runtime loads prompts from that directory instead.
Otherwise it uses this folder: `configs/prompts`.
