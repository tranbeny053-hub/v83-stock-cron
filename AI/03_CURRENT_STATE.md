# Current State

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
