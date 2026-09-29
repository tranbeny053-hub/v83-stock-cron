-- Rehearsal assertion for migration 0011. It runs on the rehearsal database after the rehearse-mode
-- apply, and on a database rebuilt from migrations 0001-0011 alone: target contract v1 must hold
-- on both. One DO block that raises on any departure. Every probe row is inserted in its own
-- sub-block, which always ends in an exception and so rolls back: nothing persists.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as the tables' owner.
-- Never run it against a real database.
DO $$
DECLARE
  expected_column record;
  expected_constraint record;
  probe record;
  violated text;
  probes_run integer := 0;
  core_at timestamptz := '2026-09-29 12:00:01+00';
  issued_at timestamptz := '2026-09-29 12:00:02+00';
  after_issued_at timestamptz := '2026-09-29 12:00:03+00';
BEGIN
  -- (a) The four columns, exactly typed, nullable, with no default, identity or generation.
  FOR expected_column IN
    SELECT *
    FROM (
      VALUES
        ('target_version', 'text'),
        ('reference_venue', 'text'),
        ('core_computed_at_utc', 'timestamp with time zone'),
        ('issued_at_utc', 'timestamp with time zone')
    ) AS v(column_name, type_name)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_attribute AS a
      WHERE a.attrelid = 'public.predictions'::regclass
        AND a.attname = expected_column.column_name
        AND a.attnum > 0
        AND NOT a.attisdropped
        AND pg_catalog.format_type(a.atttypid, a.atttypmod) = expected_column.type_name
        AND NOT a.attnotnull
        AND NOT a.atthasdef
        AND a.attidentity = ''
        AND a.attgenerated = ''
    ) THEN
      RAISE EXCEPTION 'predictions.% is not a nullable % with no default',
        expected_column.column_name, expected_column.type_name;
    END IF;
  END LOOP;

  -- (b) The three constraints, each a validated CHECK constraint on predictions.
  FOR expected_constraint IN
    SELECT *
    FROM (
      VALUES
        ('predictions_target_version_chk'),
        ('predictions_reference_venue_chk'),
        ('predictions_target_stamp_chk')
    ) AS v(constraint_name)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_constraint AS c
      WHERE c.conrelid = 'public.predictions'::regclass
        AND c.conname = expected_constraint.constraint_name
        AND c.contype = 'c'
        AND c.convalidated
    ) THEN
      RAISE EXCEPTION '% is not a validated CHECK constraint on predictions',
        expected_constraint.constraint_name;
    END IF;
  END LOOP;

  -- (c) No existing row carries any stamp value: every row that predates the contract stays v0.
  IF EXISTS (
    SELECT 1
    FROM public.predictions AS p
    WHERE pg_catalog.num_nonnulls(
      p.target_version, p.reference_venue, p.core_computed_at_utc, p.issued_at_utc
    ) > 0
  ) THEN
    RAISE EXCEPTION 'an existing predictions row carries a target stamp';
  END IF;

  -- (d) Behavioural probes. Each inserts a full valid row, with only the four stamp values varied.
  -- An accepted row raises the sentinel, which only the raise_exception handler swallows. A row
  -- that must be rejected must hit check_violation, from exactly the constraint named. Anything
  -- else propagates and fails the rehearsal.
  FOR probe IN
    SELECT *
    FROM (
      VALUES
        ('v0-unstamped', NULL, NULL, NULL, NULL, NULL),
        ('tc-v1-binance', 'tc-v1', 'BINANCE_PUBLIC', core_at, issued_at, NULL),
        ('tc-v1-okx', 'tc-v1', 'OKX_PUBLIC', core_at, issued_at, NULL),
        ('tc-v1-core-equals-issued', 'tc-v1', 'BINANCE_PUBLIC', issued_at, issued_at, NULL),
        ('version-tc-v2', 'tc-v2', 'BINANCE_PUBLIC', core_at, issued_at, 'predictions_target_version_chk'),
        ('version-empty', '', 'BINANCE_PUBLIC', core_at, issued_at, 'predictions_target_version_chk'),
        ('venue-cross-provider', 'tc-v1', 'CROSS_PROVIDER', core_at, issued_at, 'predictions_reference_venue_chk'),
        ('venue-lowercase-binance', 'tc-v1', 'binance', core_at, issued_at, 'predictions_reference_venue_chk'),
        ('venue-empty', 'tc-v1', '', core_at, issued_at, 'predictions_reference_venue_chk'),
        ('stamp-without-target-version', NULL, 'BINANCE_PUBLIC', core_at, issued_at, 'predictions_target_stamp_chk'),
        ('stamp-without-reference-venue', 'tc-v1', NULL, core_at, issued_at, 'predictions_target_stamp_chk'),
        ('stamp-without-core-computed-at', 'tc-v1', 'BINANCE_PUBLIC', NULL, issued_at, 'predictions_target_stamp_chk'),
        ('stamp-without-issued-at', 'tc-v1', 'BINANCE_PUBLIC', core_at, NULL, 'predictions_target_stamp_chk'),
        ('core-after-issued', 'tc-v1', 'BINANCE_PUBLIC', after_issued_at, issued_at, 'predictions_target_stamp_chk')
    ) AS v(probe_name, target_version, reference_venue, core_computed_at_utc, issued_at_utc, rejected_by)
  LOOP
    probes_run := probes_run + 1;
    BEGIN
      INSERT INTO public.predictions (
        prediction_id, run_id, operator_id, symbol, normalized_symbol, timeframe, horizon_bars,
        predicted_at_utc, reference_close_utc, reference_price, horizon_end_utc,
        p_up_frac, p_down_frac, p_timeout_frac, decision_band_frac,
        model_version, methodology_version, calibration_status, reliability_status,
        data_source, is_live_data, created_at, prediction_origin,
        target_version, reference_venue, core_computed_at_utc, issued_at_utc
      ) VALUES (
        'rehearsal-probe-' || probe.probe_name, 'rehearsal-probe-run', 'operator', 'BTC',
        'BTC/USDT', '4H', 6,
        '2026-09-29 12:00:00+00', '2026-09-29 12:00:00+00', 100, '2026-09-30 12:00:00+00',
        0.40, 0.35, 0.25, 0.003,
        'phase1a-wave4b0', 'heuristic-v1-wave4b0', 'DEFAULT_PHASE1A', 'INSUFFICIENT_SAMPLE',
        'BINANCE_PUBLIC', true, '2026-09-29 12:00:03+00', 'USER_REQUESTED',
        probe.target_version, probe.reference_venue, probe.core_computed_at_utc,
        probe.issued_at_utc
      );
      IF probe.rejected_by IS NULL THEN
        RAISE EXCEPTION 'migration 0011 rehearsal probe accepted';
      END IF;
      RAISE EXCEPTION 'probe % was accepted, but % must reject it',
        probe.probe_name, probe.rejected_by;
    EXCEPTION
      WHEN check_violation THEN
        GET STACKED DIAGNOSTICS violated = CONSTRAINT_NAME;
        IF probe.rejected_by IS NULL OR violated IS DISTINCT FROM probe.rejected_by THEN
          RAISE EXCEPTION 'probe % was rejected by %, not by %',
            probe.probe_name, violated, COALESCE(probe.rejected_by, 'no constraint');
        END IF;
      WHEN raise_exception THEN
        IF probe.rejected_by IS NOT NULL
          OR SQLERRM <> 'migration 0011 rehearsal probe accepted' THEN
          RAISE;
        END IF;
    END;
  END LOOP;

  IF probes_run <> 14 THEN
    RAISE EXCEPTION 'ran % probes, not 14', probes_run;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.predictions AS p
    WHERE p.prediction_id LIKE 'rehearsal-probe-%'
  ) THEN
    RAISE EXCEPTION 'a rehearsal probe row persisted';
  END IF;
END
$$;
