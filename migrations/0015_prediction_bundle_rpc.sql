-- B9: the atomic, idempotent forecast bundle for the REST writer (governing plan §8.1; PERS-0 C1b, C3).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization, through its own
-- one-shot route (scripts/apply_migration_0015.py). The bulk scripts/apply_migrations.py applies EVERY
-- migration and must never be used for it.
--
-- ONE FUNCTION, NOTHING ELSE: public.save_prediction_bundle(p_prediction, p_feature_snapshot,
-- p_derivatives_snapshot). No table, column, constraint, index, trigger, policy or table privilege
-- changes. Production's REST writer calls it as one PostgREST request:
--   POST /rest/v1/rpc/save_prediction_bundle
--   {"p_prediction": {...}, "p_feature_snapshot": {...} | null, "p_derivatives_snapshot": {...} | null}
-- PostgREST runs each request in its own transaction, so the whole bundle commits or none of it does.
--
-- WHAT IT DOES, in that one transaction:
-- - each row is read with jsonb_populate_record, the JSON-to-column conversion PostgREST's own inserts
--   use, so it stores exactly what the REST writer's per-row inserts store today;
-- - a key that is not a column, a missing or OOS (oosb-) prediction id, a snapshot of another
--   prediction, or a value its column refuses is an error: the request fails and nothing is written;
-- - the prediction is inserted, or, if its id is stored, compared column by column with the stored
--   row: identical content is IDENTICAL_DUPLICATE, anything else is CONFLICT;
-- - each submitted snapshot likewise (INSERTED, IDENTICAL_DUPLICATE or CONFLICT);
-- - any CONFLICT refuses the bundle: a sub-transaction rolls back everything this call wrote, and the
--   result says so ("refused": true). A refusal is an answer, not an outage;
-- - it only ever INSERTs and SELECTs, so 0014's append-only triggers never fire.
--
-- SECURITY: SECURITY INVOKER (the caller's privileges; the REST writer's service_role already holds
-- INSERT and SELECT on the three tables), a fixed search_path with every object qualified (§8.2), and
-- EXECUTE for service_role only: never PUBLIC, anon or authenticated.

CREATE OR REPLACE FUNCTION public.save_prediction_bundle(
    p_prediction jsonb,
    p_feature_snapshot jsonb DEFAULT NULL,
    p_derivatives_snapshot jsonb DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    prediction_keys CONSTANT text[] := ARRAY[
        'prediction_id', 'run_id', 'operator_id', 'symbol', 'normalized_symbol', 'timeframe',
        'horizon_bars', 'predicted_at_utc', 'reference_close_utc', 'reference_price',
        'horizon_end_utc', 'p_up_frac', 'p_down_frac', 'p_timeout_frac', 'decision_band_frac',
        'model_version', 'methodology_version', 'calibration_status', 'reliability_status',
        'epistemic_sufficiency', 'gate_action', 'data_source', 'is_live_data',
        'cross_provider_state', 'prediction_origin', 'target_version', 'reference_venue',
        'core_computed_at_utc', 'issued_at_utc'
    ];
    feature_keys CONSTANT text[] := ARRAY[
        'prediction_id', 'run_id', 'symbol', 'normalized_symbol', 'timeframe',
        'prediction_as_of_utc', 'reference_close_utc', 'quant_v2_schema_version',
        'feature_methodology_version', 'influence_mode', 'no_lookahead_assertion', 'block_status',
        'feature_count', 'degraded_count', 'provider_signature', 'snapshot_payload', 'snapshot_hash'
    ];
    derivatives_keys CONSTANT text[] := ARRAY[
        'prediction_id', 'run_id', 'normalized_symbol', 'derivatives_schema_version',
        'derivatives_methodology_version', 'influence_mode', 'decision_influence_frac',
        'block_status', 'core_prediction_as_of_utc', 'observation_as_of_utc', 'snapshot_payload',
        'snapshot_hash'
    ];
    incoming public.predictions;
    stored public.predictions;
    feature public.prediction_feature_snapshots;
    stored_feature public.prediction_feature_snapshots;
    derivatives public.prediction_derivatives_snapshots;
    stored_derivatives public.prediction_derivatives_snapshots;
    prediction_status text;
    feature_status text;
    derivatives_status text;
    written integer;
BEGIN
    IF p_feature_snapshot = 'null'::jsonb THEN
        p_feature_snapshot := NULL;
    END IF;
    IF p_derivatives_snapshot = 'null'::jsonb THEN
        p_derivatives_snapshot := NULL;
    END IF;
    IF pg_catalog.jsonb_typeof(p_prediction) IS DISTINCT FROM 'object'
        OR (p_feature_snapshot IS NOT NULL
            AND pg_catalog.jsonb_typeof(p_feature_snapshot) <> 'object')
        OR (p_derivatives_snapshot IS NOT NULL
            AND pg_catalog.jsonb_typeof(p_derivatives_snapshot) <> 'object') THEN
        RAISE EXCEPTION 'save_prediction_bundle: every row must be a JSON object'
            USING ERRCODE = '22023';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(p_prediction) AS k(key)
        WHERE k.key <> ALL (prediction_keys)
    ) OR (p_feature_snapshot IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(p_feature_snapshot) AS k(key)
        WHERE k.key <> ALL (feature_keys)
    )) OR (p_derivatives_snapshot IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(p_derivatives_snapshot) AS k(key)
        WHERE k.key <> ALL (derivatives_keys)
    )) THEN
        RAISE EXCEPTION 'save_prediction_bundle: a row carries a key that is not its column'
            USING ERRCODE = '22023';
    END IF;

    incoming := pg_catalog.jsonb_populate_record(NULL::public.predictions, p_prediction);
    IF incoming.prediction_id IS NULL OR pg_catalog.btrim(incoming.prediction_id) = '' THEN
        RAISE EXCEPTION 'save_prediction_bundle: the prediction has no id' USING ERRCODE = '22023';
    END IF;
    IF incoming.prediction_id LIKE 'oosb-%' THEN
        RAISE EXCEPTION 'save_prediction_bundle: section 5A OOS identities keep their own write path'
            USING ERRCODE = '22023';
    END IF;
    IF p_feature_snapshot IS NOT NULL THEN
        feature := pg_catalog.jsonb_populate_record(
            NULL::public.prediction_feature_snapshots, p_feature_snapshot
        );
        IF feature.prediction_id IS DISTINCT FROM incoming.prediction_id THEN
            RAISE EXCEPTION 'save_prediction_bundle: the feature snapshot belongs to another prediction'
                USING ERRCODE = '22023';
        END IF;
    END IF;
    IF p_derivatives_snapshot IS NOT NULL THEN
        derivatives := pg_catalog.jsonb_populate_record(
            NULL::public.prediction_derivatives_snapshots, p_derivatives_snapshot
        );
        IF derivatives.prediction_id IS DISTINCT FROM incoming.prediction_id THEN
            RAISE EXCEPTION 'save_prediction_bundle: the derivatives snapshot belongs to another prediction'
                USING ERRCODE = '22023';
        END IF;
    END IF;

    BEGIN
        INSERT INTO public.predictions (
            prediction_id, run_id, operator_id, symbol, normalized_symbol, timeframe, horizon_bars,
            predicted_at_utc, reference_close_utc, reference_price, horizon_end_utc, p_up_frac,
            p_down_frac, p_timeout_frac, decision_band_frac, model_version, methodology_version,
            calibration_status, reliability_status, epistemic_sufficiency, gate_action, data_source,
            is_live_data, cross_provider_state, prediction_origin, target_version, reference_venue,
            core_computed_at_utc, issued_at_utc
        )
        VALUES (
            incoming.prediction_id, incoming.run_id, incoming.operator_id, incoming.symbol,
            incoming.normalized_symbol, incoming.timeframe, incoming.horizon_bars,
            incoming.predicted_at_utc, incoming.reference_close_utc, incoming.reference_price,
            incoming.horizon_end_utc, incoming.p_up_frac, incoming.p_down_frac,
            incoming.p_timeout_frac, incoming.decision_band_frac, incoming.model_version,
            incoming.methodology_version, incoming.calibration_status, incoming.reliability_status,
            incoming.epistemic_sufficiency, incoming.gate_action, incoming.data_source,
            incoming.is_live_data, incoming.cross_provider_state, incoming.prediction_origin,
            incoming.target_version, incoming.reference_venue, incoming.core_computed_at_utc,
            incoming.issued_at_utc
        )
        ON CONFLICT (prediction_id) DO NOTHING;
        GET DIAGNOSTICS written = ROW_COUNT;
        IF written = 1 THEN
            prediction_status := 'INSERTED';
        ELSE
            SELECT * INTO stored FROM public.predictions WHERE prediction_id = incoming.prediction_id;
            IF ROW(
                stored.run_id, stored.operator_id, stored.symbol, stored.normalized_symbol,
                stored.timeframe, stored.horizon_bars, stored.predicted_at_utc,
                stored.reference_close_utc, stored.reference_price, stored.horizon_end_utc,
                stored.p_up_frac, stored.p_down_frac, stored.p_timeout_frac,
                stored.decision_band_frac, stored.model_version, stored.methodology_version,
                stored.calibration_status, stored.reliability_status, stored.epistemic_sufficiency,
                stored.gate_action, stored.data_source, stored.is_live_data,
                stored.cross_provider_state, stored.prediction_origin, stored.target_version,
                stored.reference_venue, stored.core_computed_at_utc, stored.issued_at_utc
            ) IS NOT DISTINCT FROM ROW(
                incoming.run_id, incoming.operator_id, incoming.symbol, incoming.normalized_symbol,
                incoming.timeframe, incoming.horizon_bars, incoming.predicted_at_utc,
                incoming.reference_close_utc, incoming.reference_price, incoming.horizon_end_utc,
                incoming.p_up_frac, incoming.p_down_frac, incoming.p_timeout_frac,
                incoming.decision_band_frac, incoming.model_version, incoming.methodology_version,
                incoming.calibration_status, incoming.reliability_status,
                incoming.epistemic_sufficiency, incoming.gate_action, incoming.data_source,
                incoming.is_live_data, incoming.cross_provider_state, incoming.prediction_origin,
                incoming.target_version, incoming.reference_venue, incoming.core_computed_at_utc,
                incoming.issued_at_utc
            ) THEN
                prediction_status := 'IDENTICAL_DUPLICATE';
            ELSE
                prediction_status := 'CONFLICT';
                RAISE EXCEPTION 'save_prediction_bundle: refused' USING ERRCODE = 'UB9C1';
            END IF;
        END IF;

        IF p_feature_snapshot IS NOT NULL THEN
            INSERT INTO public.prediction_feature_snapshots (
                prediction_id, run_id, symbol, normalized_symbol, timeframe, prediction_as_of_utc,
                reference_close_utc, quant_v2_schema_version, feature_methodology_version,
                influence_mode, no_lookahead_assertion, block_status, feature_count, degraded_count,
                provider_signature, snapshot_payload, snapshot_hash
            )
            VALUES (
                feature.prediction_id, feature.run_id, feature.symbol, feature.normalized_symbol,
                feature.timeframe, feature.prediction_as_of_utc, feature.reference_close_utc,
                feature.quant_v2_schema_version, feature.feature_methodology_version,
                feature.influence_mode, feature.no_lookahead_assertion, feature.block_status,
                feature.feature_count, feature.degraded_count, feature.provider_signature,
                feature.snapshot_payload, feature.snapshot_hash
            )
            ON CONFLICT (prediction_id) DO NOTHING;
            GET DIAGNOSTICS written = ROW_COUNT;
            IF written = 1 THEN
                feature_status := 'INSERTED';
            ELSE
                SELECT * INTO stored_feature FROM public.prediction_feature_snapshots
                WHERE prediction_id = incoming.prediction_id;
                IF ROW(
                    stored_feature.run_id, stored_feature.symbol, stored_feature.normalized_symbol,
                    stored_feature.timeframe, stored_feature.prediction_as_of_utc,
                    stored_feature.reference_close_utc, stored_feature.quant_v2_schema_version,
                    stored_feature.feature_methodology_version, stored_feature.influence_mode,
                    stored_feature.no_lookahead_assertion, stored_feature.block_status,
                    stored_feature.feature_count, stored_feature.degraded_count,
                    stored_feature.provider_signature, stored_feature.snapshot_payload,
                    stored_feature.snapshot_hash
                ) IS NOT DISTINCT FROM ROW(
                    feature.run_id, feature.symbol, feature.normalized_symbol, feature.timeframe,
                    feature.prediction_as_of_utc, feature.reference_close_utc,
                    feature.quant_v2_schema_version, feature.feature_methodology_version,
                    feature.influence_mode, feature.no_lookahead_assertion, feature.block_status,
                    feature.feature_count, feature.degraded_count, feature.provider_signature,
                    feature.snapshot_payload, feature.snapshot_hash
                ) THEN
                    feature_status := 'IDENTICAL_DUPLICATE';
                ELSE
                    feature_status := 'CONFLICT';
                    RAISE EXCEPTION 'save_prediction_bundle: refused' USING ERRCODE = 'UB9C1';
                END IF;
            END IF;
        END IF;

        IF p_derivatives_snapshot IS NOT NULL THEN
            INSERT INTO public.prediction_derivatives_snapshots (
                prediction_id, run_id, normalized_symbol, derivatives_schema_version,
                derivatives_methodology_version, influence_mode, decision_influence_frac,
                block_status, core_prediction_as_of_utc, observation_as_of_utc, snapshot_payload,
                snapshot_hash
            )
            VALUES (
                derivatives.prediction_id, derivatives.run_id, derivatives.normalized_symbol,
                derivatives.derivatives_schema_version, derivatives.derivatives_methodology_version,
                derivatives.influence_mode, derivatives.decision_influence_frac,
                derivatives.block_status, derivatives.core_prediction_as_of_utc,
                derivatives.observation_as_of_utc, derivatives.snapshot_payload,
                derivatives.snapshot_hash
            )
            ON CONFLICT (prediction_id) DO NOTHING;
            GET DIAGNOSTICS written = ROW_COUNT;
            IF written = 1 THEN
                derivatives_status := 'INSERTED';
            ELSE
                SELECT * INTO stored_derivatives FROM public.prediction_derivatives_snapshots
                WHERE prediction_id = incoming.prediction_id;
                IF ROW(
                    stored_derivatives.run_id, stored_derivatives.normalized_symbol,
                    stored_derivatives.derivatives_schema_version,
                    stored_derivatives.derivatives_methodology_version,
                    stored_derivatives.influence_mode, stored_derivatives.decision_influence_frac,
                    stored_derivatives.block_status, stored_derivatives.core_prediction_as_of_utc,
                    stored_derivatives.observation_as_of_utc, stored_derivatives.snapshot_payload,
                    stored_derivatives.snapshot_hash
                ) IS NOT DISTINCT FROM ROW(
                    derivatives.run_id, derivatives.normalized_symbol,
                    derivatives.derivatives_schema_version,
                    derivatives.derivatives_methodology_version, derivatives.influence_mode,
                    derivatives.decision_influence_frac, derivatives.block_status,
                    derivatives.core_prediction_as_of_utc, derivatives.observation_as_of_utc,
                    derivatives.snapshot_payload, derivatives.snapshot_hash
                ) THEN
                    derivatives_status := 'IDENTICAL_DUPLICATE';
                ELSE
                    derivatives_status := 'CONFLICT';
                    RAISE EXCEPTION 'save_prediction_bundle: refused' USING ERRCODE = 'UB9C1';
                END IF;
            END IF;
        END IF;
    EXCEPTION
        WHEN SQLSTATE 'UB9C1' THEN
            -- Everything this call wrote is rolled back: a prediction it had inserted is not kept.
            RETURN pg_catalog.jsonb_build_object(
                'prediction',
                CASE WHEN prediction_status = 'INSERTED' THEN 'CONFLICT' ELSE prediction_status END,
                'feature_snapshot', feature_status,
                'derivatives_snapshot', derivatives_status,
                'refused', true
            );
    END;

    RETURN pg_catalog.jsonb_build_object(
        'prediction', prediction_status,
        'feature_snapshot', feature_status,
        'derivatives_snapshot', derivatives_status,
        'refused', false
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb)
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) TO service_role;

NOTIFY pgrst, 'reload schema';
