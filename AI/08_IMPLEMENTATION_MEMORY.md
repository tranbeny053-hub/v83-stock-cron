# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave2a-market-data-v2`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 2A expands public Binance/OKX REST market-data collection and symbol-universe validation.
The app remains analysis-only; no trading, private/signed exchange call, News Authority, calibration, WebSocket, or deploy work was added.
Provider observability and derived market metrics are advisory metadata only and do not affect score/probability/gates/news.
Targeted adapter/API/frontend/validation tests, full pytest, safety checkers, schema validation, manual smoke, and targeted greps passed.
No merge/deploy/push to Hugging Face has been performed by Codex.

## Latest App State
Default data mode remains live public Binance/OKX market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes remain `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
Symbol normalization now accepts arbitrary syntactically valid USDT spot aliases and defers live support to the provider universe.
Live symbol availability can be `BOTH_PROVIDERS`, `BINANCE_ONLY`, `OKX_ONLY`, `UNSUPPORTED`, or `TO_VERIFY`.
Provider-only live symbols are allowed only when `UCPE_CROSS_PROVIDER_REQUIRED=false`; otherwise they block.
Detail Analysis includes `Market Data v2 / Provider Observability`.
Persistence remains best-effort and non-blocking; provider observations stay compact.

## Implemented Components
- adapters: Binance/OKX public REST expansion for ticker, recent trades, and symbol universe.
- symbol universe: cached provider symbol support from Binance exchangeInfo and OKX instruments.
- market metrics: advisory formulas for spread, mid, depth imbalance, shallow slippage, recent trade pressure, freshness, and cross-provider disagreement.
- provider selection: filters providers by symbol availability and records provider resources/derived metrics in data quality.
- api/watchlist: live-mode add validates symbol support; delete remains permissive for cleanup.
- detail/frontend: renders backend-provided provider observability without recomputing.
- tests: offline mocked coverage for parsers, symbol universe, provider-only fallback/blocking, unsupported symbols, cache, derived metrics, API detail, watchlist, and frontend hooks.
- docs: source matrix, decisions, release gate, deployment checklist, changelog, current state, and handoff updated.

## Files Changed By Area
- adapters: `src/crypto_probability_engine/adapters/types.py`, `mappers.py`, `public_market.py`, `provider_selection.py`, `symbol_universe.py`, `market_metrics.py`
- api: `src/crypto_probability_engine/api/app.py`
- detail/frontend: `src/crypto_probability_engine/detail/builder.py`, `frontend/app.js`
- config/normalization: `src/crypto_probability_engine/config/defaults.py`, `src/crypto_probability_engine/config/settings.py`, `src/crypto_probability_engine/normalizers/symbols.py`
- docs: `IMPLEMENTATION_DECISIONS.md`, `docs/source_verification_matrix.md`, `DEPLOYMENT_CHECKLIST.md`, `RELEASE_GATE.md`, `CHANGELOG.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/adapters/test_market_data_v2_metrics.py`, `tests/adapters/test_provider_selection.py`, `tests/adapters/test_public_market_adapters.py`, `tests/adapters/test_symbol_normalization.py`, `tests/api/test_analysis_endpoints.py`, `tests/api/test_analysis_live_data_wiring.py`, `tests/api/test_watchlist_endpoints.py`, `tests/frontend/test_frontend_static.py`

## Important Decisions
Use official public REST endpoints only; no Binance/OKX API keys are required.
Symbol universe uses cached public metadata and avoids refetching while TTL is fresh.
Ticker/trades are optional observability resources; candles/depth remain required for analysis.
Derived metrics must include formula/status/source metadata and remain advisory unless a future reviewed phase explicitly wires them.
Frontend remains a thin renderer of backend JSON.
WebSocket, News Authority, calibration, private endpoints, and trading capability are out of scope.

## Commands Run And Results
- `git checkout -b codex/wave2a-market-data-v2`: PASS, branch created from clean `dev`.
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

## Known Blockers
No local implementation blocker is known after final offline verification.
No merge/deploy/push has been performed.

## Open Risks
Live deployed smoke for broader symbols and provider observability was not run by Codex.
Public provider rate limits, listings, and temporary source outages remain operational risks.
Symbol universe cache TTL may briefly lag listings/delistings.
Derived metrics are advisory and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter may differ from Docker Python 3.11.

## Next Recommended Steps
1. User/Claude reviews the `codex/wave2a-market-data-v2` branch before merge/deploy.
2. After approval, merge from the app root worktree only.
3. Deploy only after approval, from the app root `v8-crypto-api-clean/`, not the parent repo.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls, signed endpoints, API keys, WebSocket, or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change backend quant/scoring/gates/news math for Wave 2A.
Do not deploy or push to Hugging Face without explicit approval.
