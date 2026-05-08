# Source Code Layout

Use these module boundaries:

1. `src/ingestion/`: source connectors and raw-event writers.
2. `src/discovery/`: channel discovery and expansion logic.
3. `src/scoring/`: reliability and confidence scoring.
4. `src/decision/`: rule mapping and recommendation.
5. `src/execution/`: deterministic order logic and risk gates.

Create folders only when implementation for that module starts.
