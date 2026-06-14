-- Wave 4B.2 immutable prediction outcome resolver foundation.
-- Idempotent only: no destructive actions, no secrets, no full article storage.

CREATE TABLE IF NOT EXISTS prediction_outcomes (
  prediction_id TEXT PRIMARY KEY,
  resolved_at_utc TIMESTAMPTZ NOT NULL,
  outcome_close_utc TIMESTAMPTZ NOT NULL,
  outcome_reference_price NUMERIC NOT NULL,
  terminal_return_frac NUMERIC NOT NULL,
  realized_label TEXT NOT NULL CHECK (realized_label IN ('UP','DOWN','TIMEOUT')),
  decision_band_frac NUMERIC,
  max_favorable_frac NUMERIC,
  max_adverse_frac NUMERIC,
  candles_observed INTEGER,
  resolver_version TEXT NOT NULL,
  data_source TEXT,
  is_live_data BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_realized_label
  ON prediction_outcomes (realized_label);
