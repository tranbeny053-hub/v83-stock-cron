# Current State

Updated: 2026-06-08

## Branch / Worktree

- Branch: `codex/wave2a-market-data-v2`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 2A Symbol Universe and Official Market Data v2.
- Current status: implementation complete; final offline tests, safety checkers, schema validation, manual smoke, and targeted greps passed.
- Scope: public Binance/OKX spot REST symbol universe, ticker/trade resource collection, provider observability, advisory derived market metrics, detail/frontend rendering, tests, and docs.

## What Changed

- Added public symbol-universe resolution for USDT spot pairs from Binance `exchangeInfo` and OKX `public/instruments`.
- Relaxed static base-symbol normalization so arbitrary valid USDT aliases can be resolved by live provider universe.
- Added symbol availability labels: `BOTH_PROVIDERS`, `BINANCE_ONLY`, `OKX_ONLY`, `UNSUPPORTED`, and `TO_VERIFY`.
- Expanded Binance public REST adapter to collect ticker and recent trades in addition to klines/depth.
- Expanded OKX public REST adapter to collect ticker and recent trades in addition to candles/books.
- Added compact provider resource status metadata for candles/depth/ticker/trades availability, latency, and freshness.
- Added advisory derived metrics from real public data only: spread bps, mid price, depth imbalance, shallow slippage estimate, recent trade pressure, freshness age, and cross-provider disagreement.
- Added `Market Data v2 / Provider Observability` to structured Detail Analysis.
- Watchlist live-mode add now validates symbol support through the symbol universe; delete remains permissive so delisted symbols can be removed.

## What Was Not Changed

- No quant/scoring/gates/probability/news math changed.
- No News Authority Engine, calibration, Market Data WebSocket, deployment automation, or Docker change was implemented.
- No Binance/OKX private/authenticated endpoint or API key was added.
- No frontend Supabase calls or Supabase values were added.
- No live news fetching was added.
- No secrets, env files, API keys, service role values, or access values added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git checkout -b codex/wave2a-market-data-v2`: PASS, branch created from clean `dev`.
- `git branch --show-current`: PASS, `codex/wave2a-market-data-v2`.
- `git status --short --untracked-files=all -- .`: PASS, only Wave 2A app-root changes present before commit.
- `python3 --version`: PASS, Python 3.14.3.
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

## Current Blockers / Unknowns

- No local implementation blocker is known after final offline verification.
- Live deployed smoke for arbitrary symbols and provider-resource observability is not run by Codex.
- Public provider availability/rate limits and symbol-list freshness remain operational risks.
- Derived market metrics are advisory metadata only and remain non-binding.

## Next Steps

1. User/Claude reviews the `codex/wave2a-market-data-v2` branch before merge/deploy.
2. After approval, merge from the app root worktree only.
3. Deploy only after approval, from `v8-crypto-api-clean/`, not the parent repo.
