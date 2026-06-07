# Current State

Updated: 2026-06-07

## Branch / Worktree

- Branch: `codex/sprint2-live-market-data`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy

## Current Phase

- Phase: Sprint 2 final targeted fix pass.
- Claude verdict being addressed: latest `APPROVE_WITH_TARGETED_FIXES`.
- Current status: FIX-S2-5 applied; offline checks and volatile-symbol live smoke pass; commit next.

## Targeted Fix Applied

- FIX-S2-5: systematic `_frac` defect-class closure.
- Renamed unbounded magnitude fields:
  - `realized_vol_frac` -> `realized_vol`
  - `risk_pressure_frac` -> `risk_pressure`
  - `cvar_loss_frac` -> `cvar_loss`
- Kept strict `_frac` sentinel validation unchanged.
- Added high-volatility fixture and full-response recursive `_frac` bounds test.
- Kept `spread_frac`, `slippage_frac`, and `round_trip_cost_frac` only with bounded emission; invalid wide spread degrades before unsafe fraction output.

## What Exists Now

- Sprint 2 live public Binance/OKX market-data wiring remains in place.
- Live mode still does not silently substitute fixture data on failure.
- Fixture mode remains explicit only through `UCPE_DATA_MODE=fixture`.
- Unit tests remain offline with socket guard.
- Frontend data honesty remains backend-driven through `is_live_data` and `data_source`.
- No Binance/OKX API keys are required.
- No trading/order/withdraw/transfer/leverage/autonomous capability exists.
- No live news fetching exists.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `python3 --version`: PASS, Python 3.14.3.
- Required read-first docs/code scan: PASS.
- `PYTHONPATH=src python3 -m pytest tests/quant/test_quant_pipeline.py tests/api/test_analysis_live_data_wiring.py -q`: PASS, 18 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 83 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "realized_vol_frac\|risk_pressure_frac" src schemas tests || true`: PASS, no output.
- `grep -R "_frac" src/crypto_probability_engine schemas tests`: REVIEWED; remaining emitted `_frac` fields are true `[0,1]` fractions with tests.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R "apiKey\|api_key\|secretKey\|private endpoint\|signed endpoint" src/crypto_probability_engine/adapters tests || true`: PASS, no output.
- `grep -R "hashlib.sha256" src scripts tests || true`: PASS_WITH_NOTE; hits are analysis hash and session HMAC signing, not access-code hashing.
- `UCPE_LIVE_SMOKE_ENABLED=true UCPE_LIVE_SMOKE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT PYTHONPATH=src python3 scripts/live_smoke.py`: PASS; BTC/ETH/SOL, `METRICS_ONLY`/`NEWS_ADDON`, all `CROSS_PROVIDER`.

## Live Smoke Status

- Flag: `UCPE_LIVE_SMOKE_ENABLED=true`
- Symbols/modes: BTC/USDT, ETH/USDT, SOL/USDT; `METRICS_ONLY` and `NEWS_ADDON`
- Result: PASS
- `is_live_data`: true in all smoke responses
- `data_source`: `CROSS_PROVIDER` in all smoke responses
- Schema valid: yes
- Probability invariant: validated by response model
- `NEWS_ADDON` state: `UNAVAILABLE`
- Secret/body leak: no leak detected by smoke checks

## Files Changed

- `IMPLEMENTATION_DECISIONS.md`
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `RELEASE_GATE.md`
- `scripts/live_smoke.py`
- `src/crypto_probability_engine/execution_realism/realism.py`
- `src/crypto_probability_engine/features/liquidity_depth.py`
- `src/crypto_probability_engine/features/regime_2state.py`
- `src/crypto_probability_engine/features/volatility.py`
- `src/crypto_probability_engine/gates/composite.py`
- `src/crypto_probability_engine/quant/horizon_timeout.py`
- `src/crypto_probability_engine/quant/risk_arbiter.py`
- `src/crypto_probability_engine/quant/tail_cvar.py`
- `src/crypto_probability_engine/score_stack/score.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `tests/fixtures/market_data.py`
- `tests/quant/test_quant_pipeline.py`

## Current Blockers / Unknowns

- No final fix blocker remains.
- Merge still requires user/Claude approval.
- Deployment still requires pre-deploy checklist execution.
- External provider availability/rate limits remain an operational risk.
- Local interpreter is Python 3.14.3; Docker target remains Python 3.11.
- `jsonschema.RefResolver` deprecation warning remains non-blocking.

## Next Steps

1. Commit FIX-S2-5 on `codex/sprint2-live-market-data`.
2. Request user/Claude approval to merge.
3. If approved, run the pre-deploy checklist before any Hugging Face deploy.
