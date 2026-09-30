# F1 node classification — UOR proposal (handoff files 04 and 05) under UCPE canon

**Scope.** The source is UOR's `05_PROPOSAL_UCPE_GOVERNED_AUTOMATION_INTERFACE.md` (sha256
`e8d6d9ac…`), together with the F1 deliverables of `04_FINAL_PHASE_PLAN_DEPENDENCIES_AND_DECISIONS.md`.
Both are proposals, not canon. UCPE canon wins. The contract that results is `RADAR_EVIDENCE_V1.md`.

**Classes:**
- `SATISFIED`: ALREADY_SATISFIED_BY_CURRENT_WORK.
- `INTEGRATED`: SAFE_TO_INTEGRATE_NOW, done in this milestone.
- `PARALLEL`: SAFE_PARALLEL_WITHIN_CURRENT_LOOP.
- `SERIAL`: SERIALIZE_AFTER_CURRENT_NODE.
- `OWNER`: OWNER_GOVERNANCE_BLOCKED.
- `MODIFIED`: REJECT_MODIFY_UNDER_UCPE_CANON.

| # | Proposal node | Class | UCPE disposition |
|---|---|---|---|
| 0.1 | `/v1/analyze*` forbidden for automated use | SATISFIED | The human routes need a human session. A machine credential gets 401 on every one of them (tested). |
| 0.2 | No existing origin is a UOR input | SATISFIED + INTEGRATED | The cohorts are untouched. `AUTOMATED_RADAR` is new, and isolated outside `PredictionOrigin`. |
| 0.3 | `response.v1` lacks origin and release identity | INTEGRATED | `radar_evidence.v1` carries both. `response.v1` is unchanged. |
| 1.1 | Separate machine endpoint | INTEGRATED | `POST /v1/automation/radar-evidence`, OFF by default. |
| 1.2 | One symbol per call; any batch is a separate endpoint | INTEGRATED | One symbol per call. No batch endpoint is offered. |
| 1.3 | "Same inputs at the same `as_of_utc` on the same release give the same analysis" | MODIFIED | Determinism is over canonical inputs plus release identity, and is proven in tests. A repeated LIVE call is not reproducible (`live_repeat_reproducible: false`). |
| 2.1–2.3 | Dedicated credential, route-scoped, header only | INTEGRATED | `X-UCPE-Automation-Credential` holds `ucpea.<id>.<value>`; the server keeps sha256 digests and compares in constant time. A human session is refused here (403); the credential is refused on human routes (401). |
| 2.4 | Rotation and revocation | INTEGRATED + OWNER | The registry supports several ACTIVE records, REVOKED and `not_after_utc`. Issuing any credential is owner-performed; UCPE never issues or sees a value. |
| 2.5 | UOR resolves the credential by NAME | SERIAL | UOR side (step F3). |
| 3.1 | Server-stamped `evidence_origin` | INTEGRATED | Stamped from the credential, never from the client. |
| 3.2 | "Persisted with the run" | MODIFIED | Persisted only in the isolated `automation_radar_ledger`, never with the shared run or prediction rows. The owner's rule: no `AUTOMATED_RADAR` in shared prediction-origin or storage semantics. |
| 3.3 / 9.1 | Isolated from calibration and control | INTEGRATED | Structural. `analyze_request_isolated` has no origin, row, persistence or run store, and there are regression tests. |
| 4 | Strict request, `client_request_id`, no free-form fields | INTEGRATED | Strict parser plus schema. `deadline_ms` is 5000–60000; timeframes are `15m/1H/4H/1D`; the mode is always METRICS_ONLY. |
| 4.1 | Idempotency: the same run or 409, never a second run | INTEGRATED | Reserved before analysis; replay, conflict, in-progress and abandoned are handled. The durable ledger is authored (0013). Its Postgres path is tested with a fake connection only: **NOT_RUN on real PostgreSQL.** |
| 5.1 | New pinned schema version | INTEGRATED | `radar_evidence.v1` and `radar_evidence_error.v1`, pinned by sha256. |
| 5.2 | Required fields, **including the sample count behind each probability** | MODIFIED | Every field is present except that no sample count is fabricated: `sample_count: null` with `sample_count_basis: "NONE_UNCALIBRATED_HEURISTIC"`. UCPE's probabilities are uncalibrated heuristics (`INSUFFICIENT_SAMPLE`). |
| 5.3 | Shadow blocks omitted | INTEGRATED | `quant_v2` and `derivatives_intelligence` are never carried. |
| 5.4 | Versioning rules | INTEGRATED | Any semantic change is a new version; notice before retirement. |
| 6.1 / 6.3 | `run_id` unique; `as_of_utc` aware UTC | INTEGRATED | Read from the analysis; the schema enforces the patterns. |
| 6.2 | `analysis_hash` re-verifiable offline | MODIFIED | `analysis_hash` is carried as UCPE's identity, and is proven NOT recomputable from `response.v1`. The offline-verifiable hash is the published `evidence_hash`. |
| 6.4 | UOR persists the identities | SERIAL | UOR side (F3). |
| 7.1–7.2 | Server deadline; fixed status codes | INTEGRATED | Deadline enforced; no partial evidence; a fixed catalogue within the proposed status classes. |
| 7.3 | UOR's no-evidence rule | SERIAL | UOR side. |
| 8.1 | Per-credential quota, 5 minutes and daily | INTEGRATED + OWNER | Enforced from the ledger, defaults 6 and 120. The final level is **G6**. |
| 8.2 | UOR caps deep calls | SERIAL | UOR side. |
| 8.3 | The cost model is stated | INTEGRATED | Public market data plus Space CPU; no paid API. |
| 9.2 | Section 5A never used or inferable | SATISFIED | The route reads live data and the published gate only. The automation package imports no oos, calibration or resolution module (tested). |
| 9.3 | Isolation provable | INTEGRATED + OWNER | Regression tests, plus the audit SQL in the contract. Running it needs an enabled route and an owner database read. |
| 10.1–10.2 | Per-call audit; retention stated | INTEGRATED | One ledger row per authenticated, well-formed call; retention 90 days; the purge is owner-authorized. |
| 11.1 | `build_info.release_id` and fingerprint in every response | INTEGRATED | `build_info_payload()` of the serving release. |
| 11.2 | UOR release allowlist | SERIAL + OWNER | UOR side; **G2**. |
| 12.1 | Kill switch | INTEGRATED | `UCPE_AUTOMATION_ENABLED`, default OFF (503). |
| 12.2–12.3 | UOR rollback; deprecation notice | SERIAL / INTEGRATED | UOR side; deprecation policy documented. |
| 13 | Schemas plus sha256; at least 2 non-holdout, provenance-declared examples; hash algorithm, quota, errors, credential procedure | INTEGRATED | `docs/automation/`: the contract, the examples with their manifest, and this file. |
| 14 | UOR's prepared boundary | SERIAL | UOR side; UCPE never writes into UOR. |
| F1-a | Ledger migration 0013 | INTEGRATED (authored) | Applying it is an owner **T4**. |
| F1-b | Dedicated one-shot apply route for 0013 (script plus dispatch-only workflow, real-PostgreSQL rehearsal) | SERIAL | Built when the owner schedules enablement, following the 0012 pattern. |
| F1-c | `SUPABASE_DB_URL` present on the Space for the ledger | OWNER | T3 configuration check. Unverified. |
| F1-d | Release carrying F1, deploy, guard re-pin | OWNER | T4 deploy and T3 re-pin. The guarded delta is `analysis_service.py` and `api/app.py`. |
| F1-e | Enable plus a CONTROLLED canary call | OWNER / SERIAL | T3 Space configuration, then a canary under its own authorization. |
| F1-f | Register `AUTOMATED_RADAR` in UCPE's shared `PredictionOrigin` | MODIFIED | Not done. UCPE keeps the origin in the isolated automation domain. Any future sharing needs the cohort-reader dependency audit first (prepared in this milestone) and an owner decision. |

**Owner decisions this surfaces (none is taken):**
- **G2:** accept or modify this interface.
- **G6:** the quota level.
- The T3 configuration check of `SUPABASE_DB_URL`.
- The 0013 apply route build, then its T4 apply.
- A release T4 and the re-pin T3.
- Credential issuance, the enable T3, and the canary.
