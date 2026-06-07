# Current State

Updated: 2026-06-07

## Branch / Worktree

- Branch: `codex/wave1-supabase-watchlist`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 1 Supabase persistence and watchlist foundation.
- Current status: implemented locally and offline checks pass; commit pending.
- Scope: optional backend persistence, idempotent migration, watchlist API/UI, docs, and tests.

## What Changed

- Added optional backend Supabase Postgres settings for `SUPABASE_DB_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`; all are repr/log safe.
- Added `migrations/0001_init.sql` with idempotent tables for watchlist, analysis run summaries, timeframe summaries, provider observations, and app events.
- Added `scripts/apply_migrations.py`; it requires the database URL from local env and never prints it.
- Added backend persistence repository layer:
  - `STATELESS` when no database URL is configured.
  - `OK` when configured database writes succeed.
  - `UNAVAILABLE` when database operations fail.
- Analysis now best-effort persists compact run/timeframe/provider summaries and still returns normally if persistence fails.
- Added `persistence_status` in debug-safe response data and detail debug-lite data.
- Added session-gated watchlist endpoints:
  - `GET /v1/watchlist`
  - `POST /v1/watchlist`
  - `DELETE /v1/watchlist/{symbol}`
- Added Watchlist frontend tab with add/remove/list, six-timeframe symbol view, structured Detail support, and browser storage fallback when persistence is not OK.
- Added `psycopg[binary]>=3,<4` to `requirements.txt`.
- Updated docs, release gate, deployment checklist, source matrix, changelog, memory, and test commands.

## What Was Not Changed

- No quant/scoring/gates/probability/news math changed.
- No provider adapter or public market-data behavior changed.
- No auth/session logic changed beyond adding session-gated watchlist routes.
- No Dockerfile/deployment logic changed.
- No frontend Supabase calls or Supabase values were added.
- No secrets, env files, API keys, or access values added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/wave1-supabase-watchlist`.
- `git status --short --untracked-files=all -- .`: PASS, only Wave 1 app-root files modified/untracked before commit.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py tests/api/test_watchlist_endpoints.py tests/persistence/test_persistence_foundation.py tests/frontend/test_frontend_static.py -q`: PASS, 25 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 102 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- First `PYTHONPATH=src python3 scripts/check_no_secrets.py`: FAIL, checker flagged safe `os.environ.get(...)` settings reads; checker updated to allow env reads while still denying real assignments.
- Second `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`: PASS, no output.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `IMPLEMENTATION_DECISIONS.md`
- `README.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `migrations/0001_init.sql`
- `requirements.txt`
- `scripts/apply_migrations.py`
- `scripts/check_no_secrets.py`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/config/settings.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/api/test_watchlist_endpoints.py`
- `tests/frontend/test_frontend_static.py`
- `tests/persistence/test_persistence_foundation.py`

## Current Blockers / Unknowns

- No implementation blocker remains.
- Supabase migration was not applied because no real database operation was requested.
- Supabase connectivity was not live-tested; unit tests use in-memory/mocked paths only.
- Claude/User review is still required before merge/deploy.

## Next Steps

1. Commit Wave 1 on `codex/wave1-supabase-watchlist`.
2. Claude/User reviews the persistence/watchlist foundation.
3. If approved, apply migrations in Supabase and then merge/deploy through the normal release gate.
