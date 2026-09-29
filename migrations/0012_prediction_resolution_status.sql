-- The resolution-status table of retry/quarantine policy rq-v1 (owner decisions D4 and D5,
-- accepted 2026-09-29).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization. It is applied
-- ONCE, and only by the dispatch-only workflow .github/workflows/apply-migration-0012.yml
-- (scripts/apply_migration_0012.py). That route executes exactly this file in ONE transaction,
-- between read-only pre-checks and post-checks, and rolls back on any surprise. The default
-- scripts/apply_migrations.py applies EVERY migration and must never be used for it.
--
-- WHY. A due prediction the resolver cannot resolve is retried on every run, and enough of them can
-- crowd out the fresh ones. Under rq-v1 the resolver records, per unresolved prediction, how often
-- it was attempted and why it stayed unresolved; it backs retries off, and it quarantines rows
-- that cannot resolve. A status row is written only after an unresolved attempt, so a prediction
-- that resolves on its first attempt never gets one.
--
-- THE TABLE, one row per prediction:
-- - resolution_status is RETRYABLE, QUARANTINED or RESOLVED. RESOLVED is terminal; only an owner T4
--   leaves QUARANTINED. The resolver's upsert changes a row only while it is RETRYABLE.
-- - Reasons are the resolver's reason keys (skip_* or error_*); policy_version is rq-v<N>.
-- - prs_state_shape enforces each state's shape: RETRYABLE carries next_eligible_utc, QUARANTINED
--   carries quarantined_at_utc, RESOLVED carries resolved_at_utc, and each carries only its own.
-- - A partial index serves the resolver's read of the retryable rows that are due.
--
-- NO FOREIGN KEY, so applying takes no lock on predictions or prediction_outcomes. It is independent
-- of migration 0011's columns.
--
-- ACCESS, the 0009 pattern: row-level security on, no policy, and no privilege for PUBLIC, anon,
-- authenticated or service_role. Supabase's default privileges grant every new table to the API
-- roles, so they are revoked explicitly. Only the owning role reads or writes it: the role that
-- applies it through SUPABASE_DB_URL, which the resolver also connects as. Row-level security that
-- is not forced does not restrict an owner. The REST repository never touches it.

CREATE TABLE IF NOT EXISTS public.prediction_resolution_status (
    prediction_id      TEXT        NOT NULL,
    resolution_status  TEXT        NOT NULL,
    attempt_count      INTEGER     NOT NULL,
    first_attempt_utc  TIMESTAMPTZ NOT NULL,
    last_attempt_utc   TIMESTAMPTZ NOT NULL,
    first_reason       TEXT        NOT NULL,
    last_reason        TEXT        NOT NULL,
    next_eligible_utc  TIMESTAMPTZ,
    quarantined_at_utc TIMESTAMPTZ,
    resolved_at_utc    TIMESTAMPTZ,
    policy_version     TEXT        NOT NULL,
    resolver_version   TEXT        NOT NULL,
    updated_at_utc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT prediction_resolution_status_pkey PRIMARY KEY (prediction_id),
    CONSTRAINT prs_prediction_id_nonblank CHECK (btrim(prediction_id) <> ''),
    CONSTRAINT prs_status_valid CHECK (resolution_status IN ('RETRYABLE', 'QUARANTINED', 'RESOLVED')),
    CONSTRAINT prs_attempt_count_positive CHECK (attempt_count >= 1),
    CONSTRAINT prs_attempt_chronology CHECK (last_attempt_utc >= first_attempt_utc),
    CONSTRAINT prs_reason_format CHECK (
        first_reason ~ '^(skip|error)_[a-z0-9_]{1,58}$' AND last_reason ~ '^(skip|error)_[a-z0-9_]{1,58}$'),
    CONSTRAINT prs_policy_version_format CHECK (policy_version ~ '^rq-v[1-9][0-9]*$'),
    CONSTRAINT prs_resolver_version_nonblank CHECK (btrim(resolver_version) <> ''),
    CONSTRAINT prs_state_shape CHECK (
        (resolution_status = 'RETRYABLE' AND next_eligible_utc IS NOT NULL
            AND quarantined_at_utc IS NULL AND resolved_at_utc IS NULL)
        OR (resolution_status = 'QUARANTINED' AND next_eligible_utc IS NULL
            AND quarantined_at_utc IS NOT NULL AND resolved_at_utc IS NULL)
        OR (resolution_status = 'RESOLVED' AND next_eligible_utc IS NULL
            AND quarantined_at_utc IS NULL AND resolved_at_utc IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS prediction_resolution_status_retry_idx
    ON public.prediction_resolution_status (next_eligible_utc, prediction_id)
    WHERE resolution_status = 'RETRYABLE';
ALTER TABLE public.prediction_resolution_status ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.prediction_resolution_status FROM PUBLIC;
REVOKE ALL ON TABLE public.prediction_resolution_status FROM anon, authenticated, service_role;
-- No policy, no GRANT (0009 pattern): only the owning SUPABASE_DB_URL role reads/writes it.
