-- Section 5A one-look durable seal (V1_QUANT_CONTRACT §5A.9).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization. It is applied
-- ONCE, and only by the dispatch-only workflow .github/workflows/section-5a-apply-seal-migration.yml
-- (scripts/apply_section_5a_seal.py; owner ruling K2=A). That route executes exactly this file in ONE
-- transaction, between read-only pre-checks and post-checks, and rolls back on any surprise. It never
-- drags in the deliberately unapplied 0008. The default `scripts/apply_migrations.py` applies EVERY
-- migration and must never be used for it; `--only 0009_section_5a_evaluation_seal.sql` is the only
-- safe manual selection.
--
-- WHY THE DATABASE. The evaluation runs on a fresh GitHub runner per dispatch, so a filesystem
-- seal is empty every time. Postgres is the only durable, atomic, cross-run authority here.
--
-- THE LIFECYCLE, enforced below rather than trusted to application code:
--
--   CLAIMED               claimed BEFORE any probability is exposed. Singleton, so exactly one
--                         consumer can ever hold it; only that consumer may read.
--   CLAIMED + raw_evidence the probabilities, written here in the SAME transaction that reads
--                         them and before they are returned. Exposure never precedes capture.
--   SEALED_RAW_CAPTURED   the canonical snapshot and its digests are recorded, once.
--   COMPLETE | SEALED_NO_RESULT   the result, or a statistics failure recoverable from the
--                         captured evidence without re-reading the holdout.
--   CAPTURE_FAILED        terminal; needs an owner decision.
--
-- WHO SPENT THE LOOK (owner ruling E2=A). Every claim carries the verified run provenance of the
-- dispatch that made it: commit, workflow run, interpreter, dependency lock and evaluator pin. A
-- claim without a verified record is refused here, so the look can only be spent by a verified
-- dispatch of the evaluation workflow on main at the owner's expected commit.

CREATE TABLE IF NOT EXISTS public.section_5a_evaluation_seal (
  seal_id                TEXT PRIMARY KEY CHECK (seal_id = 'SINGLETON'),
  sealed_at_utc          TIMESTAMPTZ NOT NULL,
  evaluator_pin_digest   TEXT NOT NULL,
  contract_instants      JSONB NOT NULL,
  run_provenance         JSONB NOT NULL,
  raw_evidence           JSONB,
  snapshot_payload       JSONB,
  evidence_snapshot_id   TEXT,
  result_inputs_digest   TEXT,
  state                  TEXT NOT NULL
    CHECK (state IN ('CLAIMED', 'SEALED_RAW_CAPTURED', 'COMPLETE',
                     'SEALED_NO_RESULT', 'CAPTURE_FAILED')),
  state_detail           TEXT NOT NULL DEFAULT '',
  updated_at_utc         TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- A CLAIMED seal carries no snapshot and no digests. Evidence cannot be handed to the claim,
  -- so claim-before-read cannot be bypassed.
  CONSTRAINT section_5a_claimed_has_no_snapshot CHECK (
    state <> 'CLAIMED'
    OR (snapshot_payload IS NULL AND evidence_snapshot_id IS NULL
        AND result_inputs_digest IS NULL)
  ),
  -- The claim names a verified dispatch on main at the expected commit, under the claimed pin.
  -- Application code verifies the full record first; this is the authority's own refusal.
  -- COALESCE matters: a CHECK whose expression is NULL PASSES, and a missing key makes ->> NULL,
  -- so without it an incomplete record would be accepted.
  CONSTRAINT section_5a_claim_has_verified_provenance CHECK (COALESCE(
    jsonb_typeof(run_provenance) = 'object'
    AND run_provenance ->> 'schema_version' = 'section-5a-run-provenance.v1'
    AND run_provenance -> 'dispatch_verified' = 'true'::jsonb
    AND run_provenance ->> 'event_name' = 'workflow_dispatch'
    AND run_provenance ->> 'ref' = 'refs/heads/main'
    AND run_provenance ->> 'workflow_ref' = (run_provenance ->> 'repository')
        || '/.github/workflows/section-5a-evaluation.yml@refs/heads/main'
    AND run_provenance ->> 'expected_sha' ~ '^[0-9a-f]{40}$'
    AND run_provenance ->> 'sha' = run_provenance ->> 'expected_sha'
    AND run_provenance ->> 'git_head' = run_provenance ->> 'expected_sha'
    AND run_provenance ->> 'run_id' ~ '^[0-9]+$'
    AND run_provenance ->> 'python_version' ~ '^[0-9]+[.][0-9]+[.][0-9]+$'
    AND run_provenance ->> 'lock_sha256' ~ '^[0-9a-f]{64}$'
    AND run_provenance ->> 'interpreter_flags'
        = 'isolated,ignore_environment,no_user_site,safe_path,no_site,dont_write_bytecode'
    AND run_provenance ->> 'installed_files_sha256' ~ '^[0-9a-f]{64}$'
    AND run_provenance ->> 'pin_digest' = evaluator_pin_digest,
    false)),
  -- A captured state requires the raw capture AND the snapshot AND both digests. A snapshot
  -- can never exist without the raw evidence it was exposed from.
  CONSTRAINT section_5a_captured_is_complete CHECK (
    state NOT IN ('SEALED_RAW_CAPTURED', 'COMPLETE', 'SEALED_NO_RESULT')
    OR (raw_evidence IS NOT NULL AND snapshot_payload IS NOT NULL
        AND evidence_snapshot_id IS NOT NULL AND result_inputs_digest IS NOT NULL)
  )
);

CREATE OR REPLACE FUNCTION public.section_5a_seal_guard()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'section 5A seal cannot be deleted: the one look stays recorded';
  END IF;

  -- Fixed at claim time, forever.
  IF NEW.seal_id IS DISTINCT FROM OLD.seal_id
     OR NEW.sealed_at_utc IS DISTINCT FROM OLD.sealed_at_utc
     OR NEW.evaluator_pin_digest IS DISTINCT FROM OLD.evaluator_pin_digest
     OR NEW.contract_instants IS DISTINCT FROM OLD.contract_instants
     OR NEW.run_provenance IS DISTINCT FROM OLD.run_provenance THEN
    RAISE EXCEPTION 'section 5A seal claim fields are immutable';
  END IF;

  -- Write-once: may go from NULL to a value, never change, never be cleared.
  IF (OLD.raw_evidence IS NOT NULL AND NEW.raw_evidence IS DISTINCT FROM OLD.raw_evidence)
     OR (OLD.snapshot_payload IS NOT NULL
         AND NEW.snapshot_payload IS DISTINCT FROM OLD.snapshot_payload)
     OR (OLD.evidence_snapshot_id IS NOT NULL
         AND NEW.evidence_snapshot_id IS DISTINCT FROM OLD.evidence_snapshot_id)
     OR (OLD.result_inputs_digest IS NOT NULL
         AND NEW.result_inputs_digest IS DISTINCT FROM OLD.result_inputs_digest) THEN
    RAISE EXCEPTION 'section 5A captured evidence is write-once';
  END IF;

  -- Legal transitions only.
  IF NOT (
       (OLD.state = 'CLAIMED' AND NEW.state IN ('CLAIMED', 'SEALED_RAW_CAPTURED', 'CAPTURE_FAILED'))
    OR (OLD.state = 'SEALED_RAW_CAPTURED'
        AND NEW.state IN ('SEALED_RAW_CAPTURED', 'COMPLETE', 'SEALED_NO_RESULT'))
    OR (OLD.state = 'SEALED_NO_RESULT' AND NEW.state IN ('SEALED_NO_RESULT', 'COMPLETE'))
    OR (OLD.state = 'COMPLETE' AND NEW.state = 'COMPLETE')
    OR (OLD.state = 'CAPTURE_FAILED' AND NEW.state = 'CAPTURE_FAILED')
  ) THEN
    RAISE EXCEPTION 'illegal section 5A seal transition % -> %', OLD.state, NEW.state;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS section_5a_seal_immutable ON public.section_5a_evaluation_seal;
DROP TRIGGER IF EXISTS section_5a_seal_guard ON public.section_5a_evaluation_seal;
CREATE TRIGGER section_5a_seal_guard
  BEFORE UPDATE OR DELETE ON public.section_5a_evaluation_seal
  FOR EACH ROW EXECUTE FUNCTION public.section_5a_seal_guard();

-- V807-F8: TRUNCATE does not fire row-level triggers, so the row guard above cannot stop it.
-- A statement-level guard closes that route. Known residual limit, stated rather than hidden:
-- DROP TABLE, or a superuser disabling triggers, is outside what a table trigger can prevent.
CREATE OR REPLACE FUNCTION public.section_5a_seal_truncate_guard()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'section 5A seal cannot be truncated: the one look stays recorded';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS section_5a_seal_truncate_guard ON public.section_5a_evaluation_seal;
CREATE TRIGGER section_5a_seal_truncate_guard
  BEFORE TRUNCATE ON public.section_5a_evaluation_seal
  FOR EACH STATEMENT EXECUTE FUNCTION public.section_5a_seal_truncate_guard();

-- F-0009-A (owner ruling K1=A). No API role may reach the seal: the project's convention since 0005
-- and 0006. On Supabase, tables in public inherit grants for the PostgREST roles. With row-level
-- security off, an anon-key INSERT could squat the singleton and deny the one look, and the guards
-- above would then keep that row. The evaluator connects as the table's owner, which row-level
-- security that is not forced does not restrict, and the REST repository refuses every seal
-- operation. So no GRANT follows.
ALTER TABLE public.section_5a_evaluation_seal ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.section_5a_evaluation_seal
FROM PUBLIC, anon, authenticated, service_role;
