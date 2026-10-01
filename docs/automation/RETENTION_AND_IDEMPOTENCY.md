# Retention and idempotency: the F1 audit

Scope: the automation ledger `public.automation_radar_ledger` and the credential registry
`public.automation_credential` (migration 0013, authored, **not applied**). Each statement below
names the code or test that holds it.

## 1. What is recorded, and what never is

- **One ledger row per authenticated, well-formed call**, keyed by `(credential_id,
  client_request_id)`. The row is reserved `IN_PROGRESS` before any analysis starts, then completed
  with the outcome, the HTTP status and the exact response body (`automation/ledger.py`).
- **Never recorded (no row, no log line):** a missing, malformed, unknown, mismatched, revoked or
  expired credential (401); a human session cookie (403); a malformed body (400); an unsupported
  symbol or timeframe (422); the route disabled or misconfigured (503); the registry or ledger
  unreachable before the reservation (503). Unauthenticated traffic can therefore never grow the
  table (`test_invalid_credential_writes_no_row`, `test_request_refusals_write_no_row`,
  `test_an_unavailable_registry_fails_closed_and_writes_no_row`).
- **Repeats are answered from the row** and never recorded again: a replay, a conflict, or a repeat
  while the first call is still running.
- **Refusals after the reservation are recorded** against their key (`QUOTA_EXCEEDED`,
  `CONCURRENCY_LIMIT`, `DEADLINE_EXCEEDED`, the analysis and contract failures). A repeat of that
  key therefore replays the same refusal. `QUOTA_EXCEEDED` and `CONCURRENCY_LIMIT` never count
  against the quota.
- **Capacity refusals are never recorded** (section 2): a full ledger (503 `LEDGER_UNAVAILABLE`),
  or a credential past its rolling-day row ceiling (429 `QUOTA_EXCEEDED`).
- **The registry** records a digest per credential, never a value (`CREDENTIAL_ROTATION.md`).

## 2. Retention and the capacity contract (frozen; `automation/config.py`)

Storage is bounded, and the route itself never deletes a row. There is no recurring job and no
automatic production mutation. The route fails closed at its bound.

- **Retention: at least 90 days** (`LEDGER_RETENTION_DAYS`).
  - No code path, script, workflow or migration deletes or truncates a ledger or registry row
    (`tests/automation/test_retention_semantics.py`).
  - Only an owner-run purge, of ledger rows older than 90 days, ever removes one. A registry row is
    never removed.
- **The row cap: the ledger never takes a new row once it holds 25,000 rows** (`LEDGER_ROW_CAP`).
  - A new request is then refused with 503 `LEDGER_UNAVAILABLE`, and nothing is written.
  - A repeat of an already recorded request is still answered.
  - One advisory lock covers the whole ledger, so the cap holds under concurrency.
- **The row ceiling: a credential records at most 2 x its daily quota rows in any rolling day,
  refusals included** (`LEDGER_ROWS_PER_QUOTA_UNIT`).
  - Beyond that, a new request is refused with 429 `QUOTA_EXCEEDED`, nothing is written, and
    `Retry-After` says when the oldest row of the day leaves the window.
  - So no client, however it misbehaves, can fill the ledger. At the maximum it adds 240 rows a day.
- **The body bound: no stored response body exceeds 8,192 bytes** of RFC 8785 JCS
  (`LEDGER_MAX_BODY_BYTES`).
  - A success body that would exceed it is withheld as `CONTRACT_VIOLATION`.
  - A real evidence body is about 2.2 KB, and a schema-maximal one about 2.9 KB.
- **The quota is bounded by the contract: at most 120 per day** (`MAX_QUOTA_PER_DAY`).
  - At that maximum, 90 days of one credential (21,600 rows) always fit under the cap.
  - A higher quota is refused as a misconfiguration (503 `NOT_CONFIGURED`).
  - G6 stays provisional at 6 per 5 minutes and 120 per day. Raising it needs measured production
    resource evidence and a reviewed change of this contract.
- **Storage bound.**
  - Hard: at most 25,000 rows, each with a body of at most 8 KB, which is about 220 MB worst case.
  - Expected at the maximum quota with the full refusal allowance: about 21,600 rows of mostly
    2-3 KB bodies after 90 days, about 40 MB.
  - Several credentials active at once share the one cap.
- **When the cap is reached.** At sustained maximum use, that is after about 104 days. The route
  then refuses new requests (fail closed) until the owner purges rows older than 90 days.
  - At the maximum, purges are then needed about every two weeks.
  - At realistic use, measure the rate in production first. The purge is on demand, never
    scheduled.
- **The owner's purge (a T4, on demand, in the Supabase SQL editor).** It removes only completed
  rows older than 90 days:
  ```sql
  DELETE FROM public.automation_radar_ledger
   WHERE state = 'COMPLETED' AND received_at_utc < now() - interval '90 days';
  ```
- **The owner's headroom check (read-only):**
  ```sql
  SELECT count(*) AS rows, 25000 - count(*) AS headroom, min(received_at_utc) AS oldest
    FROM public.automation_radar_ledger;
  ```

## 3. Idempotency: what the key guarantees, and for how long

- **Scope: per credential.** The key is `(credential_id, client_request_id)`, the table's primary
  key. The same `client_request_id` under a different credential is a different request. After a
  rotation, a retry must use the credential it began under (`CREDENTIAL_ROTATION.md`, step 3).
- **Lifetime: as long as the row exists.** That is at least the 90-day retention, and in practice
  until an owner-authorized purge. After a purge, a reused `client_request_id` would start a new
  analysis.
- **The consumer's duty.** Use a fresh random UUID (version 4) for every logical request, and reuse
  it only to retry that same request. The contract validates the UUID's form, not its freshness.
- **Outcomes:**
  - a repeat with the same fingerprint REPLAYS the stored answer, byte for byte (RFC 8785 JCS).
    The replay is re-validated against its schema before it is sent. The real-PostgreSQL rehearsal
    proves byte identity through JSONB storage;
  - a different body under the same key is `IDEMPOTENCY_CONFLICT` (409);
  - a repeat while the first call runs is `REQUEST_IN_PROGRESS` (409);
  - a reservation still `IN_PROGRESS` past its deadline plus 60 seconds of grace is ABANDONED. It is
    closed as `DEADLINE_EXCEEDED` and **never re-run**.
- **An unknown outcome.** A 503 `LEDGER_UNAVAILABLE` answer after an analysis means the record's
  commit may or may not have landed; only a replay of that key reveals which. Evidence is returned
  only after its on-time record commits, so the ledger never says less than the caller was told.
- **Revocation outranks replay.** A revoked credential cannot replay even its own earlier evidence:
  authentication runs before the ledger is read
  (`test_a_revoked_credential_cannot_replay_its_earlier_evidence`).

## 4. The in-memory ledger

`InMemoryAutomationLedger` exists for tests and local runs only; production always wires the
PostgreSQL ledger (`api/automation_endpoint.py`). It prunes entries older than a day plus two hours,
enough for the quota windows. Its idempotency therefore lasts about 26 hours, not 90 days, which is
one more reason it must never be wired in production.

## 5. Verdict

- Retention and idempotency semantics are consistent with the contract.
- Storage is bounded by the frozen capacity contract (section 2). The route fails closed at its
  bound, and never deletes a row itself.
- The only open items are the owner's: G6 stays provisional until measured production resource
  evidence exists, and the purge stays on demand.
- Neither blocks the merge. Neither is needed before a canary.
