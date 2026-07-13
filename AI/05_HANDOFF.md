# Handoff Packet

## Ops-RT.1 Pinned HF Baseline Handoff — 2026-07-13

- Goal: replace the scheduler-checkout production-intent assumption with a committed HF baseline
  and add a strictly advisory scheduler deployment delta.
- Q1: `ops/hf_runtime_baseline.json`, validated by
  `schemas/hf_runtime_baseline.schema.json`, pins HF release 2A.0 at
  `30d4982903e6f44e063616bc3f03f334bd2544e2`. All intended release, milestone, fingerprint,
  frontend token, and critical-digest values come from that manifest.
- Fail-closed behavior: missing or invalid pin/schema is `PIN_MISSING` before network activity;
  confirmed HF main identity drift is `PIN_DRIFT`. Existing source, runtime, frontend, transition,
  unavailable-probe, and metadata-anomaly semantics remain intact.
- Q2: only a fully `HEALTHY` Q1 can evaluate the local scheduler SHA and governed checkout bytes.
  Missing local pin history causes no fetch or failure; the ahead count is null and the advisory
  remains non-failing. Q2 cannot change Q1 classification or exit code.
- Ownership: scheduler commits may advance independently and do not become production intent. A
  pin change requires separate reviewed deployment authorization plus mechanical regeneration and
  fidelity verification from the authorized app-root HF Git object.
- Incident interpretation: the current red guard was caused by the old baseline model, not an HF
  production defect. No HF deployment, production mutation, schedule weakening, or guard
  weakening occurred.
- Separate gates remain closed: cadence freeze, sentinel/window decisions, 4D.4, 4D.5, production
  evidence writes, and Decision influence.
- Verification: 62 focused guard tests and 724 full offline tests pass. Ruff, schema, build-info,
  secret, forbidden-scope, article-body, and offline manual-smoke checks pass.
- Next: Claude high-risk merge-readiness review of the exact local implementation commit.

---

## Wave 4D.3-Ops Phase 2D.0A Versioned Response + Selector Handoff — 2026-06-23

- Goal: add the safe internal selector seam needed by a future trusted caller while preserving
  default v0 behavior for every existing caller.
- Branch: `codex/wave-4d3-ops-2d0a-versioned-response-and-selector`; base tag
  `wave-4d3-ops-2b-okx-only-method-v1`.
- Implementation: `analyze_request` accepts a keyword-only
  `derivatives_methodology_version` defaulting to `deriv-intel-shadow-v0`, validates against a
  closed allowlist of v0/v1 constants before market/provider work, and forwards the value only to
  `build_derivatives_intelligence`.
- Response contract: `AnalysisResponse` and `schemas/response.schema.json` now accept exactly the
  historical v0 derivatives block or the OKX-only v1 block. V1 requires the reviewed provider
  policy, OKX-only summary/metrics, empty comparability/disagreement, and complete valid OKX
  evidence for `ACTIVE`.
- Safety: `AnalysisRequest`, `app.py`, collector, cadence identity, persistence, migrations,
  workflows, frontend, build fingerprint, Quant V2, probability, score, gates, Decision, and
  decision influence remain unchanged.
- Still blocked: collector v1 wiring, Phase 2D cutover guard, collection windows, scheduler
  deployment, HF deployment, workflow dispatch, dry run, `WRITE-EVIDENCE`, cron, 4D.4, 4D.5, and
  any production write.
- Next: Claude merge-readiness review of the exact selector/response-contract commit.

---

## Wave 4D.3-Ops Phase 2B OKX-only v1 Handoff — 2026-06-23

- Goal: add an explicit OKX-only derivatives shadow methodology contract without changing
  historical v0 evidence, cadence identity, collector source, API models, workflows, migrations,
  or build identity.
- Branch: `codex/wave-4d3-ops-2b-okx-only-method-v1`; base tag
  `wave-4d3-ops-binance-registry-diagnostic`.
- Versioning: v0 stays `deriv-intel-shadow-v0` / `deriv-intel.v0`; v1 is
  `deriv-intel-okx-shadow-v1` / `deriv-intel.v1` with provider policy
  `deriv-provider-policy-okx-only-v1`.
- Provider policy: v1 requires exactly `OKX_SWAP`, emits no Binance summary or metrics, and
  leaves comparability empty because there is no cross-provider comparison.
- Status semantics: v1 `ACTIVE` requires the complete valid OKX metric set; partial OKX evidence
  is `DEGRADED`; zero valid OKX evidence or provider unavailability is `UNAVAILABLE`.
- Safety: `SHADOW_ONLY`, decision influence zero, provider-native values only, no aggregation,
  no score/probability/gate/decision impact, no live provider call, no DB access, and no evidence
  generation.
- Limitation: cadence identity does not include derivatives methodology. Do not authorize a
  production v1 write until Phase 2D reviews identity and first-write semantics.
- Next: Claude merge-readiness review of the exact implementation commit.

---

## Wave 4D.3-Ops Phase 2A Collector Review Handoff — 2026-06-22

- Goal: add a dormant manual collector around the deployed deterministic identity and synchronous
  persistence primitives, without changing the runtime or generating evidence.
- Branch: `codex/wave-4d3-ops-2a-collector-foundation`; base tag
  `wave-4d3-ops-2a0-cadence-runtime` at `cc8d4f0`.
- Gate order: validate fixed matrix, evaluate the process-local enable gate, require dry-run/write
  confirmation, construct dependencies, then process cells sequentially.
- Matrix: BTC/ETH at 1H/4H only; maximum four cells, predictions, and derivatives snapshots.
- Identity and persistence: `analyze_request(..., deterministic_identity=True,
  prediction_origin="SCHEDULED_SHADOW_EVIDENCE")`, followed only in confirmed write mode by
  `persist_analysis_now`.
- Workflow: `workflow_dispatch` only, defaults disabled and dry-run, exact confirmation token
  `WRITE-EVIDENCE`, read-only repository permission, non-cancelling concurrency.
- Safety: no normal runtime change, no global derivatives activation, no migration, no SQL, no
  direct repository save, no secret output, no HF token, no schedule, and no evidence generated.
- Next: Claude merge-readiness review before GitHub-only deployment and any manual dispatch.

---

## Ops-RT.1 Review Handoff — 2026-06-22

- Goal: detect persistent disagreement between intended source, HF `main`, public build identity,
  and live frontend serving without mutating any system.
- Branch: `codex/ops-rt1-source-integrity-guard`; base `dev` at
  `wave-4d3-derivatives-snapshots`.
- Topology: app-subtree workflow paths publish to repository-root `.github/workflows` on
  `tranbeny053-hub/v83-stock-cron`.
- Probe: three rounds, 20 seconds apart; four public GET resources and an isolated exact-commit HF
  Git comparison of eleven runtime-critical files.
- Verdict: only 3/3 persistent runtime, frontend, source, or contract divergence exits non-zero.
  Metadata anomalies, transitions, and probe unavailability remain non-failing.
- Safety: exact URL/method allowlist, no session/authentication, no response-body logging, no
  analysis/calibration/watchlist request, and no database/deployment action.
- Workflow: every two hours at minute 27, manual dispatch available to the operator, read-only
  contents permission, no repository secrets.
- Fingerprint remains `UCPE-W4D3-DERIV-SNAPSHOT-20260622-A`; runtime files are unchanged.
- Next: Claude merge-readiness review before merge. Do not dispatch or deploy from this branch.

---

## Wave 4D.3 Review Handoff — 2026-06-22

- Goal: persist the already-built 4D.2 derivatives block as immutable, prediction-linked shadow
  evidence without changing the response or any analysis artifact.
- Branch: `codex/wave-4d3-derivatives-snapshots`; base tag
  `wave-4d2-derivatives-intel-runtime`.
- Eligibility: only `ACTIVE`, `DEGRADED`, and `UNAVAILABLE` blocks with valid shadow constants,
  matching normalized symbol/core timestamp, and a non-earlier observation timestamp.
- Projection: exact top-level, provider-summary, provenance-metric, and comparability allowlists;
  presentation text, raw envelopes, unknown future fields, and non-finite values are excluded or
  rejected.
- Immutability: canonical full-envelope SHA-256 plus insert-ignore/read-classify semantics across
  memory, PostgreSQL, and REST repositories. Conflicts never overwrite the first row.
- Database boundary: RLS enabled, no client policies, server-role `SELECT`/`INSERT` only, with
  update/delete/truncate rejection triggers. The migration is source-only and remains unapplied.
- Persistence ordering: prediction ledger, existing Quant V2 snapshot, then derivatives snapshot;
  parent failure prevents an orphan write, and derivatives failure never escapes core analysis.
- Safety: `SHADOW_ONLY`, decision influence zero, no validation, backfill, promotion, frontend,
  provider collection, resolver, calibration, probability, gate, or decision change.
- Fingerprint: `UCPE-W4D3-DERIV-SNAPSHOT-20260622-A`.
- Next: Claude reviews the one implementation commit before any merge or migration action.

---

## Wave 4D.2 Review Handoff — 2026-06-22

- Goal: add a default-OFF, public-only derivatives context block without changing any protected
  analysis, identity, decision, or persistence artifact.
- Branch: `codex/wave-4d2-derivatives-runtime`; base `dev` at `87eb22c`.
- Runtime: current Binance USD-M and OKX SWAP funding/open-interest only, sequential and bounded;
  no historical default calls.
- Cache: immutable allowlisted raw payloads only; two registry entries for six hours, 256
  provider/symbol entries for 60 seconds, and 64 fixed process-local lock stripes.
- Timing: `core_prediction_as_of_utc` is the existing snapshot timestamp, while
  `observation_as_of_utc` is the honest post-fetch derivatives cutoff. Original endpoint fetch
  timestamps survive cache hits, and staleness/no-lookahead are rebuilt per request.
- Deadline: no new request starts after nine seconds; an already-started three-second request may
  place the cold-path completion near twelve seconds.
- Governance: `SHADOW_ONLY`, decision influence zero, provider-native values only, no averaging.
- Future boundary: 4D.3 must retain both timestamps; 4D.4 must not align later derivatives
  evidence to the earlier core prediction timestamp.
- Next gate: Claude merge-readiness review. Do not merge or deploy before review.

---

## Goal / Branch

- Goal: UI-D1.5B render the backend `trade_plan_skeleton` as a safe Scenario plan.
- Branch: `codex/ui-d1-5b-trade-plan-render`
- Base: `dev` at merged UI-D1.5A milestone `02b0bc0`.
- Risk: frontend rendering only; review before merge.

## Implementation

- Upgraded `renderTradePlanSkeleton` to read the D1.5A mode, plan status, direction,
  false-only immediate/chase permissions, disabled reason, confirmation list, chase warning,
  plan-change conditions, and safety copy.
- Added an always-present `data-trade-plan-skeleton` QA hook and visible `Scenario plan`
  heading, including a compact missing-contract fallback.
- Backend enum values are mapped only to neutral display copy; candidate status is display-only
  and does not imply immediate action.
- Numeric planning remains disabled. The eight known zone/trigger/stop/target/risk-reward fields
  are accepted only when the backend provides non-empty text; numbers and objects are ignored,
  and the frontend performs no calculation.
- Added contained, mobile-safe, neutral Scenario plan styling below the core Decision,
  Risk/Probability, Actionability, and Advisor information. Hard-gate visuals remain dominant.
- Updated frontend asset/build stamp to `ui-d1-5b-trade-plan-render`.

## Safety Boundaries

- No backend, schema, endpoint, database, calibration, score, probability, gate, resolver,
  prediction, or migration change.
- No new network request; the renderer uses the existing detail payload only.
- No numeric entry, stop, target, or risk/reward generation.
- Immediate action and chase are displayed as `No` only when the backend value is false;
  unexpected values display as unavailable.
- No direct database/service credential reference and no executable trading workflow.

## Verification

- Frontend static tests: PASS, 51 passed.
- Full pytest: PASS, 287 passed with 7 existing deprecation warnings.
- JavaScript syntax: PASS.
- Ruff: PASS.
- Forbidden-scope, secret, and full-article-body safeguards: PASS.
- Schema validation: PASS.
- Manual smoke: PASS; frontend asset stamp verified.
- Protected backend/schema/script/migration diffs: empty.
- Targeted plan-calculation, database, and trade/execution endpoint greps: empty.
- Wording grep reports only required, explicitly negated D1.4 Model Quality copy.

## Files

- Changed: `frontend/app.js`, `frontend/styles.css`, `frontend/index.html`,
  `tests/frontend/test_frontend_static.py`, `AI/05_HANDOFF.md`.
- Read but unchanged: project instruction/current-state/test-command docs,
  `src/crypto_probability_engine/detail/decision_synthesis.py`, and
  `schemas/response.schema.json`.
- `AI/03_CURRENT_STATE.md` was not edited because the task's strict allowlist permits only
  `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, and `CHANGELOG.md` documentation.

## User Summary / Next Step

The Detail view now explains the backend Scenario plan, why it is limited, what confirmation
is missing, and the mandatory safety notes without inventing a tradable level or instruction.
Next: Claude review, then deployment and browser DOM QA as a separate approved step.
## Wave 4D.3-Ops Phase 1 Handoff

- Branch: `codex/wave-4d3-ops-prediction-origin`.
- Adds migration `0007_prediction_origin.sql` and a shared exact prediction-origin contract.
- Existing analyses persist `USER_REQUESTED`; explicit controlled/scheduled origins are accepted
  only through the internal `analyze_request` keyword and never alter identity or response logic.
- Calibration and Quant V2 shadow validation filter to `USER_REQUESTED` by default and allow a
  future explicit cohort argument. Resolver behavior is unchanged for every origin.
- Release contract: `UCPE-W4D3-OPS-COHORT-20260622-A`, milestone
  `wave-4d3-ops-prediction-origin`; the frontend marker remains backend-driven.
- The migration has not been applied. Before Phase 2, inventory the six historical derivatives
  smoke prediction IDs/outcomes and complete a separately reviewed `CONTROLLED_SMOKE`
  classification or prove they cannot enter calibration.
- No cadence, workflow, derivatives activation, merge, push, deploy, or production mutation.

## Wave 4D.3-Ops Phase 2A.0 Handoff

- Branch: `codex/wave-4d3-ops-2a0-cadence-runtime`.
- Adds only deterministic closed-candle identity and synchronous persistence confirmation to the
  existing analysis service; normal callers remain unchanged.
- Persistence confirmation reuses the approved work projection, repository writes, ordering,
  parent-success gates, and immutable duplicate classifications.
- Release contract: `UCPE-W4D3-OPS-2A0-20260622-A`, milestone
  `wave-4d3-ops-2a0-cadence-runtime`.
- No collector or workflow exists, no evidence was generated, no cadence is active, and the
  production derivatives flag remains false.
- A future coordinated deployment must sync the scheduler subtree and HF runtime, then confirm
  Ops-RT.1 is `HEALTHY`. Collector work remains a separate independent branch.
- Verification: 554 offline tests passed; Ruff, schemas, manual smoke, build-info, forbidden-scope,
  secret, full-article-body, protected-diff, and whitespace checks passed.
- Changed scope: analysis service, canonical build identity, focused API/release tests, and the
  four approved state/deployment documents. Read unchanged: persistence repositories and snapshot
  builders, derivatives runtime, API schemas/app, workflows, migrations, frontend, and scripts.
- Remaining risk: the synchronous helper depends on the existing in-process pending handoff and
  is intended for a later one-shot manual collector; no collector or cross-process contract exists
  in this phase.

## Wave 4D.3-Ops Phase 2D.1 Handoff

- Branch: `codex/wave-4d3-ops-2d1-cutover-guard`.
- Adds a pure internal cadence admission guard for v1 derivatives evidence and wires the existing
  manual collector to request `deriv-intel-okx-shadow-v1`.
- Guard constants keep the current approved source blocked: sentinel cutover close
  `2100-01-01T00:00:00Z`, `1H` window 300-1200 seconds post-close, and `4H` window 300-1800
  seconds post-close.
- Rejected methodology-cutover or outside-window preflight happens after deterministic analysis
  identity is known and before repository construction or persistence.
- Full four-cell v1 derivatives-provider budget is documented/tested as five logical OKX-only
  requests and five HTTP attempts; Binance request count is zero for the v1 derivatives path.
- No workflow change, production collector run, dry run, write run, Supabase access, HF access,
  migration, fingerprint change, persistence change, scheduler, cron, 4D.4, 4D.5, or Decision
  influence is included. Next step is Claude merge-readiness review of the source commit only.

## Wave 4D.3-Ops Phase 2D.2A Handoff

- Branch: `codex/wave-4d3-ops-2d2a-cadence-readiness-diagnostic`.
- Adds `scripts/measure_okx_cadence_readiness.py` for write-free, public-read-only OKX v1 cadence
  readiness measurement.
- Adds the manual-only `Derivatives Cadence Readiness Diagnostic` workflow; it has no schedule,
  no secrets, no database URL, and no collector invocation.
- The diagnostic measures OKX server time, latest closed candles, SWAP instruments, current
  funding, and current open interest for the fixed BTC/ETH 1H/4H matrix. Full-matrix bounds are
  five derivatives logical requests, four candle requests, one server-time request, and zero
  Binance requests.
- Sanitized output reports timing offsets, required metric presence, no-lookahead status, and
  final readiness classification only. It does not generate predictions, persist evidence, call
  Supabase, call Hugging Face, change runtime flags, or bypass the existing v1 cutover guard.
- Remaining blocked items: merge, tag, workflow dispatch, measurement run, collector dry run,
  `WRITE-EVIDENCE`, cron, 4D.4, 4D.5, deployment, and Decision influence.
