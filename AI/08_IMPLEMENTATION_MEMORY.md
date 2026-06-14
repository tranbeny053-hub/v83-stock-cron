# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4b1-prediction-ledger`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4B.1 adds immutable prediction ledger writes at analysis time.
This is foundation only: no resolver, no calibration metrics, no UI, no API response contract change.
No quant/probability/score/gate/news/provider/auth/frontend/dependency changes were made.
`migrations/0003_prediction_ledger.sql` exists but was not run by Codex.

## Latest App State
Full local verification passes.
Schema validation passes and the response contract is unchanged.
Prediction rows are written only for live data with a valid closed-candle reference price/time.
Fixture/non-live analyses skip prediction writes.
Persistence remains best-effort; failed prediction writes do not break `/v1/analyze`.

## Implemented Components
- migration: `migrations/0003_prediction_ledger.sql` idempotent `predictions` table and indexes.
- config: `MODEL_VERSION` and `METHODOLOGY_VERSION` constants added.
- persistence: `save_prediction(row)` added to protocol, in-memory, direct Postgres, and Supabase REST repositories.
- analysis service: compact prediction row derived from live snapshot and queued into existing background persistence work.
- tests: migration safety, immutable/idempotent repository writes, REST/Postgres non-overwrite semantics, live row content, non-live skip, missing-anchor skip, failure isolation.

## Files Changed By Area
- api: `src/crypto_probability_engine/api/analysis_service.py`
- persistence: `src/crypto_probability_engine/persistence/repository.py`
- config: `src/crypto_probability_engine/config/defaults.py`
- migrations: `migrations/0003_prediction_ledger.sql`
- tests: `tests/persistence/test_persistence_foundation.py`, `tests/api/test_analysis_live_data_wiring.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `IMPLEMENTATION_DECISIONS.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
- Prediction ID is `"{run_id}:{timeframe}"`.
- Prediction rows are immutable: Postgres uses `ON CONFLICT (prediction_id) DO NOTHING`; REST uses `resolution=ignore-duplicates`; in-memory keeps the first row.
- The ledger row is not added to `AnalysisResponse`; a run-id keyed internal pending map transfers it to the existing background persistence work.
- Reference anchor is the last closed candle from the selected live snapshot; if candles are missing, future-dated, non-live, or price is invalid, the ledger write is skipped.
- `horizon_end_utc = reference_close_utc + H_primary_bars * TIMEFRAME_SECONDS[timeframe]`.
- Calibration/reliability/profitability status remains unchanged: `DEFAULT_PHASE1A`, `INSUFFICIENT_SAMPLE`, `false`.
- `news_influence_frac` remains `0.0`.

## Commands Run And Results
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

## Known Blockers
No implementation blocker is known.
Final commit is still pending.

## Open Risks
Migration must be reviewed/applied separately by the user/operator.
Wave 4B.2 resolver must later use only post-prediction closed candles; it is not implemented here.
Ledger rows are useful for future calibration only after enough live samples accumulate.

## Next Recommended Steps
1. Commit `feat: add prediction ledger foundation`.
2. Send to Claude for review before merge/deploy.
3. Apply `migrations/0003_prediction_ledger.sql` only after review and operator approval.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit secrets or env files.
Do not run migrations from Codex.
Do not add resolver, calibration metrics, UI, response schema fields, endpoints, dependencies, or trading capability.
Do not change quant/probability/score/gate/news/provider/auth/frontend logic for Wave 4B.1.
