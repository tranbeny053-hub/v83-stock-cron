-- P3-W-A: the rollback of draft_0017_forecast_bundle_rpc.sql. It restores the catalog to exactly its state
-- after the draft of 0016: the function is dropped, and ucpe_bundle_owner's grants and policies on the run
-- and detail tables are removed. Rows it wrote stay: evidence is never deleted. It runs as the tables'
-- owner, in one transaction (the caller's), and ONLY on a scratch PostgreSQL in this rehearsal.

-- Dropping the function needs the privileges of its owner (an INHERIT membership), for that statement only.
GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
DROP FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb);
REVOKE ucpe_bundle_owner FROM CURRENT_USER;

DROP POLICY ucpe_bundle_owner_select ON public.analysis_runs;
DROP POLICY ucpe_bundle_owner_insert ON public.analysis_runs;
DROP POLICY ucpe_bundle_owner_select ON public.analysis_run_details;
DROP POLICY ucpe_bundle_owner_insert ON public.analysis_run_details;
REVOKE SELECT, INSERT ON TABLE public.analysis_runs, public.analysis_run_details FROM ucpe_bundle_owner;

NOTIFY pgrst, 'reload schema';
