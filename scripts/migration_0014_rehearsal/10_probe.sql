-- Migration 0014 rehearsal, after the apply: the catalog, the surviving legacy rows and every refusal.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner. Never run it against a real database.
-- Each probe raises REHEARSAL_FAIL unless the expected outcome happens.
DO $$
DECLARE
    found INTEGER;
BEGIN
    -- NOT VALID: the legacy rows are still there, unchanged, and no check was validated.
    SELECT count(*) INTO found FROM public.predictions
    WHERE prediction_id = 'legacy:invalid' AND reference_price = 0 AND horizon_bars = 0;
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the legacy prediction changed'; END IF;
    SELECT count(*) INTO found FROM public.prediction_outcomes
    WHERE prediction_id = 'legacy:invalid' AND outcome_reference_price = 0;
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the legacy outcome changed'; END IF;
    SELECT count(*) INTO found FROM public.prediction_feature_snapshots
    WHERE prediction_id = 'legacy:invalid' AND snapshot_hash = 'legacy-hash';
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the legacy feature snapshot changed'; END IF;
    SELECT count(*) INTO found FROM pg_catalog.pg_constraint
    WHERE conname IN ('predictions_probability_simplex_chk', 'predictions_reference_price_chk',
                      'predictions_horizon_chronology_chk', 'prediction_outcomes_reference_price_chk')
      AND NOT convalidated;
    IF found <> 4 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: expected 4 NOT VALID checks, found %', found; END IF;
    SELECT count(*) INTO found FROM pg_catalog.pg_trigger
    WHERE tgname ~ '^trg_(pred|pout|pfs)_reject_(update|delete|truncate)$' AND NOT tgisinternal;
    IF found <> 9 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: expected 9 triggers, found %', found; END IF;
    -- The function: a fixed search_path, and no API role may execute it.
    SELECT count(*) INTO found FROM pg_catalog.pg_proc
    WHERE proname = 'reject_core_evidence_mutation'
      AND proconfig = ARRAY['search_path=pg_catalog, pg_temp'];
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the function search_path is not fixed'; END IF;
    IF has_function_privilege('anon', 'public.reject_core_evidence_mutation()', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.reject_core_evidence_mutation()', 'EXECUTE')
       OR has_function_privilege('service_role', 'public.reject_core_evidence_mutation()', 'EXECUTE') THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: an API role may execute the trigger function';
    END IF;
END;
$$;

-- Every check refuses its violation, with check_violation.
DO $$
DECLARE
    probe RECORD;
BEGIN
    FOR probe IN
        SELECT * FROM (VALUES
            ('probability above 1',   1.2,  0.0,  0.0, 120.95, 6, '2026-10-01T00:00:00Z'),
            ('probability below 0',  -0.1,  0.6,  0.5, 120.95, 6, '2026-10-01T00:00:00Z'),
            ('probability sum 1.5',   0.5,  0.5,  0.5, 120.95, 6, '2026-10-01T00:00:00Z'),
            ('sum off by 2e-6',       0.400002, 0.3, 0.3, 120.95, 6, '2026-10-01T00:00:00Z'),
            ('NaN probability',       'NaN', 0.5, 0.5, 120.95, 6, '2026-10-01T00:00:00Z'),
            ('zero price',            0.4,  0.3,  0.3, 0,      6, '2026-10-01T00:00:00Z'),
            ('NaN price',             0.4,  0.3,  0.3, 'NaN',  6, '2026-10-01T00:00:00Z'),
            ('infinite price',        0.4,  0.3,  0.3, 'Infinity', 6, '2026-10-01T00:00:00Z'),
            ('zero-bar horizon',      0.4,  0.3,  0.3, 120.95, 0, '2026-10-01T00:00:00Z'),
            ('reference after it',    0.4,  0.3,  0.3, 120.95, 6, '2026-09-30T23:00:00Z')
        ) AS v(label, p_up, p_down, p_timeout, price, bars, predicted_at)
    LOOP
        BEGIN
            INSERT INTO public.predictions (
                prediction_id, run_id, symbol, normalized_symbol, timeframe, horizon_bars,
                predicted_at_utc, reference_close_utc, reference_price, horizon_end_utc,
                p_up_frac, p_down_frac, p_timeout_frac, model_version, methodology_version,
                calibration_status, reliability_status
            ) VALUES (
                'probe:' || probe.label, 'probe', 'BTC', 'BTC/USDT', '4H', probe.bars,
                probe.predicted_at::timestamptz, '2026-10-01T00:00:00Z', probe.price::numeric,
                '2026-10-02T00:00:00Z', probe.p_up::numeric, probe.p_down::numeric,
                probe.p_timeout::numeric, 'm', 'distributional-v1', 'UNCALIBRATED', 'UNRELIABLE'
            );
            RAISE EXCEPTION 'REHEARSAL_FAIL: % was accepted', probe.label;
        EXCEPTION WHEN check_violation THEN
            NULL;
        END;
    END LOOP;
    BEGIN
        INSERT INTO public.prediction_outcomes (
            prediction_id, resolved_at_utc, outcome_close_utc, outcome_reference_price,
            terminal_return_frac, realized_label, resolver_version
        ) VALUES ('probe:zero-outcome', '2026-10-02T00:00:00Z', '2026-10-02T00:00:00Z', 0,
                  0, 'TIMEOUT', 'probe');
        RAISE EXCEPTION 'REHEARSAL_FAIL: a zero outcome price was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END;
$$;

-- Core evidence is append-only: UPDATE, DELETE and TRUNCATE are refused on all three tables.
DO $$
DECLARE
    statement TEXT;
BEGIN
    FOREACH statement IN ARRAY ARRAY[
        'UPDATE public.predictions SET model_version = model_version',
        'DELETE FROM public.predictions WHERE prediction_id = ''legacy:invalid''',
        'UPDATE public.prediction_outcomes SET resolver_version = resolver_version',
        'DELETE FROM public.prediction_outcomes WHERE prediction_id = ''legacy:invalid''',
        'TRUNCATE public.prediction_outcomes',
        'TRUNCATE public.predictions CASCADE',
        'UPDATE public.prediction_feature_snapshots SET prediction_id = prediction_id',
        'DELETE FROM public.prediction_feature_snapshots',
        'TRUNCATE public.prediction_feature_snapshots'
    ]
    LOOP
        BEGIN
            EXECUTE statement;
            RAISE EXCEPTION 'REHEARSAL_FAIL: accepted: %', statement;
        EXCEPTION WHEN raise_exception THEN
            IF SQLERRM NOT LIKE '%append-only%' THEN
                RAISE;
            END IF;
        END;
    END LOOP;
END;
$$;
