# Implementation Memory

## Context-Resume Summary
Sprint 2 final `_frac` defect-class fix is applied on `codex/sprint2-live-market-data`.
Worktree scope is `v8-crypto-api-clean/` under the parent Git repo; do not touch sibling folders.
Claude latest review was `APPROVE_WITH_TARGETED_FIXES`; FIX-S2-5 is implemented.
The systematic `_frac` sweep renamed unbounded magnitudes and kept the strict `[0,1]` sentinel unchanged.
Offline tests/checkers pass, high-volatility response coverage passes, and live smoke passed for BTC, ETH, and SOL in both modes.
No merge, deploy, private exchange call, live news fetch, trading path, API key, or secret file was added.
Next step is user/Claude approval for merge path; deployment still needs pre-deploy checklist execution.

## Latest App State
Default data mode remains live public market data with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Binance/OKX public adapters remain keyless and public-only.
Unbounded payload magnitudes now use non-`_frac` names: `realized_vol`, `risk_pressure`, and `cvar_loss`.
Previously fixed signed fields remain non-`_frac`: `primary_return`, `extended_return`, `alpha_signal`, `net_signal`, and `directional_edge`.
Remaining emitted `_frac` fields are recursively tested as numeric `[0,1]` values.
High-volatility offline fixture proves `realized_vol`, `risk_pressure`, and `cvar_loss` can exceed `1.0` without schema/sentinel failure.
Live smoke with `UCPE_LIVE_SMOKE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT` passed in `METRICS_ONLY` and `NEWS_ADDON`.
`NEWS_ADDON` still returns unavailable/no-op news state without live news fetching.
Access-code hash helper remains PBKDF2-HMAC-SHA256 and requires `UCPE_ACCESS_CODE_SALT`.

## Implemented Components
- api: done for final fix scope; response validation unchanged and strict.
- adapters: unchanged for this pass; live public Binance/OKX still pass smoke.
- quant: targeted field renames only; values/math unchanged.
- features: volatility field renamed; liquidity emits bounded `spread_frac` or degrades.
- execution_realism: guards invalid spread before emitting cost/spread fractions.
- gates: tail guard reads `cvar_loss`.
- score: score stack reads `risk_pressure`.
- news: unchanged; no live fetching, no-op influence.
- frontend: unchanged; backend display remains authoritative.
- docs: `_frac` audit table, current state, handoff, memory, changelog, release gate, deployment/test commands updated.
- tests: high-volatility fixture and recursive `_frac` full-response test added.

## Files Changed By Area
- api/tests: `tests/api/test_analysis_live_data_wiring.py`
- features: `src/crypto_probability_engine/features/volatility.py`, `src/crypto_probability_engine/features/regime_2state.py`, `src/crypto_probability_engine/features/liquidity_depth.py`
- quant: `src/crypto_probability_engine/quant/risk_arbiter.py`, `src/crypto_probability_engine/quant/horizon_timeout.py`, `src/crypto_probability_engine/quant/tail_cvar.py`
- gates/score/execution: `src/crypto_probability_engine/gates/composite.py`, `src/crypto_probability_engine/score_stack/score.py`, `src/crypto_probability_engine/execution_realism/realism.py`
- scripts: `scripts/live_smoke.py`
- tests: `tests/fixtures/market_data.py`, `tests/quant/test_quant_pipeline.py`
- docs: `IMPLEMENTATION_DECISIONS.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/06_TEST_COMMANDS.md`, `AI/07_DECISION_LOG.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `DEPLOYMENT_CHECKLIST.md`, `RELEASE_GATE.md`
- frontend: none
- config: none
- deployment: docs only; no deploy/config credential changes

## Important Decisions
FIX-S2-5: `_frac` suffix is reserved for emitted values guaranteed within `[0,1]`.
`realized_vol_frac` -> `realized_vol`; `risk_pressure_frac` -> `risk_pressure`; `cvar_loss_frac` -> `cvar_loss`.
`spread_frac`, `slippage_frac`, and `round_trip_cost_frac` are retained only because invalid wide spread degrades before unsafe fraction emission.
No unbounded value is clamped into a fake fraction.
`IMPLEMENTATION_DECISIONS.md` contains the systematic `_frac` classification table.
Hugging Face Variables/Secrets table remains current: no Binance/OKX API keys or exchange secrets are required.
See `AI/07_DECISION_LOG.md` for the dated FIX-S2-5 decision.

## Commands Run And Results
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
- `grep -R "_frac" src/crypto_probability_engine schemas tests`: REVIEWED; remaining emitted `_frac` fields are bounded and covered by recursive response test.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R "apiKey\|api_key\|secretKey\|private endpoint\|signed endpoint" src/crypto_probability_engine/adapters tests || true`: PASS, no output.
- `grep -R "hashlib.sha256" src scripts tests || true`: PASS_WITH_NOTE; hits are analysis hash and session HMAC signing, not access-code hashing.
- `UCPE_LIVE_SMOKE_ENABLED=true UCPE_LIVE_SMOKE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT PYTHONPATH=src python3 scripts/live_smoke.py`: PASS; all six symbol/mode runs returned schema-valid `CROSS_PROVIDER` payloads.

## Known Blockers
No FIX-S2-5 blocker remains.

## Open Risks
External provider availability/rate limits remain operational risks.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter is Python 3.14.3 while Docker targets Python 3.11.
`jsonschema.RefResolver` warning remains non-blocking technical debt.
Secrets must still be generated by the operator and entered only in Hugging Face Settings.
No deployment has been performed; pre-deploy checklist is still required.

## Next Recommended Steps
1. Commit FIX-S2-5 on `codex/sprint2-live-market-data`.
2. Ask user/Claude for approval to merge this branch.
3. If merge is approved, run the pre-deploy checklist before any Hugging Face push/deploy.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, hashes from real codes, signing keys, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not merge or deploy without explicit approval.
