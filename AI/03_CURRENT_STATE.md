# Current State

Updated: 2026-06-07

## Branch / Worktree

- Branch: `codex/wave1-supabase-watchlist`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 1 targeted fixes after Claude `APPROVE_WITH_TARGETED_FIXES`.
- Current status: fixes implemented locally and checks pass; commit pending.
- Scope: non-blocking persistence scheduling, Supabase circuit breaker/pool, defensive failure-path tests, docs/memory.

## What Changed

- Analysis no longer performs DB writes inline.
- `POST /v1/analyze` and `POST /v1/analyze_batch` inject `BackgroundTasks`.
- Background task only submits compact `PersistenceWork` to a bounded `ThreadPoolExecutor`; it does not carry the full analysis payload.
- In-memory detail/run store remains immediate, so Detail endpoints work right after analysis.
- `SupabasePersistenceRepository` now uses a small `psycopg_pool.ConnectionPool`.
- Supabase repository circuit behavior:
  - first DB failure marks `UNAVAILABLE`;
  - circuit opens for 60 seconds;
  - calls during cooldown skip DB immediately and use fallback;
  - after cooldown one trial is allowed;
  - trial success closes circuit and status becomes `OK`; trial failure reopens it.
- Watchlist reads/writes update in-memory fallback and degrade quickly when the circuit is open.
- Added tests for non-blocking analyze, defensive persistence wrapper, circuit breaker transitions, and degraded watchlist response.
- Updated requirement to `psycopg[binary,pool]>=3,<4`.

## What Was Not Changed

- No quant/scoring/gates/probability/news math changed.
- No Binance/OKX provider adapter logic changed.
- No frontend Supabase calls or Supabase values were added.
- No auth/session logic changed beyond existing watchlist session gating.
- No Dockerfile/deployment logic changed.
- No secrets, env files, API keys, or access values added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/wave1-supabase-watchlist`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/persistence -q`: PASS, 4 passed.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py -q`: PASS, 9 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 106 passed, 3 warnings.
- `ruff check src tests scripts`: PASS after import-format fixes.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`: PASS, no output.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R "psycopg_pool\|ConnectionPool\|circuit" src tests requirements.txt || true`: PASS, source/test hits confirm pool and circuit code; generated ignored `__pycache__` binary matches also appeared.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `RELEASE_GATE.md`
- `requirements.txt`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/api/test_watchlist_endpoints.py`
- `tests/persistence/test_persistence_foundation.py`

## Current Blockers / Unknowns

- No implementation blocker remains.
- Supabase live connectivity was not tested.
- Browser visual smoke for Watchlist was not run.
- Claude/User review is still required before merge/deploy.

## Next Steps

1. Commit targeted fixes on `codex/wave1-supabase-watchlist`.
2. Claude/User reviews; if approved, apply migrations in Supabase.
3. Proceed through merge/deploy release gate only after approval.
