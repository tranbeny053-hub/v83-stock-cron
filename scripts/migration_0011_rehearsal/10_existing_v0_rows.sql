-- Rehearsal fixture for migration 0011, part 3: two synthetic v0 rows in public.predictions of the
-- scratch rehearsal database. It runs after migrations 0001-0010 and before the rehearse-mode
-- apply, so that the new constraints are validated over real rows. The stamp columns do not exist
-- yet, so these rows are what every production row is today: v0. Every NOT NULL column of
-- migration 0003 is given a valid value, and the probabilities of each row sum to 1.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as the tables' owner.
-- Never run it against a real database.
INSERT INTO public.predictions (
  prediction_id, run_id, operator_id, symbol, normalized_symbol, timeframe, horizon_bars,
  predicted_at_utc, reference_close_utc, reference_price, horizon_end_utc,
  p_up_frac, p_down_frac, p_timeout_frac, decision_band_frac,
  model_version, methodology_version, calibration_status, reliability_status,
  epistemic_sufficiency, gate_action, data_source, is_live_data, cross_provider_state,
  created_at, prediction_origin
) VALUES
  (
    'rehearsal-v0-1', 'rehearsal-run-1', 'operator', 'BTC', 'BTC/USDT', '4H', 6,
    '2026-09-28 00:00:07+00', '2026-09-28 00:00:00+00', 100, '2026-09-29 00:00:00+00',
    0.40, 0.35, 0.25, 0.003,
    'phase1a-wave4b0', 'heuristic-v1-wave4b0', 'DEFAULT_PHASE1A', 'INSUFFICIENT_SAMPLE',
    'SUFFICIENT', 'WATCH', 'CROSS_PROVIDER', true, 'COHERENT',
    '2026-09-28 00:00:09+00', 'USER_REQUESTED'
  ),
  (
    'rehearsal-v0-2', 'rehearsal-run-2', 'operator', 'ETH', 'ETH/USDT', '1H', 6,
    '2026-09-28 01:00:04+00', '2026-09-28 01:00:00+00', 50, '2026-09-28 07:00:00+00',
    0.30, 0.30, 0.40, 0.004,
    'phase1a-wave4b0', 'heuristic-v1-wave4b0', 'DEFAULT_PHASE1A', 'INSUFFICIENT_SAMPLE',
    'SUFFICIENT', 'WATCH', 'OKX_PUBLIC', true, 'UNAVAILABLE',
    '2026-09-28 01:00:06+00', 'USER_REQUESTED'
  );
