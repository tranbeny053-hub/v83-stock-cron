-- Migration 0015 rehearsal, after the apply: the catalog, then the bundle function called as each of
-- PostgREST's roles. Runs ONLY in a scratch local PostgreSQL on a CI runner, as the role that owns the
-- tables (a member of the three API roles: 00_supabase_like_function_grants.sql). Never run it
-- against a real database. Each probe raises REHEARSAL_FAIL unless the expected outcome happens.

-- The catalog: one SECURITY INVOKER function, a fixed search_path, EXECUTE for service_role only.
DO $$
DECLARE
    found INTEGER;
BEGIN
    SELECT count(*) INTO found FROM pg_catalog.pg_proc
    WHERE pronamespace = 'public'::regnamespace AND proname = 'save_prediction_bundle';
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: expected one bundle function, found %', found; END IF;
    SELECT count(*) INTO found FROM pg_catalog.pg_proc
    WHERE oid = 'public.save_prediction_bundle(jsonb,jsonb,jsonb)'::regprocedure
      AND NOT prosecdef AND proconfig = ARRAY['search_path=pg_catalog, pg_temp']
      AND provolatile = 'v' AND prorettype = 'jsonb'::regtype;
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the function is not the reviewed one'; END IF;
    IF has_function_privilege('public', 'public.save_prediction_bundle(jsonb,jsonb,jsonb)', 'EXECUTE')
       OR has_function_privilege('anon', 'public.save_prediction_bundle(jsonb,jsonb,jsonb)', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.save_prediction_bundle(jsonb,jsonb,jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: PUBLIC, anon or authenticated may execute the bundle function';
    END IF;
    IF NOT has_function_privilege('service_role', 'public.save_prediction_bundle(jsonb,jsonb,jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: service_role may not execute the bundle function';
    END IF;
END;
$$;

-- As service_role, the role PostgREST switches to for the REST writer's key.
SET ROLE service_role;

DO $$
DECLARE
    pred CONSTANT jsonb := jsonb_build_object(
        'prediction_id', 'probe:4H:6', 'run_id', 'probe', 'operator_id', 'operator',
        'symbol', 'BTC', 'normalized_symbol', 'BTC/USDT', 'timeframe', '4H', 'horizon_bars', 6,
        'predicted_at_utc', '2026-10-02T08:00:00Z', 'reference_close_utc', '2026-10-02T08:00:00Z',
        'reference_price', 61234.56789012345, 'horizon_end_utc', '2026-10-03T08:00:00Z',
        'p_up_frac', 0.33333333333333337, 'p_down_frac', 0.33333333333333337,
        'p_timeout_frac', 0.33333333333333326, 'decision_band_frac', 0.01,
        'model_version', 'm', 'methodology_version', 'distributional-v1',
        'calibration_status', 'UNCALIBRATED', 'reliability_status', 'INSUFFICIENT',
        'epistemic_sufficiency', 'LOW', 'gate_action', 'WAIT', 'data_source', 'BINANCE_PUBLIC',
        'is_live_data', true, 'cross_provider_state', 'UNAVAILABLE',
        'prediction_origin', 'CONTROLLED_SMOKE'
    );
    feat CONSTANT jsonb := jsonb_build_object(
        'prediction_id', 'probe:4H:6', 'run_id', 'probe', 'symbol', 'BTC',
        'normalized_symbol', 'BTC/USDT', 'timeframe', '4H',
        'prediction_as_of_utc', '2026-10-02T08:00:00Z', 'reference_close_utc', '2026-10-02T08:00:00Z',
        'quant_v2_schema_version', 'v2', 'feature_methodology_version', 'f1',
        'influence_mode', 'SHADOW_ONLY', 'no_lookahead_assertion', true, 'block_status', 'ACTIVE',
        'feature_count', 3, 'degraded_count', 0, 'provider_signature', 'binance',
        'snapshot_payload', jsonb_build_object('k', 1), 'snapshot_hash', repeat('a', 64)
    );
    deriv CONSTANT jsonb := jsonb_build_object(
        'prediction_id', 'probe:4H:6', 'run_id', 'probe', 'normalized_symbol', 'BTC/USDT',
        'derivatives_schema_version', 'd1', 'derivatives_methodology_version', 'dm1',
        'influence_mode', 'SHADOW_ONLY', 'decision_influence_frac', 0, 'block_status', 'ACTIVE',
        'core_prediction_as_of_utc', '2026-10-02T08:00:00Z',
        'observation_as_of_utc', '2026-10-02T08:00:00Z',
        'snapshot_payload', jsonb_build_object(
            'schema_version', 'd1', 'methodology_version', 'dm1', 'influence_mode', 'SHADOW_ONLY',
            'decision_influence_frac', 0, 'normalized_symbol', 'BTC/USDT',
            'core_prediction_as_of_utc', '2026-10-02T08:00:00Z',
            'observation_as_of_utc', '2026-10-02T08:00:00Z', 'block_status', 'ACTIVE',
            'provider_summary', '[]'::jsonb, 'metrics', '[]'::jsonb, 'comparability', '[]'::jsonb,
            'disagreement', '[]'::jsonb, 'warnings', '[]'::jsonb, 'not_trade_command', true,
            'not_financial_advice', true
        ),
        'snapshot_hash', repeat('d', 64)
    );
    seven CONSTANT jsonb := jsonb_build_object('prediction_id', 'probe:4H:7', 'run_id', 'probe7');
    answer jsonb;
    found INTEGER;
BEGIN
    -- A new bundle: all three rows, in one call.
    answer := public.save_prediction_bundle(pred, feat, deriv);
    IF answer <> '{"prediction": "INSERTED", "feature_snapshot": "INSERTED",
                   "derivatives_snapshot": "INSERTED", "refused": false}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: a new bundle answered %', answer;
    END IF;

    -- An identical replay confirms and writes nothing new; its numbers kept every JSON digit.
    answer := public.save_prediction_bundle(pred, feat, deriv);
    IF answer <> '{"prediction": "IDENTICAL_DUPLICATE", "feature_snapshot": "IDENTICAL_DUPLICATE",
                   "derivatives_snapshot": "IDENTICAL_DUPLICATE", "refused": false}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: an identical replay answered %', answer;
    END IF;
    SELECT count(*) INTO found FROM public.predictions
    WHERE prediction_id = 'probe:4H:6' AND reference_price = 61234.56789012345
      AND p_timeout_frac = 0.33333333333333326;
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the stored prediction is not the sent one'; END IF;

    -- A conflicting prediction is refused, and the stored row is unchanged.
    answer := public.save_prediction_bundle(
        jsonb_set(pred, '{reference_price}', '61234.5'::jsonb), feat, deriv);
    IF answer <> '{"prediction": "CONFLICT", "feature_snapshot": null,
                   "derivatives_snapshot": null, "refused": true}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: a conflicting prediction answered %', answer;
    END IF;
    SELECT count(*) INTO found FROM public.predictions
    WHERE prediction_id = 'probe:4H:6' AND reference_price = 61234.56789012345;
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: a conflicting prediction changed the stored one'; END IF;

    -- A conflicting feature snapshot is refused; the stored snapshot is unchanged.
    answer := public.save_prediction_bundle(
        pred, jsonb_set(feat, '{snapshot_hash}', to_jsonb(repeat('b', 64))), deriv);
    IF answer <> '{"prediction": "IDENTICAL_DUPLICATE", "feature_snapshot": "CONFLICT",
                   "derivatives_snapshot": null, "refused": true}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: a conflicting feature snapshot answered %', answer;
    END IF;
    SELECT count(*) INTO found FROM public.prediction_feature_snapshots
    WHERE prediction_id = 'probe:4H:6' AND snapshot_hash = repeat('a', 64);
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the stored feature snapshot changed'; END IF;

    -- A conflicting derivatives snapshot is refused; the stored one is unchanged.
    answer := public.save_prediction_bundle(
        pred, feat, jsonb_set(deriv, '{snapshot_hash}', to_jsonb(repeat('e', 64))));
    IF answer <> '{"prediction": "IDENTICAL_DUPLICATE", "feature_snapshot": "IDENTICAL_DUPLICATE",
                   "derivatives_snapshot": "CONFLICT", "refused": true}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: a conflicting derivatives snapshot answered %', answer;
    END IF;
    SELECT count(*) INTO found FROM public.prediction_derivatives_snapshots
    WHERE prediction_id = 'probe:4H:6' AND snapshot_hash = repeat('d', 64);
    IF found <> 1 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: the stored derivatives snapshot changed'; END IF;

    -- ATOMIC: a new bundle whose feature snapshot its CHECK refuses fails whole, and keeps nothing:
    -- the prediction row it wrote first is rolled back with it.
    BEGIN
        PERFORM public.save_prediction_bundle(
            pred || seven, jsonb_set(feat || seven, '{influence_mode}', '"ACTIVE"'::jsonb), NULL);
        RAISE EXCEPTION 'REHEARSAL_FAIL: a refused snapshot did not fail its bundle';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
    SELECT count(*) INTO found FROM public.predictions WHERE prediction_id = 'probe:4H:7';
    IF found <> 0 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: a failed bundle kept its prediction'; END IF;

    -- Malformed bundles fail before anything is written.
    BEGIN
        PERFORM public.save_prediction_bundle(pred || seven || '{"not_a_column": 1}'::jsonb, NULL, NULL);
        RAISE EXCEPTION 'REHEARSAL_FAIL: an unknown key was accepted';
    EXCEPTION WHEN invalid_parameter_value THEN
        NULL;
    END;
    BEGIN
        PERFORM public.save_prediction_bundle(
            pred || jsonb_build_object('prediction_id', 'oosb-' || repeat('0', 32) || ':4H:BASELINE',
                                       'prediction_origin', 'SCHEDULED_SHADOW_EVIDENCE'), NULL, NULL);
        RAISE EXCEPTION 'REHEARSAL_FAIL: an OOS identity was accepted';
    EXCEPTION WHEN invalid_parameter_value THEN
        NULL;
    END;
    BEGIN
        PERFORM public.save_prediction_bundle(pred || seven, feat, NULL);
        RAISE EXCEPTION 'REHEARSAL_FAIL: a snapshot of another prediction was accepted';
    EXCEPTION WHEN invalid_parameter_value THEN
        NULL;
    END;
    BEGIN
        PERFORM public.save_prediction_bundle('[1]'::jsonb, NULL, NULL);
        RAISE EXCEPTION 'REHEARSAL_FAIL: a non-object prediction was accepted';
    EXCEPTION WHEN invalid_parameter_value THEN
        NULL;
    END;
    SELECT count(*) INTO found FROM public.predictions
    WHERE prediction_id = 'probe:4H:7' OR prediction_id LIKE 'oosb-%';
    IF found <> 0 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: a malformed bundle wrote a row'; END IF;

    -- A prediction alone (its snapshot failed to build): written, never refused; JSON nulls are NULL.
    answer := public.save_prediction_bundle(pred || seven, NULL, NULL);
    IF answer <> '{"prediction": "INSERTED", "feature_snapshot": null,
                   "derivatives_snapshot": null, "refused": false}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: a prediction alone answered %', answer;
    END IF;
    answer := public.save_prediction_bundle(pred || seven, 'null'::jsonb, 'null'::jsonb);
    IF answer <> '{"prediction": "IDENTICAL_DUPLICATE", "feature_snapshot": null,
                   "derivatives_snapshot": null, "refused": false}'::jsonb THEN
        RAISE EXCEPTION 'REHEARSAL_FAIL: JSON null snapshots answered %', answer;
    END IF;
END;
$$;

RESET ROLE;

-- Neither anon nor authenticated may call it at all.
SET ROLE anon;
DO $$
BEGIN
    PERFORM public.save_prediction_bundle('{"prediction_id": "probe:anon"}'::jsonb);
    RAISE EXCEPTION 'REHEARSAL_FAIL: anon executed the bundle function';
EXCEPTION WHEN insufficient_privilege THEN
    NULL;
END;
$$;
RESET ROLE;

SET ROLE authenticated;
DO $$
BEGIN
    PERFORM public.save_prediction_bundle('{"prediction_id": "probe:authenticated"}'::jsonb);
    RAISE EXCEPTION 'REHEARSAL_FAIL: authenticated executed the bundle function';
EXCEPTION WHEN insufficient_privilege THEN
    NULL;
END;
$$;
RESET ROLE;

DO $$
DECLARE
    found INTEGER;
BEGIN
    SELECT count(*) INTO found FROM public.predictions WHERE prediction_id LIKE 'probe:%';
    IF found <> 2 THEN RAISE EXCEPTION 'REHEARSAL_FAIL: expected exactly 2 probe predictions, found %', found; END IF;
END;
$$;
