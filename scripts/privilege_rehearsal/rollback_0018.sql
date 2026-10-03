-- The rollback of migration 0018 (migrations/0018_narrow_service_role.sql). It gives service_role back
-- exactly what 0018 revoked, table by table as migrations 0005, 0006, 0008 and 0010 left it (with
-- Supabase's default MAINTAIN on PostgreSQL 17), and EXECUTE on both bundle functions. It runs as the
-- tables' owner, in one transaction (the caller's). Against production it is a separate T4, never
-- automatic. P3-PRIV-R's D4 proves it restores the catalog exactly on scratch PostgreSQL.

GRANT INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
    public.analysis_runs,
    public.predictions,
    public.prediction_feature_snapshots,
    public.prediction_outcomes
TO service_role;
GRANT INSERT, UPDATE ON TABLE public.analysis_run_details TO service_role;
GRANT INSERT ON TABLE public.prediction_derivatives_snapshots TO service_role;

DO $$
BEGIN
    IF pg_catalog.current_setting('server_version_num')::integer >= 170000 THEN
        EXECUTE 'GRANT MAINTAIN ON TABLE public.analysis_runs, public.predictions, '
            || 'public.prediction_feature_snapshots, public.prediction_outcomes TO service_role';
    END IF;
END;
$$;

-- As the bundle functions' owner, by an INHERIT membership held for these two statements only.
GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
GRANT EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb) TO service_role;
REVOKE ucpe_bundle_owner FROM CURRENT_USER;

NOTIFY pgrst, 'reload schema';
