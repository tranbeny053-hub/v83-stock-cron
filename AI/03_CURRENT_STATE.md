# Current State

Updated: 2026-06-20

## Branch / Worktree

- Branch: `codex/ui-d1-2-decision-tab`
- Base branch: `dev` at merged UI-D1.1 milestone `d2046e9`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope: frontend rendering and frontend static tests only, plus handoff docs
- Merge/deploy/push status: none performed
- Migration status: no migration added or run

## Current Phase

- Phase: UI-D1.2 Decision section frontend rendering.
- Risk: frontend-only presentation of existing backend truth; no backend, schema,
  endpoint, methodology, persistence, dependency, or navigation-flow change.
- Current status: implementation and local verification complete; not merged or deployed.

## What Changed

- Added `renderDecisionSynthesis(...)` as the first block in the shared structured
  Detail view used by single, batch, and watchlist results.
- Added a five-second summary card with the backend label, strength, explanation,
  primary reason, next action, and explicit `No / Plan only-or-Observe only / No`
  permissions.
- Added backend-driven actionability, risk, probability, timeframe, advisor,
  reliability, disabled plan, and shadow-only future-context rendering.
- Added safe missing-contract fallback to the existing `decision_brief` without
  probability, gate, permission, or zone inference.
- Preserved every existing Detail/evidence section and added no navigation tab or
  analyze flow.
- Bumped frontend asset query versions so the new renderer and styles are not hidden
  by an older browser cache.

## Safety Invariants

- Frontend reads `payload.decision_synthesis`; it does not create a decision label.
- Primary reason comes only from ordered backend `BLOCK`/`WARN` stack items, then
  backend source fields.
- Entry-now and chase display `No` only for backend `false`; any other value displays
  `Unavailable`, never an affirmative permission.
- Candidate labels display as plan-only and never use standalone action wording.
- Null entry, trigger, invalidation, target, chase, and risk/reward fields are never read
  or rendered.
- Probability is secondary and visibly muted when backend `informational_only=true`.
- 1W/1M raw probability uses the backend hide-by-default flag and renders collapsed.
- Hard-gate and tail-risk `BLOCK` rows visually dominate.
- Quant V2 is advanced context only and renders backend shadow-only/zero influence.

## Checks Run

- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`:
  PASS, 25 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 248 passed with 6 existing
  deprecation warnings.
- `ruff check src tests scripts`: PASS.
- Bundled Node syntax parse of `frontend/app.js`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with the existing
  `RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Local visual QA: PASS for normal `WATCH` and hard-gated `NO_TRADE` fixtures.
- Protected working-tree diffs for `src`, `scripts`, `migrations`, and `schemas`: empty.
- Targeted unsafe-wording and client-inference greps: empty.
- Contract-reference grep: PASS with hits for all required synthesis blocks.

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
- `src/crypto_probability_engine/detail/decision_synthesis.py`
- `schemas/response.schema.json`

## Risks / Unknowns

- Current probabilities remain heuristic and uncalibrated; the UI presents them as
  secondary informational context.
- Numeric trade-plan geometry remains intentionally unavailable.
- The existing D1.1 model-quality explanation key is `warning`; the renderer also
  supports a future backend `plain_english` value without requiring it.

## Next Steps

1. Send the single commit and verification evidence to Claude for review.
2. After approval, merge normally; deployment and migrations are not part of this task.
3. Keep future Decision UI changes backend-contract-driven and separately scoped.
