# Handoff Packet

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
