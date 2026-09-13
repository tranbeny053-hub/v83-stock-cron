-- Section 5A one-look durable seal (V1_QUANT_CONTRACT §5A.9).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization, and it
-- must be applied with `scripts/apply_migrations.py --only 0009_section_5a_evaluation_seal.sql`
-- so that the deliberately unapplied 0008 is not dragged in with it.
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

CREATE TABLE IF NOT EXISTS section_5a_evaluation_seal (
  seal_id                TEXT PRIMARY KEY CHECK (seal_id = 'SINGLETON'),
  sealed_at_utc          TIMESTAMPTZ NOT NULL,
  evaluator_pin_digest   TEXT NOT NULL,
  contract_instants      JSONB NOT NULL,
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
  -- A captured state requires the raw capture AND the snapshot AND both digests. A snapshot
  -- can never exist without the raw evidence it was exposed from.
  CONSTRAINT section_5a_captured_is_complete CHECK (
    state NOT IN ('SEALED_RAW_CAPTURED', 'COMPLETE', 'SEALED_NO_RESULT')
    OR (raw_evidence IS NOT NULL AND snapshot_payload IS NOT NULL
        AND evidence_snapshot_id IS NOT NULL AND result_inputs_digest IS NOT NULL)
  )
);

CREATE OR REPLACE FUNCTION section_5a_seal_guard()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'section 5A seal cannot be deleted: the one look stays recorded';
  END IF;

  -- Fixed at claim time, forever.
  IF NEW.seal_id IS DISTINCT FROM OLD.seal_id
     OR NEW.sealed_at_utc IS DISTINCT FROM OLD.sealed_at_utc
     OR NEW.evaluator_pin_digest IS DISTINCT FROM OLD.evaluator_pin_digest
     OR NEW.contract_instants IS DISTINCT FROM OLD.contract_instants THEN
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

DROP TRIGGER IF EXISTS section_5a_seal_immutable ON section_5a_evaluation_seal;
DROP TRIGGER IF EXISTS section_5a_seal_guard ON section_5a_evaluation_seal;
CREATE TRIGGER section_5a_seal_guard
  BEFORE UPDATE OR DELETE ON section_5a_evaluation_seal
  FOR EACH ROW EXECUTE FUNCTION section_5a_seal_guard();
