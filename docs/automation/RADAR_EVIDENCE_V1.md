# Governed automation interface — `POST /v1/automation/radar-evidence` (`radar_evidence.v1`)

**Status (2026-10-01).** This is UCPE canon, LIVE in release `UCPE-PROD-F1-AUTOMATION-20261001-A`.
- The owner enabled the route and issued one credential (`uor-radar-2026-10`); the canary passed.
- Its ledger (migration 0013) is applied in production.
- The exact states are in `UOR_HANDOFF.md` section 1. The route still fails closed at every layer:
  a cleared kill switch answers 503 `AUTOMATION_DISABLED`, an unreachable ledger 503
  `LEDGER_UNAVAILABLE`.

This document is UCPE's answer to UOR's proposal (UOR handoff file 05). UCPE canon wins wherever the
two differ, and the differences are listed in `F1_NODE_CLASSIFICATION.md`.

## 1. The route

- **Shape.** `POST /v1/automation/radar-evidence`, JSON in and out, one symbol per call. There is no
  batch endpoint.
- **Separation from the human routes.** It is separate from `/v1/analyze*` and omitted from the
  OpenAPI schema.
  - It shares no session, run store, persistence repository or skill-evidence refresh with them.
  - It does share the analysis computation, the runtime settings and the read-only published
    skill-gate cache.
- **Layout.** `api/automation_endpoint.py` is a thin adapter. All policy lives in
  `crypto_probability_engine.automation`, one module per contract:
  - `origin`: the automation origin;
  - `config`: configuration and the kill switch;
  - `credentials`: machine authentication;
  - `contract`: request, response, errors and hashes;
  - `canonical`: RFC 8785 canonical JSON;
  - `ledger`: idempotency and audit;
  - `quota`: rate bounds;
  - `service`: orchestration.

## 2. Authentication (route-only machine credential)

- **Header.** `X-UCPE-Automation-Credential: ucpea.<credential_id>.<value>`.
  - `credential_id` matches `^[a-z0-9][a-z0-9-]{2,31}$`.
  - The value is exactly 43 URL-safe base64 characters (256 bits).
  - The credential is never accepted in a URL, a query string or a body.
- **Server side.**
  - UCPE never issues or stores a credential value. It hashes the presented value in memory and
    compares `sha256(value)` with the stored digest using `hmac.compare_digest`.
  - The comparison runs for every well-formed token, including unknown ids.
  - A missing header gets 401 `CREDENTIAL_REQUIRED`. Every other refusal (malformed, unknown,
    mismatched, revoked, expired) gets the same 401 `CREDENTIAL_INVALID`.
  - A malformed token is rejected on its format alone, before any digest work. Nothing secret
    depends on that path.
- **Scope.**
  - The credential authenticates this route only. The human routes read only their session
    cookies, so a machine-only request gets 401 on every one of them (tested for all 14 human
    method-path pairs).
  - A request that carries a human session cookie (`ucpe_session` or `ucpe_dev_session`) is refused
    here with 403 `HUMAN_SESSION_REFUSED`, even alongside a valid machine credential.
  - **CORS is not a control here.** UCPE's own CORS policy does not grant the credential header
    (tested in process). In production, though, the Hugging Face edge answers CORS preflights
    itself and reflects any origin, so a page on another site can send the header and read the
    answer (observed on 2026-10-01). The route's security never relies on CORS:
    - the credential is a bearer token in a custom header, never a cookie. A browser never holds it
      unless a person puts it into a page, and anyone who holds it can call the route from anywhere;
    - a human session cookie is refused here (above). Those cookies are `SameSite=Lax`, and
      `hf.space` is a public suffix, so no other site's request carries them.
  - **Consumer rule:** the token is used only by a server-side caller, never from a browser or a web
    page.
- **Registry.** The database table `public.automation_credential` (migration 0013) holds one row per
  credential:
  - `credential_id`, `secret_sha256`, `status` (`ACTIVE` or `REVOKED`), and the optional
    `not_after_utc`, `created_at_utc` and `revoked_at_utc`;
  - digests only, never a value.
  The environment holds no credential and no digest.
- **Read on every request, with no cache.** A registry change applies to the next request, with no
  restart:
  - a rotation overlaps: the new row works at once and the old one until it is revoked;
  - a revocation refuses the next request presenting that credential, including a replay.
  Each read is bounded (2 s), and at most two are in flight at once.
  - A well-formed token reaches the database before it is authenticated. A flood of such tokens can
    make legitimate calls fail closed (503), but it can never take more than two database
    connections from the rest of the product.
  - A registry that cannot be read, or holds a malformed row, authenticates nothing: 503
    `LEDGER_UNAVAILABLE`, with no row written.
- **Issuance, rotation and revocation** are owner-performed T4 actions on the production database,
  following `CREDENTIAL_ROTATION.md`. UCPE never issues a credential, never sees a value outside a
  request, and never writes to the registry. UOR keeps the full `ucpea.<id>.<value>` token in its
  governed secret store, referred to by NAME only.

## 3. Provenance and cohort isolation (non-negotiable)

- **The origin.** `evidence_origin` is always `AUTOMATED_RADAR`, stamped by the server from the
  credential. The client cannot assert it.
- **Not a prediction origin.** `AUTOMATED_RADAR` is not, and cannot be validated as, a
  `PredictionOrigin`. The cohorts (`USER_REQUESTED`, `CONTROLLED_SMOKE`,
  `SCHEDULED_SHADOW_EVIDENCE`) are untouched and never relabelled.
- **The isolated analysis.** The route runs `analysis_service.analyze_request_isolated`. It takes no
  origin by construction, builds no prediction row, parks nothing for persistence and writes no
  run-store entry.
- **What an automated run never touches.**
  - The cohort tables: `predictions`, `prediction_outcomes`, `analysis_runs` and the snapshots.
  - Calibration, the skill gate's evidence and control statistics.
  - `/v1/runs`, run detail and the resolver.
- **Where it lives instead.** Automated runs live only in the isolated
  `public.automation_radar_ledger`, which no cohort reader reads.
- **Why isolation, not a shared origin.** `COHORT_READER_AUDIT.md` shows that several generic
  readers include an unknown origin by default: lower-level due readers, the in-memory run store and
  debug runs, and the target contract, which rejects only `SCHEDULED_SHADOW_EVIDENCE`. Adding
  `AUTOMATED_RADAR` to the shared origin set would therefore leak.
- **Live data only.** The route reads live market data and the published skill gate only. Protected
  section 5A evidence is never used, returned or inferable here. An analysis that did not use live
  data yields no evidence at all: 503 `UPSTREAM_UNAVAILABLE`, enforced before the body is built.
- **Proof.**
  - `tests/automation/test_cohort_isolation.py` covers byte-identity with the recorded analysis, no
    pending rows, no persistence call, no run-store write, no cohort field and no cohort writer
    imported.
  - After enablement, an owner-authorized read-only audit query must return 0:
    `SELECT count(*) FROM public.predictions p JOIN public.automation_radar_ledger l ON
    p.prediction_id LIKE l.run_id || ':%';`

## 4. Request (strict; unknown, missing or duplicate fields are refused)

```json
{"symbol": "BTC", "primary_timeframe": "4H", "client_request_id": "<canonical lowercase UUID>", "deadline_ms": 30000}
```

- **The body.** At most 1024 bytes of UTF-8 JSON. NaN and Infinity are refused.
- **`symbol`** must match `^[A-Za-z0-9/_:.-]{1,32}$`, otherwise 400. It must also normalize as a UCPE
  spot symbol, otherwise 422 `UNSUPPORTED_SYMBOL`. The symbol and `client_request_id` are the only
  caller-supplied values echoed back.
- **`primary_timeframe`** is one of `15m`, `1H`, `4H`, `1D`, otherwise 422 `UNSUPPORTED_TIMEFRAME`.
- **`deadline_ms`** is an integer from 5000 to 60000.
- **Mode.** Every call is `METRICS_ONLY` spot: no news add-on and no paid API.

## 5. Response `radar_evidence.v1` (`schemas/radar_evidence.schema.json`, draft 2020-12)

- **Strictness.** `additionalProperties: false` at every level. Every success body is validated
  against the pinned schema before it is recorded or sent; a failing body is withheld as 503
  `CONTRACT_VIOLATION`. Every error body, and every replayed body, is validated too.
- **What it carries.** Codes, numbers, identities and release metadata, each read from UCPE's
  governed analysis. There is no free prose: every code-like field matches `^[A-Z0-9_]{1,64}$`.
- **Identity:** `schema_version`, `evidence_origin`, `client_request_id`, `run_id`, `analysis_hash`,
  and `analysis_schema_version` (the `response.v1` schema_version it was read from).
- **Time:** `as_of_utc` (the market-data instant) and `issued_at_utc` (server time when built).
- **Market:** `symbol`, `normalized_symbol`, `primary_timeframe`, `horizon.bars`.
- **Release:** `build_info`, exactly the serving release's `GET /v1/build-info` payload
  (`schema_version`, `release_id`, `release_label`, `environment`, `source_milestone`,
  `fingerprint`).
- **`probability_state`:** `probability_type`, `calibration_status`, and per horizon (`H_primary`,
  `H_extended`) `status`, `p_up_frac`, `p_down_frac`, `p_timeout_frac`, `confidence_frac`,
  `sample_count: null`, `sample_count_basis: "NONE_UNCALIBRATED_HEURISTIC"`.
  - When `status` is `OK`, the three fractions sum to 1 within 1e-9, checked before sending.
  - When `status` is not `OK`, all four numbers are `null`. UCPE computes placeholders on that path,
    and they are never evidence.
  - UCPE's probabilities are uncalibrated heuristics (`reliability_status` `INSUFFICIENT_SAMPLE`),
    so no sample count stands behind them and none is reported. Fabricating one is forbidden, and a
    calibrated future means a new version.
- **Governance context:**
  - `calibration_state.{calibration_status,reliability_status,profitability_claim}`;
  - `gate_result.{hard_gate_passed,hard_blocks,directional_evidence_hold}`;
  - `decision_brief.{action,hard_blockers,model_readiness,reliability_status,profitability_claim}`;
  - `frontend_display.{is_live_data,disposition}`;
  - `data_quality.{status,is_live_data,data_source,cross_provider_state}`.
  - Both `is_live_data` flags and both `profitability_claim` flags are constants (`true` and `false`
    respectively).
- **Withheld:**
  - the shadow blocks (`quant_v2`, `derivatives_intelligence`), which have 0.0 decision influence;
  - `skill_evidence`, including `observed_directional_rate`;
  - all free-text reasons and labels;
  - the H2 hold's `legacy_verdict`. The hold is carried as `{active, hold_reason}`. Its presence
    does imply a legacy verdict under correction; it grants nothing, and `hard_gate_passed: false`
    remains binding.
- **Hard gates outrank everything.**

## 6. Evidence identity and hashes (RFC 8785)

- **The wire.** Every response body, whether success, refusal or replay, is sent as its **RFC 8785
  JSON Canonicalization Scheme (JCS)** bytes:
  - members are sorted by the UTF-16 code units of their keys;
  - there is no whitespace;
  - strings are escaped as ECMAScript `JSON.stringify` does;
  - numbers are ECMAScript shortest round-trip: `1` not `1.0`, `1e-7`, `1e+21`, and `-0` as `0`.
- **`evidence_hash`** is `"sha256:" + hex(sha256(JCS(body without "evidence_hash")))`. Any language
  with a JCS implementation re-verifies it offline, from the parsed body alone.
- **`run_id`** matches `run_<32 hex>` and is unique per run.
- **`analysis_hash`** is UCPE's own analysis identity: its `stable_hash` over the analysis before the
  shadow blocks. It is carried as read. It is proven NOT recomputable from the validated `response.v1`
  (serialization changes the bytes), and the full analysis is not carried here, so consumers must not
  try to recompute it.

## 7. Determinism

- **What is deterministic.** Analysis content is a function of these canonical inputs:
  - the market snapshot as captured at `as_of_utc`;
  - the published skill-gate state at analysis time. It changes as that cache refreshes or expires,
    which changes gate and hold fields;
  - the release (`build_info.release_id` plus `fingerprint`) with its runtime settings.
- **What is per call.** `run_id` (also inside `analysis_hash`), `issued_at_utc`,
  `client_request_id` and `evidence_hash` are per-call identity and time. They are not "content".
- **The proof.** `tests/automation/test_cohort_isolation.py` proves the isolated analysis equals the
  recorded one byte for byte, on fixed inputs with a fixed run id.
- **What is not.** A repeated live call is **not** reproducible: it fetches new market data, and the
  skill-gate state may have moved. `determinism.live_repeat_reproducible` is the constant `false`.

## 8. Deadline, errors and replay

- **The deadline contract.** `deadline_ms` is a monotonic budget that starts when the request
  arrives at the route, before its credential is checked and its body is read.
  - The analysis may use the budget up to 1 s before its end.
  - A success is recorded only if the recording statement runs at least 0.25 s before the deadline
    by the database clock; the 0.25 s is the commit's margin. The deadline is compared across the
    app's and the database's clocks, so it is only as exact as the gap between them.
  - Otherwise the result is recorded and answered as 503 `DEADLINE_EXCEEDED`, so the ledger always
    says what the caller was told. Evidence is returned only after its record commits.
  - NOT bounded by the deadline:
    - the commit's own completion: it follows the check and is bounded by the recording timeouts; a
      check after the commit could not undo the record;
    - the response's network transit;
    - an analysis that outlives its deadline: it is not cancelled, and its result is never recorded
      or returned.
- **The body.** The route reads a body only after admitting the request (kill switch, human session,
  credential):
  - never more than 1,024 bytes; a larger declared Content-Length is refused unread;
  - never for longer than 2 s.
  A body refused for size or time is 400 `MALFORMED_REQUEST`.
- **Overruns.** An analysis that overruns keeps its concurrency slot until its thread ends, so
  overruns never pile up.
- **Error bodies.** `{"schema_version": "radar_evidence_error.v1", "error": {"code", "message",
  "retry_after_seconds"}}`. The code is from a fixed catalogue, and the message is that code's fixed
  text (a schema enum). No body carries a credential, a request field, user data or partial evidence.
  Every response has `Cache-Control: no-store`.

| Status | Codes |
|---|---|
| 400 | `MALFORMED_REQUEST` |
| 401 | `CREDENTIAL_REQUIRED`, `CREDENTIAL_INVALID` |
| 403 | `HUMAN_SESSION_REFUSED` |
| 409 | `IDEMPOTENCY_CONFLICT`, `REQUEST_IN_PROGRESS` |
| 422 | `UNSUPPORTED_SYMBOL`, `UNSUPPORTED_TIMEFRAME` |
| 429 (+ `Retry-After`) | `QUOTA_EXCEEDED`, `CONCURRENCY_LIMIT` |
| 503 | `AUTOMATION_DISABLED`, `NOT_CONFIGURED`, `LEDGER_UNAVAILABLE`, `DEADLINE_EXCEEDED`, `UPSTREAM_UNAVAILABLE`, `ANALYSIS_FAILED`, `CONTRACT_VIOLATION` |

**Consumer rule:** any non-200 or timeout means no evidence for that symbol this cycle, never a
degraded guess.

## 9. Idempotency

- **The key.** `client_request_id` is scoped per credential. Its ledger row is reserved before any
  analysis starts.
- **Repeats while the key is retained.** Retention is 90 days in the production ledger, until an
  owner-authorized purge; the in-memory test ledger keeps a key about 26 hours. "The same request"
  means the same `symbol`, `primary_timeframe` and `deadline_ms`.
  - A completed request is answered with the recorded outcome, byte for byte: a 200 body or a
    refusal, re-rendered as JCS, with `Idempotent-Replay: true`.
  - A replay returns the recorded evidence whenever it is asked for. Consumers judge freshness from
    `as_of_utc` and `issued_at_utc`.
  - A replayed refusal keeps its original `Retry-After`.
  - While the first call is running: 409 `REQUEST_IN_PROGRESS`.
  - Past the deadline plus 60 s, the key is closed and answered 503 `DEADLINE_EXCEEDED`, never re-run.
- **A different request under the same key:** 409 `IDEMPOTENCY_CONFLICT`.
- **Refusals that write no row, so the key stays usable.** They come before the reservation, or are
  refused by it:
  - 400, 401 and 403;
  - the 422s of the request's own form (an unsupported timeframe or symbol syntax);
  - a 503 answered before the reservation (disabled, misconfigured, or the registry or the ledger
    unreachable);
  - the capacity refusals of section 12: a full ledger (503 `LEDGER_UNAVAILABLE`) and a credential
    past its rolling-day row ceiling (429 `QUOTA_EXCEEDED`).
- **Refusals recorded against the key.** Once the reservation succeeds, the outcome is recorded and
  replayed, refusals included:
  - an `UNSUPPORTED_SYMBOL` that only the analysis discovers;
  - the rate quota (429 `QUOTA_EXCEEDED`) and `CONCURRENCY_LIMIT`;
  - the 503s of the deadline and the analysis: `DEADLINE_EXCEEDED`, `UPSTREAM_UNAVAILABLE`,
    `ANALYSIS_FAILED` and `CONTRACT_VIOLATION`.
- **Scope and lifetime.** Idempotency is per credential and lasts as long as the row: at least the
  90-day retention (`RETENTION_AND_IDEMPOTENCY.md`). After a rotation, a retry uses the credential it
  began under.
- **An unknown outcome.** A 503 `LEDGER_UNAVAILABLE` answer after an analysis means the outcome is
  unknown: the record's commit may or may not have landed. Only a replay of that key can reveal it.
  UOR, which never retries inside a cycle, simply treats the symbol as having no evidence.

## 10. Quota, concurrency and cost

- **Per credential, counted from the ledger.** A restart never resets it.
  - `UCPE_AUTOMATION_QUOTA_PER_5MIN`: default 6, allowed 1–60.
  - `UCPE_AUTOMATION_QUOTA_PER_DAY`: default 120, allowed 1–120. The capacity contract (section 12)
    bounds it; raising it needs measured production resource evidence and a reviewed change.
  - `Retry-After` covers every exhausted window.
  - Refusals made before an analysis (`QUOTA_EXCEEDED`, `CONCURRENCY_LIMIT`) do not count against
    the quota. They do count against the credential's row ceiling: at most 2 x the daily quota rows
    in any rolling day. Beyond the ceiling, a new request gets 429 `QUOTA_EXCEEDED` and is recorded
    nowhere.
- **Concurrency.** One automated analysis runs at a time per service instance, which is one per app
  process; a busy slot gets 429 at once and never queues.
- **Cost.** Each counted call is one METRICS_ONLY analysis: public exchange market-data requests
  (free) plus a few seconds of Space CPU. There is no paid API. The owner sets the level (G6).

## 11. Kill switch, rollback and deprecation

- **The switch.** `UCPE_AUTOMATION_ENABLED` is on only for `1` or `true` (case-insensitive,
  surrounding spaces ignored). It defaults to off. Clearing it (a T3 Space configuration change)
  returns every call to 503 `AUTOMATION_DISABLED`. A Space configuration change restarts the Space.
- **The faster stop.** Revoking the credential stops a consumer at its next request, with no restart
  (`CREDENTIAL_ROTATION.md`).
- **The consumer** falls back to no evidence on any error.
- **Versioning.** Any breaking or semantic change is a new schema version. A version is retired only
  after notice, and the schema files are pinned by sha256 (`UOR_HANDOFF.md`).

## 12. Audit and retention

- **One ledger row per (credential, `client_request_id`)**, written by the call that reserved it. Its
  repeats (replay, conflict, in-progress) are answered from that row and not recorded separately.
- **The row holds:**
  - `credential_id`, never its value;
  - `evidence_origin`, `client_request_id`, `request_fingerprint`;
  - `state`, `outcome_code`, `http_status` and the exact `response_body`;
  - `run_id`, `analysis_hash`, `evidence_hash`, `release_id`;
  - `deadline_ms`, `received_at_utc` and `completed_at_utc` (never before reception).
- **Retention** is at least 90 days. The route itself never deletes a row; only an owner-run,
  on-demand purge removes ledger rows older than 90 days. Unauthenticated and malformed calls are
  never recorded.
- **The capacity contract** (frozen; `RETENTION_AND_IDEMPOTENCY.md` section 2) bounds storage:
  - the ledger never takes a new row past 25,000 rows: 503 `LEDGER_UNAVAILABLE`, nothing written,
    and replays are still served;
  - a credential records at most 2 x its daily quota rows in any rolling day;
  - no stored body exceeds 8,192 bytes;
  - at the maximum quota of 120 per day, 90 days of one credential fit under the cap.
  The route fails closed at its bound. There is no recurring job.

## 13. Enablement prerequisites (all owner-gated; the exact states are in `UOR_HANDOFF.md` section 1)

1. **G2:** the owner accepts or modifies this interface.
2. **Registry and ledger:** the dedicated one-shot apply route for migration 0013 is BUILT
   (`scripts/apply_migration_0013.py` and `.github/workflows/apply-migration-0013.yml`, the 0012
   pattern). It is rehearsed on a real PostgreSQL on every pull request that touches it, and again
   inside the dispatch before the secret is handed out. The apply itself is a T4.
3. **Database access:** the route uses the Space's `SUPABASE_DB_URL`. The human persistence already
   reaches the database through it (W26 PASS_PROVEN). The route's own connections are proven: the
   post-enable check read the registry, and the canary recorded and replayed its ledger row
   (2026-10-01).
4. **Release:** a release carrying F1 is deployed (T4), and the source guard is re-pinned (T3).
5. **Credential and quota:** the owner issues the credential by inserting its digest into the
   registry (T4, `CREDENTIAL_ROTATION.md`) and decides the quota (G6, a T3 Space variable).
6. **Enable:** `UCPE_AUTOMATION_ENABLED=1` (T3). A controlled canary call follows, under its own
   authorization.
7. **UOR side:** registries and the transport, built in UOR's own sessions. UCPE never writes into
   UOR.
