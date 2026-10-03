-- Migration 0016 rehearsal, the probe: the applied catalog, read as the tables' owner, independently of
-- the route's own post-checks. Each block raises if 0016's result is not as reviewed. Runs ONLY in a
-- scratch local PostgreSQL on a CI runner. Never run it against a real database.
DO $$
DECLARE
    role_name text;
BEGIN
    -- The four roles, with no power at all.
    IF (SELECT count(*) FROM pg_catalog.pg_roles
        WHERE rolname IN ('ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver')
          AND NOT rolsuper AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolcanlogin AND NOT rolreplication AND NOT rolbypassrls) <> 4 THEN
        RAISE EXCEPTION '0016 probe: the four roles are not exactly as reviewed';
    END IF;
    -- PostgREST may switch to the writer, without inheriting it, and to no other new role.
    IF NOT pg_catalog.pg_has_role('authenticator', 'ucpe_api_writer', 'SET')
        OR pg_catalog.pg_has_role('authenticator', 'ucpe_api_writer', 'USAGE') THEN
        RAISE EXCEPTION '0016 probe: authenticator does not switch to the writer as reviewed';
    END IF;
    FOREACH role_name IN ARRAY ARRAY['ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver'] LOOP
        IF pg_catalog.pg_has_role('authenticator', role_name, 'SET') THEN
            RAISE EXCEPTION '0016 probe: authenticator may switch to %', role_name;
        END IF;
    END LOOP;
    -- W2: the bundle RPC runs as its narrow owner, with its fixed search_path.
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS p JOIN pg_catalog.pg_roles AS o ON o.oid = p.proowner
        WHERE p.oid = 'public.save_prediction_bundle(jsonb, jsonb, jsonb)'::pg_catalog.regprocedure
          AND p.prosecdef AND o.rolname = 'ucpe_bundle_owner'
          AND p.proconfig = ARRAY['search_path=pg_catalog, pg_temp']
    ) THEN
        RAISE EXCEPTION '0016 probe: the bundle RPC is not SECURITY DEFINER of ucpe_bundle_owner';
    END IF;
    IF NOT pg_catalog.has_function_privilege('ucpe_api_writer', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE')
        OR NOT pg_catalog.has_function_privilege('service_role', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE')
        OR pg_catalog.has_function_privilege('public', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE')
        OR pg_catalog.has_function_privilege('anon', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE')
        OR pg_catalog.has_function_privilege('authenticated', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE')
        OR pg_catalog.has_function_privilege('ucpe_space_db', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE')
        OR pg_catalog.has_function_privilege('ucpe_resolver', 'public.save_prediction_bundle(jsonb, jsonb, jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION '0016 probe: the bundle RPC''s EXECUTE list is not the writer and service_role';
    END IF;
    -- One permissive policy per grant: 40.
    IF (SELECT count(*) FROM pg_catalog.pg_policies
        WHERE schemaname = 'public'
          AND roles && ARRAY['ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver']::name[]) <> 40 THEN
        RAISE EXCEPTION '0016 probe: the new roles do not hold exactly 40 policies';
    END IF;
    -- Correction 01: the Space role keeps the live F1/UOR registry (read) and ledger (read, insert,
    -- update), and nothing more on them.
    IF NOT (pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_credential', 'SELECT')
            AND pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_radar_ledger', 'SELECT')
            AND pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_radar_ledger', 'INSERT')
            AND pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_radar_ledger', 'UPDATE'))
        OR pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_credential', 'UPDATE')
        OR pg_catalog.has_table_privilege('ucpe_space_db', 'public.automation_credential', 'INSERT') THEN
        RAISE EXCEPTION '0016 probe: the Space role does not hold exactly the F1/UOR grants';
    END IF;
    -- W2: the writer has no direct write to core evidence or labels.
    FOREACH role_name IN ARRAY ARRAY['predictions', 'prediction_feature_snapshots',
                                     'prediction_derivatives_snapshots', 'prediction_outcomes'] LOOP
        IF pg_catalog.has_table_privilege('ucpe_api_writer', 'public.' || role_name, 'INSERT')
            OR pg_catalog.has_table_privilege('ucpe_api_writer', 'public.' || role_name, 'UPDATE') THEN
            RAISE EXCEPTION '0016 probe: the writer may write %', role_name;
        END IF;
    END LOOP;
    -- Nothing existing was revoked: the live writer's service_role keeps its rights.
    IF NOT (pg_catalog.has_table_privilege('service_role', 'public.predictions', 'INSERT')
            AND pg_catalog.has_table_privilege('service_role', 'public.predictions', 'SELECT')) THEN
        RAISE EXCEPTION '0016 probe: service_role lost a right on predictions';
    END IF;
    -- No new role may create in schema public.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles AS r
        WHERE r.rolname IN ('ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver')
          AND pg_catalog.has_schema_privilege(r.oid, 'public', 'CREATE')
    ) THEN
        RAISE EXCEPTION '0016 probe: a new role may create in schema public';
    END IF;
END;
$$;
