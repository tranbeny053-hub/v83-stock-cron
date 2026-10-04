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
| `docs/automation/examples/MANIFEST.json` | synthetic example provenance and digests | `484c03ec6252277a7b3acba5015778f725c5977e724ba1164c8c1fcad5d0b466` |
| `docs/automation/examples/radar_evidence.v1.synthetic-btc-4h-gate-blocked.json` | synthetic example: gate blocked | `c47e0e5ef6f30725d488c56e6b3b73849b445ef19f7079aac1bc98cbd872620f` |
| `docs/automation/examples/radar_evidence.v1.synthetic-eth-1h-h2-hold.json` | synthetic example: H2 hold | `2c33037891d5d44f9f625f47681bba1f281e0de7c37bb025aea11f84048b5c65` |
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
- **Release rollback:** a separate owner T4 to `2096af6d` (`UCPE-PROD-TC-V1-STAMP-20260930-A`), which removes the
  route. The ledger stays inert.
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
A4_ARTIFACT_STATUS=PREPARED_AND_VERIFIED_LOCALLY (not production-executed; the scratch-PostgreSQL rehearsal is a required check of the pull request that merges it)
ARTIFACT_NAME=ucpe.a4_ledger_audit.v1
ARTIFACT_SHA256=ad699bb0a541de7c81b7b8ef6cf59ca00b9d4e5c91f884ebb054fca3a0f6050e
UPSTREAM_RELEASE_IDENTITY=UCPE-PROD-E2-20261004-A (commit 1caa8b08ebfc45b79a9b14d8217dad3b112cda8d) serves radar_evidence.v1 through the route introduced by UCPE-PROD-F1-AUTOMATION-20261001-A (5a3ef022db10462675361e8d15aa8f4f572dc1aa), byte-identical since; each request's own release is the expected build_info.release_id taken from its response
INPUT_BINDING=(credential_id, client_request_id), the ledger's primary key, both from UOR's own request (client_request_id alone is not unique across credentials); cross-checked against the received 200 response: run_id, build_info.release_id, evidence_hash
OUTPUT_CONTRACT=one canonical JSON line (sorted keys): artifact, sql_sha256, verdict (PASS|FAIL), reason (OK, or the first of SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN, NOT_COMPLETED, NOT_SUCCEEDED, BODY_IDENTITY_MISMATCH, RUN_MISMATCH, RELEASE_MISMATCH, EVIDENCE_MISMATCH, or a runner stop), bound_credential_id, bound_client_request_id, schema_ok, matched_rows, evidence_origin, origin_automated_radar, state, outcome_code, http_status, run_id, run_id_matches, release_id, release_id_matches, evidence_hash, evidence_hash_matches, body_identity_consistent, transaction_read_only; exit 0 only for PASS; never the stored response body, another row, a timestamp, a fingerprint or any secret
READ_ONLY_PROOF=one sealed WITH...SELECT (static guard: no write, lock, SET, DDL or side-effect function; adversarial mutants rejected), run only inside SET TRANSACTION READ ONLY with transaction_read_only=on proven first, a 5 s statement timeout and an unconditional rollback; the rehearsal proves INSERT, UPDATE, DELETE, TRUNCATE and CREATE refused under that preamble and the ledger digest unchanged across every audit
ISOLATION_PROOF=reads only public.automation_radar_ledger and four pg_catalog relations; the static guard denies every other table, view and function any migration creates (predictions, outcomes, analysis runs, snapshots, the credential registry, the section 5A seal); requires evidence_origin AUTOMATED_RADAR on the row and in its stored body; the rehearsal runs it as a role that can read only the ledger; no application code changes, so USER_REQUESTED, CONTROLLED_SMOKE and SCHEDULED_SHADOW_EVIDENCE are untouched
TESTS=tests/automation/test_a4_ledger_audit.py: 52 (structural guard; schema equal to migration 0013; 18 adversarial SQL mutants rejected; runner offline: read-only session, unconditional rollback, refusals before contact, no URL, credential or exception message echoed, independent cross-check); tests/workflows/test_a4_ledger_audit_rehearsal_workflow.py: 3; runner mutants: 12/12 killed; full ./verify.sh: PASS; scratch-PostgreSQL rehearsal (23 audit cases, a ledger-only probe role, 6 refused writes): a required check of the pull request that merges this package
INDEPENDENT_REVIEW=PENDING_REVIEW
PRODUCTION_QUERY_EXECUTED=NO
PACKAGE_PATH=ops/a4_ledger_audit/
```

| File | Role | sha256 |
|---|---|---|
| `ops/a4_ledger_audit/MANIFEST.json` | the package seal: ARTIFACT_SHA256 | `ad699bb0a541de7c81b7b8ef6cf59ca00b9d4e5c91f884ebb054fca3a0f6050e` |
| `ops/a4_ledger_audit/a4_ledger_audit.sql` | the sealed SELECT | `115fde82e6f2452d349cb8202fcea594374e2229a7019e02d21734d9365a5f8a` |
| `ops/a4_ledger_audit/a4_ledger_audit.py` | the read-only runner | `b33d9ba3e6bb6ac7f3e23198e6959dcb26a883e883861377d51ed5e8f252c536` |
| `ops/a4_ledger_audit/CARD.md` | the owner card for the episode | `c9d9183abf9920adf21ab43ca6a05a5eb3ffc3a03e75447a9bc1fec9012cb473` |
