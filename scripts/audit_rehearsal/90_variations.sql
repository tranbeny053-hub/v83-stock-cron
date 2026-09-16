-- Rehearsal fixture, part 2: one variation per branch of the audit's assessment, applied AFTER the real
-- migrations. Runs ONLY in a scratch local PostgreSQL on a CI runner. Never against a real database.
-- Needs PostgreSQL 16 or later (GRANT ... WITH INHERIT).

-- Roles anon belongs to. anon is NOINHERIT, as on Supabase, so only a membership granted WITH INHERIT
-- TRUE passes privileges, policies and ownership on to it. The first name is deliberately non-standard:
-- the audit must withhold it everywhere.
CREATE ROLE "rehearsal reader" NOLOGIN;
CREATE ROLE rehearsal_owner NOLOGIN;
CREATE ROLE rehearsal_bystander NOLOGIN;
GRANT "rehearsal reader" TO anon WITH INHERIT TRUE;
GRANT rehearsal_owner TO anon WITH INHERIT TRUE;
GRANT rehearsal_bystander TO anon WITH INHERIT FALSE;

-- RLS on, no policy that applies: anon and authenticated are denied everything; service_role bypasses.
-- The only policy names a role anon belongs to WITHOUT inheriting it, so it never applies to anon.
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY rehearsal_not_inherited ON public.predictions FOR SELECT TO rehearsal_bystander USING (true);

-- RLS on, one PERMISSIVE read policy for anon, and one PERMISSIVE insert policy for a role anon inherits.
ALTER TABLE public.prediction_outcomes ENABLE ROW LEVEL SECURITY;
CREATE POLICY rehearsal_read ON public.prediction_outcomes FOR SELECT TO anon USING (true);
CREATE POLICY rehearsal_inherited_insert ON public.prediction_outcomes FOR INSERT TO "rehearsal reader" WITH CHECK (false);

-- RLS on, only a RESTRICTIVE policy: it can narrow rows but never admit them.
ALTER TABLE public.news_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY rehearsal_narrow ON public.news_items AS RESTRICTIVE FOR SELECT TO anon USING (true);

-- No API role holds anything. A role anon belongs to without inheriting it holds SELECT, which anon
-- therefore does not.
REVOKE ALL ON TABLE public.watchlist FROM anon, authenticated, service_role;
GRANT SELECT ON TABLE public.watchlist TO rehearsal_bystander;

-- anon holds no table privilege, only columns: one granted to it, one to PUBLIC, one to a role it inherits.
REVOKE ALL ON TABLE public.analysis_timeframe_results FROM anon;
GRANT SELECT (run_id) ON TABLE public.analysis_timeframe_results TO anon;
GRANT INSERT (timeframe) ON TABLE public.analysis_timeframe_results TO PUBLIC;
GRANT UPDATE (disposition) ON TABLE public.analysis_timeframe_results TO "rehearsal reader";

-- Owned by a role anon inherits, RLS on, no policy: anon acts as the owner, so RLS does not apply to it.
-- anon's own grants are revoked; it holds the owner's privileges through the membership.
ALTER TABLE public.news_evidence_links OWNER TO rehearsal_owner;
ALTER TABLE public.news_evidence_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.news_evidence_links FROM anon;

-- The same ownership, but RLS is FORCED, so it applies to the owner too.
ALTER TABLE public.provider_observations OWNER TO rehearsal_owner;
ALTER TABLE public.provider_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.provider_observations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.provider_observations FROM anon;

-- A view over an audited table, which inherits the default grants.
CREATE VIEW public.rehearsal_runs_view AS SELECT run_id FROM public.analysis_runs;

-- A table in the Realtime publication.
CREATE PUBLICATION supabase_realtime FOR TABLE public.app_events;

-- A grant to PUBLIC.
GRANT SELECT ON TABLE public.news_clusters TO PUBLIC;
