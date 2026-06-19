# Current State

Updated: 2026-06-20

## Branch / Worktree

- Branch: `codex/ui-d1-3-tactical-matrix`
- Base branch: `dev` at merged UI-D1.2 milestone `a5b0ddd`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope: frontend rendering and frontend static tests only, plus handoff docs
- Merge/deploy/push status: none performed
- Migration status: no migration added or run

## Current Phase

- Phase: UI-D1.3 Tactical Horizon Matrix and Regime Context.
- Risk: frontend-only reorganization of stored six-timeframe payloads; no backend,
  schema, endpoint, methodology, persistence, dependency, or Detail-flow change.
- Current status: implementation and local verification complete; not merged or deployed.

## What Changed

- Reorganized single and watchlist six-timeframe results into an ordered Tactical
  Horizon Matrix (`15m`, `1H`, `4H`) and quieter Regime Context (`1D`, `1W`, `1M`).
- Group placement prefers backend `timeframe_role.tactical` and uses the approved
  timeframe sets only as fallback.
- Added horizon cards sourced from backend role, decision label, permissions,
  probability interpretation, actionability, and model-quality fields.
- Added prominent backend BLOCK banners and muted informational-only probability.
- Added a neutral tactical alignment state derived only from backend labels,
  actionability statuses, and reliability state.
- Added safe missing/errored timeframe cards and unavailable alignment until all three
  tactical payloads are resolved.
- Kept 1W/1M raw probability collapsed under `Advanced (uncalibrated context)` and
  kept Regime Context visually secondary.
- Preserved click-to-Detail behavior and the D1.2 Decision-first Detail renderer.
- Bumped frontend asset query versions to `ui-d1-3-tactical-matrix`.

## Safety Invariants

- Frontend does not create or infer a decision label, enter-now permission, chase
  permission, numeric risk, or trade-plan geometry.
- Tactical alignment never reads or compares probability values.
- Alignment states are limited to `blocked`, `aligned`, `mixed`, `insufficient`, and
  `unavailable`; copy is display-only and non-actionable.
- Entry-now/chase render `No` only for backend false; otherwise `Unavailable`.
- Candidate labels remain plan-only.
- Any backend BLOCK dominates the card; backend informational-only probability is muted.
- 1W/1M raw values are collapsed by backend hide-by-default state or safe fallback.
- Missing tactical payloads cannot borrow readiness from another timeframe.
- Numeric entry, trigger, invalidation, target, chase, and risk/reward fields are never
  read or rendered in matrix/regime cards.

## Checks Run

- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`:
  PASS, 32 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 255 passed with 6 existing
  deprecation warnings.
- `ruff check src tests scripts`: PASS.
- Bundled Node syntax parse of `frontend/app.js`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with the existing
  `RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Local visual QA normal fixture: PASS; ordered groups, six cards, six Detail buttons,
  `insufficient` alignment, and two collapsed 1W/1M advanced contexts.
- Local visual QA hard-gated fixture: PASS; `blocked` alignment, six BLOCK banners,
  six muted probability blocks, `No` entry/chase on every card, and no raw null.
- Protected working-tree diffs for `src`, `scripts`, `migrations`, and `schemas`: empty.
- Targeted unsafe-wording and client-inference greps: empty.
- Grouping/role/version grep: PASS with expected references.

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

## Risks / Unknowns

- Current probabilities remain heuristic and uncalibrated; tactical and regime cards
  render them as informational context only.
- Current reliability is insufficient, so the normal fixture appropriately reports
  tactical alignment as `insufficient` rather than promoting apparent agreement.
- Numeric plan geometry remains intentionally unavailable in Detail.

## Next Steps

1. Send the single commit and verification evidence to Claude for review.
2. After approval, merge normally; deployment and migrations are not part of this task.
3. Keep future matrix logic label/status-derived and separately scoped.
