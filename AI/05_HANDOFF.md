# Handoff Packet

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
