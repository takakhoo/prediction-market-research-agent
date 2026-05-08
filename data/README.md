# Data Zones

1. `data/raw/`: immutable source payloads.
2. `data/normalized/`: cleaned and translated records.
3. `data/derived/`: features, scores, and evaluation artifacts.

Rules:
1. Never modify records in `data/raw/`.
2. Keep source references (`event_id`, `source_message_id`) in all derived records.
