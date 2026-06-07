# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 1 targeted fixes: make Supabase persistence non-blocking, add circuit breaker/pool, and prove the persistence failure path. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave1-supabase-watchlist` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 persistence/runtime behavior. Analysis math, scoring, gates, news authority, provider adapters, auth internals, Docker, and deployment behavior were not changed.

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

## Files Read But Not Changed
- `IMPLEMENTATION_DECISIONS.md`
- `DEPLOYMENT_CHECKLIST.md`
- `src/crypto_probability_engine/config/settings.py`
- `tests/frontend/test_frontend_static.py`
- `scripts/check_no_secrets.py`

## Commands Run
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

## What Works Now
- Analyze responses are no longer blocked by Supabase writes.
- FastAPI `BackgroundTasks` schedules a quick submit operation only.
- The actual persistence work runs in a bounded `ThreadPoolExecutor`.
- Background work receives compact rows only: run summary, timeframe summary, provider observations.
- Immediate in-memory run store is preserved for Detail endpoints.
- Supabase repository uses a small `ConnectionPool` and disables prepared-statement reliance with `prepare_threshold=None`.
- First DB failure opens circuit; open circuit skips DB attempts immediately.
- Watchlist endpoints use fallback state quickly when Supabase is unavailable.
- Failure-path tests prove analyze returns 200 with `persistence_status=UNAVAILABLE` and no exception leak.

## What Is Still Broken / Unknown
- Supabase migration was not applied in a live project.
- Supabase connectivity was not live-tested.
- Browser visual smoke for Watchlist was not run.
- No merge/deploy/push was performed.

## Next 3 Steps
1. Commit targeted fix on `codex/wave1-supabase-watchlist`.
2. Claude/User reviews; if approved, apply migrations in Supabase.
3. Merge/deploy only through the release gate after approval.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not add Binance/OKX private/authenticated calls or live news fetching.
- Do not change backend quant/scoring/gates/news/provider behavior as part of Wave 1 fixes.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Fix này làm phần lưu Supabase chạy nền, nên nút Analyze không phải chờ database. Nếu Supabase lỗi, hệ thống mở “cầu dao” tạm thời để bỏ qua DB nhanh và app vẫn trả kết quả phân tích bình thường. Chưa deploy, chưa merge, và không thêm secret nào.
