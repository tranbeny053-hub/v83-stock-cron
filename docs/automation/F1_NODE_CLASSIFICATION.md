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
| 1.3 | "Same inputs at the same `as_of_utc` on the same release give the same analysis" | MODIFIED | The canonical inputs are named: the market snapshot, the published skill-gate state and the release with its settings. Per-call identity and time fields are excluded. Equality is proven on fixed inputs. A repeated LIVE call is not reproducible (`live_repeat_reproducible: false`). |
| 2.1–2.3 | Dedicated credential, route-scoped, header only | INTEGRATED | `X-UCPE-Automation-Credential` holds `ucpea.<id>.<value>`; the server keeps sha256 digests and compares them with compare_digest on every well-formed token. A malformed token is refused on its format alone. A human session is refused here (403); the credential gets 401 on all 14 human method-paths (tested). |
| 2.4 | Rotation and revocation | INTEGRATED + OWNER | Zero-downtime rotation and immediate revocation. The registry is the database table `automation_credential` (0013), read on every request with no cache, so a change applies to the next request with no Space restart. Several ACTIVE rows may overlap; there are REVOKED rows and `not_after_utc`. Tested in unit tests and on real PostgreSQL in the PR rehearsal. Issuing, rotating and revoking are owner T4 actions (`CREDENTIAL_ROTATION.md`). UCPE never issues or stores a value; it only hashes the presented one in memory. |
| 2.5 | UOR resolves the credential by NAME | SERIAL | UOR side (step F3). |
| 3.1 | Server-stamped `evidence_origin` | INTEGRATED | Stamped from the credential, never from the client. |
| 3.2 | "Persisted with the run" | MODIFIED | Persisted only in the isolated `automation_radar_ledger`, never with the shared run or prediction rows. The owner's rule: no `AUTOMATED_RADAR` in shared prediction-origin or storage semantics. |
| 3.3 / 9.1 | Isolated from calibration and control | INTEGRATED | Structural. `analyze_request_isolated` has no origin, row, persistence or run store, and there are regression tests. |
| 4 | Strict request, `client_request_id`, no free-form fields | INTEGRATED | Strict parser plus schema. `deadline_ms` is 5000–60000; timeframes are `15m/1H/4H/1D`; the mode is always METRICS_ONLY. |
| 4.1 | Idempotency: the same run or 409, never a second run | INTEGRATED | Reserved before analysis; replay, conflict, in-progress and abandoned are handled while the key is retained: 90 days in production (until an owner purge), about 26 hours in the in-memory test ledger. The durable ledger is authored (0013). Its Postgres path is exercised on a real scratch PostgreSQL by `scripts/migration_0013_rehearsal/probe_app_sql.py` in the PR rehearsal workflow. |
| 5.1 | New pinned schema version | INTEGRATED | `radar_evidence.v1` and `radar_evidence_error.v1`, pinned by sha256. |
| 5.2 | Required fields, **including the sample count behind each probability** | MODIFIED | Every field is present except that no sample count is fabricated: `sample_count: null` with `sample_count_basis: "NONE_UNCALIBRATED_HEURISTIC"`. UCPE's probabilities are uncalibrated heuristics (`INSUFFICIENT_SAMPLE`). A horizon whose status is not OK carries null numbers. The projection holds codes only, never prose. |
| 5.3 | Shadow blocks omitted | INTEGRATED | `quant_v2` and `derivatives_intelligence` are never carried. |
| 5.4 | Versioning rules | INTEGRATED | Any semantic change is a new version; notice before retirement. |
| 6.1 / 6.3 | `run_id` unique; `as_of_utc` aware UTC | INTEGRATED | Read from the analysis; the schema enforces the patterns. |
| 6.2 | `analysis_hash` re-verifiable offline | MODIFIED | `analysis_hash` is carried as UCPE's identity, and is proven NOT recomputable from `response.v1`. The offline-verifiable hash is `evidence_hash` over **RFC 8785 JCS**, which is cross-language. Every response is also sent as its JCS bytes, so replays are byte-identical. |
| 6.4 | UOR persists the identities | SERIAL | UOR side (F3). |
| 7.1–7.2 | Server deadline; fixed status codes | INTEGRATED | A monotonic budget runs from arrival to the ledger commit. A success is recorded only if the database clock is within the deadline; otherwise it is recorded and answered DEADLINE_EXCEEDED. No partial evidence. A fixed catalogue, with fixed messages (schema enum), inside the proposed status classes. |
| 7.3 | UOR's no-evidence rule | SERIAL | UOR side. |
| 8.1 | Per-credential quota, 5 minutes and daily | INTEGRATED + OWNER | Enforced from the ledger, defaults 6 and 120. The daily quota is bounded at 120 by the capacity contract. **G6** stays provisional until measured production resource evidence exists. |
| 8.2 | UOR caps deep calls | SERIAL | UOR side. |
| 8.3 | The cost model is stated | INTEGRATED | Public market data plus Space CPU; no paid API. |
| 9.2 | Section 5A never used or inferable | SATISFIED | The route reads live data and the published gate only. The automation package imports no oos, calibration or resolution module (tested). |
| 9.3 | Isolation provable | INTEGRATED + OWNER | Regression tests, plus the audit SQL in the contract. Running it needs an enabled route and an owner database read. |
| 10.1–10.2 | Per-call audit; retention stated | INTEGRATED | One ledger row per (credential, client_request_id). Its repeats are answered from that row and not recorded separately. Unauthenticated and malformed calls are never recorded. Retention is at least 90 days. Storage is bounded by the frozen capacity contract: a 25,000-row cap, a rolling-day row ceiling per credential, and an 8 KB body bound. It fails closed, with no recurring job and no automatic deletion (`RETENTION_AND_IDEMPOTENCY.md`). |
| 11.1 | `build_info.release_id` and fingerprint in every response | INTEGRATED (success bodies) | Every 200 carries the full six-field `GET /v1/build-info` payload. Error bodies carry only the catalogued error. |
| 11.2 | UOR release allowlist | SERIAL + OWNER | UOR side; **G2**. |
| 12.1 | Kill switch | INTEGRATED | `UCPE_AUTOMATION_ENABLED`, default OFF (503). |
| 12.2–12.3 | UOR rollback; deprecation notice | SERIAL / INTEGRATED | UOR side; deprecation policy documented. |
| 13 | Schemas plus sha256; at least 2 non-holdout, provenance-declared examples; hash algorithm, quota, errors, credential procedure | INTEGRATED | `docs/automation/UOR_HANDOFF.md` lists every file with its sha256: schemas, contract, examples and their manifest, classification, audit. |
| 14 | UOR's prepared boundary | SERIAL | UOR side; UCPE never writes into UOR. |
| F1-a | Ledger migration 0013 | INTEGRATED (authored) | Applying it is an owner **T4**. |
| F1-b | Dedicated one-shot apply route for 0013 (script plus dispatch-only workflow, real-PostgreSQL rehearsal) | INTEGRATED | `scripts/apply_migration_0013.py`, `.github/workflows/apply-migration-0013.yml` (dispatch-only, one shot) and `apply-migration-0013-rehearsal.yml` (every PR, no secret), in the 0012 pattern. The bulk `apply_migrations.py` is never used, and no workflow runs it (tested). The apply is an owner **T4**. |
| F1-c | `SUPABASE_DB_URL` present on the Space for the ledger | OWNER | T3 configuration check. Unverified. |
| F1-d | Release carrying F1, deploy, guard re-pin | OWNER | T4 deploy and T3 re-pin. The guarded delta is `analysis_service.py` and `api/app.py`. |
| F1-e | Enable plus a CONTROLLED canary call | OWNER / SERIAL | T3 Space configuration, then a canary under its own authorization. |
| F1-f | Register `AUTOMATED_RADAR` in UCPE's shared `PredictionOrigin` | MODIFIED | Not done. `COHORT_READER_AUDIT.md` found generic readers that would include an unknown origin by default, so UCPE keeps the origin isolated. Any change needs those readers allowlisted first, and an owner decision. |

## Adversarial review (Codex, read-only, at 4f9ae93) and the repair

| Finding | Severity | Disposition |
|---|---|---|
| F1: evidence could be returned after the deadline | HIGH | REPAIRED. There is a monotonic budget from arrival; a success is recorded only within the deadline, checked by the database clock inside the recording transaction; late means DEADLINE_EXCEEDED, recorded and answered; every database operation is timeout-bounded. |
| F2: Retry-After ignored a full daily window | MEDIUM | REPAIRED. It is now the max over exhausted windows. |
| F3: a durable replay was not byte-identical (JSONB reorders keys) | MEDIUM | REPAIRED. Every response is sent as RFC 8785 JCS bytes. |
| F4: the hash was Python-specific | MEDIUM | REPAIRED. The hash is over RFC 8785 JCS, with ECMAScript number vectors tested. |
| F5: schema strings could carry prose | MEDIUM | REPAIRED. The projection has no prose; code patterns; null numbers on non-OK horizons; fixed error messages as a schema enum; error and replay bodies validated at runtime. |
| F6: the determinism statement omitted the skill cache | MEDIUM | REPAIRED in the docs. The inputs are named. |
| F7–F10: documentation absolutes, clock rollback, live data | LOW | REPAIRED. The docs are exact; `completed_at` is never before reception; non-live data yields no evidence. F8, where `analyze_request` now refuses an out-of-contract `run_store=None` up front, is kept as a deliberate improvement. |

The pin-test attestation: the reviewer's sandbox could not run the pin tests, so that item was NOT_RUN. Claude's full `./verify.sh` covers the pin and closure tests, and it passes. The planned Codex delta review of the repair could not run either, because the Codex quota was exhausted. It was replaced by Claude's own diff review and the regression tests in `tests/automation/test_repair_contract.py` and `test_canonical.py`.

**Owner decisions this surfaces:**
- **G2:** ACCEPTED by the owner as the local contract candidate.
- **G6:** provisional at 6 per 5 minutes and 120 per day. This is not an activation or spend
  approval.
- The rest, none of it taken, in the order of `F1_RELEASE_PLAN.md`:
  - the merge (T3);
  - the 0013 apply (T4);
  - a release (T4) and the re-pin (T3);
  - credential issuance (T4);
  - the enable (T3);
  - the canary.
