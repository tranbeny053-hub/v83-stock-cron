# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4B.3 Read-Only Calibration Metrics: compute diagnostic calibration metrics and sample gates from immutable prediction/outcome pairs through service/CLI only.

## Current Branch / Worktree
`codex/wave4b3-calibration-metrics` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
Diagnostic read-only service/CLI plus one SELECT-only persistence read method. Review before merge/deploy.

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

## Commands Run
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

## What Works Now
- Calibration metrics are computed from already-resolved prediction/outcome rows only.
- Repository calibration read joins `public.predictions p` with `public.prediction_outcomes o` and is SELECT-only.
- CLI defaults to JSON output and exits `0` for diagnostic states such as `NO_SAMPLES` or `INSUFFICIENT_SAMPLE`.
- Operational CLI/repository failures exit nonzero without printing secrets.
- Metrics include Brier score, multiclass log loss, top-label hit rate, reliability buckets, outcome distribution, directional subset hit rate, and terminal-return diagnostics.
- Sample gates are per requested report scope and never write back to model status fields.
- Version-mix warnings and versions-present metadata are reported when pooled rows cross model or methodology versions.
- Calibration service/CLI use DB-first operator repository selection when `SUPABASE_DB_URL` exists, even if Supabase REST secrets also exist.
- Reliability-bucket `calibration_gap` is signed: positive means overconfident, negative means underconfident.

## What Is Still Unknown
- Calibration API/UI exposure and `/v1/calibration` are intentionally not implemented.
- Supabase REST calibration read is intentionally not implemented; use direct Postgres for operator reports.
- Calibration diagnostics do not promote reliability, confidence, accuracy, or profitability.

## Next 3 Steps
1. Send this branch/report to Claude for Wave 4B.3 review.
2. If approved, merge normally; no migration/deploy step is part of this branch.
3. Run `PYTHONPATH=src python3 scripts/calibration_report.py --timeframe 15m --limit 100 --format json` in an operator environment with direct DB access when a real calibration report is needed.

## Do Not Change
- Do not touch API routes, response schemas, frontend, quant/probability/score/gates/news logic, providers, auth, dependencies, migrations, or resolver labeling.
- Do not run migrations from Codex.
- Do not add calibration API/UI, `/v1/calibration`, or prediction/outcome mutation.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not claim measured reliability, calibration, accuracy, or profitability.
