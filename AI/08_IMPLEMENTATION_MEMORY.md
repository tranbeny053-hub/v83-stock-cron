# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4b0-longtf-methodology`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4B0 fixes backend long-timeframe methodology artifacts for probability saturation, volatility scaling, timeout pinning, tail CVaR thresholds, and 1M low-sample sufficiency.
This is an R4 methodology patch and needs Claude review before merge/deploy.
No frontend, provider, auth, news, migration, dependency, private endpoint, or trading capability changes were made.

## Latest App State
Offline tests, lint, schema validation, safety checkers, and manual smoke pass locally.
Probability invariant remains enforced.
`calibration_status` remains `DEFAULT_PHASE1A`.
`reliability_status` remains `INSUFFICIENT_SAMPLE`.
`profitability_claim` remains `false`.
`news_influence_frac` remains `0.0`.
1M runs below `60` bars are now marked `LOW_SAMPLE` while retaining the `24`-bar minimum run threshold.

## Implemented Components
- volatility: done, `realized_vol` is per-bar log-return population standard deviation.
- probability: done, directional split uses bounded volatility-normalized signal input.
- timeout: done, volatility contribution uses timeframe-specific reference constants.
- tail CVaR/gate: done, emitted tail threshold scales by timeframe duration and gates use the emitted threshold.
- epistemic sufficiency: done, monthly low-sample band added.
- tests: done, golden tests added for Wave 4B0 methodology.
- docs: done, current state/handoff/memory/decision/release/changelog updated.

## Files Changed By Area
- quant: `src/crypto_probability_engine/quant/probability_three_state.py`, `horizon_timeout.py`, `tail_cvar.py`, `epistemic_sufficiency.py`, `pipeline.py`
- features: `src/crypto_probability_engine/features/volatility.py`
- gates: `src/crypto_probability_engine/gates/composite.py`
- config: `src/crypto_probability_engine/config/defaults.py`
- tests: `tests/quant/test_quant_pipeline.py`, `tests/features/test_volatility_methodology.py`, `tests/gates/test_long_timeframe_tail_gate.py`, `tests/api/test_analysis_endpoints.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `IMPLEMENTATION_DECISIONS.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
- Direction probability now uses `bounded(net_signal / max(realized_vol, 0.02), +/-2.0) * 0.25` before `tanh`.
- `realized_vol` is now `pstdev(log returns)` per bar; no `sqrt(sample_count)` multiplier.
- Timeout volatility references are explicit by timeframe: `15m=0.02`, `1H=0.035`, `4H=0.06`, `1D=0.18`, `1W=0.45`, `1M=0.80`.
- Tail CVaR breach threshold scales from the existing 4H `0.05` baseline by `sqrt(timeframe_seconds / 4H_seconds)`.
- Monthly minimum run history remains `24`; monthly low-sample threshold is `60`.
- Score penalty was not changed; score effects come from corrected volatility/risk pressure and probability inputs.

## Commands Run And Results
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

## Known Blockers
No local implementation blocker is known after offline verification.
Claude R4 review is required before merge/deploy.

## Open Risks
Methodology constants are intentionally explicit but still heuristic and uncalibrated.
Live BTC/SOL 1D/1W/1M behavior needs deployed smoke after review/merge/deploy.
No prediction ledger or calibration measurement exists yet.

## Next Recommended Steps
1. Send the branch/report to Claude for R4 review.
2. After approval, merge into `dev` and deploy from the app root only.
3. Re-smoke live BTC/SOL 1D/1W/1M and document observations without claiming accuracy or profitability.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit secrets or env files.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not change frontend/provider/auth/news/deployment/migrations/dependencies in this branch.
Do not promote confidence, calibration, reliability, accuracy, or profitability claims.
