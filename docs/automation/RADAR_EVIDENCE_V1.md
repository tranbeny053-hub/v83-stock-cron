# Governed automation interface — `POST /v1/automation/radar-evidence` (`radar_evidence.v1`)

**Status: UCPE canon, AUTHORED LOCALLY. Not deployed, not enabled, and no credential has been
issued.** The route ships OFF: until the owner enables it, every call gets 503
`AUTOMATION_DISABLED`. Its ledger (migration 0013) is authored but not applied, so an enabled route
still fails closed with 503 `LEDGER_UNAVAILABLE`. This document is UCPE's answer to UOR's proposal
(UOR handoff file 05). UCPE canon wins wherever they differ; the differences are listed in
`F1_NODE_CLASSIFICATION.md`.

## 1. The route

- `POST /v1/automation/radar-evidence`, JSON in and out, one symbol per call. There is no batch
  endpoint.
- It is separate from `/v1/analyze*` and shares nothing with the human routes: no session, run store,
  persistence repository or skill-evidence refresh. It is omitted from the OpenAPI schema.
- It is a thin adapter (`api/automation_endpoint.py`). All policy lives in
  `crypto_probability_engine.automation`, one module per contract:

| Contract | Owner module |
|---|---|
| origin | `origin` |
| configuration and kill switch | `config` |
| machine authentication | `credentials` |
| request, response, errors, hashes | `contract` |
| idempotency and audit | `ledger` |
| rate bounds | `quota` |
| orchestration | `service` |

## 2. Authentication (route-only machine credential)

- **Header.** `X-UCPE-Automation-Credential: ucpea.<credential_id>.<value>`.
  - `credential_id` matches `^[a-z0-9][a-z0-9-]{2,31}$`.
  - The value is exactly 43 URL-safe base64 characters (256 bits).
  - The credential is never accepted in a URL, query string or body.
- **Server side.** UCPE stores only `sha256(value)` (lowercase hex) and compares digests with
  `hmac.compare_digest`. Missing, malformed, unknown, mismatched, revoked and expired credentials all
  get the same answer: 401 `CREDENTIAL_REQUIRED` when the header is absent, 401 `CREDENTIAL_INVALID`
  otherwise. Nothing distinguishes them.
- **Scope.**
  - The credential authenticates this route only. The human routes read only their session cookies,
    so a machine credential gets 401 there.
  - A request that carries a human session cookie (`ucpe_session` or `ucpe_dev_session`) is refused
    here with 403 `HUMAN_SESSION_REFUSED`, even alongside a valid machine credential.
  - CORS does not allow the credential header, so a browser cannot send it cross-origin.
- **Registry.** The environment variable `UCPE_AUTOMATION_CREDENTIALS` holds a JSON array of
  `{"credential_id", "secret_sha256", "status": "ACTIVE"|"REVOKED", "not_after_utc"?}`. It holds
  digests only, never a credential value.
- **Issuance procedure (owner-performed; UCPE never issues or sees a value).**
  1. On the owner's machine, generate the value, for example with Python's
     `secrets.token_urlsafe(32)`, which is 43 characters.
  2. Compute its SHA-256 hex digest.
  3. Add `{"credential_id": ..., "secret_sha256": <digest>, "status": "ACTIVE"}` to the Space secret
     (T3).
  4. Hand the full `ucpea.<id>.<value>` token to UOR's governed secret store, by NAME only. Never put
     it in a file, a chat or a log.
- **Rotation.** Add the new record, move UOR to the new token, verify, then set the old record to
  `REVOKED`. Revocation is immediate once the Space configuration changes.

## 3. Provenance and cohort isolation (non-negotiable)

- **Origin.** `evidence_origin` is always `AUTOMATED_RADAR`, stamped by the server from the
  credential. The client cannot assert it.
- **Not a prediction origin.** `AUTOMATED_RADAR` is not, and cannot be validated as, a
  `PredictionOrigin`. The cohorts `USER_REQUESTED`, `CONTROLLED_SMOKE` and
  `SCHEDULED_SHADOW_EVIDENCE` are untouched and never relabelled.
- **The analysis.** The route runs `analysis_service.analyze_request_isolated`. It is the same
  computation as the human analysis, and the response is byte-identical, which is proven. But it
  takes no origin by construction, builds no prediction row, parks nothing for persistence and
  writes no run-store entry.
- **What an automated run never touches:**
  - `predictions`, `prediction_outcomes`, `analysis_runs` or any snapshot table;
  - calibration, the skill gate's evidence and control statistics;
  - `/v1/runs`, run detail and the resolver.
- **Storage.** Automated runs are stored only in the isolated ledger
  `public.automation_radar_ledger`, which no cohort reader reads.
- **Protected evidence.** Protected section 5A holdout evidence is never used, returned or inferable
  here. The route reads only live market data and the published skill gate.
- **Proof.**
  - `tests/automation/test_cohort_isolation.py`: byte-identity, no pending rows, no persistence call,
    no run-store write, no cohort field, and no cohort writer imported.
  - After enablement, an owner-authorized read-only audit query must return 0:
    `SELECT count(*) FROM public.predictions p JOIN public.automation_radar_ledger l ON
    p.prediction_id LIKE l.run_id || ':%';`

## 4. Request (strict; unknown, missing or duplicate fields are refused)

```json
{"symbol": "BTC", "primary_timeframe": "4H", "client_request_id": "<canonical lowercase UUID>", "deadline_ms": 30000}
```

- **Body limits.** At most 1024 bytes of UTF-8 JSON. NaN and Infinity are refused.
- **`primary_timeframe`** ∈ `15m`, `1H`, `4H`, `1D`. Anything else gets 422
  `UNSUPPORTED_TIMEFRAME`.
- **`symbol`** must normalize as a UCPE spot symbol. Otherwise, or if market data rejects it, 422
  `UNSUPPORTED_SYMBOL`.
- **`deadline_ms`** is an integer from 5000 to 60000.
- **Mode.** Every call is `METRICS_ONLY` spot: no news add-on and no paid API. News could never
  override a hard gate anyway.
- **No holdout selector.** There is no free-form field, no user identity and no holdout selector.

## 5. Response `radar_evidence.v1` (`schemas/radar_evidence.schema.json`, draft 2020-12)

- **Strictness.** `additionalProperties: false` at every level. Every body is validated against the
  pinned schema before it is sent; a body that fails is withheld (503 `CONTRACT_VIOLATION`).
- **Fields.** Every value is read from UCPE's governed analysis and never recomputed:
  - identity: `schema_version`, `evidence_origin`, `client_request_id`, `run_id`, `analysis_hash`,
    `analysis_schema_version` (the `response.v1` schema_version it was read from);
  - time: `as_of_utc` (the market-data instant) and `issued_at_utc` (server time when issued);
  - market: `symbol`, `normalized_symbol`, `primary_timeframe`, `horizon.{bars,label}`;
  - release: `build_info`, exactly the serving release's public `GET /v1/build-info` payload:
    `schema_version`, `release_id`, `release_label`, `environment`, `source_milestone`,
    `fingerprint`.
- **`probability_state`:** `probability_type`, `calibration_status`, and for `H_primary` and
  `H_extended`:
  - `p_up_frac`, `p_down_frac`, `p_timeout_frac`, `confidence_frac`, `status`, `null_reason`;
  - the three fractions sum to 1 within 1e-9, checked before sending;
  - `sample_count: null` and `sample_count_basis: "NONE_UNCALIBRATED_HEURISTIC"`.
- **Sample counts.** UCPE's probabilities are uncalibrated heuristic estimates (`reliability_status`
  `INSUFFICIENT_SAMPLE`), so no sample count stands behind them and none is ever reported.
  Fabricating one is forbidden. A calibrated future is a new schema version.
- **Governance context:**
  - `calibration_state.{calibration_status,reliability_status,profitability_claim,reason}`;
  - `gate_result.{hard_gate_passed,hard_blocks,directional_evidence_hold}`;
  - `decision_brief.{action,hard_blockers,model_readiness,reliability_status,profitability_claim}`;
  - `frontend_display.{is_live_data,disposition}`;
  - `data_quality.{status,is_live_data,data_source,cross_provider_state}`.
  - `profitability_claim` is the constant `false`: the schema refuses any other value.
- **Withheld on purpose:**
  - the shadow blocks (`quant_v2`, `derivatives_intelligence`), which have 0.0 decision influence;
  - `skill_evidence`, and in particular `observed_directional_rate`;
  - the H2 hold's `legacy_verdict`, the verdict under correction. The hold is carried as
    `{active, hold_reason}` only.
- **Hard gates.** They outrank everything. UOR must treat `hard_gate_passed: false` as binding.

## 6. Evidence identity and hashes

- **`run_id`** matches `run_<32 hex>` and is unique per run.
- **`analysis_hash`** is UCPE's own analysis identity: `stable_hash` over the analysis before its
  shadow blocks. It is carried as read.
  - It is NOT recomputable from the validated `response.v1` (proven: serialization changes the
    bytes), and the automation body does not carry the full analysis. So UOR must not try to
    recompute it.
- **`evidence_hash`** is the published, offline-verifiable hash of what UOR receives:

```python
import hashlib, json

def evidence_hash(body: dict) -> str:
    unsigned = {k: v for k, v in body.items() if k != "evidence_hash"}
    text = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return "sha256:" + hashlib.sha256(text.encode("ascii")).hexdigest()
```

## 7. Determinism

- Determinism is defined over **canonical evidence inputs and the release identity**: the same
  market snapshot, analyzed by the same release (`build_info.release_id` plus `fingerprint`),
  yields the same analysis content. `tests/automation/test_cohort_isolation.py` proves the isolated
  analysis equals the recorded one byte for byte.
- A repeated live call is **not** reproducible: each call fetches live market data, so
  `determinism.live_repeat_reproducible` is the constant `false`.
- `run_id` and `issued_at_utc` are per call.
- UCPE makes no stronger claim.

## 8. Deadlines and errors (`radar_evidence_error.v1`, `schemas/radar_evidence_error.schema.json`)

- **Deadline.** The server enforces `deadline_ms` and keeps 0.5 s for building and recording the
  body. Past the deadline the answer is 503 `DEADLINE_EXCEEDED`, never partial evidence.
- **Overrun work.** An analysis that overruns keeps its concurrency slot until its thread ends, so
  overruns never pile up.
- **Error body.** Every error is `{"schema_version": "radar_evidence_error.v1", "error": {"code",
  "message", "retry_after_seconds"}}`. Messages are fixed, and no body echoes a credential, a request
  field or user data. Every response has `Cache-Control: no-store`.

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

- **Key.** `client_request_id` is scoped per credential. Its row is reserved before any analysis
  starts, so a repeat can never start a second run.
- **Repeats of the same request.** "Same" means the same `symbol`, `primary_timeframe` and
  `deadline_ms`:
  - once it has completed, the stored outcome is replayed byte for byte, whether a 200 body or a
    refusal, with `Idempotent-Replay: true`;
  - while it is still running, 409 `REQUEST_IN_PROGRESS`;
  - past its deadline plus 60 s it counts as abandoned, and is closed and answered 503
    `DEADLINE_EXCEEDED`, never re-run.
- **A different request under the same key:** 409 `IDEMPOTENCY_CONFLICT`.
- **No ledger row.** Refusals before the reservation (400, 401, 403, 422) write none, so the key
  stays usable.

## 10. Quota, concurrency and cost

- **Quota.** Per credential, counted from the ledger so a restart never resets it:
  - `UCPE_AUTOMATION_QUOTA_PER_5MIN`: default 6, allowed 1–60;
  - `UCPE_AUTOMATION_QUOTA_PER_DAY`: default 120, allowed 1–2000.
  - Refusals before an analysis (`QUOTA_EXCEEDED`, `CONCURRENCY_LIMIT`) do not count.
- **Concurrency.** One automated analysis at a time per process; a busy slot gets 429 at once and
  never queues.
- **Cost model.** Each counted call is one METRICS_ONLY analysis: public exchange market-data
  requests (free) plus Space CPU for a few seconds. There is no paid API. The default caps bound the
  load at 120 analyses a day. The quota level is owner decision G6.

## 11. Kill switch, rollback and deprecation

- **Kill switch.** `UCPE_AUTOMATION_ENABLED` must be exactly `1` or `true`, and it defaults to off.
  Clearing it (a Space configuration change, T3) returns every call to 503 `AUTOMATION_DISABLED`.
- **Consumer rollback.** UOR observes errors and falls back to no evidence.
- **Deprecation.** Any breaking or semantic change is a new schema version, and a version is retired
  only after notice. The schema files are pinned by sha256 (see the handoff manifest).

## 12. Audit and retention

- **One ledger row per authenticated, well-formed call**, holding:
  - `credential_id` (never the value) and `evidence_origin`;
  - `client_request_id` and `request_fingerprint`;
  - `state`, `outcome_code`, `http_status` and the exact `response_body`;
  - `run_id`, `analysis_hash`, `evidence_hash` and `release_id`;
  - `deadline_ms`, `received_at_utc` and `completed_at_utc`.
- **Retention:** 90 days. The purge is a separate owner-authorized operation and is not automated.

## 13. Enablement prerequisites (all owner-gated; none is done)

1. **G2.** The owner accepts or modifies this interface.
2. **Ledger.** A dedicated one-shot apply route for migration 0013 is built, following the 0012
   pattern, then applied (T4).
3. **Database.** The Space has `SUPABASE_DB_URL` for the ledger's own connection (T3). This is
   unverified today.
4. **Release.** A release carrying F1 is deployed (T4), and the source guard is re-pinned (T3).
5. **Credential and quota.** The owner issues the credential by the procedure above (T3 Space
   secret) and decides the quota (G6).
6. **Switch on.** `UCPE_AUTOMATION_ENABLED=1` (T3). A CONTROLLED canary call runs under its own
   authorization.
7. **UOR side (UOR's own sessions).**
   - Register `AUTOMATED_RADAR`, `radar_evidence.v1` and the accepted release in UOR's allowlists.
   - Build the transport.
   - UCPE never writes into UOR.
