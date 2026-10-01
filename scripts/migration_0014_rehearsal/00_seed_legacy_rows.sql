-- Migration 0014 rehearsal, step 0: BEFORE 0014, seed rows its checks would refuse.
-- They prove NOT VALID: the apply must succeed without scanning them, and they must survive unchanged.
-- Scratch database only (a CI runner's local PostgreSQL); synthetic values.
INSERT INTO public.predictions (
    prediction_id, run_id, symbol, normalized_symbol, timeframe, horizon_bars,
    predicted_at_utc, reference_close_utc, reference_price, horizon_end_utc,
    p_up_frac, p_down_frac, p_timeout_frac, model_version, methodology_version,
    calibration_status, reliability_status
) VALUES (
    'legacy:invalid', 'legacy', 'BTC', 'BTC/USDT', '4H', 0,
    '2026-01-01T00:00:00Z', '2026-01-01T04:00:00Z', 0, '2026-01-01T00:00:00Z',
    0.5, 0.5, 0.5, 'legacy-model', 'legacy-method', 'UNCALIBRATED', 'UNRELIABLE'
);
INSERT INTO public.prediction_outcomes (
    prediction_id, resolved_at_utc, outcome_close_utc, outcome_reference_price,
    terminal_return_frac, realized_label, resolver_version
) VALUES (
    'legacy:invalid', '2026-01-02T00:00:00Z', '2026-01-01T08:00:00Z', 0,
    0, 'TIMEOUT', 'legacy-resolver'
);
