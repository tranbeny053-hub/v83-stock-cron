# Current State

Updated: 2026-06-08

## Branch / Worktree

- Branch: `codex/wave1-2-supabase-rest-runtime`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 1.2 Supabase runtime connectivity hotfix.
- Current status: targeted implementation complete; full offline check suite passed after one test-only secret-scan syntax fix.
- Scope: backend-only Supabase REST persistence for Hugging Face runtime, repository selection priority, safe diagnostics, tests, and docs.

## What Changed

- Added backend-only `SupabaseRestRepository` using Supabase REST/PostgREST over HTTPS.
- Runtime persistence selection now prefers:
  - `SUPABASE_REST` when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` exist;
  - `SUPABASE_POSTGRES` when only `SUPABASE_DB_URL` exists;
  - `IN_MEMORY` when no persistence config exists.
- Direct Postgres via `SUPABASE_DB_URL` remains supported for migrations/local direct DB or non-HF runtime.
- REST persistence supports compact run summaries, timeframe summaries, provider observations, watchlist CRUD, recent runs, and get-run summary.
- REST persistence uses short timeout, best-effort behavior, circuit breaker, and in-memory fallback.
- `/v1/system_status` reports repository type without exposing Supabase URL, DB URL, host, username, password, or service role key.
- Docs now state Hugging Face runtime should use `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY`.

## What Was Not Changed

- No quant/scoring/gates/probability/news math changed.
- No Market Data v2, News Authority Engine, or calibration was implemented.
- No Binance/OKX private/authenticated endpoint or API key was added.
- No frontend Supabase calls or Supabase values were added.
- No live news fetching was added.
- No Dockerfile/deployment automation changed.
- No secrets, env files, API keys, service role values, or access values added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/wave1-2-supabase-rest-runtime`.
- `git status --short --untracked-files=all -- .`: PASS, only expected Wave 1.2 modified files.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/persistence -q`: PASS, 9 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 28 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 119 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: initially FAIL on fake test `supabase_*` keyword assignments; after test-only syntax fix, PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`: PASS, no output.
- `grep -R "service_role\|apikey\|Authorization" frontend || true`: PASS, no output.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R --exclude-dir=__pycache__ "SUPABASE_REST\|SupabaseRestRepository\|repository_type" src tests docs frontend || true`: PASS, expected backend/test/doc references only.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `IMPLEMENTATION_DECISIONS.md`
- `README.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `src/crypto_probability_engine/api/health.py`
- `src/crypto_probability_engine/config/settings.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/api/test_auth_health.py`
- `tests/persistence/test_persistence_foundation.py`

## Current Blockers / Unknowns

- No implementation blocker is known after the full offline suite.
- Live Hugging Face runtime smoke is not run by Codex.
- Supabase project REST/RLS/API settings can still affect live persistence after deployment.

## Next Steps

1. Review the Wave 1.2 diff and commit when ready.
2. User configures HF `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in Secrets.
3. Redeploy/smoke only after approval; confirm `Persistence: OK` in the app.
