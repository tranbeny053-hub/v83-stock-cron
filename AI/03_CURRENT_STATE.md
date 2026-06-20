# Current State

Updated: 2026-06-20

## Branch / Scope

- Branch: `codex/ui-d1-4-fe-model-quality-polish`
- Base: `dev` at merged UI-D1.3 milestone `85d72c2`
- Scope: frontend rendering/static tests plus required handoff docs
- Status: implemented and locally verified; not merged, deployed, or pushed
- Migration status: none added or run

## UI-D1.4-FE Implementation

- Decision remains the first Detail section.
- A dedicated Model Quality section now appears immediately after Decision and before
  Overview/deep evidence.
- Model Quality reads only `decision_synthesis.model_quality_summary` and
  `probability_interpretation.reliability_warning` already present in the analyze payload.
- Calibration/reliability status and availability render when present. Resolved sample
  count, sample gate, Brier score, log loss, and top-label hit rate render only when the
  corresponding payload value is non-null.
- Missing metrics use honest not-measured/collecting-samples copy; no number is invented.
- Added a compact collapsible education layer for heuristic probability, insufficient
  samples, measured calibration, and the optional diagnostic metrics.
- Added containment rules for horizon cards, Decision cards, actionability rows,
  probability/model-quality blocks, key/value grids, tables, details, IDs, and long text.
- Asset version is `ui-d1-4-model-quality-polish`.

## Safety Invariants

- Frontend-only; no backend, schema, endpoint, database, methodology, or migration change.
- No calibration fetch or database client was added.
- Model Quality never changes or overrides the backend decision or hard gates.
- No decision, enter-now, chase, trade-zone, entry, stop, or target inference was added.
- Candidates remain plan-only; hard-gate dominance and informational-only probability
  remain unchanged.
- Important user-facing text wraps rather than being clipped; raw JSON retains scrolling.
- No reliability, correctness, profitability, or trading-edge claim is emitted.

## Verification

- Frontend static tests: PASS, 37 passed.
- Full suite: PASS, 260 passed with 6 existing deprecation warnings.
- Ruff: PASS.
- Forbidden-scope, secret, full-article-body, schema, and manual smoke checks: PASS.
- Manual smoke confirmed the versioned frontend bundle.
- Targeted unsafe-wording and frontend calibration/DB greps: empty.
- Protected backend/schema/script/migration diffs: empty.
- Responsive containment is covered by deterministic CSS/static assertions. The attempted
  synthetic in-app browser fixture was rejected by browser URL policy and was not bypassed.

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

- Current probabilities remain heuristic and calibration reliability is not established.
- Real per-timeframe calibration metrics still require a separately approved read-only
  backend plan; this frontend does not fabricate or fetch them.
- Next: Claude reviews the single commit; merge/deploy remain separate user-approved steps.
