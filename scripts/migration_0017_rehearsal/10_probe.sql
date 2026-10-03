-- Migration 0017 rehearsal, the probe: the applied catalog, read as the tables' owner, independently of
-- the route's own post-checks. Each block raises if 0017's result is not as reviewed. Runs ONLY in a
-- scratch local PostgreSQL on a CI runner. Never run it against a real database.
DO $$
DECLARE
    wide CONSTANT text := 'public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)';
    role_name text;
    table_name text;
BEGIN
    -- W-A: exactly one function of that name, running as 0016's narrow owner, with its fixed
    -- search_path.
    IF (SELECT count(*) FROM pg_catalog.pg_proc
        WHERE pronamespace = 'public'::pg_catalog.regnamespace AND proname = 'save_forecast_bundle') <> 1 THEN
        RAISE EXCEPTION '0017 probe: save_forecast_bundle is not exactly one function';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS p JOIN pg_catalog.pg_roles AS o ON o.oid = p.proowner
        WHERE p.oid = wide::pg_catalog.regprocedure
          AND p.prosecdef AND o.rolname = 'ucpe_bundle_owner'
          AND p.proconfig = ARRAY['search_path=pg_catalog, pg_temp']
          AND p.provolatile = 'v' AND p.prorettype = 'jsonb'::pg_catalog.regtype
    ) THEN
        RAISE EXCEPTION '0017 probe: save_forecast_bundle is not SECURITY DEFINER of ucpe_bundle_owner';
    END IF;
    -- The writer and service_role may execute it, and no one else.
    IF NOT pg_catalog.has_function_privilege('ucpe_api_writer', wide, 'EXECUTE')
        OR NOT pg_catalog.has_function_privilege('service_role', wide, 'EXECUTE')
        OR pg_catalog.has_function_privilege('public', wide, 'EXECUTE')
        OR pg_catalog.has_function_privilege('anon', wide, 'EXECUTE')
        OR pg_catalog.has_function_privilege('authenticated', wide, 'EXECUTE')
        OR pg_catalog.has_function_privilege('ucpe_space_db', wide, 'EXECUTE')
        OR pg_catalog.has_function_privilege('ucpe_resolver', wide, 'EXECUTE') THEN
        RAISE EXCEPTION '0017 probe: save_forecast_bundle''s EXECUTE list is not the writer and service_role';
    END IF;
    -- W2: its owner inserts and reads the run and the detail, and never updates or deletes them.
    FOREACH table_name IN ARRAY ARRAY['analysis_runs', 'analysis_run_details'] LOOP
        IF NOT (pg_catalog.has_table_privilege('ucpe_bundle_owner', 'public.' || table_name, 'INSERT')
                AND pg_catalog.has_table_privilege('ucpe_bundle_owner', 'public.' || table_name, 'SELECT'))
            OR pg_catalog.has_table_privilege('ucpe_bundle_owner', 'public.' || table_name, 'UPDATE')
            OR pg_catalog.has_table_privilege('ucpe_bundle_owner', 'public.' || table_name, 'DELETE')
            OR pg_catalog.has_table_privilege('ucpe_bundle_owner', 'public.' || table_name, 'TRUNCATE') THEN
            RAISE EXCEPTION '0017 probe: ucpe_bundle_owner does not hold exactly INSERT and SELECT on %', table_name;
        END IF;
    END LOOP;
    -- One permissive policy per grant: 0016's 40 plus 0017's 4, each for ucpe_bundle_owner alone.
    IF (SELECT count(*) FROM pg_catalog.pg_policies
        WHERE schemaname = 'public'
          AND roles && ARRAY['ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver']::name[]) <> 44 THEN
        RAISE EXCEPTION '0017 probe: the new roles do not hold exactly 44 policies';
    END IF;
    IF (SELECT count(*) FROM pg_catalog.pg_policies
        WHERE schemaname = 'public' AND tablename IN ('analysis_runs', 'analysis_run_details')
          AND policyname IN ('ucpe_bundle_owner_select', 'ucpe_bundle_owner_insert')
          AND roles = ARRAY['ucpe_bundle_owner']::name[] AND permissive = 'PERMISSIVE') <> 4 THEN
        RAISE EXCEPTION '0017 probe: the four policies of ucpe_bundle_owner are not as reviewed';
    END IF;
    -- Migration 0015's bundle RPC is untouched: still SECURITY DEFINER of ucpe_bundle_owner.
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS p JOIN pg_catalog.pg_roles AS o ON o.oid = p.proowner
        WHERE p.oid = 'public.save_prediction_bundle(jsonb, jsonb, jsonb)'::pg_catalog.regprocedure
          AND p.prosecdef AND o.rolname = 'ucpe_bundle_owner'
    ) THEN
        RAISE EXCEPTION '0017 probe: the bundle RPC is no longer SECURITY DEFINER of ucpe_bundle_owner';
    END IF;
    -- The owner change's temporary powers are gone: no new role may create in schema public, and the
    -- applying role may not switch to ucpe_bundle_owner.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles AS r
        WHERE r.rolname IN ('ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver')
          AND pg_catalog.has_schema_privilege(r.oid, 'public', 'CREATE')
    ) THEN
        RAISE EXCEPTION '0017 probe: a new role may create in schema public';
    END IF;
    IF pg_catalog.pg_has_role(current_user, 'ucpe_bundle_owner', 'SET') THEN
        RAISE EXCEPTION '0017 probe: the applying role may still switch to ucpe_bundle_owner';
    END IF;
    -- PostgREST still switches to the writer only.
    IF NOT pg_catalog.pg_has_role('authenticator', 'ucpe_api_writer', 'SET') THEN
        RAISE EXCEPTION '0017 probe: authenticator no longer switches to the writer';
    END IF;
    FOREACH role_name IN ARRAY ARRAY['ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver'] LOOP
        IF pg_catalog.pg_has_role('authenticator', role_name, 'SET') THEN
            RAISE EXCEPTION '0017 probe: authenticator may switch to %', role_name;
        END IF;
    END LOOP;
    -- The writer still has no direct write to core evidence or labels.
    FOREACH table_name IN ARRAY ARRAY['predictions', 'prediction_feature_snapshots',
                                      'prediction_derivatives_snapshots', 'prediction_outcomes'] LOOP
        IF pg_catalog.has_table_privilege('ucpe_api_writer', 'public.' || table_name, 'INSERT')
            OR pg_catalog.has_table_privilege('ucpe_api_writer', 'public.' || table_name, 'UPDATE') THEN
            RAISE EXCEPTION '0017 probe: the writer may write %', table_name;
        END IF;
    END LOOP;
    -- Correction 01: the Space role's live F1/UOR registry (read) and ledger (read, insert, update)
    -- grants are untouched, and nothing more on them.
    IF NOT (pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_credential', 'SELECT')
            AND pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_radar_ledger', 'SELECT')
            AND pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_radar_ledger', 'INSERT')
            AND pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_radar_ledger', 'UPDATE'))
        OR pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_credential', 'UPDATE')
        OR pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_credential', 'INSERT') THEN
        RAISE EXCEPTION '0017 probe: the Space role does not hold exactly the F1/UOR grants';
    END IF;
    -- Nothing existing was revoked: the live writer's service_role keeps its rights.
    IF NOT (pg_catalog.has_table_privilege('service_role', 'public.analysis_runs', 'INSERT')
            AND pg_catalog.has_table_privilege('service_role', 'public.analysis_runs', 'SELECT')
            AND pg_catalog.has_table_privilege('service_role', 'public.predictions', 'INSERT')) THEN
        RAISE EXCEPTION '0017 probe: service_role lost a right';
    END IF;
END;
$$;
