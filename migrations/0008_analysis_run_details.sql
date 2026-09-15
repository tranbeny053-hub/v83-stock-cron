-- Durable sanitized Detail for the operator's own analyses (PR #59).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization. It is applied
-- ONCE, and only by the dispatch-only workflow .github/workflows/apply-migration-0008.yml
-- (scripts/apply_migration_0008.py). That route executes exactly this file in ONE transaction,
-- between read-only pre-checks and post-checks, and rolls back on any surprise. The default
-- scripts/apply_migrations.py applies EVERY migration and must never be used for it.
--
-- ADDITIVE ONLY. The table has no link to any other table, so applying it cannot lock, rewrite or
-- constrain predictions, outcomes or analysis runs. Reads join to predictions on run_id in the
-- application, behind the prediction_origin guard.

CREATE TABLE IF NOT EXISTS public.analysis_run_details (
  run_id TEXT PRIMARY KEY,
  analysis_hash TEXT,
  detail_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_run_details_created_at
  ON public.analysis_run_details (created_at DESC);

-- No API role reaches a new table by default: the project's convention since 0005 and 0006, and
-- again for 0009 (owner ruling K1=A). On Supabase, tables in public inherit grants for the PostgREST
-- roles, so without these statements the operator's Detail payloads would be readable and writable
-- with the project's anon key.
--
-- The Hugging Face runtime reads and writes this table through PostgREST as service_role
-- (persistence.repository.SupabaseRestRepository: an upsert on run_id, then reads). So exactly
-- SELECT, INSERT and UPDATE are granted back to service_role, which bypasses row-level security in
-- Supabase. The direct-Postgres repository connects as the table's owner, which row-level security
-- that is not forced does not restrict. anon and authenticated keep nothing.
ALTER TABLE public.analysis_run_details ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.analysis_run_details
FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.analysis_run_details
TO service_role;
