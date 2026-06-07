# Implementation Memory

## Context-Resume Summary
Sprint 3 UI/timeframe polish is implemented on `codex/sprint3-ui-1m-timeframe`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
The branch was created from `dev` per user instruction.
Backend now supports `1M` monthly analysis with timeframe-specific min history.
Single Analysis now renders six progressive timeframe cards and structured detail sections.
Full offline pytest, ruff, safety scripts, schema validation, and manual smoke pass.
No merge, deploy, auth/security change, Docker change, quant/scoring/gate/news math change, secret, private exchange call, live news fetch, or trading path was added.
Next step is commit and Claude/User UI/timeframe review.

## Latest App State
Default data mode remains live public market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes are `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
`1M` uses approximate 30-day validation/freshness duration and requires 24 candles.
Sub-monthly timeframes still use the global 200-bar minimum.
Binance monthly mapping is `1M`; OKX monthly mapping is `1Mutc`.
Single Analysis submits six backend `/v1/analyze` calls, renders each card progressively, and isolates per-timeframe failures.
Batch Analysis still uses a dropdown and now includes `1M`.
Detail view is structured; raw JSON is collapsed under Debug / Raw JSON.
Live smoke remains gated and was not run with timeframe targeting because the current script does not support timeframe selection.

## Implemented Components
- api: unchanged except tests cover `/v1/analyze` with `timeframe="1M"`.
- adapters: 1M provider interval mappings and timeframe-specific fetch limits added; HTTP client internals unchanged.
- validation: `validate_candles`/`validate_market_snapshot` use `min_history_for()` when caller does not override.
- quant: epistemic sufficiency now reports timeframe-specific `min_history_bars`; quant/scoring/probability/gate math unchanged.
- news: unchanged; no live fetching.
- frontend: Single Analysis six-card grid, red-to-grey signal heat styling, structured detail sections, collapsed raw JSON, Batch `1M` option.
- config: `1M`, approximate monthly seconds, `MIN_HISTORY_BARS_BY_TIMEFRAME`, and `min_history_for()`.
- docs: Sprint 3 decision/source matrix/changelog/release/test/current-state/handoff/memory updated.
- tests: adapter mapping/fetch-limit tests, validation tests, API monthly test, quant monthly epistemic test, frontend static UI contract tests.
- deployment: unchanged; no deploy.

## Files Changed By Area
- api: `tests/api/test_analysis_endpoints.py`
- adapters: `src/crypto_probability_engine/adapters/mappers.py`, `src/crypto_probability_engine/adapters/provider_selection.py`, `src/crypto_probability_engine/adapters/public_market.py`, `tests/adapters/test_public_market_adapters.py`
- quant: `src/crypto_probability_engine/quant/epistemic_sufficiency.py`, `tests/quant/test_quant_pipeline.py`
- news: none
- frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `tests/frontend/test_frontend_static.py`
- config: `src/crypto_probability_engine/config/defaults.py`
- docs: `IMPLEMENTATION_DECISIONS.md`, `docs/source_verification_matrix.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/06_TEST_COMMANDS.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `RELEASE_GATE.md`
- tests: `tests/fixtures/market_data.py`, `tests/validation/test_market_validation.py`
- deployment: none

## Important Decisions
Sprint 3 adds `1M` as a supported analysis timeframe without changing primary default `4H` or trend timeframes `{1H, 4H, 1D}`.
`TIMEFRAME_SECONDS["1M"] = 30 * 24 * 60 * 60` is an approximate calendar-month duration.
`MIN_HISTORY_BARS_BY_TIMEFRAME["1M"] = 24`; sub-monthly timeframes keep `DEFAULT_PHASE1A.min_history_bars = 200`.
OKX monthly candles use `1Mutc` to reduce monthly boundary mismatch.
Existing OKX 1D/1W HK alignment mismatch is documented as future work and was not changed.
Frontend may map backend `total_score` to card color only; it still must not recompute score, probability, trend, disposition, or news influence.
`IMPLEMENTATION_DECISIONS.md` records the Sprint 3 timeframe decision.

## Commands Run And Results
- `git branch --show-current`: PASS, `codex/sprint3-ui-1m-timeframe`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits only app-root Sprint 3 files modified.
- `python3 --version`: PASS, Python 3.14.3.
- Branch setup from `dev`: PASS.
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
- Targeted 1M/config/frontend greps: PASS.
- Frontend no-recompute grep over `frontend/app.js`: PASS, no output.
- Forbidden capability grep: PASS, no output.
- Frontend secret-marker grep: PASS, no output.
- `PYTHONPATH=src python3 scripts/live_smoke.py`: PASS/SKIP, flag not enabled.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 7 passed after final frontend safety polish.
- Manual browser UI smoke: NOT RUN; no visual browser run was performed.
- 1M live smoke: NOT RUN; script does not support timeframe targeting.

## Known Blockers
No Sprint 3 offline-verification blocker remains.

## Open Risks
Manual browser UI smoke was not performed, so visual polish is verified by static tests and code review rather than a live browser run.
Timeframe-targeted 1M live smoke was not run because `scripts/live_smoke.py` does not support timeframe selection.
Monthly duration is an approximate 30-day value, as approved in the Sprint 3 plan.
External provider availability/rate limits remain operational risks.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter is Python 3.14.3 while Docker targets Python 3.11.
`jsonschema.RefResolver` warning remains non-blocking technical debt.

## Next Recommended Steps
1. Commit Sprint 3 changes on `codex/sprint3-ui-1m-timeframe`.
2. Ask Claude/User for UI/timeframe review.
3. After review, run a browser UI smoke if desired before merge/pre-deploy.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, hashes from real codes, signing keys, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change auth/security/session, Docker/deployment, provider HTTP client internals, core quant/scoring/gate/news math, or the `_frac` sentinel guard for Sprint 3.
Do not merge or deploy without explicit approval.
