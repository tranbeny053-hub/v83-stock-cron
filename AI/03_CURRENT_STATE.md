# Current State

Updated: 2026-07-13

## Phase 2D.2F Evidence-Backed Cadence Policy Freeze

- `CADENCE_POLICY_FREEZE_2D2F.md` records the six write-free OKX scheduler samples and ratifies
  the existing `cadence-cutover-okx-v1` values unchanged: 1H = 300-1200 seconds and 4H =
  300-1800 seconds after close.
- The activation sentinel remains `2100-01-01T00:00:00Z` as an intentional fail-closed lock.
- The direct 4H observations were approximately +3072 through +11167 seconds. No sample measured
  the 4H early edge near +300 to +400 seconds, so the 300-second 4H delay remains an inference and
  may not be tightened from this cohort.
- This phase adds a decision record and a test-only constant lock. It changes no runtime source,
  workflow, deployment, collector state, cadence classification, production data, or Decision
  influence.
- No production write is authorized. The next gate remains a separate Phase 2D.2G review for any
  activation or cutover decision.
- Offline verification: 15 focused cadence tests and 725 full-suite tests pass with the existing
  15 warnings; Ruff, schema, build-info, secret, forbidden-scope, article-body, manual-smoke, and
  whitespace checks pass.

---

## Ops-RT.1 Pinned HF Baseline and Deployment-Delta Advisory

- Q1 production intent now comes only from the committed, schema-versioned
  `ops/hf_runtime_baseline.json`; the current authorized pin is HF release 2A.0 at
  `30d4982903e6f44e063616bc3f03f334bd2544e2`.
- Manifest/schema failures are fail-closed as `PIN_MISSING` before any probe, while an observed
  HF `main` SHA mismatch is confirmed across the existing three-round evidence contract as
  `PIN_DRIFT`.
- HF critical blobs, live build identity, live frontend tokens, and live asset bytes are compared
  only with the pin. Scheduler checkout contents no longer define Q1 production intent.
- Q2 is a non-failing local advisory evaluated only after fully `HEALTHY` Q1 evidence. It reports
  the bounded governed-path delta and locally provable ahead count; shallow history requires no
  fetch and leaves the count unavailable.
- Scheduler source may advance without becoming HF production intent. Pin advancement requires a
  separate reviewed deployment authorization and a mechanically regenerated manifest.
- The current red guard was a baseline-model defect, not evidence of an HF production defect. No
  HF deployment or mutation occurred, and the workflow schedule, confirmation rounds, transport
  limits, and fail-closed classifications were not weakened.
- Cadence freeze remains a separate later gate. The cutover sentinel, cadence windows, 4D.4/4D.5,
  and Decision influence remain unchanged.
- Offline verification: 62 focused guard tests and 724 full-suite tests pass; Ruff, schema,
  build-info, secret, forbidden-scope, article-body, and manual-smoke checks pass.

---

Updated: 2026-06-23

## Wave 4D.3-Ops Phase 2D.0A Versioned Response + Selector Seam

- Branch: `codex/wave-4d3-ops-2d0a-versioned-response-and-selector`, based on
  `wave-4d3-ops-2b-okx-only-method-v1`.
- Implements a local internal-only `analyze_request` keyword selector for derivatives
  methodology version. Omitted callers remain on `deriv-intel-shadow-v0`.
- Adds strict version-aware API response validation for the historical two-provider v0 block and
  the OKX-only v1 block. V1 requires `deriv-intel.v1`,
  `deriv-intel-okx-shadow-v1`, and provider policy
  `deriv-provider-policy-okx-only-v1`.
- HTTP request models and FastAPI handlers remain unchanged; users cannot select the derivatives
  methodology through request JSON, query parameters, or headers.
- The collector remains unchanged and does not pass v1. Cutover guard, collection windows,
  workflow deployment, dry runs, writes, cron, 4D.4, 4D.5, and decision influence remain blocked.
- No build-info, persistence, migration, frontend, workflow, runtime provider, cadence identity,
  probability, score, gate, or Decision behavior changed.

---

## Wave 4D.3-Ops Phase 2B OKX-only Methodology v1

- Branch: `codex/wave-4d3-ops-2b-okx-only-method-v1`, based on the merged
  `wave-4d3-ops-binance-registry-diagnostic` milestone.
- Adds a local, explicit derivatives methodology contract:
  `deriv-intel-okx-shadow-v1` with schema `deriv-intel.v1` and provider policy
  `deriv-provider-policy-okx-only-v1`.
- Historical v0 remains representable as `deriv-intel-shadow-v0` / `deriv-intel.v0`
  with the two-provider Binance+OKX provider set.
- v1 collection requests only OKX SWAP current funding and current open interest. It does
  not call Binance, fabricate a Binance summary, or create cross-provider comparability.
- v1 remains `SHADOW_ONLY` with `decision_influence_frac = 0.0`, no normalization,
  no aggregation, no decision influence, no migration, and no workflow/runtime deployment.
- Current cadence identity still does not include derivatives methodology, so no production
  v1 evidence write is authorized before Phase 2D reviews identity and first-write semantics.

---

Updated: 2026-06-22

## Wave 4D.3-Ops Phase 2A Collector Foundation

- Branch: `codex/wave-4d3-ops-2a-collector-foundation`, based on the deployed
  `wave-4d3-ops-2a0-cadence-runtime` milestone.
- Added a dormant, manual-only collector CLI and `workflow_dispatch` workflow. There is no cron,
  recurring schedule, historical range, backfill, or catch-up loop.
- The collector defaults to disabled and dry-run. Write mode additionally requires the exact
  `WRITE-EVIDENCE` confirmation and the existing database URL contract.
- The fixed matrix contains BTC/ETH at 1H/4H only, with four-cell, four-prediction, and
  four-derivatives-snapshot circuit breakers.
- Analysis uses the deployed deterministic-identity primitive with origin
  `SCHEDULED_SHADOW_EVIDENCE`; persistence is delegated only to `persist_analysis_now`.
- The normal Hugging Face derivatives flag remains false. No runtime source, response schema,
  release fingerprint, migration, provider adapter, frontend, or existing workflow changed.
- No collector run or evidence generation has occurred. Next gate is Claude merge-readiness
  review before any GitHub-only deployment or manual dispatch.

---

Updated: 2026-06-22

## Ops-RT.1 Runtime Source/Serving Integrity Guard

- Branch: `codex/ops-rt1-source-integrity-guard`, based on `dev` at the merged Wave 4D.3 tag.
- Added a public-read-only three-round guard comparing source-controlled release identity,
  allowlisted HF `main` blobs, public build information, root asset tokens/marker, and exact live
  JavaScript/stylesheet hashes.
- Persistent divergence fails only when all three rounds agree on `STALE_RUNTIME`,
  `STALE_FRONTEND`, `SOURCE_DIVERGENCE`, or `CONTRACT_MISSING`. Transitioning and unavailable
  probes remain non-failing signals.
- The GitHub scheduler uses the existing subtree topology: this app's `.github/workflows` becomes
  repository-root `.github/workflows` on `tranbeny053-hub/v83-stock-cron`.
- The guard performs no authenticated request, analysis request, database access, workflow
  dispatch, deployment, restart, or mutation. Output is strictly allowlisted and contains no raw
  response bodies.
- No runtime source, frontend asset, schema, migration, release fingerprint, or existing workflow
  was modified.

---

Updated: 2026-06-22

## Wave 4D.3 Immutable Derivatives Evidence Snapshots

- Branch: `codex/wave-4d3-derivatives-snapshots`, based on the merged 4D.2 milestone.
- Added an unapplied additive migration for immutable prediction-linked derivatives snapshots.
- Eligible `ACTIVE`, `DEGRADED`, and `UNAVAILABLE` shadow blocks are projected through explicit
  nested allowlists; `DISABLED`, malformed, mismatched, or timestamp-inconsistent blocks are not
  persisted.
- Both the core prediction timestamp and the later derivatives observation timestamp are retained
  in dedicated columns and the immutable payload.
- First-write-wins storage distinguishes inserted rows, identical retries, conflicts, and
  repository unavailability without overwriting original evidence.
- RLS is enabled with no client policy. The server role receives only `SELECT` and `INSERT`, and
  database triggers reject update, delete, and truncate operations at the data plane.
- Snapshot construction occurs after response validation and identity finalization. Persistence is
  parent-gated after the prediction and existing Quant V2 feature snapshot paths; failures degrade
  persistence health but cannot fail core analysis.
- No validation, outcome join, backfill, frontend, provider-runtime, decision, Quant V2, resolver,
  or calibration behavior is added or changed.

## Wave 4D.3 Release Boundary

- Runtime fingerprint source is `UCPE-W4D3-DERIV-SNAPSHOT-20260622-A`.
- Migration `0006_prediction_derivatives_snapshots.sql` has not been applied.
- Next gate: Claude merge-readiness review before merge and before migration approval.

---

Updated: 2026-06-22

## Wave 4D.2 Derivatives Intelligence Shadow Runtime

- Branch: `codex/wave-4d2-derivatives-runtime`, based on `dev` at `87eb22c`.
- A required, default-OFF `derivatives_intelligence` response block is attached only after
  `analysis_hash`, prediction identity, and Quant V2 have been finalized.
- The block is `SHADOW_ONLY` with `decision_influence_frac=0.0`; it cannot affect probability,
  score, gates, decisions, permissions, Scenario Plan, persistence, resolver, or calibration.
- Enabled acquisition uses only current Binance USD-M and OKX SWAP public funding/open-interest
  resources. No historical or private resource is in the default runtime path.
- Process-local raw evidence uses a six-hour/two-entry registry cache, a 60-second/256-entry LRU
  symbol cache, and 64 fixed lock stripes for per-process single-flight.
- The nine-second budget is a new-call start deadline, not a hard completion cap. With a
  three-second request timeout and no retries, a cold path may finish near twelve seconds.
- `core_prediction_as_of_utc` preserves the market-snapshot prediction timestamp;
  `observation_as_of_utc` is captured honestly after derivatives fetching. Cached endpoint fetch
  timestamps are retained and request-specific provenance is rebuilt for each observation.
- Future 4D.3 work must retain both timestamps. Wave 4D.4 must not treat derivatives evidence as
  observed at the earlier core prediction timestamp.

## Wave 4D.2 Safety Boundary

- Feature flag: `UCPE_ENABLE_DERIVATIVES_INTEL`, default `false`.
- OFF returns before client construction, cache/lock access, registry lookup, or network activity.
- Provider failures and malformed payloads degrade only the derivatives block; core analysis
  remains valid.
- Funding remains signed. Negative quantity, contract, base-asset, USD, or USDT notional values
  become `INVALID_UNIT`; missing or non-finite values become `COMPUTE_ERROR`.
- Provider-native units remain separate. No averaging, magnitude threshold, or directional
  interpretation is introduced.

---

Updated: 2026-06-20

## Branch / Scope

- Branch: `codex/ui-d1-4b-calibration-metrics`
- Base: `dev` at merged UI-D1.4A milestone `e947ab3`
- Scope: frontend calibration rendering/static tests plus required handoff docs
- Status: implemented and locally verified; not merged, deployed, or pushed
- Migration status: none added or run

## UI-D1.4B Implementation

- Existing Decision section remains first and renders synchronously.
- Existing payload-only Model Quality summary and education layer remain intact.
- Model Quality now mounts a loading placeholder, then requests `GET /v1/calibration` once
  for the endpoint's all-timeframe response after Detail is rendered.
- Added a module-level 60-second cache for the full endpoint response and one shared
  in-flight request; safe unavailable responses are cached to prevent aggressive retries.
- Added backend-driven per-timeframe cards with dominant sample-gate badges, resolved and
  valid sample counts, reliability status, Brier score, log loss, diagnostic top-label hit
  rate, outcome distribution, version-mix warning, advanced version context, and warning.
- Null/non-numeric metrics render as an em dash; zero is shown only when supplied as a
  numeric backend value.
- Network, session, API, empty, and `UNAVAILABLE` states render a quiet heuristic fallback
  without exposing error details.
- Asset version is `ui-d1-4b-calibration-metrics`.

## Safety Invariants

- Frontend-only; no backend, schema, endpoint, calibration, scoring, probability, gate,
  resolver, outcome, prediction, migration, dependency, or secret change.
- Calibration fields are referenced only in the isolated diagnostics renderer; they never
  enter decision labels, permissions, candidates, gate actions, tactical alignment, or
  probability presentation.
- No timeframe samples are pooled and no timeframe borrows readiness from another.
- Hard gates and backend Decision remain authoritative.
- Diagnostic wording explicitly says not accuracy, not profitability evidence, and not EV.
- No direct database client, connection string, environment name, or credential is present
  in frontend code.
- Existing text-containment rules are extended to diagnostics cards and mobile layouts;
  important text is wrapped rather than clipped.

## Current Backend-Reported State

The renderer does not hardcode these values. With the currently observed endpoint payload,
it displays: `15m` 93 insufficient, `1H` 83 insufficient, `4H` 72 insufficient, `1D` 8
insufficient, `1W` 0 no samples, and `1M` 0 no samples. No timeframe is measured yet.

## Verification

- Frontend static tests: PASS, 44 passed.
- Full suite: PASS, 277 passed with 7 existing deprecation warnings.
- Bundled Node syntax check: PASS.
- Ruff: PASS.
- Forbidden-scope, secret, full-article-body, schema, and manual smoke checks: PASS.
- Manual smoke confirmed the versioned frontend bundle.
- Protected `src`, `scripts`, `migrations`, and `schemas` diffs: empty.
- Targeted unsafe-wording and frontend database/secret greps: empty.
- Accuracy grep contains only explicitly negated safety copy.
- Calibration field/fetch and version greps contain expected references.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/frontend/test_frontend_static.py`

## Files Read but Not Changed

- `AGENTS.md`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/04_TASK_BOARD.md`
- `AI/06_TEST_COMMANDS.md`
- `IMPLEMENTATION_SPEC.md`

## Risks / Next Step

- Diagnostics can be up to 60 seconds old by design; they remain informational only.
- An unavailable/expired session displays heuristic fallback and does not disturb Detail.
- Live endpoint rendering was not exercised with real credentials; static, full-suite, and
  offline smoke verification passed without secrets.
- Next: Claude reviews the single commit before merge/deployment.
## Wave 4D.3-Ops Phase 1 — Prediction-Origin Cohort Separation

- Runtime release source advances to `UCPE-W4D3-OPS-COHORT-20260622-A`.
- Predictions gain an immutable origin contract: `USER_REQUESTED`, `CONTROLLED_SMOKE`, or
  `SCHEDULED_SHADOW_EVIDENCE`; existing analysis callers default to `USER_REQUESTED`.
- Origin is ledger metadata only and does not enter analysis hash, prediction identity,
  probabilities, gates, decisions, Scenario Plan, Quant V2, or derivatives influence.
- Calibration and Quant V2 shadow validation default to `USER_REQUESTED`; outcome resolution
  remains origin-agnostic.
- Migration `0007_prediction_origin.sql` is source-only until separately reviewed/applied.
- Phase 2 stays blocked pending an inventory and explicit classification decision for the six
  historical derivatives smoke predictions and their outcome links.
- No cadence collector, scheduler, evidence generation, derivatives activation, or production
  mutation is part of this phase.

## Wave 4D.3-Ops Phase 2A.0 — Cadence Runtime Primitives

- Adds an opt-in deterministic identity mode derived from the canonical normalized symbol,
  timeframe, model/methodology versions, and latest validated closed-candle timestamp.
- Adds synchronous persist-and-confirm by reusing the existing persistence work builders,
  ordering, parent gates, and repository methods; no SQL or persistence implementation changes.
- Default analyses keep UUID run IDs and unchanged response/decision behavior.
- Release source advances to `UCPE-W4D3-OPS-2A0-20260622-A`.
- Runtime primitives only: no collector, workflow, cadence schedule, evidence generation,
  migration, or derivatives activation exists. The production derivatives flag remains false.
- Any later deployment requires coordinated scheduler-subtree source sync and HF deployment,
  followed by an Ops-RT.1 `HEALTHY` result.
- The Phase 2A collector remains a separate, later reviewed branch.

## Wave 4D.3-Ops Phase 2D.1 — v1 Cutover Guard Source State

- Local source adds a pure internal cadence admission guard and wires the manual collector to
  request `deriv-intel-okx-shadow-v1` through the existing `analyze_request` selector seam.
- v1 collection is still blocked by the provisional sentinel cutover close
  `2100-01-01T00:00:00Z`; current evidence attempts are expected to return
  `REJECTED_METHODOLOGY_CUTOVER` and perform no writes.
- Source collection windows are `1H` = 300 to 1200 seconds after the validated closed candle and
  `4H` = 300 to 1800 seconds after the validated closed candle.
- The collector remains manual-only, disabled by default, and non-writing unless all existing
  enable and confirmation gates pass; rejected preflight constructs no production repository.
- No workflow, scheduler, runtime API, persistence implementation, migration, build fingerprint,
  frontend, deployment, dry run, write run, 4D.4 evaluation, 4D.5 opening, or Decision influence
  is part of this local source state.

## Wave 4D.3-Ops Phase 2D.2A — OKX Cadence Readiness Diagnostic Source State

- Local source adds a write-free OKX cadence-readiness diagnostic and a manual-only diagnostic
  workflow for scheduler-runner measurement.
- The diagnostic probes only public OKX resources: server time, latest closed 1H/4H candles,
  SWAP instruments, current funding, and current open interest for the fixed BTC/ETH matrix.
- The full four-cell probe is bounded to five derivatives logical requests, four candle requests,
  one server-time request, and zero Binance requests.
- Output is sanitized readiness evidence only and contains no raw provider body, database row,
  secret, header, analysis payload, prediction, or persistence result.
- No collector change, cutover-guard change, runtime source change, persistence, migration,
  fingerprint bump, deployment, workflow dispatch, dry run, write run, cron, 4D.4, 4D.5, or
  Decision influence is part of this source state.
