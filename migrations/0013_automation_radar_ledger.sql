-- The automation ledger of the governed machine route POST /v1/automation/radar-evidence (F1).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization, through a
-- dedicated one-shot route that is not yet built. The default scripts/apply_migrations.py applies
-- EVERY migration and must never be used for it. Until it is applied the route has no ledger and
-- answers every authenticated call with 503 LEDGER_UNAVAILABLE: it fails closed.
--
-- WHY. Automated runs must never enter the human cohorts that calibration and control count. The
-- route therefore writes nothing to the shared prediction tables: it computes an isolated analysis
-- and records each call here, and only here. The ledger gives strict idempotency (one row per
-- credential and client request id, reserved before any analysis starts, so a repeat can never
-- start a second run), the per-credential quota counts, and the audit trail.
--
-- THE TABLE, one row per authenticated, well-formed call:
-- - evidence_origin is always AUTOMATED_RADAR, stamped by the server.
-- - credential_id is the machine credential's id, never its value.
-- - state is IN_PROGRESS until the outcome is known, then COMPLETED with an outcome code, the HTTP
--   status and the exact response body, so a repeat replays it byte for byte.
-- - A SUCCEEDED row carries the run id, the analysis hash, the evidence hash and a 200 body.
-- - arl_credential_received serves the quota counts.
-- - Retention is 90 days (stated in docs/automation/RADAR_EVIDENCE_V1.md); a purge is a separate
--   owner-authorized step.
--
-- NO FOREIGN KEY and no reference to any other table: no calibration, control or resolution reader
-- reads this table, and applying it takes no lock on any existing table.
--
-- ACCESS, the 0009 pattern: row-level security on, no policy, and no privilege for PUBLIC, anon,
-- authenticated or service_role. Supabase's default privileges grant every new table to the API
-- roles, so they are revoked explicitly. Only the owning role reads or writes it, through
-- SUPABASE_DB_URL. Row-level security that is not forced does not restrict an owner. The REST
-- repository never touches it.
CREATE TABLE IF NOT EXISTS public.automation_radar_ledger (
    credential_id       TEXT        NOT NULL,
    client_request_id   UUID        NOT NULL,
    request_fingerprint TEXT        NOT NULL,
    evidence_origin     TEXT        NOT NULL DEFAULT 'AUTOMATED_RADAR',
    state               TEXT        NOT NULL,
    outcome_code        TEXT,
    http_status         INTEGER,
    response_body       JSONB,
    run_id              TEXT,
    analysis_hash       TEXT,
    evidence_hash       TEXT,
    release_id          TEXT        NOT NULL,
    deadline_ms         INTEGER     NOT NULL,
    received_at_utc     TIMESTAMPTZ NOT NULL,
    completed_at_utc    TIMESTAMPTZ,
    CONSTRAINT automation_radar_ledger_pkey PRIMARY KEY (credential_id, client_request_id),
    CONSTRAINT arl_credential_id_format CHECK (credential_id ~ '^[a-z0-9][a-z0-9-]{2,31}$'),
    CONSTRAINT arl_fingerprint_format CHECK (request_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT arl_origin_automated CHECK (evidence_origin = 'AUTOMATED_RADAR'),
    CONSTRAINT arl_state_valid CHECK (state IN ('IN_PROGRESS', 'COMPLETED')),
    CONSTRAINT arl_release_id_format CHECK (release_id ~ '^UCPE-[A-Z0-9-]{3,}$'),
    CONSTRAINT arl_deadline_bounds CHECK (deadline_ms BETWEEN 5000 AND 60000),
    CONSTRAINT arl_state_shape CHECK (
        (state = 'IN_PROGRESS' AND outcome_code IS NULL AND http_status IS NULL
            AND response_body IS NULL AND completed_at_utc IS NULL)
        OR (state = 'COMPLETED' AND outcome_code IS NOT NULL AND http_status IS NOT NULL
            AND response_body IS NOT NULL AND completed_at_utc IS NOT NULL
            AND completed_at_utc >= received_at_utc)),
    CONSTRAINT arl_success_shape CHECK (
        outcome_code IS DISTINCT FROM 'SUCCEEDED'
        OR (http_status = 200 AND run_id ~ '^run_[0-9a-f]{32}$'
            AND analysis_hash ~ '^sha256:[0-9a-f]{64}$'
            AND evidence_hash ~ '^sha256:[0-9a-f]{64}$')),
    CONSTRAINT arl_refusal_shape CHECK (
        outcome_code IS NULL OR outcome_code = 'SUCCEEDED'
        OR (http_status BETWEEN 400 AND 599 AND run_id IS NULL
            AND analysis_hash IS NULL AND evidence_hash IS NULL))
);
CREATE INDEX IF NOT EXISTS arl_credential_received
    ON public.automation_radar_ledger (credential_id, received_at_utc);
ALTER TABLE public.automation_radar_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.automation_radar_ledger FROM PUBLIC;
REVOKE ALL ON TABLE public.automation_radar_ledger FROM anon, authenticated, service_role;
-- No policy, no GRANT (0009 pattern): only the owning SUPABASE_DB_URL role reads/writes it.
