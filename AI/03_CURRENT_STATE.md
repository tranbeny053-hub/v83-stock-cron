# Current State

Updated: 2026-06-14

## Branch / Worktree

- Branch: `codex/wave4b1-prediction-ledger`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face
- Migration status: `migrations/0003_prediction_ledger.sql` created but not run by Codex

## Current Phase

- Phase: Wave 4B.1 Prediction Ledger Foundation.
- Risk: persistence foundation; no resolver, calibration metrics, UI, or API response change.
- Current status: implementation complete, full local verification passed, not merged/deployed.

## What Changed

- Added idempotent `predictions` migration with immutable `prediction_id` primary key and lookup indexes.
- Added `MODEL_VERSION = "phase1a-wave4b0"` and `METHODOLOGY_VERSION = "heuristic-v1-wave4b0"`.
- Added `save_prediction(row)` to in-memory, direct Postgres, and Supabase REST repositories.
- Prediction rows are immutable/idempotent: in-memory does not overwrite, Postgres uses `ON CONFLICT (prediction_id) DO NOTHING`, REST uses `resolution=ignore-duplicates`.
- Analysis now derives a compact ledger row only for live data with valid closed-candle reference time and price.
- Prediction persistence uses the existing best-effort background persistence path and never mutates the API response payload.
- Added tests for migration safety, repository immutability/idempotency, REST/Postgres non-overwrite semantics, live analysis ledger write, non-live skip, missing-anchor skip, and failure isolation.

## Checks Run / Attempted

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

## Current Blockers / Unknowns

- No local implementation blocker is known.
- Migration was created but not applied.
- Wave 4B.2 resolver/outcome metrics are intentionally not implemented.

## Next Steps

1. Commit `feat: add prediction ledger foundation`.
2. Send this branch to Claude for review before merge/deploy.
3. Apply `migrations/0003_prediction_ledger.sql` only after review and operator approval.
