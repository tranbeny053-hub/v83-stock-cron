# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 1.2 Supabase runtime connectivity hotfix: make Hugging Face persistence use backend-only Supabase REST/PostgREST over HTTPS when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are configured. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave1-2-supabase-rest-runtime` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 persistence/runtime connectivity. Scoring, probability, gates, news authority, market-data provider behavior, frontend Supabase exposure, Docker, and deployment automation were not changed.

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

## Files Read But Not Changed
- `src/crypto_probability_engine/api/app.py`
- `frontend/app.js`
- `tests/api/test_watchlist_endpoints.py`
- `tests/conftest.py`
- `scripts/check_no_secrets.py`

## Commands Run
- `git checkout -b codex/wave1-2-supabase-rest-runtime`: PASS, branch created from `dev`.
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

## What Works Now
- Runtime selects `SUPABASE_REST` first when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are present.
- Runtime falls back to `SUPABASE_POSTGRES` only when REST secrets are absent and `SUPABASE_DB_URL` exists.
- Runtime falls back to `IN_MEMORY` when no persistence config exists.
- Supabase REST persistence uses backend-only `apikey` and `Authorization` headers.
- REST repository supports compact analysis run, timeframe result, provider observation, watchlist, recent-run, and get-run methods.
- REST failures return `UNAVAILABLE`, open the circuit, and analysis still returns normally.
- `/v1/system_status` reports repository type and persistence status without showing URL/key/DB details.
- Unit tests mock `httpx`; no real Supabase network/DB is required.

## What Is Still Broken / Unknown
- Full required offline check suite passed locally.
- Hugging Face runtime persistence still needs live smoke after secrets are configured.
- Supabase project API/RLS/table permissions can still affect live REST calls.
- No merge/deploy/push was performed.

## Next 3 Steps
1. Review and commit the Wave 1.2 diff when ready.
2. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in Hugging Face Secrets.
3. Redeploy/smoke only after approval; confirm `Persistence: OK`.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not add Binance/OKX private/authenticated calls or live news fetching.
- Do not silently fall back from live mode to fixture mode.
- Do not expose Supabase values to frontend/status/debug/logs.
- Do not change backend quant/scoring/gates/news math as part of Wave 1.2.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Fix này đổi đường lưu dữ liệu trên Hugging Face sang Supabase REST qua HTTPS, vì Hugging Face có thể không cho app gọi trực tiếp cổng Postgres `5432/6543`. Bạn sẽ cần đặt `SUPABASE_URL` và `SUPABASE_SERVICE_ROLE_KEY` trong Hugging Face Secrets. App vẫn không có chức năng giao dịch, và frontend không nhìn thấy key Supabase.
