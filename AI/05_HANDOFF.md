# Handoff Packet

## From
Codex

## To
Claude / User

## Current Goal
Sprint 3 UI/timeframe polish. Add `1M` timeframe support, replace Single Analysis timeframe dropdown with six progressive timeframe cards, and make Detail Analysis structured/readable. Commit on `codex/sprint3-ui-1m-timeframe`, then seek Claude/User review. Do not merge or deploy.

## Current Branch / Worktree
`codex/sprint3-ui-1m-timeframe` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R1 UI polish plus R2 timeframe validation/min-history change. Auth/security/session, provider HTTP client internals, Docker/deployment, core quant/scoring/gate/news math, and `_frac` sentinel guard were not changed.

## Files Changed
- `IMPLEMENTATION_DECISIONS.md`
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `src/crypto_probability_engine/adapters/mappers.py`
- `src/crypto_probability_engine/adapters/provider_selection.py`
- `src/crypto_probability_engine/adapters/public_market.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/quant/epistemic_sufficiency.py`
- `src/crypto_probability_engine/validation/market_data.py`
- `tests/adapters/test_public_market_adapters.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/fixtures/market_data.py`
- `tests/frontend/test_frontend_static.py`
- `tests/quant/test_quant_pipeline.py`
- `tests/validation/test_market_validation.py`

## Files Read But Not Changed
- `IMPLEMENTATION_SPEC.md`
- `AI/07_DECISION_LOG.md`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/detail/frontend_display.py`
- `src/crypto_probability_engine/detail/builder.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `scripts/live_smoke.py`

## Commands Run
- `git branch --show-current`: PASS, `codex/sprint3-ui-1m-timeframe`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits only Sprint 3 app-root files modified.
- `python3 --version`: PASS, Python 3.14.3.
- Branch setup from `dev`: PASS, created `codex/sprint3-ui-1m-timeframe`.
- Required read-first docs/code scan: PASS.
- `PYTHONPATH=src python3 -m pytest tests/adapters/test_public_market_adapters.py tests/validation/test_market_validation.py tests/api/test_analysis_endpoints.py tests/quant/test_quant_pipeline.py tests/frontend/test_frontend_static.py -q`: PASS, 47 passed.
- First `ruff check src tests scripts`: FAIL, one E501 long test line; fixed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 91 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Targeted `1M` config/mapping/frontend grep: PASS.
- Frontend no-recompute grep over `frontend/app.js`: PASS, no output.
- Forbidden capability grep: PASS, no output.
- Frontend secret-marker grep: PASS, no output.
- `PYTHONPATH=src python3 scripts/live_smoke.py`: PASS/SKIP, `UCPE_LIVE_SMOKE_ENABLED` not true.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 7 passed after final frontend safety polish.
- Manual browser UI smoke: NOT RUN; visual browser interaction was not performed.
- 1M live smoke: NOT RUN; current live smoke script does not support timeframe targeting.

## What Works Now
- Backend accepts `timeframe="1M"` and returns schema-valid fixture-mode analysis in tests.
- Binance public monthly mapping is `1M`; OKX public monthly mapping is `1Mutc`.
- 1M validation and epistemic sufficiency use 24-candle minimum.
- Sub-monthly validation remains at the existing 200-bar default.
- Single Analysis has six progressive cards for `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
- Each Single Analysis card can fail independently without blanking all results.
- Batch Analysis can select `1M`.
- Detail Analysis is structured into readable sections, with raw JSON collapsed/debug-only.
- Static frontend no-recompute/no-secret checks pass.

## What Is Still Broken / Unknown
- No merge or deploy has been performed.
- Manual browser UI smoke was not performed.
- Timeframe-targeted 1M live smoke was not run because the current script does not support timeframe selection.
- Existing OKX 1D/1W HK alignment mismatch remains a future item and was not changed.
- Local interpreter is Python 3.14.3; Docker target is Python 3.11.
- Existing `jsonschema.RefResolver` deprecation warning remains non-blocking.

## Next 3 Steps
1. Commit Sprint 3 changes on `codex/sprint3-ui-1m-timeframe`.
2. Ask Claude/User for UI/timeframe review.
3. After review, run a browser UI smoke if desired before merge or pre-deploy.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not edit external source Markdown files.
- Do not commit `.env`, salts, codes, real hashes, signing keys, API keys, or env dumps.
- Do not add trading/order/withdraw/transfer/leverage/autonomous capability.
- Do not add private exchange calls, live news fetching, or live-to-fixture silent fallback.
- Do not change auth/security/session, Docker/deployment, provider HTTP client internals, core quant/scoring/gate/news math, or `_frac` sentinel guard.
- Do not merge or deploy without approval.

## Notes for Non-Coder User
Sprint 3 làm giao diện Single Analysis dễ đọc hơn: bây giờ một lần nhập coin sẽ hiện 6 khung thời gian cùng lúc, có cả `1M`. Trang Detail Analysis không còn bắt người dùng nhìn JSON thô trước; JSON chỉ nằm trong phần debug thu gọn. Ứng dụng vẫn chỉ phân tích, không có khả năng giao dịch.
