# ucpe.a4_card04_companion.v1: the owner card for one future UOR qualification episode

**PREPARED, NOT RUN.** Nothing in this package has queried production. Running it is a separate owner
decision, made at the qualification episode itself, beside the accepted A4 audit
(`ucpe.a4_ledger_audit.v1`) of the same request.

## What it is
- **The one job:** prove the five durable facts UOR Card 04 still needs for one qualification request
  to `POST /v1/automation/radar-evidence`:
  - the request's `deadline_ms`, from its ledger row;
  - the run's `analysis_hash`, from the same row;
  - how many `public.predictions` rows carry the run's `run_id`;
  - how many ledger rows the credential has from the qualification's activation on;
  - how many ledger rows carry the request's `client_request_id`, under any credential (owner ruling
    A4-CRID-UNIQUENESS, 2026-10-05). It names no credential.
- **What it is not:** a database tool. It reads ten columns of `public.automation_radar_ledger` and
  `public.predictions.run_id`, and nothing else: no probability, label, outcome, snapshot, calibration,
  credential registry, section 5A data or response body.
- **The `predictions` read** returns one count. It is isolation evidence, never model or directional
  evidence (owner ruling, 2026-10-05).
- **The sealed SELECT:** `a4_card04_companion.sql`. The runner `a4_card04_companion.py` pins its sha256,
  and before contacting anything it checks every package file against `MANIFEST.json`.
- **Read only:**
  - the runner opens the transaction `READ ONLY`, with row security off, proves both, bounds it at
    5 s, and always rolls back;
  - with row security off, a row-level policy that would hide a row raises an error instead, so neither
    count can be silently filtered to zero;
  - it never prints the database URL, a credential value or an exception message.

## ACTION_ID
A4-CARD04-COMPANION, once per qualification request, only inside the owner-authorized episode.

## WHY
UOR Card 04 must see the request's deadline, the run's analysis identity, that run's footprint in the
shared prediction table, the credential's ledger activity since activation, and that the request's
client_request_id has one ledger row in all (the ledger's key is the pair, not the id), each read from
the durable record rather than from UOR's own memory of it.

## WHERE
- A terminal with this repository at the commit that carries this package.
- **The database role:** the role that owns both `public.automation_radar_ledger` and
  `public.predictions`, or a role with BYPASSRLS and SELECT on exactly the ten ledger columns and
  `predictions.run_id`.
  - The owning role can do far more than read; this run stays read-only only because of its READ ONLY
    transaction, which the runner proves before it reads anything.
  - No migration creates a BYPASSRLS reader. Creating one is a production change, for the owner to
    authorize separately.
  - A role that row-level policies apply to is refused (exit 4, `InsufficientPrivilege`) rather than
    counted through a policy. That includes `ucpe_space_db`, which the A4 audit accepts.
- The URL is entered without echo. It never goes into a command line, a chat, a file or a log.

## EXACT_STEPS
1. From UOR's own record of the request and its received 200 response, copy six values:
   - the credential **id** (e.g. `uor-radar-2026-10`; never the `ucpea.` token);
   - `client_request_id`;
   - `run_id`;
   - the request's `deadline_ms`;
   - the response's `analysis_hash`;
   - the qualification's activation instant, as UTC: `YYYY-MM-DDTHH:MM:SSZ` (fractional seconds
     allowed).
2. `read -rs A4_COMPANION_DATABASE_URL && export A4_COMPANION_DATABASE_URL`, then paste the URL. It is
   not echoed.
3. Run:
   `python ops/a4_card04_companion/a4_card04_companion.py --credential-id <id> --client-request-id <uuid> --run-id <run_id> --deadline-ms <deadline_ms> --analysis-hash <analysis_hash> --qualification-activation-utc <activation>`
4. `unset A4_COMPANION_DATABASE_URL`.

## DO_NOT_DO
- Never run it outside the episode, and never against anything but the ledger's own database.
- Never edit the SQL or any package file. A change is a new artifact version, with a new seal that UOR
  must pin again.
- Never pass the credential token or the URL as an argument.
- Never bind on `client_request_id` alone: the ledger's key is the pair.
- Never treat a count as accepted or rejected here. Card 04 judges the counts; this card only reports
  them.

## EXPECTED_RESULT
One JSON line, with sorted keys:
- **PASS:** `"verdict":"PASS","reason":"OK"` and exit code 0. The five facts are evidence only on a
  PASS.
- **FAIL, the audit ran:** exit code 1, with `reason` naming the first failing check: `SCHEMA_DRIFT`,
  `NO_ROW`, `AMBIGUOUS`, `WRONG_ORIGIN`, `NOT_COMPLETED`, `NOT_SUCCEEDED`, `RUN_MISMATCH`,
  `DEADLINE_MISMATCH`, `ANALYSIS_HASH_MISMATCH` or `ACTIVATION_AFTER_REQUEST`.
  - `SCHEMA_DRIFT` means a column it reads has another type or nullability than its migration gives
    it, a table it reads is not an ordinary table (a view, for example) or has an inheritance child, or
    the ledger's primary key is not the pair. A column it does not read is not drift.
  - `RUNNER_DISAGREES` (also exit 1) means the runner's own reading of the SQL's answer differs from it.
- **Stopped, nothing contacted:** exit 2 means an input was refused; exit 3 means a package file or the
  SQL does not match its seal.
- **Database stop:** exit 4, named by `reason` and `error_class` only. `InsufficientPrivilege` means the
  role is not one of those in WHERE.
- **The credential count** includes every ledger row of the credential received at or after the
  activation instant, the bound request's own row included, whatever its outcome.
- **The cross-credential count** includes every ledger row carrying the bound `client_request_id`,
  under any credential and whatever its state or outcome. When the row is bound it is at least 1.
  Card 04 adjudicates it (its acceptance value is 1); this card reports it and never names another
  credential.
- The ledger keeps rows for at least 90 days (docs/automation/RETENTION_AND_IDEMPOTENCY.md), so run it
  within that window.

## HOW_VERIFIED
- The package's sha256s match `docs/automation/UOR_HANDOFF.md` §15, which UOR pins.
- tests/automation/test_a4_card04_companion.py checks the guard, the schema against migrations 0013 and
  0003, the adversarial mutants and the runner.
- The scratch-PostgreSQL 17.6 rehearsal (scripts/a4_card04_companion_rehearsal/) runs every case on a
  real server, including a role that can read only the eleven columns.

## RESUME
Hand the one JSON line to UOR for its Card 04 adjudication. UCPE writes nothing, and UCPE never writes
to UOR.
