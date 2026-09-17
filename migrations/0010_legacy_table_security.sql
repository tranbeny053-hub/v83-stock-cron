-- The security posture of the legacy tables (migrations 0001-0004 and 0007), codified.
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization. It is applied
-- ONCE, and only by the dispatch-only workflow .github/workflows/apply-migration-0010.yml
-- (scripts/apply_migration_0010.py). That route executes exactly this file in ONE transaction,
-- between read-only pre-checks and post-checks, and rolls back on any surprise. The default
-- scripts/apply_migrations.py applies EVERY migration and must never be used for it.
--
-- WHAT THE READ-ONLY AUDIT MEASURED IN PRODUCTION (run 35120616278, 2026-09-16), on all ten tables:
-- row-level security on (not forced) and no policy. anon and authenticated hold every table
-- privilege, but row-level security denies them every row. service_role holds every privilege and
-- bypasses row-level security. There is no PUBLIC grant, column grant, view, rule, parent table or
-- publication. "Every privilege" is eight there: the audit saw MAINTAIN granted, so production runs
-- PostgreSQL 17 or later.
--
-- WHY:
-- - The migrations never enabled row-level security, so a database rebuilt from them would leave
--   these tables open to the project's anon key.
-- - Row-level security with no policy is today's only barrier. anon and authenticated still hold
--   every privilege, including TRUNCATE, REFERENCES and TRIGGER, which row-level security never
--   filters.
--
-- WHAT THIS DOES, AND WHY EFFECTIVE ACCESS DOES NOT CHANGE:
-- 1. Row-level security is enabled wherever it is off. In production it is already on everywhere, so
--    nothing is altered there and no table lock is taken; on a rebuild it is turned on.
-- 2. PUBLIC, anon and authenticated lose every privilege on the ten tables and on their three serial
--    sequences. Row-level security already denies them every row, so no reachable read or write
--    changes; only the latent privileges go.
-- 3. service_role keeps exactly the table privileges it holds today. The seven that every supported
--    PostgreSQL has are stated explicitly, so a rebuild does not depend on Supabase's default
--    privileges. On PostgreSQL 17 and later, REVOKE ALL also takes MAINTAIN from PUBLIC, anon and
--    authenticated, while service_role keeps the MAINTAIN it holds from those defaults.
--    service_role bypasses row-level security, which the Hugging Face runtime's REST repository
--    requires. Its sequence privileges are not touched.
--
-- Nothing else changes: ownership, policies (none), forced row-level security (off), and every
-- other table. The applying role owns these tables, and row-level security that is not forced does
-- not restrict an owner, so the direct-Postgres routes are unaffected.

DO $$
DECLARE
  legacy_table text;
BEGIN
  FOREACH legacy_table IN ARRAY ARRAY[
    'analysis_runs',
    'analysis_timeframe_results',
    'app_events',
    'news_clusters',
    'news_evidence_links',
    'news_items',
    'prediction_outcomes',
    'predictions',
    'provider_observations',
    'watchlist'
  ]
  LOOP
    IF NOT (
      SELECT c.relrowsecurity
      FROM pg_catalog.pg_class AS c
      WHERE c.oid = pg_catalog.to_regclass('public.' || legacy_table)
    ) THEN
      EXECUTE pg_catalog.format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', legacy_table);
    END IF;
  END LOOP;
END
$$;

REVOKE ALL ON TABLE
  public.analysis_runs,
  public.analysis_timeframe_results,
  public.app_events,
  public.news_clusters,
  public.news_evidence_links,
  public.news_items,
  public.prediction_outcomes,
  public.predictions,
  public.provider_observations,
  public.watchlist
FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
  public.analysis_runs,
  public.analysis_timeframe_results,
  public.app_events,
  public.news_clusters,
  public.news_evidence_links,
  public.news_items,
  public.prediction_outcomes,
  public.predictions,
  public.provider_observations,
  public.watchlist
TO service_role;

REVOKE ALL ON SEQUENCE
  public.analysis_timeframe_results_id_seq,
  public.app_events_id_seq,
  public.provider_observations_id_seq
FROM PUBLIC, anon, authenticated;
