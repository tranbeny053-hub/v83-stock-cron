CREATE TABLE IF NOT EXISTS analysis_run_details (
  run_id TEXT PRIMARY KEY,
  analysis_hash TEXT,
  detail_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_run_details_created_at
  ON analysis_run_details (created_at DESC);
