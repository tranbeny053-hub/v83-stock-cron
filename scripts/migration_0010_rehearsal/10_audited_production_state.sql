-- Rehearsal fixture for migration 0010, part 3: the state the read-only audit measured in production
-- (run 35120616278), applied after migrations 0001-0009. Row-level security is on for every legacy
-- table; no policy exists; the API roles keep Supabase's default privileges. Runs ONLY in a scratch
-- local PostgreSQL on a CI runner, as the tables' owner. Never run it against a real database.
ALTER TABLE public.analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_timeframe_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.news_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.news_evidence_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.news_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prediction_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.provider_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watchlist ENABLE ROW LEVEL SECURITY;
