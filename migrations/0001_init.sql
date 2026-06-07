-- Wave 1 persistence foundation. Idempotent, compact summaries only.

CREATE TABLE IF NOT EXISTS watchlist (
  operator_id TEXT NOT NULL DEFAULT 'operator',
  normalized_symbol TEXT NOT NULL,
  display_symbol TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (operator_id, normalized_symbol)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
  run_id TEXT PRIMARY KEY,
  operator_id TEXT NOT NULL DEFAULT 'operator',
  symbol TEXT NOT NULL,
  normalized_symbol TEXT NOT NULL,
  analysis_mode TEXT NOT NULL,
  asset_class TEXT NOT NULL,
  primary_timeframe TEXT NOT NULL,
  disposition TEXT,
  total_score NUMERIC,
  data_source TEXT,
  is_live_data BOOLEAN NOT NULL DEFAULT FALSE,
  persistence_status TEXT,
  analysis_hash TEXT,
  as_of_utc TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analysis_timeframe_results (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  disposition TEXT,
  total_score NUMERIC,
  prob_up_pct NUMERIC,
  prob_down_pct NUMERIC,
  prob_timeout_pct NUMERIC,
  gate_action TEXT,
  data_source TEXT,
  is_live_data BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS provider_observations (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_status TEXT,
  active_provider TEXT,
  data_source TEXT,
  is_live_data BOOLEAN NOT NULL DEFAULT FALSE,
  warning_count INTEGER NOT NULL DEFAULT 0,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_events (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'INFO',
  run_id TEXT,
  message TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_operator_created
  ON watchlist (operator_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_created
  ON analysis_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_symbol_created
  ON analysis_runs (normalized_symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_timeframe_results_run
  ON analysis_timeframe_results (run_id);

CREATE INDEX IF NOT EXISTS idx_provider_observations_run
  ON provider_observations (run_id);

CREATE INDEX IF NOT EXISTS idx_app_events_created
  ON app_events (created_at DESC);
