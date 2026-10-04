-- Migration 0018 rehearsal, the probe: the applied catalog, read as the tables' owner, independently of
-- the route's own post-checks. Each block raises if 0018's result is not as reviewed. Runs ONLY in a
-- scratch local PostgreSQL on a CI runner. Never run it against a real database.
DO $$
DECLARE
    core CONSTANT text[] := ARRAY['analysis_runs', 'analysis_run_details', 'predictions',
        'prediction_feature_snapshots', 'prediction_derivatives_snapshots', 'prediction_outcomes'];
    writes CONSTANT text[] := ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'];
    bundle CONSTANT text := 'public.save_prediction_bundle(jsonb, jsonb, jsonb)';
    wide CONSTANT text := 'public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)';
    table_name text;
    privilege text;
BEGIN
    -- D6: service_role keeps SELECT and holds no write privilege on any core table, by table or column.
    FOREACH table_name IN ARRAY core LOOP
        IF NOT pg_catalog.has_table_privilege('service_role', 'public.' || table_name, 'SELECT') THEN
            RAISE EXCEPTION '0018 probe: service_role lost SELECT on %', table_name;
        END IF;
        FOREACH privilege IN ARRAY writes LOOP
            IF pg_catalog.has_table_privilege('service_role', 'public.' || table_name, privilege) THEN
                RAISE EXCEPTION '0018 probe: service_role still holds % on %', privilege, table_name;
            END IF;
        END LOOP;
        IF pg_catalog.has_any_column_privilege(
            'service_role', 'public.' || table_name, 'INSERT, UPDATE, REFERENCES') THEN
            RAISE EXCEPTION '0018 probe: service_role still holds a column write privilege on %', table_name;
        END IF;
    END LOOP;
    -- Neither bundle function is executable by service_role; their owner and the writer still are.
    IF pg_catalog.has_function_privilege('service_role', bundle, 'EXECUTE')
        OR pg_catalog.has_function_privilege('service_role', wide, 'EXECUTE') THEN
        RAISE EXCEPTION '0018 probe: service_role may still execute a bundle function';
    END IF;
    IF NOT pg_catalog.has_function_privilege('ucpe_api_writer', bundle, 'EXECUTE')
        OR NOT pg_catalog.has_function_privilege('ucpe_api_writer', wide, 'EXECUTE')
        OR NOT pg_catalog.has_function_privilege('ucpe_bundle_owner', bundle, 'EXECUTE')
        OR NOT pg_catalog.has_function_privilege('ucpe_bundle_owner', wide, 'EXECUTE') THEN
        RAISE EXCEPTION '0018 probe: the writer or the owner lost EXECUTE on a bundle function';
    END IF;
    -- The temporary ownership grant is gone: the applying role no longer inherits ucpe_bundle_owner.
    IF pg_catalog.pg_has_role(current_user, 'ucpe_bundle_owner', 'USAGE') THEN
        RAISE EXCEPTION '0018 probe: the applying role still inherits ucpe_bundle_owner';
    END IF;
    -- The least-privilege roles keep their grants: the bundle owner inserts core evidence, the
    -- resolver inserts outcomes, and the writer reads predictions and writes them only through the RPC.
    IF NOT pg_catalog.has_table_privilege('ucpe_bundle_owner', 'public.predictions', 'INSERT')
        OR NOT pg_catalog.has_table_privilege('ucpe_resolver', 'public.prediction_outcomes', 'INSERT')
        OR NOT pg_catalog.has_table_privilege('ucpe_api_writer', 'public.predictions', 'SELECT')
        OR pg_catalog.has_table_privilege('ucpe_api_writer', 'public.predictions', 'INSERT') THEN
        RAISE EXCEPTION '0018 probe: a least-privilege role''s grants changed';
    END IF;
    -- G1's login is untouched, and the writer and the bundle owner still never log in.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'ucpe_resolver' AND rolcanlogin)
        OR EXISTS (SELECT 1 FROM pg_catalog.pg_roles
                   WHERE rolname IN ('ucpe_api_writer', 'ucpe_bundle_owner') AND rolcanlogin) THEN
        RAISE EXCEPTION '0018 probe: a least-privilege role''s login changed';
    END IF;
    -- 0016's 40 policies and 0017's 4 are untouched.
    IF (SELECT count(*) FROM pg_catalog.pg_policies
        WHERE schemaname = 'public'
          AND roles && ARRAY['ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver']::name[]) <> 44 THEN
        RAISE EXCEPTION '0018 probe: the new roles do not hold exactly 44 policies';
    END IF;
    -- service_role keeps its privileges outside D6's scope (the watchlist, for one).
    IF NOT pg_catalog.has_table_privilege('service_role', 'public.watchlist', 'INSERT') THEN
        RAISE EXCEPTION '0018 probe: service_role lost a privilege outside D6''s scope';
    END IF;
END;
$$;
