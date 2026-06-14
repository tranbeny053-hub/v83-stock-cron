-- Wave 4B.1 immutable prediction ledger foundation.
-- Idempotent only: no destructive actions, no secrets, no full article storage.

CREATE TABLE IF NOT EXISTS predictions (
  prediction_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  operator_id TEXT,
  symbol TEXT NOT NULL,
  normalized_symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  horizon_bars INTEGER NOT NULL,
  predicted_at_utc TIMESTAMPTZ NOT NULL,
  reference_close_utc TIMESTAMPTZ NOT NULL,
  reference_price NUMERIC NOT NULL,
  horizon_end_utc TIMESTAMPTZ NOT NULL,
  p_up_frac NUMERIC NOT NULL,
  p_down_frac NUMERIC NOT NULL,
  p_timeout_frac NUMERIC NOT NULL,
  decision_band_frac NUMERIC,
  model_version TEXT NOT NULL,
  methodology_version TEXT NOT NULL,
  calibration_status TEXT NOT NULL,
  reliability_status TEXT NOT NULL,
  epistemic_sufficiency TEXT,
  gate_action TEXT,
  data_source TEXT,
  is_live_data BOOLEAN NOT NULL DEFAULT false,
  cross_provider_state TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predictions_horizon_end
  ON predictions (horizon_end_utc);

CREATE INDEX IF NOT EXISTS idx_predictions_symbol_timeframe_predicted
  ON predictions (normalized_symbol, timeframe, predicted_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_model_timeframe
  ON predictions (model_version, timeframe);
