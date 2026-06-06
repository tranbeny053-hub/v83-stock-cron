# Implementation Memory

## Context-Resume Summary
Sprint 2 targeted fixes are applied on `codex/sprint2-live-market-data`.
Worktree scope is `v8-crypto-api-clean/` under the parent Git repo; do not touch sibling folders.
Claude review result was `APPROVE_WITH_TARGETED_FIXES`; FIX-S2-1 through FIX-S2-4 are implemented.
Signed market return/signal/edge fields no longer use `_frac`; true `_frac` fields remain bounded by sentinel validation.
Offline tests/checkers pass, and real gated live smoke passed for BTC and ETH in `METRICS_ONLY` and `NEWS_ADDON`.
No merge, deploy, private exchange call, live news fetch, trading path, or secret file was added.
Next step is Claude re-review of this targeted fix commit before any merge/deploy discussion.

## Latest App State
Default data mode remains live public market data with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Binance/OKX public adapters fetch a small candle buffer (`min_history_bars + 5`, capped by provider) before closed-candle validation.
Live smoke returned schema-valid `CROSS_PROVIDER` payloads for BTC/USDT and ETH/USDT in both analysis modes.
`NEWS_ADDON` still returns unavailable/no-op news state without live news fetching.
Down-market fixtures now cover negative signed returns/signals/edge offline.
Access-code hashing remains PBKDF2-HMAC-SHA256; `scripts/make_access_hash.py` helps generate deploy hashes without printing plaintext.

## Implemented Components
- api: done for Sprint 2 targeted scope; response validation accepts negative signed fields after rename.
- adapters: done for targeted scope; Binance/OKX fetch margin added.
- quant: targeted rename only; math unchanged.
- news: unchanged; no live fetching, no-op influence.
- frontend: unchanged behavior; live/demo/degraded honesty remains backend-driven.
- config: unchanged for this pass except existing PBKDF2 defaults are reused by helper.
- docs: updated for hash helper, HF secrets, release gate, current state, handoff, changelog, decision log.
- tests: down-market quant/API coverage and hash-helper tests added.
- deployment: no deploy; deployment checklist updated with non-coder secret-generation steps.

## Files Changed By Area
- api: `tests/api/test_analysis_live_data_wiring.py`
- adapters: `src/crypto_probability_engine/adapters/public_market.py`
- quant: `src/crypto_probability_engine/features/trend_mtf.py`, `src/crypto_probability_engine/quant/risk_arbiter.py`, `src/crypto_probability_engine/quant/probability_three_state.py`, `src/crypto_probability_engine/quant/pipeline.py`, `src/crypto_probability_engine/score_stack/score.py`
- tests: `tests/fixtures/market_data.py`, `tests/quant/test_quant_pipeline.py`, `tests/scripts/test_make_access_hash.py`
- scripts: `scripts/make_access_hash.py`, `scripts/live_smoke.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/06_TEST_COMMANDS.md`, `AI/07_DECISION_LOG.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `DEPLOYMENT_CHECKLIST.md`, `README.md`, `RELEASE_GATE.md`
- frontend: none
- config: none
- deployment: docs only; no Docker/HF deployment change

## Important Decisions
Signed ratio/edge fields are named `primary_return`, `extended_return`, `alpha_signal`, `net_signal`, and `directional_edge`; `_frac` remains reserved for bounded `[0,1]` fraction/probability/confidence/cost/risk fields.
Values and math for the signed fields were not changed.
Down-market regression coverage is required because rising-only fixtures hid the signed-field sentinel bug.
Access-code deploy hashes should be generated with `scripts/make_access_hash.py` using local `UCPE_ACCESS_CODE_SALT`; no plaintext code, salt, or hash is committed.
Sprint 2 public Binance/OKX remains keyless; no Binance/OKX API keys are required.
Hugging Face table status: Variables/secrets are documented in README, RELEASE_GATE, DEPLOYMENT_CHECKLIST, AI/05, and this memory.
See `AI/07_DECISION_LOG.md` for the dated targeted-fix decision.

## Commands Run And Results
- `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits, only in-project targeted files changed/untracked.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/quant/test_quant_pipeline.py tests/api/test_analysis_live_data_wiring.py tests/scripts/test_make_access_hash.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 80 passed, 3 warnings.
- `ruff check src tests scripts`: initially FAIL on two long lines; PASS after wrapping.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "primary_return_frac\|extended_return_frac\|alpha_signal_frac\|net_signal_frac\|directional_edge_frac" src schemas tests || true`: PASS, no output after removing literal old-name test strings.
- `grep -R "hashlib.sha256" src scripts tests || true`: PASS_WITH_NOTE; hits are analysis hash and session HMAC signing, not access-code hashing.
- `grep -R "_frac" src/crypto_probability_engine schemas tests`: REVIEWED; remaining text fields are true bounded fractions/probabilities/confidence/cost/risk fields.
- `UCPE_LIVE_SMOKE_ENABLED=true PYTHONPATH=src python3 scripts/live_smoke.py`: PASS; BTC and ETH in both modes returned schema-valid `CROSS_PROVIDER` live payloads.

## Known Blockers
No targeted-fix blocker remains.

## Open Risks
Claude re-review is still required before merge or deploy.
Provider live behavior depends on external Binance/OKX public endpoint availability and rate limits.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter is Python 3.14.3 while Docker targets Python 3.11.
`jsonschema.RefResolver` warning remains non-blocking technical debt.
Secrets must still be generated and entered by the operator in Hugging Face settings only.

## Next Recommended Steps
1. Commit the targeted fixes on `codex/sprint2-live-market-data`.
2. Hand to Claude for re-review of signed schema fix, down-market coverage, live smoke, access hash helper, and HF variables/secrets table.
3. After approval, decide merge/deploy path separately; do not deploy from this pass.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, hashes from real codes, signing keys, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not merge or deploy without explicit approval.
