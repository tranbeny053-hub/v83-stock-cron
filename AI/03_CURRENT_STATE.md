# Current State

Updated: 2026-06-07

## Branch / Worktree

- Branch: `codex/sprint3-ui-1m-timeframe`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy

## Current Phase

- Phase: Sprint 3 UI/timeframe polish.
- Claude verdict supplied by user: `SAFE_TO_IMPLEMENT`.
- Current status: implementation complete locally; full offline checks pass; commit next.

## What Changed

- Added `1M` to supported backend timeframes.
- Added monthly provider mappings:
  - Binance: `1M -> 1M`
  - OKX: `1M -> 1Mutc`
- Added `TIMEFRAME_SECONDS["1M"] = 30 * 24 * 60 * 60`.
- Added `MIN_HISTORY_BARS_BY_TIMEFRAME["1M"] = 24` and `min_history_for(timeframe)`.
- Wired timeframe-specific min-history into validation, provider selection, public adapter fetch limits, and epistemic sufficiency.
- Kept global `min_history_bars = 200` for sub-monthly timeframes.
- Kept trend timeframes unchanged: `{1H, 4H, 1D}`.
- Replaced Single Analysis primary timeframe dropdown with six progressive timeframe cards: `15m`, `1H`, `4H`, `1D`, `1W`, `1M`.
- Added `1M` to Batch Analysis dropdown.
- Replaced raw JSON as primary detail display with structured sections and collapsed raw JSON debug.
- Preserved frontend thin-renderer boundary; frontend static grep confirms no banned backend compute-key strings in `frontend/app.js`.

## What Was Not Changed

- No auth/security/session code changed.
- No provider HTTP client internals changed.
- No probability, scoring, gate, or news authority math changed.
- No `_frac` sentinel guard changed.
- No Dockerfile, deployment config, `.dockerignore`, `.gitignore`, secrets, or env files changed.
- No private/authenticated exchange call, live news fetching, or trading/order/withdraw/transfer/leverage/autonomous path added.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/sprint3-ui-1m-timeframe`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits only app-root allowed Sprint 3 files are modified.
- `python3 --version`: PASS, Python 3.14.3.
- Required read-first docs/code scan: PASS.
- Branch setup from `dev`: PASS, created `codex/sprint3-ui-1m-timeframe`.
- `PYTHONPATH=src python3 -m pytest tests/adapters/test_public_market_adapters.py tests/validation/test_market_validation.py tests/api/test_analysis_endpoints.py tests/quant/test_quant_pipeline.py tests/frontend/test_frontend_static.py -q`: PASS, 47 passed.
- First `ruff check src tests scripts`: FAIL, one E501 long test line; fixed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 91 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `rg -n '"1M"|1Mutc|MIN_HISTORY_BARS_BY_TIMEFRAME|min_history_for' ...`: PASS, expected config/mapping/test/frontend hits.
- `rg -n 'name="timeframe"|<option>1M</option>|timeframe-card-grid|renderStructuredDetail|raw-json|Debug / Raw JSON|Signal heat — not risk' frontend tests/frontend`: PASS.
- `rg -n 'p_up_frac|p_down_frac|p_timeout_frac|score_stack|trend_summary|news_influence_frac' frontend/app.js || true`: PASS, no output.
- `rg -n 'place_order|create_order|submit_order|cancel_order|withdraw|transfer_funds|leverage_set|auto_trade' src tests schemas .github || true`: PASS, no output.
- `rg -n 'APP_ACCESS_CODE_HASH|DEV_MODE_CODE_HASH|SESSION_SIGNING_KEY|API_KEY|PASSWORD|PRIVATE_KEY' frontend || true`: PASS, no output.
- `PYTHONPATH=src python3 scripts/live_smoke.py`: PASS/SKIP, live smoke gated off.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 7 passed after final frontend safety polish.
- Manual local browser UI smoke: NOT RUN; no visual browser run was performed in this pass. Static frontend checks and backend/API tests cover the requested UI contract.
- 1M live smoke: NOT RUN; `scripts/live_smoke.py` does not support timeframe targeting, per Sprint 3 optional-smoke rule.

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

## Current Blockers / Unknowns

- No code blocker remains for Sprint 3 offline verification.
- Manual browser UI smoke was not performed.
- Timeframe-targeted 1M live smoke was not run because the current script does not support timeframe selection.
- Existing OKX 1D/1W HK alignment mismatch remains a documented future item; Sprint 3 changed only 1M to `1Mutc`.
- Local interpreter is Python 3.14.3 while Docker target remains Python 3.11.
- `jsonschema.RefResolver` deprecation warning remains non-blocking.

## Next Steps

1. Commit Sprint 3 changes on `codex/sprint3-ui-1m-timeframe`.
2. Hand back to Claude/User for UI/timeframe review.
3. After approval, run any desired browser UI smoke before merge or pre-deploy.
