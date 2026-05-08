BEGIN;

CREATE TABLE IF NOT EXISTS market_groups (
  group_slug TEXT PRIMARY KEY,
  event_id TEXT,
  scope_label TEXT NOT NULL DEFAULT 'Other',
  group_title TEXT NOT NULL,
  representative_market_id TEXT REFERENCES markets(market_id) ON DELETE SET NULL,
  market_count INTEGER NOT NULL DEFAULT 0,
  tradable_market_count INTEGER NOT NULL DEFAULT 0,
  earliest_end_date TIMESTAMPTZ,
  latest_end_date TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  sample_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_groups_scope
  ON market_groups (scope_label, tradable_market_count DESC);

CREATE INDEX IF NOT EXISTS idx_market_groups_last_seen
  ON market_groups (last_seen_at DESC);

CREATE TABLE IF NOT EXISTS market_group_members (
  group_slug TEXT NOT NULL REFERENCES market_groups(group_slug) ON DELETE CASCADE,
  market_id TEXT NOT NULL REFERENCES markets(market_id) ON DELETE CASCADE,
  event_slug TEXT NOT NULL,
  is_tradable BOOLEAN NOT NULL DEFAULT TRUE,
  priority_rank INTEGER,
  source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (group_slug, market_id)
);

CREATE INDEX IF NOT EXISTS idx_market_group_members_market
  ON market_group_members (market_id);

CREATE INDEX IF NOT EXISTS idx_market_group_members_group
  ON market_group_members (group_slug, priority_rank);

COMMIT;
