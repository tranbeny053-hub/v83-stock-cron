# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4B.2 Outcome Resolver: resolve due immutable prediction-ledger rows into immutable `UP` / `DOWN` / `TIMEOUT` outcome rows using post-prediction closed candles only, without API, UI, calibration metric, schema-response, quant, gate, score, or news changes.

## Current Branch / Worktree
`codex/wave4b2-outcome-resolver` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
Standalone persistence/resolver foundation. Review before merge/deploy and before applying migration.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `migrations/0004_prediction_outcomes.sql`
- `scripts/resolve_outcomes.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/persistence/test_persistence_foundation.py`
- `tests/resolver/test_resolve_outcomes.py`

## Commands Run
- `git checkout dev`: PASS.
- `git status --short --untracked-files=all -- .`: PASS before branch creation, clean.
- `git checkout -b codex/wave4b2-outcome-resolver`: PASS.
- `PYTHONPATH=src python3 -m pytest tests/resolver -q`: PASS, 10 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 29 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/resolver tests/persistence -q`: PASS, 33 passed after operator-wiring fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 185 passed with 4 existing warnings after targeted fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 189 passed with 4 existing warnings after operator-wiring fix.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS; offline smoke and served frontend bundle guard passed.
- Protected working-tree diff for API, quant, score stack, gates, news, frontend, and `api/schemas.py`: PASS, empty.
- Targeted greps: PASS; resolver/API import grep empty; destructive prediction mutation grep has only migration test assertions; secret/full-body/forbidden capability greps show existing backend/test/checker names only and no new unsafe implementation.

## What Works Now
- `migrations/0004_prediction_outcomes.sql` creates `prediction_outcomes` idempotently with no destructive SQL.
- Repositories can fetch due live predictions with no existing outcome row.
- Repositories can save immutable prediction outcomes without overwriting existing outcomes.
- `scripts/resolve_outcomes.py` resolves due predictions in a standalone batch, isolates per-prediction failures, and never runs in `/v1/analyze`.
- Resolver filters out all candles with `close_time_utc <= reference_close_utc` before terminal return, max favorable, or max adverse calculations.
- Resolver skips unfinished horizons when no closed candle exists at or after `horizon_end_utc`.
- Resolver skips stale-window overshoots when the first available outcome candle is more than one timeframe after `horizon_end_utc`.
- Operator resolver now prefers `SUPABASE_DB_URL` direct Postgres when both direct DB and Supabase REST settings are present.
- CLI output includes safe `repository=...` and `limit=...` diagnostics without printing secrets.
- Outcome labels use frozen `decision_band_frac`, or fallback `2 * taker_fee_frac`.

## What Is Still Unknown
- Migration has not been applied.
- Bounded historical provider fetch was deferred to avoid widening the targeted fix; stale-window skip prevents wrong immutable labels.
- Outcome scheduling/cron, calibration metrics, UI/API display, and `/v1/calibration` are intentionally not implemented.

## Next 3 Steps
1. Commit `fix: prefer database repository for outcome resolver`.
2. Run `PYTHONPATH=src python3 scripts/resolve_outcomes.py --limit 10` with local operator env.
3. Apply `migrations/0004_prediction_outcomes.sql` only after approval.

## Do Not Change
- Do not touch API routes, response schemas, frontend, quant/probability/score/gates/news logic, providers, auth, dependencies, or migrations beyond `0004_prediction_outcomes.sql`.
- Do not run migrations from Codex.
- Do not add calibration metrics, resolver UI, `/v1/calibration`, or prediction mutation.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not claim measured reliability, calibration, accuracy, or profitability.
