# ucpe.a4_ledger_audit.v1: the owner card for one future UOR qualification episode

**PREPARED, NOT RUN.** Nothing in this package has queried production. Running it is a separate owner
decision, made at the qualification episode itself.

## What it is
- **The one job:** prove the single row of `public.automation_radar_ledger` (migration 0013) that
  records one UOR qualification request to `POST /v1/automation/radar-evidence`, so UOR can adjudicate
  A4.
- **What it is not:** a database tool. It reads no other application table. No cohort, prediction,
  registry or section 5A table is evidence here.
- **The sealed SELECT:** `a4_ledger_audit.sql`. The runner `a4_ledger_audit.py` pins its sha256 and
  refuses to run a changed copy. `MANIFEST.json` pins every file of the package.
- **Read only:**
  - the runner opens the transaction `READ ONLY`, proves `transaction_read_only = on`, bounds it at
    5 s, and always rolls back;
  - it never prints the database URL, a credential value or an exception message.

## ACTION_ID
A4-LEDGER-AUDIT, once per qualification request, only inside the owner-authorized episode.

## WHY
UOR must see that the request it sent produced exactly one completed, successful AUTOMATED_RADAR
ledger row, with the run, release and evidence identity of the response it received.

## WHERE
- A terminal with this repository at the commit that carries this package;
- a database role that can SELECT `public.automation_radar_ledger`: the owning role, or
  `ucpe_space_db` (0016 grants it SELECT through its policy);
- the URL entered without echo. It never goes into a command line, a chat, a file or a log.

## EXACT_STEPS
1. From UOR's own record of the request and its received 200 response, copy five values:
   - the credential **id** (e.g. `uor-radar-2026-10`; never the `ucpea.` token);
   - `client_request_id`;
   - `run_id`;
   - `build_info.release_id`;
   - `evidence_hash`.
2. `read -rs A4_AUDIT_DATABASE_URL && export A4_AUDIT_DATABASE_URL`, then paste the URL. It is not
   echoed.
3. Run:
   `python ops/a4_ledger_audit/a4_ledger_audit.py --credential-id <id> --client-request-id <uuid> --run-id <run_id> --release-id <release_id> --evidence-hash <evidence_hash>`
4. `unset A4_AUDIT_DATABASE_URL`.

## DO_NOT_DO
- Never run it outside the episode, and never against anything but the ledger's own database.
- Never edit the SQL. A change is a new artifact version, with a new sha256 that UOR must pin again.
- Never pass the credential token or the URL as an argument.
- Never bind on `client_request_id` alone: the ledger's key is the pair.
- Never treat a non-PASS as evidence of anything but a failed A4.

## EXPECTED_RESULT
One JSON line, with sorted keys:
- **PASS:** `"verdict":"PASS","reason":"OK"` and exit code 0.
- **FAIL, the audit ran:** exit code 1, with `reason` naming the first failing check: `SCHEMA_DRIFT`, `NO_ROW`,
  `AMBIGUOUS`, `WRONG_ORIGIN`, `NOT_COMPLETED`, `NOT_SUCCEEDED`, `BODY_IDENTITY_MISMATCH`,
  `RUN_MISMATCH`, `RELEASE_MISMATCH` or `EVIDENCE_MISMATCH`.
  - `WRONG_ORIGIN` is checked twice: first the row's origin, then, for a completed success only, the
    origin in its stored body.
  - `RUNNER_DISAGREES` (also exit 1) means the runner's own reading of the facts differs from the SQL's.
- **Stopped, nothing contacted:** exit 2 means an input was refused; exit 3 means the sealed SQL does
  not match its pin.
- **Database stop:** exit 4, named by `reason` and `error_class` only.
- **`NO_ROW` from a role that row-level security hides rows from** looks the same as a missing row.
  Run it as one of the roles in WHERE.
- The ledger keeps rows for at least 90 days (docs/automation/RETENTION_AND_IDEMPOTENCY.md), so run it
  within that window.

## HOW_VERIFIED
- The package's sha256s match `docs/automation/UOR_HANDOFF.md` §14, which UOR pins.
- tests/automation/test_a4_ledger_audit.py checks the guard, the schema against migration 0013, the
  adversarial mutants and the runner.
- The scratch-PostgreSQL rehearsal (.github/workflows/a4-ledger-audit-rehearsal.yml) runs every
  case on a real PostgreSQL.

## RESUME
Hand the one JSON line to UOR for its A4 adjudication. UCPE writes nothing, and UCPE never writes to
UOR.
