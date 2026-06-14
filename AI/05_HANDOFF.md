# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4B0 Long-Timeframe Methodology Patch: fix long-timeframe probability, volatility, timeout, tail-risk, and monthly sufficiency artifacts without changing frontend, providers, auth, news, migrations, dependencies, or trading scope.

## Current Branch / Worktree
`codex/wave4b0-longtf-methodology` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R4 methodology patch. Requires Claude review before merge/deploy.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/features/volatility.py`
- `src/crypto_probability_engine/gates/composite.py`
- `src/crypto_probability_engine/quant/epistemic_sufficiency.py`
- `src/crypto_probability_engine/quant/horizon_timeout.py`
- `src/crypto_probability_engine/quant/pipeline.py`
- `src/crypto_probability_engine/quant/probability_three_state.py`
- `src/crypto_probability_engine/quant/tail_cvar.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/features/test_volatility_methodology.py`
- `tests/gates/test_long_timeframe_tail_gate.py`
- `tests/quant/test_quant_pipeline.py`

## Commands Run
- `git branch --show-current`: PASS, `codex/wave4b0-longtf-methodology`.
- `git status --short --untracked-files=all -- .`: PASS before docs, only Wave 4B0 paths changed.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/quant tests/features tests/gates -q`: PASS, 20 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 32 passed, 2 existing warnings.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 162 passed, 4 existing warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS, offline smoke succeeded and served frontend bundle verified.

## What Works Now
- Realized volatility is per-bar and no longer inflates only because the same return distribution has more samples.
- Directional probability uses bounded volatility-normalized signal input, avoiding raw long-timeframe tanh saturation.
- Timeout volatility contribution is timeframe-aware and no longer mechanically pins long timeframes to the same value.
- Tail CVaR gate compares against a timeframe-scaled threshold while preserving extreme-tail blocking.
- 1M with roughly 28 candles is labeled `LOW_SAMPLE` instead of fully sufficient.
- Probability invariant still passes for all tested horizons.

## What Is Still Unknown
- Live long-timeframe BTC/SOL behavior after deployment is not verified in this branch.
- Claude should review the R4 methodology constants and formulas before merge.
- Existing warnings remain: `jsonschema.RefResolver` and Starlette TestClient cookie deprecations.

## Next 3 Steps
1. Send this branch/report to Claude for R4 methodology review.
2. After approval, merge to `dev` and deploy from the app root only.
3. Re-smoke live BTC/SOL 1D/1W/1M cards and confirm no accuracy/profitability claims are introduced.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not change frontend, providers, auth, news, migrations, dependencies, or deployment config for this branch.
- Do not claim measured reliability, calibration, accuracy, or profitability.
