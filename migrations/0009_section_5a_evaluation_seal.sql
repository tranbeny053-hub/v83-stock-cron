-- Section 5A one-look durable seal (V1_QUANT_CONTRACT §5A.9).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization.
--
-- Why the database rather than a file: the evaluation workflow runs on a fresh GitHub
-- runner per dispatch and uploads its artifact only AFTER the job, so a filesystem seal
-- is empty on every run and cannot refuse a second consumption. Postgres is the only
-- durable, atomic, cross-run authority available here.
--
-- Why the snapshot lives in the same row: claiming the seal and durably capturing the raw
-- evidence must be ONE act. Split across two writes, a crash between them spends the look
-- and leaves no record of it.
--
-- The singleton CHECK is the one-shot guarantee: at most one row can ever exist, so a
-- second INSERT conflicts on the primary key rather than relying on application logic.

CREATE TABLE IF NOT EXISTS section_5a_evaluation_seal (
  seal_id                TEXT PRIMARY KEY CHECK (seal_id = 'SINGLETON'),
  sealed_at_utc          TIMESTAMPTZ NOT NULL,
  evidence_snapshot_id   TEXT NOT NULL,
  result_inputs_digest   TEXT NOT NULL,
  evaluator_pin_digest   TEXT NOT NULL,
  contract_instants      JSONB NOT NULL,
  snapshot_payload       JSONB NOT NULL,
  state                  TEXT NOT NULL
    CHECK (state IN ('SEALED_RAW_CAPTURED', 'COMPLETE', 'SEALED_NO_RESULT')),
  state_detail           TEXT NOT NULL DEFAULT '',
  updated_at_utc         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The snapshot is immutable once claimed. Only the state may advance.
CREATE OR REPLACE FUNCTION section_5a_seal_is_immutable()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.evidence_snapshot_id IS DISTINCT FROM OLD.evidence_snapshot_id
     OR NEW.snapshot_payload  IS DISTINCT FROM OLD.snapshot_payload
     OR NEW.sealed_at_utc     IS DISTINCT FROM OLD.sealed_at_utc
     OR NEW.result_inputs_digest IS DISTINCT FROM OLD.result_inputs_digest
     OR NEW.evaluator_pin_digest IS DISTINCT FROM OLD.evaluator_pin_digest THEN
    RAISE EXCEPTION 'section 5A seal evidence is immutable once claimed';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS section_5a_seal_immutable ON section_5a_evaluation_seal;
CREATE TRIGGER section_5a_seal_immutable
  BEFORE UPDATE ON section_5a_evaluation_seal
  FOR EACH ROW EXECUTE FUNCTION section_5a_seal_is_immutable();
