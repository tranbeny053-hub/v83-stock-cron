# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4b3-calibration-metrics`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4B.3 adds read-only calibration metrics and sample gates over immutable prediction/outcome pairs.
No API route, frontend, schema-response, migration, quant/probability/score/gate/news/provider/auth/dependency, or resolver-labeling changes were made.
No migrations were added or run by Codex.

## Latest App State
Full local verification passes.
Calibration reporting is service/CLI-first through `scripts/calibration_report.py`.
The repository calibration method is SELECT-only and joins `public.predictions` to `public.prediction_outcomes`.
Metrics include Brier score, multiclass log loss, top-label hit rate, reliability buckets, outcome distribution, directional-subset hit rate, and terminal-return diagnostics.
Sample gates are diagnostic only: `NO_SAMPLES`, `INSUFFICIENT_SAMPLE`, `WARMING_UP`, `PRELIMINARY_MEASURED`, and `MEASURED`.
Version-mix warnings and versions-present metadata are included when reports pool multiple model or methodology versions.
Calibration service/CLI use DB-first operator repository selection when `SUPABASE_DB_URL` exists, even if Supabase REST secrets also exist.
Reliability-bucket `calibration_gap` is signed as `avg_predicted_max_prob - empirical_hit_rate`.
Calibration/reliability/profitability/news influence remain unchanged and are not written back.

## Implemented Components
- calibration package: `metrics.py`, `service.py`, `schemas.py`, and package init.
- persistence: `fetch_resolved_prediction_outcomes_for_calibration(...)` added to protocol, in-memory, and direct Postgres repositories.
- CLI: `scripts/calibration_report.py` with JSON default and text output.
- tests: exact Brier/log-loss fixtures, tie-break, bucket boundaries, invalid rows, sample gates, per-timeframe isolation, version mixing, repository SELECT-only SQL, and CLI behavior.

## Files Changed By Area
- calibration: `src/crypto_probability_engine/calibration/__init__.py`, `metrics.py`, `schemas.py`, `service.py`
- persistence: `src/crypto_probability_engine/persistence/repository.py`
- scripts: `scripts/calibration_report.py`
- tests: `tests/calibration/test_metrics.py`, `tests/calibration/test_service.py`, `tests/calibration/test_calibration_report.py`, `tests/persistence/test_persistence_foundation.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `IMPLEMENTATION_DECISIONS.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
- Calibration reads default to `p.is_live_data = true`, `o.is_live_data = true`, and `realized_label IN ('UP','DOWN','TIMEOUT')`.
- Direct Postgres calibration reads use the existing direct connection and literal `SET LOCAL statement_timeout` helper; no fake fallback is used.
- Supabase REST calibration read is intentionally not implemented for Wave 4B.3.
- Operator/reporting repository selection is DB-first: `SUPABASE_DB_URL` -> `SUPABASE_POSTGRES`, else Supabase REST, else in-memory.
- Probability rows are invalid if missing, non-finite, out of `[0,1]`, sum <= 0, or label is outside `UP/DOWN/TIMEOUT`.
- Valid probabilities are normalized only for diagnostic metric calculation.
- Top-label tie-break is deterministic: `UP > DOWN > TIMEOUT`.
- Reliability buckets are `0.00-0.40`, then 0.10-wide buckets through `0.90-1.00`; bucket count under 30 is `LOW_BUCKET_SAMPLE`.
- Sample gates are counts-only and diagnostic: 0 `NO_SAMPLES`, <100 `INSUFFICIENT_SAMPLE`, 100-299 `WARMING_UP`, 300-499 `PRELIMINARY_MEASURED`, >=500 `MEASURED`.
- Terminal return diagnostics are explicitly labelled not trade EV.
- Calibration/reliability/profitability status remains unchanged: `DEFAULT_PHASE1A`, `INSUFFICIENT_SAMPLE`, `false`.
- `news_influence_frac` remains `0.0`.

## Commands Run And Results
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

## Known Blockers
No implementation blocker is known.

## Open Risks
Calibration API/UI exposure is intentionally not implemented.
Supabase REST calibration read is intentionally not implemented; use direct Postgres for operator reports.
Calibration diagnostics do not promote reliability, confidence, accuracy, or profitability.

## Next Recommended Steps
1. Send this branch/report to Claude for Wave 4B.3 review.
2. If approved, merge normally; no migration/deploy step is part of this branch.
3. Run `PYTHONPATH=src python3 scripts/calibration_report.py --timeframe 15m --limit 100 --format json` in an operator environment with direct DB access when a real report is needed.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit secrets or env files.
Do not run migrations from Codex.
Do not add calibration API/UI, response schema fields, endpoints, migrations, dependencies, or trading capability.
Do not change quant/probability/score/gate/news/provider/auth/frontend/resolver-labeling logic for Wave 4B.3.
