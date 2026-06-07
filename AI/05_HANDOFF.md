# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 1 implementation: optional Supabase persistence foundation and watchlist backend/frontend. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave1-supabase-watchlist` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 persistence and backend API foundation. Analysis math, scoring, gates, news authority, provider adapters, auth internals, Docker, and deployment behavior were not changed.

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

## Files Read But Not Changed
- `IMPLEMENTATION_SPEC.md`
- `src/crypto_probability_engine/persistence/run_store.py`
- `src/crypto_probability_engine/telemetry/events.py`
- `src/crypto_probability_engine/normalizers/symbols.py`
- `src/crypto_probability_engine/detail/frontend_display.py`
- `src/crypto_probability_engine/detail/builder.py`
- Existing tests under `tests/`

## Commands Run
- `git branch --show-current`: PASS, `codex/wave1-supabase-watchlist`.
- `git status --short --untracked-files=all -- .`: PASS, only Wave 1 app-root files modified/untracked before commit.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py tests/api/test_watchlist_endpoints.py tests/persistence/test_persistence_foundation.py tests/frontend/test_frontend_static.py -q`: PASS, 25 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 102 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- First `PYTHONPATH=src python3 scripts/check_no_secrets.py`: FAIL, false positive on safe settings env reads; checker updated.
- Second `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`: PASS, no output.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.

## What Works Now
- App can run without Supabase and returns `persistence_status=STATELESS`.
- If persistence write raises, analysis still returns 200 and reports `persistence_status=UNAVAILABLE`.
- Optional Supabase repository is selected only when `SUPABASE_DB_URL` exists.
- Compact run/timeframe/provider summaries are best-effort persisted.
- Migrations create `watchlist`, `analysis_runs`, `analysis_timeframe_results`, `provider_observations`, and `app_events`.
- Watchlist CRUD endpoints are session-gated and normalize symbols through the backend.
- Frontend Watchlist tab can add/remove/list symbols and open a six-timeframe watchlist symbol view.
- Watchlist detail cards reuse the structured Detail Analysis path.
- Frontend never references Supabase names or values.

## What Is Still Broken / Unknown
- Supabase migration was not applied in a live project.
- Supabase connectivity was not live-tested.
- Browser visual smoke for Watchlist was not run.
- No merge/deploy/push was performed.

## Next 3 Steps
1. Claude/User reviews Wave 1 persistence and watchlist implementation.
2. If approved, apply `migrations/0001_init.sql` in Supabase SQL Editor or run `PYTHONPATH=src python3 scripts/apply_migrations.py` with the database URL set only in the local shell.
3. Merge/deploy only after release gate approval and Hugging Face secrets are configured.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not add Binance/OKX private/authenticated calls or live news fetching.
- Do not silently fall back from live mode to fixture mode.
- Do not change backend quant/scoring/gates/news/provider behavior as part of Wave 1.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Wave 1 đã thêm nền tảng lưu trữ Supabase tùy chọn và tab Watchlist. Nếu chưa cấu hình Supabase, app vẫn chạy bình thường ở chế độ stateless và Watchlist có fallback trong trình duyệt. Chưa deploy, chưa merge, và không có secret nào được thêm vào repo.
