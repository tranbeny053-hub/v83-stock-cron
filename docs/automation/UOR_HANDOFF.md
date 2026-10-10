# UCPE → UOR governed handoff package for F1 (`radar_evidence.v1`)

**What this is.** This is everything UCPE hands UOR for machine-to-machine evidence, per UOR handoff file 05
§13.
- UOR pins every file in section 4 by its sha256. Any change to a pinned schema means a new version.
- UCPE never writes to UOR. The owner carries this package into UOR's own governed sessions.
- The handoff itself is owner-gated (T3/G2).

## 1. States (exact, 2026-10-01)

| Step | State | Proof |
|---|---|---|
| Implementation | MERGED: main `5da10ef3` (PR #144) | CI and the real-PostgreSQL rehearsal green. The gate was a CLAUDE_ADVERSARIAL_REVIEW (not independent; Codex paused by the owner), with 48 bounded mutants, all killed. |
| Ledger and registry (migration 0013) | APPLIED in production, once (T4) | Run 36820986264: APPLIED and committed. Both tables locked: RLS on, no policy, no API-role privilege. |
| Release | `UCPE-PROD-F1-AUTOMATION-20261001-A`, commit `5a3ef022` (PR #145) | Push CI green. |
| Deploy | DEPLOYED 2026-10-01T06:40Z, one fast-forward push | Settle PASS: RUNNING at `5a3ef022`, health 200, build-info, static digests. |
| Source guard | Re-pinned (PR #146) | HEALTHY in all 3 rounds, delta `[]` (run 36828594390). |
| Route | ENABLED by the owner (`UCPE_AUTOMATION_ENABLED=1`, T3) | Post-enable check PASS 7/7; extra read-only checks PASS 6/6. |
| Credential | `uor-radar-2026-10`, ISSUED by the owner (T4), ACTIVE | Named by id and role only (section 10). |
| Canary | F1_CANARY=PASS (2026-10-01T10:25:15Z) | Section 11. |
| Live isolation | LIVE_ISOLATION=PASS | Section 11. |
| UOR side | NOT STARTED by UCPE | Section 13. |

- The UCPE side is production-ready and proven for one consumer, `uor-radar-2026-10`, at the provisional G6
  quota.
- Turning on UOR's consumption is the owner's decision in UOR's own governed sessions: its registries,
  transport, release allowlist and any Cron. Nothing in this package performs or authorizes that.

## 2. The endpoint

- **The route:** `POST https://beny053-ultimate-crypto-probability-engine.hf.space/v1/automation/radar-evidence`.
  - JSON in and out, one symbol per call, no batch endpoint.
  - Omitted from OpenAPI (contract §1).
- **The header:** `X-UCPE-Automation-Credential: ucpea.<credential_id>.<value>`.
  - Never in a URL, a query string or a body.
  - For server-side callers only: CORS is not a control here (contract §2).
- **The body:** strict, at most 1,024 bytes (contract §4).
  `{"symbol": "BTC", "primary_timeframe": "4H", "client_request_id": "<canonical lowercase UUID>", "deadline_ms": 30000}`
  - `primary_timeframe` is one of `15m`, `1H`, `4H`, `1D`.
  - `deadline_ms` is an integer from 5000 to 60000.
- **One analysis at a time per service instance.** Send calls one after another (contract §10).
  - A busy slot answers 429 `CONCURRENCY_LIMIT` with `Retry-After: 10`.
  - It never queues.

## 3. The governed origin

- `evidence_origin` is always `AUTOMATED_RADAR`, stamped by the server from the credential. The caller cannot
  assert it.
- It is not a `PredictionOrigin`. An automated run never touches:
  - the cohort tables (`predictions`, `prediction_outcomes`, `analysis_runs`, the snapshots);
  - calibration or the skill gate's evidence;
  - `/v1/runs` or the resolver.
- It lives only in `public.automation_radar_ledger` (contract §3, `COHORT_READER_AUDIT.md`).
- Live data only. No protected section 5A evidence is used, returned or inferable.

## 4. Schemas, versions and pinned files

Revision 2026-10-05 (owner ruling DP-A=2; held local until UOR qualification episode QUAL-EP-20261010-01 closed):
the MANIFEST and the two synthetic success examples below were regenerated because UX-1 changed the analysis
payload's `probability_explanation` text, which moves each example's `analysis_hash` and `evidence_hash`. The
schemas, the contract and every value's meaning are unchanged. That episode closed with qualification BLOCKED /
NOT_PROVEN: its closing ended the hold on publishing this revision, and nothing here reads it as a pass.

| File | Role | sha256 |
|---|---|---|
| `schemas/radar_evidence.schema.json` | pinned success schema (`radar_evidence.v1`) | `460458ade4f65e6850e024d3d3a6cc042c40219b802b8ddd89c93ae35a4be5c7` |
| `schemas/radar_evidence_error.schema.json` | pinned error schema (`radar_evidence_error.v1`) | `983001a75249ed5b5b0f5df5fae1910ab4a511418eaac81172a6362cfb1d6315` |
| `docs/automation/RADAR_EVIDENCE_V1.md` | the UCPE canon contract | `86f6779bb26a6855d02da0d0c2c6be2497f6bbbadea00f166515a8bf91934f78` |
| `docs/automation/F1_NODE_CLASSIFICATION.md` | proposal nodes under UCPE canon | `70fb0bad6431830498f06699d57eca5cf4f56ce4de7eb2863ac4772163d27178` |
| `docs/automation/COHORT_READER_AUDIT.md` | why the origin is isolated | `ad8b0b9c770a82063106c24f5db6f071657efdfada2913d9e84d7a505fd1b19f` |
| `docs/automation/CREDENTIAL_ROTATION.md` | credential issue, rotation and revocation | `ff791b70fb803f225ec43004dc88ad86537a1418b70517dc7af6219c4fa11827` |
| `docs/automation/RETENTION_AND_IDEMPOTENCY.md` | retention and idempotency audit | `09739bf95644b8ddff499ffdc7ef7992926dd5c4e50279983cd42c25f5312036` |
| `docs/automation/F1_RELEASE_PLAN.md` | the owner-gated release plan | `97973502ee6d71e706153164b1a92ca897e6c3ebed88cad0dd83c78b27acb791` |
| `docs/automation/examples/MANIFEST.json` | synthetic example provenance and digests | `de516e10d40e70ada6b619ad6f619a266b17d0c4c6c3762cca9b8e9078132404` |
| `docs/automation/examples/radar_evidence.v1.synthetic-btc-4h-gate-blocked.json` | synthetic example: gate blocked | `4447dc2c069d4c4bc2ee9a276d17f30b988636e2b60a2ae09d5a187dcbdd1882` |
| `docs/automation/examples/radar_evidence.v1.synthetic-eth-1h-h2-hold.json` | synthetic example: H2 hold | `b85b514cff1235d0edb8c0fb7f21c58cf51e76f191f80b30de93ef14106f201c` |
| `docs/automation/examples/radar_evidence_error.v1.synthetic-quota-exceeded.json` | synthetic error example | `55907162860e60316fd39bb4fdf07cc627fba452074123779158ff23a3a56c60` |
| `docs/automation/examples_live/PROVENANCE.json` | live example provenance and digest | `128694dd1cfb498c22dff8e06bec03a8541a05433b428e6da6cd5b50386f3860` |
| `docs/automation/examples_live/radar_evidence.v1.live-canary-btc-4h-20261001.json` | LIVE_SAVED example: the canary's exact answer | `527b81220b3ecf459d0d5a7da584f9c965225c06d20f24cffd4b88c4de47ae39` |

## 5. Release identity

- Every response carries `build_info`, the serving release's public build identity. Under F1 it read:
  - `release_id`: `UCPE-PROD-F1-AUTOMATION-20261001-A`;
  - `release_label`: `PROD-F1-AUTOMATION release of main`;
  - `environment`: `HF_PRODUCTION`;
  - `source_milestone`: `prod-f1-automation`;
  - `fingerprint`: `UCPE LIVE BUILD · PROD-F1-AUTOMATION-20261001-A`.
- **Corrected 2026-10-04.** This line used to say F1 "is the only UCPE release serving `radar_evidence.v1`".
  That is no longer true.
  - F1 introduced the route, and every later release inherits it unchanged:
    `src/crypto_probability_engine/automation/`, `api/automation_endpoint.py`, migration 0013 and both radar
    schemas are byte-identical from F1's `5a3ef022` to `1caa8b08`.
  - Production now serves it as `UCPE-PROD-E2-20261004-A`, commit `1caa8b08`.
  - Each response's `build_info.release_id`, and its ledger row's `release_id`, name the release that served
    that request.
- Adding it to UOR's `ACCEPTED_UPSTREAM_RELEASES` is an owner decision on UOR's side, made after UOR's contract
  fixtures pass against the examples in section 7.
- The synthetic examples' `UCPE-SYNTHETIC-EXAMPLE-V1` is served by no release and must never be allowlisted.

## 6. Evidence identity: JCS and hashes

**Verifying a received body.**
1. Parse the JSON body.
2. Remove `evidence_hash`.
3. Serialize the rest with RFC 8785 JCS.
4. Compare `"sha256:" + hex(sha256(bytes))` with the removed `evidence_hash`.

The raw response bytes are themselves the JCS form of the full body (contract §6).
- `run_id` matches `run_<32 hex>` and is unique per run.
- `analysis_hash` is UCPE's own analysis identity, carried as read. Consumers must not recompute it (contract §6).

## 7. Examples (non-holdout, provenance-declared)

- **SYNTHETIC_FIXTURE** (`docs/automation/examples/`, `MANIFEST.json`):
  - the real pipeline on deterministic fixture candles, with no live data, no holdout and no section 5A
    evidence;
  - two success bodies (gate blocked; H2 hold) and one 429 error body;
  - to regenerate them: `PYTHONPATH=src:. python -m tests.automation.examples_builder --write`.
- **LIVE_SAVED** (`docs/automation/examples_live/`, `PROVENANCE.json`):
  - the governed release's exact answer to the owner's canary (BTC, 4H, 2026-10-01T10:25:15Z);
  - live public market data, with no holdout and no section 5A evidence;
  - it carries the real release identity, so UOR's release allowlist can be tested against it;
  - operational evidence only, not directional or model evidence.

## 8. Quota and capacity (G6, provisional)

- **The quota** is per credential and counted from the ledger, so a restart never resets it.
  - 6 per 5 minutes and 120 per day (G6, provisional). The owner may only lower them; the code refuses a daily
    quota above 120.
  - `Retry-After` covers every exhausted window.
  - Refusals made before an analysis do not count against the quota (contract §10).
- **The capacity contract** (contract §12):
  - retention is at least 90 days;
  - at most 25,000 ledger rows, then 503 `LEDGER_UNAVAILABLE` with nothing written (replays are still served);
  - at most 2 x the daily quota rows per credential in any rolling day, then 429 `QUOTA_EXCEEDED` with nothing
    written;
  - no stored body above 8,192 bytes.
- **Cost:** free public market data plus a few seconds of Space CPU per counted call. There is no paid API.

## 9. Errors, timeouts and replay

- **Error bodies** are `radar_evidence_error.v1`, with a fixed code catalogue and fixed messages (the pinned
  error schema, contract §8):

  | Status | Codes |
  |---|---|
  | 400 | `MALFORMED_REQUEST` |
  | 401 | `CREDENTIAL_REQUIRED`, `CREDENTIAL_INVALID` |
  | 403 | `HUMAN_SESSION_REFUSED` |
  | 409 | `IDEMPOTENCY_CONFLICT`, `REQUEST_IN_PROGRESS` |
  | 422 | `UNSUPPORTED_SYMBOL`, `UNSUPPORTED_TIMEFRAME` |
  | 429 (with `Retry-After`) | `QUOTA_EXCEEDED`, `CONCURRENCY_LIMIT` |
  | 503 | `AUTOMATION_DISABLED`, `NOT_CONFIGURED`, `LEDGER_UNAVAILABLE`, `DEADLINE_EXCEEDED`, `UPSTREAM_UNAVAILABLE`, `ANALYSIS_FAILED`, `CONTRACT_VIOLATION` |

- Every response carries `Cache-Control: no-store`.
- **The deadline** (contract §8): `deadline_ms` is a monotonic budget that starts on arrival. A success is
  recorded only if its recording statement runs at least 0.25 s before the deadline.
  - Set the client timeout to the deadline plus a margin for recording and transit. The canary used 75 s for
    30000 ms.
- **The consumer rule:** any non-200 or timeout means no evidence for that symbol this cycle, never a degraded
  guess.
- **Replay** (contract §9):
  - the same `client_request_id` with the same request returns the recorded outcome byte for byte, with
    `Idempotent-Replay: true`;
  - a different request under the same key gets 409 `IDEMPOTENCY_CONFLICT`;
  - a 503 `LEDGER_UNAVAILABLE` after an analysis means the outcome is unknown.
  - UOR never retries inside a cycle.

## 10. The credential, by name and role only

- **`uor-radar-2026-10`** is the UOR radar consumer's credential for its first period. The owner issued it on
  2026-10-01 (T4), and it is ACTIVE.
- **Its value never appears in UCPE.**
  - The registry holds only its sha256 digest; the route hashes a presented value in memory.
  - The full token `ucpea.uor-radar-2026-10.<value>` lives only in the owner's custody, and once handed over, in
    UOR's governed secret store, referred to by NAME.
  - It never goes into a chat, a repository, a command line or a log.
- **Rotation, with no restart:**
  1. issue a new id;
  2. move the consumer;
  3. wait out its in-flight requests;
  4. revoke the old id.
  Revocation applies at the next request.
- **Never** reuse an id, un-revoke or delete a row (`CREDENTIAL_ROTATION.md`).
- The id `probe-never-issued` is reserved for UCPE's read-only checks and is never issued.

## 11. Isolation and audit proof

- **In code and CI:**
  - `tests/automation/test_cohort_isolation.py`: no persistence, no run store, no cohort field or writer;
  - the human-route non-regression suite.
- **In production, read-only, after the enable:**
  - a human session cookie is refused (403), and malformed and unknown credentials are refused (401);
  - the route reads its registry over its own connection: a never-issued id answers 401 `CREDENTIAL_INVALID`,
    not 503;
  - **the canary** (`client_request_id` `3e8ca8f0-5016-4e45-9ea1-0aedbe815260`):
    - 200 and schema-valid;
    - `run_id` `run_d33406cea53648829428b829198577d3`;
    - `evidence_hash` `sha256:58191ef5c11e12eaadbddc6b5289eecbf0d56fd18999074c6576dd0d8a9ba846`, re-verified
      independently;
    - the replay is byte-identical;
  - **the owner's SQL:**
    - exactly one ledger row for that request: COMPLETED / SUCCEEDED / 200, with that run_id, evidence_hash and
      release;
    - no `predictions` row carries its run_id;
    - the global isolation query of contract §3 returned 0.
- **Audit, per call** (contract §12): one ledger row per (credential, `client_request_id`), holding:
  - the credential id, never its value;
  - the origin and the request fingerprint;
  - the outcome and status, and the exact response body;
  - `run_id`, `analysis_hash`, `evidence_hash` and `release_id`;
  - the deadline and both timestamps.
  Retention is at least 90 days.

## 12. Kill switch and rollback

- **Fastest, with no restart:** revoke the credential. The next request is refused 401.
- **The kill switch:** clear `UCPE_AUTOMATION_ENABLED`, which restarts the Space. Every call then gets 503
  `AUTOMATION_DISABLED`.
- **Release rollback (corrected 2026-10-04):** this line used to name a T4 rollback to `2096af6d`
  (`UCPE-PROD-TC-V1-STAMP-20260930-A`) "which removes the route". That target is no longer safe.
  - Migration 0018 makes a code rollback write-safe only to WA `a2de125f` or later (`ops/release/releases.json`).
  - Every release from F1 on carries the route.
  - The current rollback target, `6f4420a9` (`UCPE-PROD-R1A-20261003-A`), keeps it.
  - To stop the route, use the kill switch or revoke the credential. The ledger stays inert.
- **UOR** falls back to no evidence on any error. On its side, either of these returns every cycle to
  RADAR/OBSERVE with "NO UCPE EVIDENCE":
  - removing the origin or the release from its registries;
  - setting its evidence mode back to none.
- **Deprecation:** any breaking or semantic change is a new schema version, retired only after notice.

## 13. The UOR-side boundary (not crossed here)

UCPE stops here. The rest happens in UOR's own governed sessions, under the owner's authorization there:
1. store the token by NAME in UOR's secret store;
2. run UOR's contract fixtures against the pinned schemas and the examples, then decide the release allowlist;
3. register the origin and build the transport (`uor.ucpe.governed`);
4. only then, through UOR's own chain, decide any Cron re-enable.

UCPE does none of these and authorizes none of them. It has not touched UOR and never re-enables UOR Cron.

## 14. A4 per-request ledger audit (`ucpe.a4_ledger_audit.v1`), read-only, for UOR qualification A10

UCPE authors and seals this artifact; UOR never authors UCPE SQL. UOR pins it read-only by the digests below.
It changes nothing in UOR's Card-5/A4 acceptance, and UCPE writes nothing to UOR.

```text
A4_ARTIFACT_STATUS=PREPARED_AND_VERIFIED_LOCALLY (not production-executed; its scratch-PostgreSQL rehearsal must be green on the pull request that merges it, and STATE records that run)
ARTIFACT_NAME=ucpe.a4_ledger_audit.v1
ARTIFACT_SHA256=2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577
UPSTREAM_RELEASE_IDENTITY=UCPE-PROD-E2-20261004-A (commit 1caa8b08ebfc45b79a9b14d8217dad3b112cda8d) serves radar_evidence.v1 through the route introduced by UCPE-PROD-F1-AUTOMATION-20261001-A (5a3ef022db10462675361e8d15aa8f4f572dc1aa), byte-identical since; each request's own release is the expected build_info.release_id taken from its response
INPUT_BINDING=(credential_id, client_request_id), the ledger's primary key, both from UOR's own request (client_request_id alone is not unique across credentials); cross-checked against the received 200 response: run_id, build_info.release_id, evidence_hash
OUTPUT_CONTRACT=one canonical JSON line (sorted keys): artifact, audit (the same artifact name, as the sealed SQL reports it), sql_sha256, verdict (PASS|FAIL), reason (OK, or the first of SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN (the row), NOT_COMPLETED, NOT_SUCCEEDED, WRONG_ORIGIN (the stored body of a completed success), BODY_IDENTITY_MISMATCH, RUN_MISMATCH, RELEASE_MISMATCH, EVIDENCE_MISMATCH, or a runner stop), bound_credential_id, bound_client_request_id, schema_ok, matched_rows, evidence_origin, origin_automated_radar, state, outcome_code, http_status, run_id, run_id_matches, release_id, release_id_matches, evidence_hash, evidence_hash_matches, body_identity_consistent, transaction_read_only; exit 0 only for PASS; never the stored response body, another row, a timestamp, a fingerprint or any secret
READ_ONLY_PROOF=one sealed WITH...SELECT (static guard: no write, lock, SET, DDL or side-effect function; adversarial mutants rejected), run only inside SET TRANSACTION READ ONLY with transaction_read_only=on proven first, a 5 s statement timeout and an unconditional rollback; the rehearsal proves INSERT, UPDATE, DELETE, TRUNCATE and CREATE refused under that preamble and the ledger digest unchanged across every audit
ISOLATION_PROOF=reads only public.automation_radar_ledger and four pg_catalog relations; the static guard denies every other table, view and function any migration creates (predictions, outcomes, analysis runs, snapshots, the credential registry, the section 5A seal); requires evidence_origin AUTOMATED_RADAR on the row and in its stored body; the rehearsal runs it as a role that can read only the ledger; no application code changes, so USER_REQUESTED, CONTROLLED_SMOKE and SCHEDULED_SHADOW_EVIDENCE are untouched
TESTS=tests/automation/test_a4_ledger_audit.py: 75 (structural guard with the decision order enforced; schema equal to migration 0013; 23 adversarial SQL mutants rejected; the runner offline; 14 runner mutants, each breaking a promised behaviour); tests/workflows/test_a4_ledger_audit_rehearsal_workflow.py: 4; the scratch-PostgreSQL rehearsal (23 audit cases, a ledger-only probe role, 6 refused writes) and the full suite must be green on the pull request that merges this package; STATE records those runs
INDEPENDENT_REVIEW=separate-context Claude review (a fresh context given only the commit and the requirements, no implementation transcript; the same model family, so not organizationally independent): first pass on dbc5c47 REVIEW_VERDICT=FINDINGS (1 blocker: in-progress and refused rows were reported WRONG_ORIGIN; 6 minor), all repaired in 491b460; delta review of 491b460 REVIEW_VERDICT=PASS with 3 minor findings, repaired in the next commit, dd39ef9 (a stricter comma-join guard, the OUTPUT_CONTRACT wording above, a dotfile-tolerant listing test); the final acceptance review of the merged bytes on main fc03be8e (a fresh context, the same model family) found no defect in the package (two non-blocking observations, recorded in STATE) and two in this section, the missing audit key and these review citations, both corrected on 2026-10-05 without changing a package byte
PRODUCTION_QUERY_EXECUTED=NO
PACKAGE_PATH=ops/a4_ledger_audit/
```

- **Corrected 2026-10-05**, documentation only: no package byte and no digest changed.
  - OUTPUT_CONTRACT now names `audit`, which every audited line carries. It is the sealed SQL's own
    name for the artifact, and `MANIFEST.json` already listed it.
  - INDEPENDENT_REVIEW cited `3ba2486` and `dd1093a`: local commits from before the branch was
    rebased and pushed, so not in this repository's history. Git proves their A4 files are
    byte-identical to `dbc5c47` and `491b460` on main: each pair differs only by the rebase base
    (`7a5ca4f` to `cd8b508`). The field now cites those.

| File | Role | sha256 |
|---|---|---|
| `ops/a4_ledger_audit/MANIFEST.json` | the package seal: ARTIFACT_SHA256 | `2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577` |
| `ops/a4_ledger_audit/a4_ledger_audit.sql` | the sealed SELECT | `c33aa3ad7bdbfcafe0d9f7e5bf3a16dafa3b885fac9f19d834d142d02f985eb1` |
| `ops/a4_ledger_audit/a4_ledger_audit.py` | the read-only runner | `9a8e32d2a2f1a1d09070f40e1699b426678a3600d86fdcd4704e063886bc57c2` |
| `ops/a4_ledger_audit/CARD.md` | the owner card for the episode | `29f45eccbd11e74c749f6499d13fa4a21e6814d32f1fb07c82f163c39829c4da` |
| `ops/a4_ledger_audit/build_manifest.py` | rebuilds the seal | `4af0b7d97fec68230a643fbdf0b991909713f544e4e50763f8fda053ebaabd8b` |

## 15. Card 04 companion (`ucpe.a4_card04_companion.v1`), read-only, beside the A4 audit

UCPE authors and seals this companion; UOR never authors UCPE SQL. UOR pins it read-only by the digests below.
- It proves only the five durable facts UOR Card 04 still needs for the request the A4 audit binds: the request's
  `deadline_ms`, the run's `analysis_hash`, the count of `public.predictions` rows carrying the run's `run_id`, the
  count of the credential's ledger rows since the qualification's activation, and the count of ledger rows carrying
  the request's `client_request_id` under any credential.
- It changes nothing in Card 04, and nothing in the accepted A4 component (`ucpe.a4_ledger_audit.v1`,
  ARTIFACT_SHA256 `2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577`, source `e468f1f1`), which still
  proves the row's origin, release and evidence identity. UCPE writes nothing to UOR.
- It reports the three counts as facts and never judges them: Card 04 adjudicates them.
- **The cross-credential count** (owner ruling A4-CRID-UNIQUENESS, 2026-10-05): Card 04 requires exactly one ledger
  row for the admitted `client_request_id`, while the ledger's key, and the A4 binding, is the pair. Its durable
  source is `public.automation_radar_ledger.client_request_id` (migration 0013: UUID NOT NULL, in the primary key).
  The route inserts a row only for a new `(credential_id, client_request_id)` key (a replay or a conflict writes
  nothing), never rewrites either key column, and deletes nothing; only an owner-run purge removes rows older than
  90 days, and the ledger holds at most 25,000 rows. So the count is the number of credentials that reserved that id.
  The companion reads only `client_request_id` for it, returns one number, and names no credential.
- **The two ledger counts are separate facts** (UOR's addendum, 2026-10-05): the credential count has the
  activation window and no request filter; the cross-credential count has no window and no credential
  filter; neither is derived from the other. The guard pins both counts token by token, and the rehearsal
  shows each move alone (a reused request id moves only the cross-credential count; a later activation
  moves only the credential count).
- **The card's command** (UOR's addendum, 2026-10-05): `python -I -B ops/a4_card04_companion/a4_card04_companion.py`
  with the six inputs. `-I` keeps the package folder, every `PYTHON*` variable and the user's own site
  packages off the import path, so no planted module can run; `-B` writes no bytecode, so the folder stays as
  sealed. The runner refuses any other start (`NOT_ISOLATED`, exit 2) and a folder holding anything but its
  five files (`SEAL_MISMATCH`, exit 3). The rehearsal runs this exact command against PostgreSQL 17.6.
- **What it prints:** only an answer it reproduces. Every printed value is an input, a boolean, a count, a
  reason, or a deadline or analysis hash in the ledger's own format; an answer it cannot reproduce is never
  printed (`RUNNER_DISAGREES` prints the stop line only).
- **The episode's database role** (the card's WHERE): the role that owns both tables, kept read-only by the run's
  READ ONLY transaction, or a BYPASSRLS role granted exactly the eleven columns. No migration creates such a reader;
  creating one would be a production change for the owner to authorize. A role that row-level policies apply to,
  such as `ucpe_space_db` (which the A4 audit accepts), is refused rather than counted through a policy.
- **The predictions count is a sequential scan:** no migration indexes `predictions.run_id`. On a very large
  table it can reach the 5 s statement timeout and stop with exit 4; it never returns a wrong count.

```text
COMPANION_STATUS=PREPARED_AND_VERIFIED (locally, on this branch: the offline tests, the scratch-PostgreSQL 17.6 rehearsal and the full suite; not production-executed; its pull-request rehearsal and the full suite must be green on the pull request that merges it, and STATE records those runs)
ARTIFACT_NAME=ucpe.a4_card04_companion.v1
ARTIFACT_SHA256=0b3cbb753210833d6776cab921fc6f2fa07ec89489ea150be28e2b77adddb646
SOURCE_COMMIT=d263c090a903d1de8fd9e1172340b5cad50b3d32: the commit on branch feat/a4-card04-companion that introduced these sealed bytes; it reaches main through a merge commit (never a rebase or a squash), and STATE records the merge
UPSTREAM_RELEASE_IDENTITY=UCPE-PROD-E2-20261004-A (commit 1caa8b08ebfc45b79a9b14d8217dad3b112cda8d) serves radar_evidence.v1 through the route introduced by UCPE-PROD-F1-AUTOMATION-20261001-A (5a3ef022db10462675361e8d15aa8f4f572dc1aa); src/crypto_probability_engine/automation/, src/crypto_probability_engine/api/automation_endpoint.py, migration 0013 and both radar schemas are byte-identical from 5a3ef022 to 1caa8b08 and to this branch's base, main fc03be8e; public.predictions.run_id is migration 0003's, unchanged since; each request's own release is the one the accepted A4 audit proves for the same row, so the companion takes no release input
INPUT_BINDING=(credential_id, client_request_id), the ledger's primary key, from UOR's own request (client_request_id alone is not unique across credentials), plus the received 200 response's run_id (RUN_MISMATCH otherwise; it also keys the predictions count); deadline_ms from UOR's own request and analysis_hash from the response, each compared with the row (DEADLINE_MISMATCH, ANALYSIS_HASH_MISMATCH), never trusted; qualification_activation_utc, a canonical UTC instant YYYY-MM-DDTHH:MM:SS[.ffffff]Z that opens the credential count's window and must not follow the bound request's receipt (ACTIVATION_AFTER_REQUEST); the bound client_request_id alone also keys the cross-credential count; release_id and evidence_hash are not taken, because the accepted A4 audit proves them for the same row; every input is non-secret and format-checked against migration 0013's CHECKs and the route's request contract before any contact
OUTPUT_CONTRACT=one canonical JSON line (sorted keys), exactly these 19 keys: analysis_hash, analysis_hash_matches, artifact, artifact_sha256, bound_client_request_id, bound_credential_id, bound_qualification_activation_utc, bound_run_id, credential_ledger_rows_since_activation, deadline_ms, deadline_ms_matches, ledger_rows_for_client_request_id_across_all_credentials, predictions_rows_for_run_id, reason, row_security_off, schema_ok, sql_sha256, transaction_read_only, verdict; verdict PASS only with reason OK, else FAIL with the first failing check of SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN, NOT_COMPLETED, NOT_SUCCEEDED, RUN_MISMATCH, DEADLINE_MISMATCH, ANALYSIS_HASH_MISMATCH, ACTIVATION_AFTER_REQUEST, or RUNNER_DISAGREES; artifact_sha256 is the sha256 of the MANIFEST.json the run verified; bound_qualification_activation_utc echoes the validated activation input, so the credential count names its own window; ledger_rows_for_client_request_id_across_all_credentials counts the ledger rows carrying the bound client_request_id under any credential and in any state (owner ruling A4-CRID-UNIQUENESS; Card 04 accepts exactly 1): it is at least 1 whenever the row is bound, it is reported and never judged, and it names no credential; schema_ok is the SQL's schema proof (both tables ordinary tables in public with no inheritance child, every column read with its migration's type and nullability, the ledger's primary key the pair), and transaction_read_only and row_security_off are the session proofs the runner establishes before the SELECT; exit 0 only for PASS, and the five facts are evidence only on a PASS; every value printed is an input, a boolean, a count, a reason, or a deadline or analysis hash in the ledger's own format; a runner stop prints artifact, verdict FAIL and its reason, plus sql_sha256 and the four bound identities (bound_credential_id, bound_client_request_id, bound_run_id, bound_qualification_activation_utc) once the inputs are accepted, and error_class for a database or internal error, and nothing else: RUNNER_DISAGREES (exit 1, an answer the runner cannot reproduce, none of which is printed), NOT_ISOLATED (exit 2, not started as python -I -B; refused before any input is read), INPUT_REFUSED:<input> (exit 2), SEAL_MISMATCH (exit 3: a package file, the SQL, or a folder holding anything but its five files), DATABASE_URL_MISSING, NOT_READ_ONLY, ROW_SECURITY_NOT_OFF, DATABASE_ERROR, UNEXPECTED_RESULT_SHAPE or INTERNAL_ERROR (exit 4); never the stored response body, another row, a stored timestamp, a fingerprint or a secret
DEADLINE_MS_PROOF=the bound row's public.automation_radar_ledger.deadline_ms (migration 0013: INTEGER NOT NULL, CHECK 5000 to 60000); the route writes it once, when it reserves the row, from the validated request (automation/service.py: reserve(deadline_ms=request.deadline_ms)), and never updates it (automation/ledger.py: the completion UPDATE does not set it); it is part of the request fingerprint, so a repeat under the same key with another deadline is a 409 IDEMPOTENCY_CONFLICT, never a replay; no response body carries it, so the ledger is its only durable source; reported as deadline_ms and compared NULL-safely with UOR's own value (deadline_ms_matches, DEADLINE_MISMATCH)
ANALYSIS_HASH_PROOF=the bound row's analysis_hash (migration 0013: TEXT; for a SUCCEEDED row its CHECKs require sha256:<64 hex> and equality with the stored 200 body's analysis_hash); the route writes it when it records the success, from the same evidence object it returns (automation/service.py: complete_success(analysis_hash=evidence["analysis_hash"]), then AutomationResult(200, evidence)), and a replay returns that stored body byte for byte; judged only after the row is bound as a completed 200 success of the bound run; reported as analysis_hash and compared with the response's (analysis_hash_matches, ANALYSIS_HASH_MISMATCH)
PREDICTIONS_RUN_ID_COUNT_PROOF=count(*) of public.predictions rows whose run_id (migration 0003: TEXT NOT NULL, unchanged by every later migration) equals the bound run_id; the human route and the isolated automation route draw run ids from one generator (run_<uuid4 hex>, api/analysis_service.py), and the isolated route never writes a prediction (analyze_request_isolated: record_prediction=False, prediction_origin=None), so a nonzero count would mean an automated run reached the shared cohort; it reads predictions.run_id and nothing else, so no probability, label, outcome, snapshot or section 5A data (isolation evidence only, never model or directional evidence, by the owner's ruling of 2026-10-05); with row security off the count cannot be silently filtered; reported as predictions_rows_for_run_id, never judged
CREDENTIAL_ROWS_SINCE_ACTIVATION_PROOF=count(*) of public.automation_radar_ledger rows with the bound credential_id and received_at_utc at or after qualification_activation_utc (inclusive), whatever their state, outcome or client_request_id, the bound request's own row included; a fact separate from the cross-credential count, which has no window and no credential filter; received_at_utc is TIMESTAMPTZ NOT NULL, the server's clock at admission, written once at reservation (index arl_credential_received); ledger rows are kept at least 90 days and never purged automatically; with row security off the count cannot be silently filtered; reported as credential_ledger_rows_since_activation, never judged
READ_ONLY_PROOF=one sealed WITH...SELECT (the static structural guard in tests/automation/test_a4_card04_companion.py has two layers: the first checks every property on one token stream in which a literal is a value, never SQL: printable ASCII and standard literals only, no backslash, prefixed literal, dollar quote, quoted identifier, block comment or two adjacent literals, only the modelled operators, keywords, types and functions, every other identifier a declared name, none of them a name PostgreSQL evaluates as a value; no write, lock, SET, TABLE, comma-join, derived table, DDL or side-effect function; exactly the declared reads, literals, function calls and names; the binding, the bound row and its facts, the three counts, the checks and the final SELECT pinned token by token; the second layer admits only the sealed SQL's own token stream; 100 adversarial SQL mutants, each rejected by the first layer alone; the runner executes only those guarded bytes, pinned by sha256), run only inside SET TRANSACTION READ ONLY with statement and lock timeouts (5 s, 1 s) and row_security off, with transaction_read_only=on and row_security=off both proven before it runs, and an unconditional rollback; the runner starts only as the card runs it, python -I -B ops/a4_card04_companion/a4_card04_companion.py (NOT_ISOLATED otherwise), and before any contact checks that its folder holds exactly its five files, each a regular file, all four sealed files against MANIFEST.json and the SQL against its pinned sha256; the rehearsal runs that exact command against PostgreSQL 17.6: it PASSES with the in-process line, the folder is unchanged, every other start is refused, and a folder with one more module is refused without running it (without -I that module runs: shown); on PostgreSQL 17.6 the rehearsal refuses all 10 writes it tries under that preamble (INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, TRUNCATE), and the database, rows and catalog, is unchanged across every audit
ISOLATION_PROOF=reads ten ledger columns (credential_id, client_request_id, evidence_origin, state, outcome_code, http_status, run_id, analysis_hash, deadline_ms, received_at_utc), predictions.run_id and five pg_catalog relations, and nothing else; the static guard allows exactly those reads (each relation's uses, every data column reference: the ledger three times, the third reading only client_request_id for one count) and pins every count token by token, so no credential_id is projected, grouped or aggregated and the two ledger counts stay separate; every value the runner prints is an input, a boolean, a count, a reason, or a deadline or analysis hash in the ledger's own format, and an answer it cannot reproduce is never printed; the guard denies every other column of both tables, any star but count(*) and the decision's k.*, any derived table, any whole-row use of a table, alias or CTE, and every other table, view and function any migration creates; it requires evidence_origin AUTOMATED_RADAR on the bound row; with row security off, a reader that a row-level policy applies to is refused rather than counted through the policy (without it, a hidden reader would count zero: rehearsed); on PostgreSQL 17.6 it PASSES as a BYPASSRLS role granted exactly those eleven columns, which is refused every other column and table; no application code changed, so USER_REQUESTED, CONTROLLED_SMOKE and SCHEDULED_SHADOW_EVIDENCE are untouched; it never names the section 5A seal or reads a holdout probability
TESTS=tests/automation/test_a4_card04_companion.py: 231 (the structural guard's two layers: one token stream, the exact declared reads, literals, calls and names, the pinned binding, counts, checks and output, no star, derived table or whole-row use, the decision order, and the exact token stream; the schema equal to migrations 0013 and 0003, with the route's writers pinned; 100 adversarial SQL mutants; the runner offline, 87; 33 runner mutants, each breaking a promised behaviour (among them the exact folder, the python -I -B start, the ledger's formats and a disagreement printing nothing); the seal, the accepted A4 seal unchanged, this section and section 14's corrected contract); tests/workflows/test_a4_card04_companion_rehearsal_workflow.py: 7; the scratch-PostgreSQL 17.6 rehearsal (39 audit cases, among them the cross-credential count at 0, 1 and 2, a reused request id that moves only that count and an activation that moves only the credential count; the card's exact command, python -I -B, with every other start refused and a planted module refused; the eleven-column probe, two row-security readers refused, 10 refused writes): A4C_REHEARSAL=PASS locally, with the same scripts as the pull-request workflow; the full suite: VERIFY=PASS locally (6376 passed); both must be green on the pull request that merges this package, and STATE records those runs
INDEPENDENT_REVIEW=REQUIRED_BEFORE_PUBLICATION: a fresh separate-context read-only Claude review of this branch's exact head, given only the requirements, the source paths and the commit, with no implementation transcript and no implementer summary (the same model family, so not organizationally independent). Rounds so far: review 1 of db176ec1, FINDINGS (MAJOR: the guard passed a star, a derived table or a whole-row read through a CTE; one MINOR, four NITs), repaired in 116b68cf; review 2 of 4edd6e4b, FINDINGS (MAJOR, the same class: an escape string or a non-ASCII name hid SQL from the guard; two NITs, one observation), repaired in 4f3f00cd by making the guard's model of SQL closed; review 3 of 4f3f00cd, PASS for the requirements of that time. The owner's ruling A4-CRID-UNIQUENESS (2026-10-05) then added the cross-credential count; review 4 of 0652c431, given the original requirements and that addendum, FINDINGS (MAJOR, the same class a third time: a literal could stand in for a pinned fragment; two NITs), and the session's sibling scan found a declared name PostgreSQL evaluates (current_user); escalated under the bounded-repair rule, the owner authorized one consolidated repair with runner hardening and a reseal, together with UOR's addendum (separate counts, the exact file set, python -I -B), made in SOURCE_COMMIT: the guard reads one token stream and has a second, exact layer, and the runner prints only values in the ledger's formats, nothing of an answer it cannot reproduce, starts only as python -I -B, and refuses a folder holding anything but its five files. A new fresh review of this exact head, given the original requirements, the addendum and the owner's authorization, is required; a material finding is repaired and re-reviewed. The sealed SQL never had any construct the guard findings named. The passing review's head commit and verdict are recorded in STATE.md, and nothing on this branch changes after it
PRODUCTION_QUERY_EXECUTED=NO
PRODUCTION_MUTATED=NO
PROTECTED_5A_ACCESSED=NO
PACKAGE_PATH=ops/a4_card04_companion/
```

| File | Role | sha256 |
|---|---|---|
| `ops/a4_card04_companion/MANIFEST.json` | the package seal: ARTIFACT_SHA256 | `0b3cbb753210833d6776cab921fc6f2fa07ec89489ea150be28e2b77adddb646` |
| `ops/a4_card04_companion/a4_card04_companion.sql` | the sealed SELECT | `e507caaf313a82d870f753bd502c8e915be2a3af13c1f55cdeda53ee50de9e49` |
| `ops/a4_card04_companion/a4_card04_companion.py` | the read-only runner | `dc35553c8780b084763edf4ea432890c6c48cf17be526b1fff8ecc8912d8cec5` |
| `ops/a4_card04_companion/CARD.md` | the owner card for the episode | `582be23e6db14da6bebbd8bd32ecaf0fbdd3adef5f269e2727156c0b48d092a2` |
| `ops/a4_card04_companion/build_manifest.py` | rebuilds the seal | `36be3f62ac90a93a2e95be7fba80512f96fec59eb483b5c79fa1c7973ffc7bbf` |
