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
- **The registry** records a digest per credential, never a value (`CREDENTIAL_ROTATION.md`).

## 2. Retention

- **Stated minimum: 90 days** (`LEDGER_RETENTION_DAYS = 90` in `automation/config.py`).
- **Nothing purges automatically.** No code path, script, workflow or migration deletes or
  truncates a ledger or registry row (`tests/automation/test_retention_semantics.py`). Rows are kept
  until the owner authorizes a purge. That purge is **not built**: it would be its own reviewed,
  dedicated route (T4), deleting only `COMPLETED` ledger rows older than the retention, and never a
  registry row.
- **Capacity (owner item, not a merge blocker).** A success row holds a body of about 2.7 KB, about
  3.5 KB with overhead. At the provisional maximum quota (G6: 120 per day):
  - 90 days need about 40 MB;
  - a year without a purge needs about 150 MB.
  Supabase's free tier allows 500 MB for the whole database, so a purge route, or a lower quota, is
  needed before about a year of sustained maximum use.
- **Refusal rows.** An authenticated caller that ignores `Retry-After` adds one small refusal row
  (about 0.4 KB) per new `client_request_id`. The credential holder is the owner's own consumer; if
  it misbehaves, revoke its credential (`CREDENTIAL_ROTATION.md`), which stops it at once.

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
- The only open items are the owner's: a future purge route (capacity), and G6.
- Neither blocks the merge. Neither is needed before a canary.
