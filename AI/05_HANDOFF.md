# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 2A Symbol Universe and Official Market Data v2: expand public Binance/OKX REST market-data collection and provider observability. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave2a-market-data-v2` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 public market-data and observability expansion. Scoring, probability, gates, news authority, calibration, WebSocket, private provider calls, Docker, and deployment automation were not changed.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `frontend/app.js`
- `src/crypto_probability_engine/adapters/market_metrics.py`
- `src/crypto_probability_engine/adapters/mappers.py`
- `src/crypto_probability_engine/adapters/provider_selection.py`
- `src/crypto_probability_engine/adapters/public_market.py`
- `src/crypto_probability_engine/adapters/symbol_universe.py`
- `src/crypto_probability_engine/adapters/types.py`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/config/settings.py`
- `src/crypto_probability_engine/detail/builder.py`
- `src/crypto_probability_engine/normalizers/symbols.py`
- `tests/adapters/test_market_data_v2_metrics.py`
- `tests/adapters/test_provider_selection.py`
- `tests/adapters/test_public_market_adapters.py`
- `tests/adapters/test_symbol_normalization.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `tests/api/test_watchlist_endpoints.py`
- `tests/frontend/test_frontend_static.py`

## Files Read But Not Changed
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `AI/03_CURRENT_STATE.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `docs/source_verification_matrix.md`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/conftest.py`
- Binance official market-data-only docs
- OKX official API v5 public market-data docs

## Commands Run
- `git checkout -b codex/wave2a-market-data-v2`: PASS, branch created from `dev`.
- `PYTHONPATH=src python3 -m pytest tests/adapters -q`: PASS, 37 passed.
- `PYTHONPATH=src python3 -m pytest tests/validation -q`: PASS, 12 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 29 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 130 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Targeted private/signed/API-key grep over adapters and tests: PASS, no hits.
- Targeted forbidden-capability grep over implementation/test/schema paths: PASS, no hits.

## What Works Now
- `SOL`, `SOLUSDT`, `SOL/USDT`, `SOL-USDT`, and other valid USDT aliases normalize to canonical `BASE/USDT`.
- Live provider selection validates symbols against cached Binance/OKX public symbol universes.
- Availability is visible as `BOTH_PROVIDERS`, `BINANCE_ONLY`, `OKX_ONLY`, `UNSUPPORTED`, or `TO_VERIFY`.
- Provider-only symbols can analyze only when `UCPE_CROSS_PROVIDER_REQUIRED=false`, with explicit warning.
- Unsupported live symbols return a clear invalid-symbol error instead of crashing.
- Binance public adapter collects klines, depth, ticker, recent trades, and exchangeInfo.
- OKX public adapter collects candles, books, ticker, trades, and instruments.
- Data quality/detail now expose provider resources, latency, freshness, derived metrics, symbol availability, and cross-provider state.
- Derived metrics are advisory metadata only and do not affect score/probability/gates/news.
- Existing best-effort provider-observation persistence path remains non-blocking.

## What Is Still Broken / Unknown
- Final required offline safety command suite passed.
- Live deployed smoke for arbitrary symbols and provider observability was not run by Codex.
- Public provider availability/rate limits and symbol-list freshness remain operational risks.
- No merge/deploy/push was performed.

## Next 3 Steps
1. User/Claude reviews the `codex/wave2a-market-data-v2` branch before merge/deploy.
2. After approval, merge from the app root worktree only.
3. Deploy only after approval, from the app root `v8-crypto-api-clean/`, not the parent repo.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not add Binance/OKX private/authenticated calls, signed endpoints, API keys, WebSocket, or live news fetching.
- Do not silently fall back from live mode to fixture mode.
- Do not change backend quant/scoring/gates/news math as part of Wave 2A.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Wave 2A mở rộng dữ liệu thị trường chính thức: app có thể nhận nhiều mã USDT hơn, kiểm tra mã đó có trên Binance/OKX hay không, và hiển thị thêm chất lượng dữ liệu như độ sâu sổ lệnh, ticker, giao dịch gần đây, độ trễ, độ tươi, và spread. Đây chỉ là dữ liệu quan sát; app vẫn không có chức năng giao dịch và không dùng API key sàn.
