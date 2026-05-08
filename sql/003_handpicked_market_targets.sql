BEGIN;

CREATE TABLE IF NOT EXISTS handpicked_market_targets (
  target_id BIGSERIAL PRIMARY KEY,
  source_file TEXT NOT NULL,
  source_line_number INTEGER NOT NULL,
  raw_line TEXT NOT NULL,
  requested_name TEXT NOT NULL,
  requested_bucket TEXT,
  requested_locator TEXT,
  match_status TEXT NOT NULL DEFAULT 'unmatched',
  matched_group_slug TEXT REFERENCES market_groups(group_slug) ON DELETE SET NULL,
  matched_group_title TEXT,
  matched_scope_label TEXT,
  representative_market_id TEXT REFERENCES markets(market_id) ON DELETE SET NULL,
  matched_market_count INTEGER,
  match_score DOUBLE PRECISION,
  match_method TEXT,
  candidate_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source_file, source_line_number)
);

CREATE INDEX IF NOT EXISTS idx_handpicked_market_targets_status
  ON handpicked_market_targets (match_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_handpicked_market_targets_group
  ON handpicked_market_targets (matched_group_slug);

COMMIT;
