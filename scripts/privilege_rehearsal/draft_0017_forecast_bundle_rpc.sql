-- P3-W-A: the DRAFT of migration 0017, plan §8.1's whole core bundle in ONE transaction
-- (.work/roadmap/phase3/WIDER_BUNDLE_DESIGN.md, option W-A).
--
-- NOT A MIGRATION. This file lives outside migrations/, so no route applies it to a real database, and
-- release check 5c ignores it. scripts/privilege_rehearsal/rehearse.py applies it ONLY to a scratch
-- PostgreSQL on a CI runner, after the draft of 0016 (it needs W2's ucpe_bundle_owner). If the owner
-- approves it (WB1), migration 0017 becomes these bytes under its own one-shot apply route (a T4).
--
-- ONE FUNCTION: public.save_forecast_bundle(p_run, p_prediction, p_feature_snapshot,
-- p_derivatives_snapshot, p_run_detail). In one transaction it writes:
-- - **the run identity** (analysis_runs). It is inserted, or compared with the stored row on every column
--   but persistence_status, a scheduling-time hint the first write keeps. A different stored run is a
--   CONFLICT;
-- - **the required detail payload**, when given (analysis_run_details, USER_REQUESTED analyses). It is
--   inserted, or compared on (analysis_hash, detail_payload). Different content is a CONFLICT;
-- - **the forecast bundle**, through migration 0015's unchanged public.save_prediction_bundle: the
--   prediction and its snapshots, inserted or compared.
--
-- ANY CONFLICT refuses the call: everything it wrote is rolled back, and the answer says so
-- ("refused": true). Any error fails the request with nothing written. It only INSERTs and SELECTs,
-- so no UPDATE privilege is needed, and 0014's append-only triggers never fire.
--
-- SECURITY:
-- - SECURITY DEFINER, owned by ucpe_bundle_owner (W2), which holds only INSERT and SELECT on what the
--   function writes, each with its policy;
-- - a fixed search_path, with every object qualified (§8.2);
-- - EXECUTE for ucpe_api_writer and, until step D6, service_role. Never PUBLIC, anon or authenticated.
-- It runs as the tables' owner, in one transaction (the caller's), and refuses a second application.

DO $$
BEGIN
    IF pg_catalog.to_regprocedure('public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)') IS NOT NULL THEN
        RAISE EXCEPTION 'draft 0017: save_forecast_bundle already exists; a second application is refused'
            USING ERRCODE = 'UP017';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles o ON o.oid = p.proowner
        WHERE p.oid = 'public.save_prediction_bundle(jsonb, jsonb, jsonb)'::pg_catalog.regprocedure
          AND p.prosecdef AND o.rolname = 'ucpe_bundle_owner'
    ) THEN
        RAISE EXCEPTION 'draft 0017: needs 0016 with W2 (the bundle RPC as definer of ucpe_bundle_owner)'
            USING ERRCODE = 'UP017';
    END IF;
END;
$$;

CREATE FUNCTION public.save_forecast_bundle(
    p_run jsonb,
    p_prediction jsonb,
    p_feature_snapshot jsonb DEFAULT NULL,
    p_derivatives_snapshot jsonb DEFAULT NULL,
    p_run_detail jsonb DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    run_keys CONSTANT text[] := ARRAY[
        'run_id', 'operator_id', 'symbol', 'normalized_symbol', 'analysis_mode', 'asset_class',
        'primary_timeframe', 'disposition', 'total_score', 'data_source', 'is_live_data',
        'persistence_status', 'analysis_hash', 'as_of_utc'
    ];
    detail_keys CONSTANT text[] := ARRAY['run_id', 'analysis_hash', 'detail_payload'];
    run public.analysis_runs;
    stored_run public.analysis_runs;
    detail public.analysis_run_details;
    stored_detail public.analysis_run_details;
    run_status text;
    detail_status text;
    bundle jsonb;
    written integer;
BEGIN
    IF p_run_detail = 'null'::jsonb THEN
        p_run_detail := NULL;
    END IF;
    IF pg_catalog.jsonb_typeof(p_run) IS DISTINCT FROM 'object'
        OR pg_catalog.jsonb_typeof(p_prediction) IS DISTINCT FROM 'object'
        OR (p_run_detail IS NOT NULL AND pg_catalog.jsonb_typeof(p_run_detail) <> 'object') THEN
        RAISE EXCEPTION 'save_forecast_bundle: every row must be a JSON object' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(p_run) AS k(key) WHERE k.key <> ALL (run_keys)
    ) OR (p_run_detail IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(p_run_detail) AS k(key) WHERE k.key <> ALL (detail_keys)
    )) THEN
        RAISE EXCEPTION 'save_forecast_bundle: a row carries a key that is not its column'
            USING ERRCODE = '22023';
    END IF;

    run := pg_catalog.jsonb_populate_record(NULL::public.analysis_runs, p_run);
    IF run.run_id IS NULL OR pg_catalog.btrim(run.run_id) = '' THEN
        RAISE EXCEPTION 'save_forecast_bundle: the run has no id' USING ERRCODE = '22023';
    END IF;
    IF (p_prediction ->> 'run_id') IS DISTINCT FROM run.run_id THEN
        RAISE EXCEPTION 'save_forecast_bundle: the prediction belongs to another run' USING ERRCODE = '22023';
    END IF;
    IF p_run_detail IS NOT NULL THEN
        detail := pg_catalog.jsonb_populate_record(NULL::public.analysis_run_details, p_run_detail);
        IF detail.run_id IS DISTINCT FROM run.run_id THEN
            RAISE EXCEPTION 'save_forecast_bundle: the detail belongs to another run' USING ERRCODE = '22023';
        END IF;
    END IF;

    BEGIN
        INSERT INTO public.analysis_runs (
            run_id, operator_id, symbol, normalized_symbol, analysis_mode, asset_class,
            primary_timeframe, disposition, total_score, data_source, is_live_data,
            persistence_status, analysis_hash, as_of_utc
        )
        VALUES (
            run.run_id, run.operator_id, run.symbol, run.normalized_symbol, run.analysis_mode,
            run.asset_class, run.primary_timeframe, run.disposition, run.total_score, run.data_source,
            run.is_live_data, run.persistence_status, run.analysis_hash, run.as_of_utc
        )
        ON CONFLICT (run_id) DO NOTHING;
        GET DIAGNOSTICS written = ROW_COUNT;
        IF written = 1 THEN
            run_status := 'INSERTED';
        ELSE
            SELECT * INTO stored_run FROM public.analysis_runs WHERE run_id = run.run_id;
            IF ROW(
                stored_run.operator_id, stored_run.symbol, stored_run.normalized_symbol,
                stored_run.analysis_mode, stored_run.asset_class, stored_run.primary_timeframe,
                stored_run.disposition, stored_run.total_score, stored_run.data_source,
                stored_run.is_live_data, stored_run.analysis_hash, stored_run.as_of_utc
            ) IS NOT DISTINCT FROM ROW(
                run.operator_id, run.symbol, run.normalized_symbol, run.analysis_mode,
                run.asset_class, run.primary_timeframe, run.disposition, run.total_score,
                run.data_source, run.is_live_data, run.analysis_hash, run.as_of_utc
            ) THEN
                run_status := 'IDENTICAL_DUPLICATE';
            ELSE
                run_status := 'CONFLICT';
                RAISE EXCEPTION 'save_forecast_bundle: refused' USING ERRCODE = 'UB9C1';
            END IF;
        END IF;

        IF p_run_detail IS NOT NULL THEN
            INSERT INTO public.analysis_run_details (run_id, analysis_hash, detail_payload)
            VALUES (detail.run_id, detail.analysis_hash, detail.detail_payload)
            ON CONFLICT (run_id) DO NOTHING;
            GET DIAGNOSTICS written = ROW_COUNT;
            IF written = 1 THEN
                detail_status := 'INSERTED';
            ELSE
                SELECT * INTO stored_detail FROM public.analysis_run_details WHERE run_id = run.run_id;
                IF ROW(stored_detail.analysis_hash, stored_detail.detail_payload)
                    IS NOT DISTINCT FROM ROW(detail.analysis_hash, detail.detail_payload) THEN
                    detail_status := 'IDENTICAL_DUPLICATE';
                ELSE
                    detail_status := 'CONFLICT';
                    RAISE EXCEPTION 'save_forecast_bundle: refused' USING ERRCODE = 'UB9C1';
                END IF;
            END IF;
        END IF;

        -- Migration 0015's function, unchanged. Its own refusal rolls back only its own writes, so a
        -- refusal there is raised again here, and the run and the detail go with it.
        bundle := public.save_prediction_bundle(p_prediction, p_feature_snapshot, p_derivatives_snapshot);
        IF (bundle ->> 'refused')::boolean THEN
            RAISE EXCEPTION 'save_forecast_bundle: refused' USING ERRCODE = 'UB9C1';
        END IF;
    EXCEPTION
        WHEN SQLSTATE 'UB9C1' THEN
            -- Everything this call wrote is rolled back. A part it had inserted is reported as not kept.
            RETURN pg_catalog.jsonb_build_object(
                'run', CASE WHEN run_status = 'INSERTED' THEN 'NOT_KEPT' ELSE run_status END,
                'run_detail', CASE WHEN detail_status = 'INSERTED' THEN 'NOT_KEPT' ELSE detail_status END,
                'prediction', bundle -> 'prediction',
                'feature_snapshot', bundle -> 'feature_snapshot',
                'derivatives_snapshot', bundle -> 'derivatives_snapshot',
                'refused', true
            );
    END;

    RETURN pg_catalog.jsonb_build_object(
        'run', run_status,
        'run_detail', detail_status,
        'prediction', bundle -> 'prediction',
        'feature_snapshot', bundle -> 'feature_snapshot',
        'derivatives_snapshot', bundle -> 'derivatives_snapshot',
        'refused', false
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)
TO ucpe_api_writer, service_role;

-- W2: what the function's body writes, for its narrow owner. Insert and read back; never update.
GRANT SELECT, INSERT ON TABLE public.analysis_runs, public.analysis_run_details TO ucpe_bundle_owner;
CREATE POLICY ucpe_bundle_owner_select ON public.analysis_runs FOR SELECT TO ucpe_bundle_owner USING (true);
CREATE POLICY ucpe_bundle_owner_insert ON public.analysis_runs FOR INSERT TO ucpe_bundle_owner WITH CHECK (true);
CREATE POLICY ucpe_bundle_owner_select ON public.analysis_run_details FOR SELECT TO ucpe_bundle_owner USING (true);
CREATE POLICY ucpe_bundle_owner_insert ON public.analysis_run_details FOR INSERT TO ucpe_bundle_owner WITH CHECK (true);

-- The owner change, as in 0016: SET ROLE to the new owner, and its CREATE on the schema, for that one
-- statement only.
GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
GRANT CREATE ON SCHEMA public TO ucpe_bundle_owner;
ALTER FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb) OWNER TO ucpe_bundle_owner;
REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner;
REVOKE ucpe_bundle_owner FROM CURRENT_USER;

NOTIFY pgrst, 'reload schema';
