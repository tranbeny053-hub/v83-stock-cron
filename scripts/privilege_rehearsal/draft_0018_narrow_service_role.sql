-- DRAFT of migration 0018: Phase 3, the privilege design's step D6. NOT A MIGRATION, NOT APPLIED.
--
-- It lives in scripts/privilege_rehearsal/, outside migrations/, so release check 5c ignores it.
-- THE RULING (the owner, 2026-10-03): "D6 timing=B after the next release; scope=six core evidence
-- tables + two bundle functions, keep SELECT and revoke write/EXECUTE, with deterministic inventory
-- proving no omitted core write surface before freeze." Freezing it (into migrations/, with its
-- one-shot route) comes after the next release, and only once scripts/core_write_inventory.py, run
-- read-only against production with --expect before, finds no core write surface outside this file.
--
-- service_role LOSES:
-- - INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES and TRIGGER (and MAINTAIN on PostgreSQL 17) on the
--   six core evidence tables: analysis_runs, analysis_run_details, predictions,
--   prediction_feature_snapshots, prediction_derivatives_snapshots, prediction_outcomes. A table
--   REVOKE also revokes the matching column privileges;
-- - EXECUTE on the two bundle functions, save_prediction_bundle and save_forecast_bundle.
-- service_role KEEPS SELECT on them, so a leaked key only reads. Nothing else changes: anon,
-- authenticated and the ucpe_* roles keep exactly what they hold.
-- - A second application is refused before any change (SQLSTATE UP018).
-- - The rollback is scripts/privilege_rehearsal/rollback_0018.sql. P3-PRIV-R's D4 proves it exact.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'ucpe_bundle_owner')
       OR pg_catalog.to_regprocedure('public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)') IS NULL
    THEN
        RAISE EXCEPTION 'draft 0018: migrations 0016 and 0017 must be applied first' USING ERRCODE = 'UP018';
    END IF;
    IF NOT pg_catalog.has_table_privilege('service_role', 'public.predictions', 'INSERT') THEN
        RAISE EXCEPTION 'draft 0018: service_role already cannot write core evidence; a second application is refused'
            USING ERRCODE = 'UP018';
    END IF;
END;
$$;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
    public.analysis_runs,
    public.analysis_run_details,
    public.predictions,
    public.prediction_feature_snapshots,
    public.prediction_derivatives_snapshots,
    public.prediction_outcomes
FROM service_role;

-- MAINTAIN exists from PostgreSQL 17 (production runs 17.6; the rehearsal 16).
DO $$
BEGIN
    IF pg_catalog.current_setting('server_version_num')::integer >= 170000 THEN
        EXECUTE 'REVOKE MAINTAIN ON TABLE public.analysis_runs, public.analysis_run_details, '
            || 'public.predictions, public.prediction_feature_snapshots, '
            || 'public.prediction_derivatives_snapshots, public.prediction_outcomes FROM service_role';
    END IF;
END;
$$;

-- The bundle functions belong to ucpe_bundle_owner (W2): their EXECUTE is revoked as their owner, by an
-- INHERIT membership held for these two statements only.
GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
REVOKE EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) FROM service_role;
REVOKE EXECUTE ON FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb) FROM service_role;
REVOKE ucpe_bundle_owner FROM CURRENT_USER;

NOTIFY pgrst, 'reload schema';
