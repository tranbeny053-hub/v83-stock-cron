# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4B.1 Prediction Ledger Foundation: write immutable live-analysis prediction rows at analysis time for future outcome resolution, without implementing resolver, calibration metrics, UI, endpoint, schema-response, or quant/news changes.

## Current Branch / Worktree
`codex/wave4b1-prediction-ledger` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
Persistence foundation. Review before merge/deploy and before applying migration.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `migrations/0003_prediction_ledger.sql`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `tests/persistence/test_persistence_foundation.py`

## Commands Run
- `git checkout dev`: PASS.
- `git status --short --untracked-files=all -- .`: PASS before branch creation, clean.
- `git checkout -b codex/wave4b1-prediction-ledger`: PASS.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/api -q`: PASS, 50 passed, 2 existing warnings.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 170 passed, 4 existing warnings.
- `ruff check src tests scripts`: PASS after import-order cleanup.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS; offline smoke and served frontend bundle guard passed.
- Protected working-tree diff for quant, score stack, gates, news, frontend, and `api/schemas.py`: PASS, empty.

## What Works Now
- `migrations/0003_prediction_ledger.sql` creates `predictions` idempotently with no destructive SQL.
- Live analysis with a valid closed-candle anchor builds a compact prediction row.
- Fixture/non-live analysis skips prediction ledger writes.
- Missing reference anchor skips prediction ledger writes.
- `save_prediction` is immutable/idempotent by `prediction_id` across in-memory, Postgres, and REST repositories.
- Prediction writes run through existing best-effort background persistence and do not change the response contract.
- Prediction write failure is caught by the persistence failure wrapper and does not break `/v1/analyze`.

## What Is Still Unknown
- Migration has not been applied.
- Future Wave 4B.2 outcome resolver and calibration metrics are not implemented.

## Next 3 Steps
1. Commit `feat: add prediction ledger foundation`.
2. Send to Claude for review before merge/deploy.
3. Apply `0003_prediction_ledger.sql` only after review and operator approval.

## Do Not Change
- Do not touch frontend, API response schemas, quant/probability/score/gates/news logic, providers, auth, dependencies, or migrations beyond `0003_prediction_ledger.sql`.
- Do not run migrations from Codex.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not claim measured reliability, calibration, accuracy, or profitability.
