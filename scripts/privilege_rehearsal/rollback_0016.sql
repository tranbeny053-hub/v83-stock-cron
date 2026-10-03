-- The rollback of migration 0016 (migrations/0016_least_privilege_roles.sql). It restores the catalog to
-- exactly its state before 0016:
-- - the bundle RPC goes back to SECURITY INVOKER, owned by the applying role, with its EXECUTE list
--   restored;
-- - every policy and grant of the four roles is removed;
-- - the writer's membership in authenticator is removed;
-- - the four roles are dropped.
-- Rows they wrote stay: evidence is never deleted. It runs as the tables' owner, in one transaction (the
-- caller's). Against production it is a separate T4, never automatic. P3-PRIV-R's P8 proves it on
-- scratch PostgreSQL behind a real PostgREST.

-- The owner change back needs the privileges of the current owner (an INHERIT membership). Granted for
-- that one statement only.
GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
ALTER FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) OWNER TO CURRENT_USER;
REVOKE ucpe_bundle_owner FROM CURRENT_USER;
ALTER FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) SECURITY INVOKER;
REVOKE EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) FROM ucpe_api_writer;

DROP POLICY ucpe_api_writer_select ON public.analysis_runs;
DROP POLICY ucpe_api_writer_insert ON public.analysis_runs;
DROP POLICY ucpe_api_writer_update ON public.analysis_runs;
DROP POLICY ucpe_api_writer_select ON public.analysis_run_details;
DROP POLICY ucpe_api_writer_insert ON public.analysis_run_details;
DROP POLICY ucpe_api_writer_update ON public.analysis_run_details;
DROP POLICY ucpe_api_writer_select ON public.news_items;
DROP POLICY ucpe_api_writer_insert ON public.news_items;
DROP POLICY ucpe_api_writer_update ON public.news_items;
DROP POLICY ucpe_api_writer_select ON public.news_clusters;
DROP POLICY ucpe_api_writer_insert ON public.news_clusters;
DROP POLICY ucpe_api_writer_update ON public.news_clusters;
DROP POLICY ucpe_api_writer_select ON public.news_evidence_links;
DROP POLICY ucpe_api_writer_insert ON public.news_evidence_links;
DROP POLICY ucpe_api_writer_update ON public.news_evidence_links;
DROP POLICY ucpe_api_writer_insert ON public.analysis_timeframe_results;
DROP POLICY ucpe_api_writer_insert ON public.provider_observations;
DROP POLICY ucpe_api_writer_select ON public.watchlist;
DROP POLICY ucpe_api_writer_insert ON public.watchlist;
DROP POLICY ucpe_api_writer_update ON public.watchlist;
DROP POLICY ucpe_api_writer_delete ON public.watchlist;
DROP POLICY ucpe_api_writer_select ON public.predictions;
DROP POLICY ucpe_bundle_owner_select ON public.predictions;
DROP POLICY ucpe_bundle_owner_insert ON public.predictions;
DROP POLICY ucpe_bundle_owner_select ON public.prediction_feature_snapshots;
DROP POLICY ucpe_bundle_owner_insert ON public.prediction_feature_snapshots;
DROP POLICY ucpe_bundle_owner_select ON public.prediction_derivatives_snapshots;
DROP POLICY ucpe_bundle_owner_insert ON public.prediction_derivatives_snapshots;
DROP POLICY ucpe_space_db_select ON public.predictions;
DROP POLICY ucpe_space_db_select ON public.prediction_outcomes;
DROP POLICY ucpe_space_db_select ON public.automation_credential;
DROP POLICY ucpe_space_db_select ON public.automation_radar_ledger;
DROP POLICY ucpe_space_db_insert ON public.automation_radar_ledger;
DROP POLICY ucpe_space_db_update ON public.automation_radar_ledger;
DROP POLICY ucpe_resolver_select ON public.predictions;
DROP POLICY ucpe_resolver_select ON public.prediction_outcomes;
DROP POLICY ucpe_resolver_insert ON public.prediction_outcomes;
DROP POLICY ucpe_resolver_select ON public.prediction_resolution_status;
DROP POLICY ucpe_resolver_insert ON public.prediction_resolution_status;
DROP POLICY ucpe_resolver_update ON public.prediction_resolution_status;

REVOKE ALL ON TABLE
    public.analysis_runs, public.analysis_run_details, public.analysis_timeframe_results,
    public.provider_observations, public.news_items, public.news_clusters, public.news_evidence_links,
    public.watchlist, public.predictions, public.prediction_feature_snapshots,
    public.prediction_derivatives_snapshots, public.prediction_outcomes, public.prediction_resolution_status,
    public.automation_credential, public.automation_radar_ledger
    FROM ucpe_api_writer, ucpe_bundle_owner, ucpe_space_db, ucpe_resolver;
REVOKE ALL ON SEQUENCE
    public.analysis_timeframe_results_id_seq, public.provider_observations_id_seq
    FROM ucpe_api_writer;
REVOKE USAGE ON SCHEMA public FROM ucpe_api_writer, ucpe_bundle_owner, ucpe_space_db, ucpe_resolver;
REVOKE ucpe_api_writer FROM authenticator;

DROP ROLE ucpe_api_writer, ucpe_bundle_owner, ucpe_space_db, ucpe_resolver;

NOTIFY pgrst, 'reload schema';
