# F1 release plan: merge, apply, release, credential, enable, canary, handoff

Status: **prepared; nothing here is executed.** Every numbered step is an owner boundary (T3 or T4)
and runs only under the owner's authorization of that step. Until step 6 the route is OFF (the
default), no credential exists, and the route fails closed at every layer.

## 0. Merge readiness (before step 1)

- PR CI is green on the exact head: the main `test` job and the real-PostgreSQL rehearsal
  (`apply-migration-0013-rehearsal.yml`, also a job named `test`).
- `./verify.sh` passes on the exact head.
- The independent Codex security and adversarial review of the post-repair diff has passed. **This
  gate stays OPEN until that review actually runs. It is never substituted.**

## 1. Merge the PR (T3)

- Merge with a merge commit and exact-head checks; call the result `M`.
- Merging deploys nothing: production changes only through step 3.
- After the merge, `main` contains the route (off), the migration (not applied) and the apply
  route (dispatch-only).

## 2. Apply migration 0013 (T4, one shot, never rerun)

- Dispatch `.github/workflows/apply-migration-0013.yml` on `main` with:
  - `expected_sha` = `M`, all 40 characters;
  - `confirm` = `APPLY-MIGRATION-0013-ONCE`.
- The job then runs:
  1. the isolation, dispatch and runtime attestation (no database);
  2. the rehearsal on scratch PostgreSQL (no secret): apply once, then a second apply refused; every
     API role refused; the application's own SQL probed; and a rebuild from migrations 0001-0010
     alone;
  3. the route's tests under the locked runtime;
  4. only then, the one step that holds the secret: the apply, in one transaction.
- **PASS:** the apply report says `outcome: APPLIED` and `committed: true`.
- **REFUSED:** nothing was applied. Stop and adjudicate from the report. Never re-dispatch blindly.
- **`committed: UNKNOWN`:** stop and adjudicate. Had it committed, a second dispatch would refuse as
  "not a first apply".
- Order: the apply may come before or after step 3. The route fails closed without the tables, and
  the tables are inert without the route. Applying first lets the canary follow the enable at once.
- Rollback: none needed. The tables are inert while the route is off, and no step ever drops them.

## 3. Release carrying F1 (T4), then the guard re-pin (T3)

- Follow the W26 release chain:
  - an identity commit (for example `UCPE-PROD-F1-AUTOMATION-<date>-A`) and its PR;
  - one plain fast-forward push to `hf/main`;
  - the settle checks;
  - the source-integrity guard re-pin; its guarded delta includes `api/analysis_service.py` and
    `api/app.py`.
- Rollback target: sealed when that release is prepared, as in W26. It is the production release
  being replaced: today `2096af6d1b3d54461b40c47fd96c265882e5af40` /
  `UCPE-PROD-TC-V1-STAMP-20260930-A`, and never `00705c55`.
- Human routes: unchanged. The non-regression suite covers every human method and path.

## 4. Issue the credential (T4, owner)

- `CREDENTIAL_ROTATION.md`, "Issue a credential".
- The value never goes into a chat, a file in the repository or a log. UCPE never stores it: only its
  digest goes into the registry.

## 5. The quota (G6, T3)

- G6 is provisional: 6 per 5 minutes and 120 per day, which are also the code defaults.
- 120 per day is also the maximum the capacity contract allows. Raising it needs measured
  production resource evidence and a reviewed change of the contract.
- Set `UCPE_AUTOMATION_QUOTA_PER_5MIN` and `UCPE_AUTOMATION_QUOTA_PER_DAY` only to lower them.

## 6. Enable (T3)

- Set `UCPE_AUTOMATION_ENABLED=1` on the Space. The change restarts the Space.
- To stop:
  - the fastest way is revoking the credential, which is immediate with no restart;
  - clearing the variable also works, with a restart.

## 7. Canary (owner-run, one live request, under its own authorization)

- One `POST /v1/automation/radar-evidence` from the owner's machine. The token is typed at a hidden
  prompt, never on a command line. The body is BTC, 4H, a fresh UUID v4 and a 30000 ms deadline.
- **PASS requires all of these:**
  1. HTTP 200 and a body valid against the pinned `radar_evidence.v1` schema;
  2. `evidence_origin` is `AUTOMATED_RADAR`, `is_live_data` is true, `profitability_claim` is false;
  3. `build_info.release_id` is the release of step 3;
  4. `evidence_hash` recomputes offline (the procedure in `UOR_HANDOFF.md`);
  5. the same body sent again returns byte-identical bytes, with `Idempotent-Replay: true`;
  6. a one-row owner SQL read of the ledger shows that key `COMPLETED` / `SUCCEEDED` / 200, with the
     same `run_id` and `evidence_hash`;
  7. no `predictions` row carries the canary's `run_id`.
- **Operational, not a failure:** 503 `UPSTREAM_UNAVAILABLE` (market data). Retry later with a NEW
  UUID, under the same authorization.
- **Stop and adjudicate:** 503 `LEDGER_UNAVAILABLE`. It means the Space cannot reach the registry or
  the ledger. The route stays fail-closed; revoke or disable, then investigate the Space's
  `SUPABASE_DB_URL` transport.
- **FAIL:** anything else. Revoke the credential at once (no restart) and adjudicate.
- Operational success is not directional or model evidence. The H2 hold and every skill gate are
  unchanged.

## After the canary: capacity (owner, on demand)

- The ledger fails closed at 25,000 rows (`RETENTION_AND_IDEMPOTENCY.md` section 2).
- Check the headroom with the read-only query there. Measure the real daily row rate before
  revisiting G6.
- When the ledger nears the cap, the owner runs the on-demand purge of rows older than 90 days
  (a T4). Nothing runs it on a schedule.

## 8. Handoff to UOR (UOR's own sessions)

- `UOR_HANDOFF.md` pins every contract file by sha256: the schemas, the contract, the credential
  procedure, the retention and idempotency audit, and the examples.
- UOR stores the token by NAME in its governed secret store, and builds its registry and transport
  in its own sessions. UCPE never writes to UOR.

## The transport, reconfirmed

- The route's connections to the database are:
  - made per call (nothing connects at startup);
  - bounded, per operation, not end to end: connect, statement and lock timeouts, a TCP user
    timeout for a network that stalls after connecting, and at most two registry reads in flight;
  - safe behind Supabase's transaction pooler (no server-side prepared statements).
- A database that is missing or unreachable when a request is admitted answers 503
  `LEDGER_UNAVAILABLE`, and nothing is written (`tests/automation/test_transport_fail_closed.py`; the
  real-PostgreSQL probe proves the same against a missing database).
- A failure later, while recording, can leave the reservation `IN_PROGRESS` (closed later as
  `DEADLINE_EXCEEDED`, never re-run), or an outcome whose commit is unknown
  (`RETENTION_AND_IDEMPOTENCY.md` section 3).
- The Space's reach to the database is **not assumed**. The human persistence reaches it through
  the same `SUPABASE_DB_URL` (W26 PASS_PROVEN). The route's own connections are unproven until
  step 7, and they fail closed until then.
