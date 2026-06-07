# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 1.1 stabilization hotfix: fix 1D/1W live provider disagreement usability, add visible Re-analyze, surface persistence status, and clarify Dev Mode disabled/configured UX. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave1-1-stabilization-hotfix` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2 provider-data validation/UI hotfix. Scoring, probability, gates, news authority, private provider calls, auth security semantics, Docker, and deployment behavior were not changed.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `src/crypto_probability_engine/adapters/mappers.py`
- `src/crypto_probability_engine/adapters/provider_selection.py`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/health.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `src/crypto_probability_engine/validation/market_data.py`
- `tests/adapters/test_provider_selection.py`
- `tests/adapters/test_public_market_adapters.py`
- `tests/api/test_auth_health.py`
- `tests/frontend/test_frontend_static.py`
- `tests/validation/test_market_validation.py`

## Files Read But Not Changed
- `DEPLOYMENT_CHECKLIST.md`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/config/settings.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/api/test_watchlist_endpoints.py`

## Commands Run
- `git branch --show-current`: PASS, `codex/wave1-1-stabilization-hotfix`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/validation -q`: PASS, 12 passed.
- `PYTHONPATH=src python3 -m pytest tests/adapters/test_provider_selection.py tests/adapters/test_public_market_adapters.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest tests/api/test_auth_health.py tests/frontend/test_frontend_static.py -q`: PASS, 22 passed, 1 warning.
- `PYTHONPATH=src python3 -m pytest tests/adapters -q`: PASS, 27 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 26 passed, 1 warning.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 112 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`: PASS, no output.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R "Refresh\|Re-analyze\|last refreshed\|persistence_status\|Watchlist persistence\|Dev Mode is disabled" frontend src tests || true`: PASS, expected UI/status implementation and test hits only; ignored `__pycache__` binary matches also appeared.
- `git diff -- .`: PASS, reviewed app-root diff.
- `git status --short --untracked-files=all -- .`: PASS, only expected modified app-root files before commit.

## What Works Now
- OKX 1D/1W candles map to UTC buckets (`1Dutc`, `1Wutc`).
- Provider coherence compares the latest common closed candle bucket, not blindly the latest provider row.
- Optional cross-provider mode (`UCPE_CROSS_PROVIDER_REQUIRED=false`) can return single-provider live analysis with explicit provider-state warning when providers disagree.
- Required cross-provider mode still blocks disagreement with `DATA_CONFLICT`.
- Provider state and Detail view show active provider, cross-provider state, fallback flag, disagreement bps, and reason.
- A visible app-shell `Re-analyze` button refreshes Single, Watchlist Symbol View, Batch, or status depending on active view.
- Refresh shows loading/disabled state, cooldown, and last refreshed timestamp.
- App shell, Watchlist, Detail, and system status now surface persistence status without secrets.
- Dev Mode disabled deployments show clear disabled copy and disable the re-auth controls.

## What Is Still Broken / Unknown
- Full required check suite passed locally.
- Manual deployed browser smoke was not run locally.
- Supabase can still report `UNAVAILABLE` until secrets/migrations/connectivity are correct.
- Optional single-provider fallback is intentionally less strong than coherent cross-provider data and is labeled.
- No merge/deploy/push was performed.

## Next 3 Steps
1. User/Claude reviews the hotfix.
2. Merge to `dev` only after approval.
3. Deploy only through the release gate after merge approval.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not add Binance/OKX private/authenticated calls or live news fetching.
- Do not silently fall back from live mode to fixture mode.
- Do not change backend quant/scoring/gates/news math as part of Wave 1.1.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Fix này làm app bớt “kẹt” ở khung 1D/1W: hệ thống so nến đã đóng cùng mốc thời gian, và nếu hai nguồn live vẫn lệch nhưng cấu hình cho phép, app sẽ dùng một nguồn live chính thức với cảnh báo rõ ràng thay vì báo lỗi trống. Giao diện cũng có nút Re-analyze, trạng thái lưu dữ liệu dễ thấy hơn, và Dev Mode sẽ nói rõ khi bị tắt.
