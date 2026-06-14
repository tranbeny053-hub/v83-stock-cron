# Current State

Updated: 2026-06-14

## Branch / Worktree

- Branch: `codex/wave4b0-longtf-methodology`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 4B0 Long-Timeframe Methodology Patch.
- Risk: R4 methodology change requiring Claude review before merge/deploy.
- Current status: methodology patch implemented locally; full offline verification passes.

## What Changed

- Replaced sample-count-scaled realized volatility with per-bar log-return population standard deviation.
- Changed three-state directional probability input from raw `net_signal * 25` to bounded volatility-normalized signal input.
- Made timeout volatility contribution timeframe-aware through explicit volatility reference constants.
- Added timeframe-scaled tail CVaR breach thresholds and wired gates to use the emitted threshold.
- Marked monthly runs below `60` candles as `LOW_SAMPLE` while retaining the `24`-bar minimum run threshold.
- Added golden tests for direction desaturation, probability invariant, short-timeframe stability, volatility sample-duplication invariance, horizon-aware timeout, horizon-aware tail gate pass/breach, and monthly low-sample sufficiency.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/wave4b0-longtf-methodology`.
- `git status --short --untracked-files=all -- .`: PASS, showed only Wave 4B0 changed files before docs.
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

## Current Blockers / Unknowns

- No local implementation blocker is known after offline verification.
- This is an R4 methodology patch and needs Claude review before merge/deploy.
- Live BTC/SOL long-timeframe behavior should be re-smoked after Claude approval and merge/deploy.

## Next Steps

1. Send this report and commit to Claude for R4 methodology review.
2. After approval, merge to `dev` and deploy from the app root only.
3. Re-smoke live BTC/SOL 1D/1W/1M cards and verify no profitability/accuracy claims are introduced.
