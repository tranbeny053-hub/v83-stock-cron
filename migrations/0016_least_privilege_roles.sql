-- Phase 3: the least-privilege roles (governing plan §8.2, "separate migration/runtime/jobs authority").
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action that needs owner authorization. It goes
-- through its own one-shot route, scripts/apply_migration_0016.py. The bulk scripts/apply_migrations.py
-- applies EVERY migration and must never be used for it.
--
-- THE RULING. The owner ruled E1 = YES, option W2, on 2026-10-03. The design is
-- .work/roadmap/phase3/PRIVILEGE_AUDIT_AND_DESIGN.md with its Correction 01: the Space's direct
-- Postgres also serves the live F1/UOR credential registry and ledger, so its role keeps exactly what
-- they need. Everything below the header is byte-for-byte what P3-PRIV-R rehearsed. That rehearsal ran
-- production's own code under each role, behind a real PostgREST (v14.18 and v16.4), with criteria
-- P1-P8 (scripts/privilege_rehearsal/rehearse.py).
--
-- THE ROLES. Every one is NOINHERIT, and none has SUPERUSER, CREATEDB, CREATEROLE, REPLICATION or
-- BYPASSRLS:
-- - ucpe_api_writer (NOLOGIN): the REST runtime. PostgREST's authenticator switches to it from a writer
--   JWT, and to no other role this file creates.
-- - ucpe_bundle_owner (NOLOGIN): owns the bundle RPC, which now runs SECURITY DEFINER as it (W2). So the
--   runtime has no direct INSERT path to core evidence.
-- - ucpe_space_db (NOLOGIN until the owner's credential step): the Space's direct Postgres. That is the
--   calibration endpoint, the skill-evidence refresh, and the live F1/UOR registry (SELECT) and ledger
--   (SELECT, INSERT, UPDATE).
-- - ucpe_resolver (NOLOGIN until the owner's credential step): the hourly resolver.
--
-- THE GRANTS. Every grant has a matching permissive policy for the same role and command. Row-level
-- security stays on everywhere, so every other role stays denied.
--
-- NOTHING EXISTING IS REVOKED. service_role, anon and authenticated keep exactly what they hold, so the
-- live writer keeps working (P6; step D6 narrows service_role later). The bundle RPC changes owner and
-- becomes SECURITY DEFINER. Its body, its fixed search_path and service_role's EXECUTE are unchanged.
--
-- APPLYING IT:
-- - It runs as the tables' owner, in the route's single transaction.
-- - The applying role needs CREATEROLE (Supabase's postgres has it) or SUPERUSER, and must own the
--   bundle RPC. PostgreSQL 16 or later is needed, for the GRANT ... WITH INHERIT/SET options.
-- - A second application is refused before any change (SQLSTATE UP016). The route refuses one even
--   earlier, as "not a first apply".
-- - The rollback is a separate T4, never automatic: scripts/privilege_rehearsal/rollback_0016.sql. P8
--   proves it restores the catalog exactly.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname IN ('ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver')
    ) THEN
        RAISE EXCEPTION 'draft 0016: a least-privilege role already exists; a second application is refused'
            USING ERRCODE = 'UP016';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'authenticator') THEN
        RAISE EXCEPTION 'draft 0016: PostgREST''s authenticator role is missing' USING ERRCODE = 'UP016';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = current_user AND (rolcreaterole OR rolsuper)
    ) THEN
        RAISE EXCEPTION 'draft 0016: the applying role needs CREATEROLE' USING ERRCODE = 'UP016';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc
        WHERE oid = 'public.save_prediction_bundle(jsonb, jsonb, jsonb)'::pg_catalog.regprocedure
          AND NOT prosecdef
          AND proowner = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
    ) THEN
        RAISE EXCEPTION 'draft 0016: the bundle RPC is not migration 0015''s invoker function owned by the applying role'
            USING ERRCODE = 'UP016';
    END IF;
END;
$$;

CREATE ROLE ucpe_api_writer NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ucpe_bundle_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ucpe_space_db NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ucpe_resolver NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- PostgREST switches to the writer, and never inherits its privileges.
GRANT ucpe_api_writer TO authenticator WITH INHERIT FALSE, SET TRUE;

GRANT USAGE ON SCHEMA public TO ucpe_api_writer, ucpe_bundle_owner, ucpe_space_db, ucpe_resolver;

-- C1, ucpe_api_writer: exactly what the REST runtime requests (persistence/repository.py, SupabaseRestRepository).
-- The run identity, detail and news rows are upserts (PostgREST merge-duplicates).
GRANT SELECT, INSERT, UPDATE ON TABLE
    public.analysis_runs, public.analysis_run_details,
    public.news_items, public.news_clusters, public.news_evidence_links
    TO ucpe_api_writer;
GRANT INSERT ON TABLE public.analysis_timeframe_results, public.provider_observations TO ucpe_api_writer;
GRANT USAGE ON SEQUENCE
    public.analysis_timeframe_results_id_seq, public.provider_observations_id_seq
    TO ucpe_api_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.watchlist TO ucpe_api_writer;
-- History and detail read predictions. Writing them goes only through the bundle RPC (W2).
GRANT SELECT ON TABLE public.predictions TO ucpe_api_writer;

CREATE POLICY ucpe_api_writer_select ON public.analysis_runs FOR SELECT TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_insert ON public.analysis_runs FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_update ON public.analysis_runs FOR UPDATE TO ucpe_api_writer USING (true) WITH CHECK (true);
CREATE POLICY ucpe_api_writer_select ON public.analysis_run_details FOR SELECT TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_insert ON public.analysis_run_details FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_update ON public.analysis_run_details FOR UPDATE TO ucpe_api_writer USING (true) WITH CHECK (true);
CREATE POLICY ucpe_api_writer_select ON public.news_items FOR SELECT TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_insert ON public.news_items FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_update ON public.news_items FOR UPDATE TO ucpe_api_writer USING (true) WITH CHECK (true);
CREATE POLICY ucpe_api_writer_select ON public.news_clusters FOR SELECT TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_insert ON public.news_clusters FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_update ON public.news_clusters FOR UPDATE TO ucpe_api_writer USING (true) WITH CHECK (true);
CREATE POLICY ucpe_api_writer_select ON public.news_evidence_links FOR SELECT TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_insert ON public.news_evidence_links FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_update ON public.news_evidence_links FOR UPDATE TO ucpe_api_writer USING (true) WITH CHECK (true);
CREATE POLICY ucpe_api_writer_insert ON public.analysis_timeframe_results FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_insert ON public.provider_observations FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_select ON public.watchlist FOR SELECT TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_insert ON public.watchlist FOR INSERT TO ucpe_api_writer WITH CHECK (true);
CREATE POLICY ucpe_api_writer_update ON public.watchlist FOR UPDATE TO ucpe_api_writer USING (true) WITH CHECK (true);
CREATE POLICY ucpe_api_writer_delete ON public.watchlist FOR DELETE TO ucpe_api_writer USING (true);
CREATE POLICY ucpe_api_writer_select ON public.predictions FOR SELECT TO ucpe_api_writer USING (true);

-- W2, ucpe_bundle_owner: what the bundle RPC's unchanged body does. It inserts, and reads back to compare.
GRANT SELECT, INSERT ON TABLE
    public.predictions, public.prediction_feature_snapshots, public.prediction_derivatives_snapshots
    TO ucpe_bundle_owner;
CREATE POLICY ucpe_bundle_owner_select ON public.predictions FOR SELECT TO ucpe_bundle_owner USING (true);
CREATE POLICY ucpe_bundle_owner_insert ON public.predictions FOR INSERT TO ucpe_bundle_owner WITH CHECK (true);
CREATE POLICY ucpe_bundle_owner_select ON public.prediction_feature_snapshots FOR SELECT TO ucpe_bundle_owner USING (true);
CREATE POLICY ucpe_bundle_owner_insert ON public.prediction_feature_snapshots FOR INSERT TO ucpe_bundle_owner WITH CHECK (true);
CREATE POLICY ucpe_bundle_owner_select ON public.prediction_derivatives_snapshots FOR SELECT TO ucpe_bundle_owner USING (true);
CREATE POLICY ucpe_bundle_owner_insert ON public.prediction_derivatives_snapshots FOR INSERT TO ucpe_bundle_owner WITH CHECK (true);

-- The bundle RPC: EXECUTE for the writer, then SECURITY DEFINER, owned by ucpe_bundle_owner. Its body, its
-- fixed search_path (pg_catalog, pg_temp) and service_role's EXECUTE are unchanged. PostgreSQL lets the
-- owner change only if the applying role can SET ROLE to the new owner, and the new owner holds CREATE on
-- the schema. Both are granted for that one statement and revoked straight after it.
GRANT EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) TO ucpe_api_writer;
ALTER FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) SECURITY DEFINER;
GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
GRANT CREATE ON SCHEMA public TO ucpe_bundle_owner;
ALTER FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) OWNER TO ucpe_bundle_owner;
REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner;
REVOKE ucpe_bundle_owner FROM CURRENT_USER;

-- C2 with Correction 01, ucpe_space_db: the calibration query (predictions JOIN prediction_outcomes), the
-- F1 registry (SELECT), and the F1 ledger (SELECT ... FOR UPDATE, INSERT, UPDATE ... RETURNING; it never deletes).
GRANT SELECT ON TABLE public.predictions, public.prediction_outcomes, public.automation_credential TO ucpe_space_db;
GRANT SELECT, INSERT, UPDATE ON TABLE public.automation_radar_ledger TO ucpe_space_db;
CREATE POLICY ucpe_space_db_select ON public.predictions FOR SELECT TO ucpe_space_db USING (true);
CREATE POLICY ucpe_space_db_select ON public.prediction_outcomes FOR SELECT TO ucpe_space_db USING (true);
CREATE POLICY ucpe_space_db_select ON public.automation_credential FOR SELECT TO ucpe_space_db USING (true);
CREATE POLICY ucpe_space_db_select ON public.automation_radar_ledger FOR SELECT TO ucpe_space_db USING (true);
CREATE POLICY ucpe_space_db_insert ON public.automation_radar_ledger FOR INSERT TO ucpe_space_db WITH CHECK (true);
CREATE POLICY ucpe_space_db_update ON public.automation_radar_ledger FOR UPDATE TO ucpe_space_db USING (true) WITH CHECK (true);

-- C3, ucpe_resolver: the due scans, the append-only outcome insert, and the status upsert.
GRANT SELECT ON TABLE public.predictions TO ucpe_resolver;
GRANT SELECT, INSERT ON TABLE public.prediction_outcomes TO ucpe_resolver;
GRANT SELECT, INSERT, UPDATE ON TABLE public.prediction_resolution_status TO ucpe_resolver;
CREATE POLICY ucpe_resolver_select ON public.predictions FOR SELECT TO ucpe_resolver USING (true);
CREATE POLICY ucpe_resolver_select ON public.prediction_outcomes FOR SELECT TO ucpe_resolver USING (true);
CREATE POLICY ucpe_resolver_insert ON public.prediction_outcomes FOR INSERT TO ucpe_resolver WITH CHECK (true);
CREATE POLICY ucpe_resolver_select ON public.prediction_resolution_status FOR SELECT TO ucpe_resolver USING (true);
CREATE POLICY ucpe_resolver_insert ON public.prediction_resolution_status FOR INSERT TO ucpe_resolver WITH CHECK (true);
CREATE POLICY ucpe_resolver_update ON public.prediction_resolution_status FOR UPDATE TO ucpe_resolver USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
