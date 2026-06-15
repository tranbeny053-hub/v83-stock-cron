# Current State

Updated: 2026-06-15

## Branch / Worktree

- Branch: `codex/wave4b3-calibration-metrics`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face
- Migration status: no migrations added or run in Wave 4B.3

## Current Phase

- Phase: Wave 4B.3 Read-Only Calibration Metrics and Sample Gates.
- Risk: diagnostic-only service/CLI plus one SELECT-only persistence read method; no API route, UI, schema-response, migration, quant/news, or resolver-labeling change.
- Current status: implementation complete, full local verification passed, not merged/deployed.

## What Changed

- Added `src/crypto_probability_engine/calibration/` package with pure metric functions, report schemas, and service orchestration.
- Added Brier score, multiclass log loss, deterministic top-label hit rate, reliability buckets, outcome distribution, directional-subset hit rate, and terminal-return diagnostics.
- Added sample gates: `NO_SAMPLES`, `INSUFFICIENT_SAMPLE`, `WARMING_UP`, `PRELIMINARY_MEASURED`, and `MEASURED`.
- Added `fetch_resolved_prediction_outcomes_for_calibration(...)` as a SELECT-only repository read method joining immutable predictions to immutable outcomes.
- Added `scripts/calibration_report.py` with JSON default output and text output option.
- Added offline tests for metrics, sample gates, per-timeframe isolation, version-mix warnings, SELECT-only SQL, literal statement timeout, CLI behavior, and operational error handling.
- Added Claude targeted fix: calibration service/CLI use DB-first operator repository selection when `SUPABASE_DB_URL` exists, even if Supabase REST secrets also exist.
- Added Claude targeted fix: reliability-bucket `calibration_gap` is signed as `avg_predicted_max_prob - empirical_hit_rate`.
- Calibration diagnostics do not mutate predictions/outcomes and do not write back reliability, calibration, confidence, or profitability status.

## Checks Run / Attempted

- `git checkout dev`: PASS.
- `git status --short --untracked-files=all -- .`: PASS before branch creation, clean.
- `git checkout -b codex/wave4b2a-github-resolver-cron`: PASS.
- `git checkout -b codex/wave4b2-outcome-resolver`: PASS.
- `PYTHONPATH=src python3 -m pytest tests/resolver -q`: PASS, 10 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 29 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/resolver tests/persistence -q`: PASS, 33 passed after operator-wiring fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 36 passed after Postgres due-query fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 38 passed after direct Postgres due-fetch wrapper fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 40 passed after timeout-bind/outcome-write fix.
- `PYTHONPATH=src python3 -m pytest tests/calibration tests/persistence tests/resolver -q`: PASS, 66 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 222 passed with 4 existing warnings after targeted fix.
- `PYTHONPATH=src python3 scripts/calibration_report.py --timeframe 15m --limit 10`: PASS, JSON `NO_SAMPLES` diagnostic from `IN_MEMORY`.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS; offline smoke and served frontend bundle guard passed.
- Protected working-tree diff for frontend, API, `api/schemas.py`, quant, score stack, gates, news, and migrations: PASS, empty.
- Targeted greps: PASS; calibration package has no writes/status writebacks/trading verbs; no REST-first calibration builder usage; no absolute calibration gap; statement-timeout grep shows existing safe literal helper.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `scripts/calibration_report.py`
- `src/crypto_probability_engine/calibration/__init__.py`
- `src/crypto_probability_engine/calibration/metrics.py`
- `src/crypto_probability_engine/calibration/schemas.py`
- `src/crypto_probability_engine/calibration/service.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/calibration/test_calibration_report.py`
- `tests/calibration/test_metrics.py`
- `tests/calibration/test_service.py`
- `tests/persistence/test_persistence_foundation.py`

## Current Blockers / Unknowns

- No local implementation blocker is known.
- Calibration API/UI exposure is intentionally not implemented.
- Supabase REST calibration read is intentionally not implemented; CLI/operator diagnostics now prefer direct Postgres repository when `SUPABASE_DB_URL` is configured.
- Calibration metrics are diagnostic only and do not promote reliability, confidence, or profitability.

## Next Steps

1. Send this branch/report to Claude for Wave 4B.3 review.
2. If approved, merge normally; no migration or deployment step is part of this branch.
3. Run `PYTHONPATH=src python3 scripts/calibration_report.py --timeframe 15m --limit 100 --format json` in an operator environment with direct DB access when a real report is needed.
