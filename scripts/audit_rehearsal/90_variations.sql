-- Rehearsal fixture, part 2: one variation per branch of the audit's assessment, applied AFTER the real
-- migrations. Runs ONLY in a scratch local PostgreSQL on a CI runner. Never against a real database.

-- RLS on, no policy: anon and authenticated are denied everything; service_role bypasses.
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;

-- RLS on, one PERMISSIVE read policy for anon only.
ALTER TABLE public.prediction_outcomes ENABLE ROW LEVEL SECURITY;
CREATE POLICY rehearsal_read ON public.prediction_outcomes FOR SELECT TO anon USING (true);

-- RLS on, only a RESTRICTIVE policy: it can narrow rows but never admit them.
ALTER TABLE public.news_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY rehearsal_narrow ON public.news_items AS RESTRICTIVE FOR SELECT TO anon USING (true);

-- No API role holds anything.
REVOKE ALL ON TABLE public.watchlist FROM anon, authenticated, service_role;

-- anon holds no table privilege, only one column.
REVOKE ALL ON TABLE public.analysis_timeframe_results FROM anon;
GRANT SELECT (run_id) ON TABLE public.analysis_timeframe_results TO anon;

-- A view over an audited table, which inherits the default grants.
CREATE VIEW public.rehearsal_runs_view AS SELECT run_id FROM public.analysis_runs;

-- A table in the Realtime publication.
CREATE PUBLICATION supabase_realtime FOR TABLE public.app_events;

-- A grant to PUBLIC.
GRANT SELECT ON TABLE public.news_clusters TO PUBLIC;
