# Current State

Updated: 2026-06-07

## Branch / Worktree

- Branch: `codex/sprint2-live-market-data`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy

## Current Phase

- Phase: Sprint 2 targeted fix pass after Claude review.
- Claude verdict being addressed: `APPROVE_WITH_TARGETED_FIXES`.
- Current status: FIX-S2-1 through FIX-S2-4 applied; verification pass is complete; commit and Claude re-review next.

## Targeted Fixes Applied

- FIX-S2-1: renamed signed fields so negative live returns/signals are not rejected by `_frac` sentinel validation:
  - `primary_return`, `extended_return`, `alpha_signal`, `net_signal`, `directional_edge`
  - Values/math unchanged.
- FIX-S2-2: added down-market candles/snapshot fixture plus pipeline and `/v1/analyze` coverage for negative signed fields, schema validation, and probability invariant.
- FIX-S2-3: added `scripts/make_access_hash.py` for PBKDF2-HMAC-SHA256 access-code hash generation using local `UCPE_ACCESS_CODE_SALT`; docs now include non-coder deployment steps.
- FIX-S2-4: Binance/OKX adapters now request `min_history_bars + 5` candles, capped at Binance 1000 and OKX 300, before dropping in-progress/unconfirmed rows.

## What Exists Now

- Sprint 2 live public Binance/OKX market-data wiring remains in place.
- Unit tests remain offline with socket guard.
- Fixture mode remains explicit only through `UCPE_DATA_MODE=fixture`.
- Live mode still does not silently substitute fixture data on failure.
- Frontend data honesty remains backend-driven through `is_live_data` and `data_source`.
- No Binance/OKX API keys are required.
- No trading/order/withdraw/transfer/leverage/autonomous capability exists.
- No live news fetching exists.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits, only targeted in-project files changed/untracked.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/quant/test_quant_pipeline.py tests/api/test_analysis_live_data_wiring.py tests/scripts/test_make_access_hash.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 80 passed, 3 warnings.
- `ruff check src tests scripts`: initially FAIL on two line-length issues in new/edited scripts; PASS after wrapping.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "primary_return_frac\|extended_return_frac\|alpha_signal_frac\|net_signal_frac\|directional_edge_frac" src schemas tests || true`: PASS, no output.
- `grep -R "_frac" src/crypto_probability_engine schemas tests`: REVIEWED; remaining `_frac` fields are bounded fraction/probability/confidence/cost/risk fields.
- `grep -R "hashlib.sha256" src scripts tests || true`: PASS_WITH_NOTE; hits are analysis hash and session HMAC signing, not access-code hashing.
- `grep -R "APP_ACCESS_CODE_HASH\|DEV_MODE_CODE_HASH\|UCPE_ACCESS_CODE_SALT\|SESSION_SIGNING_KEY" README.md DEPLOYMENT_CHECKLIST.md RELEASE_GATE.md AI || true`: PASS, deployment docs mention required HF secrets.
- `UCPE_LIVE_SMOKE_ENABLED=true PYTHONPATH=src python3 scripts/live_smoke.py`: PASS; BTC/ETH, `METRICS_ONLY`/`NEWS_ADDON`, all `CROSS_PROVIDER`.

## Live Smoke Status

- Flag: `UCPE_LIVE_SMOKE_ENABLED=true`
- Symbols/modes: BTC `METRICS_ONLY`, BTC `NEWS_ADDON`, ETH `METRICS_ONLY`, ETH `NEWS_ADDON`
- Result: PASS
- `is_live_data`: true in all smoke responses
- `data_source`: `CROSS_PROVIDER` in all smoke responses
- Schema valid: yes
- Probability invariant: validated by response model
- `NEWS_ADDON` state: `UNAVAILABLE`
- Secret/body leak: no leak detected by smoke checks

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `README.md`
- `RELEASE_GATE.md`
- `scripts/live_smoke.py`
- `scripts/make_access_hash.py`
- `src/crypto_probability_engine/adapters/public_market.py`
- `src/crypto_probability_engine/features/trend_mtf.py`
- `src/crypto_probability_engine/quant/pipeline.py`
- `src/crypto_probability_engine/quant/probability_three_state.py`
- `src/crypto_probability_engine/quant/risk_arbiter.py`
- `src/crypto_probability_engine/score_stack/score.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `tests/fixtures/market_data.py`
- `tests/quant/test_quant_pipeline.py`
- `tests/scripts/test_make_access_hash.py`

## Current Blockers / Unknowns

- No targeted-fix blocker remains.
- Claude re-review is still required before merge/deploy.
- External provider availability/rate limits remain an operational risk.
- Local interpreter is Python 3.14.3; Docker target remains Python 3.11.
- `jsonschema.RefResolver` deprecation warning remains non-blocking.

## Next Steps

1. Commit targeted fixes on `codex/sprint2-live-market-data`.
2. Hand to Claude for re-review of signed schema fix, down-market coverage, live smoke pass, access hash helper, and HF variable/secret table.
3. Only after approval, discuss merge/deploy path separately.
