# Current State

Updated: 2026-06-20

## Branch / Worktree

- Branch: `codex/ui-d1-1-decision-synthesis`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy/push status: none performed
- Migration status: no migration added or run

## Current Phase

- Phase: UI-D1.1 backend decision-synthesis contract.
- Risk: additive, read-only response interpretation; no scoring, probability, gate,
  calibration, resolver, news-influence, persistence, endpoint, or frontend changes.
- Current status: implementation and local verification complete; not merged or deployed.

## What Changed

- Added a pure `build_decision_synthesis(...)` builder derived only from existing
  analysis output.
- Added the top-level `decision_synthesis` response block with decision label,
  probability interpretation, timeframe role, permissions, 12-step actionability
  stack, model-quality honesty, informational change conditions, advisor copy,
  disabled trade-plan skeleton, and shadow-only future hooks.
- Attached the block in `/v1/analyze`, declared it in `AnalysisResponse`, and added
  a strict JSON Schema shape.
- Added focused builder, invariant, wording, probability-math, timeframe, schema,
  purity, and API response tests.

## Hard Invariants

- `can_enter_now=false` and `can_chase=false` in every emitted synthesis.
- Entry, stop, target, trigger, chase, and risk/reward plan fields are always `null`.
- Candidate labels mean planning context only and never entry permission.
- Probability is informational-only under a hard gate or without measured reliability.
- Decision strength cannot exceed `MODERATE` unless in-payload reliability is `MEASURED`.
- `future_quant_v2_hooks` is `SHADOW_ONLY` with zero decision influence.
- Existing `profitability_claim=false` and `news_influence_frac=0.0` remain unchanged.
- No database read, write, endpoint, migration, frontend, or protected methodology change.

## Checks Run

- `PYTHONPATH=src python3 -m pytest tests/detail/test_decision_synthesis.py -q`:
  PASS, 19 passed with 2 existing-style `RefResolver` deprecation warnings.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 36 passed with 2 existing
  Starlette cookie deprecation warnings.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 241 passed with 6 deprecation warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with the existing
  `RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Protected working-tree diff: PASS, empty.
- Targeted greps: PASS; no forbidden-wording or mutation/news-influence hit exists,
  and every `can_enter_now` occurrence is false or a false assertion.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `schemas/response.schema.json`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/detail/decision_synthesis.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/detail/test_decision_synthesis.py`

## Files Read but Not Changed

- `AGENTS.md`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/04_TASK_BOARD.md`
- `AI/06_TEST_COMMANDS.md`
- `IMPLEMENTATION_SPEC.md`
- Existing detail, quant, feature, gate, score, schema-test, and fixture files used
  to map current response shapes and safety authority.

## Risks / Unknowns

- Current probabilities remain heuristic and uncalibrated; resolved-sample reliability
  is still insufficient.
- UI-D1.1 intentionally provides no numeric entry, invalidation, or target geometry.
- Frontend rendering of this backend block is intentionally deferred.

## Next Steps

1. Send the single commit and verification evidence to Claude for review.
2. After approval, merge normally; no deployment or migration is part of this task.
3. Scope a separate frontend task to render backend truth without recomputation.
