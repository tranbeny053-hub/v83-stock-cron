# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave1-1-stabilization-hotfix`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 1 optional Supabase persistence and Watchlist are already implemented.
This pass applies only Wave 1.1 stabilization: daily/weekly provider alignment/fallback, visible refresh, persistence status visibility, and clearer Dev Mode UX.
No Market Data v2, News Authority Engine, calibration, scoring/probability/gates/news math, private provider calls, deployment, or trading capability was added.
Targeted validation/provider/frontend/API tests and full offline gates passed.
No merge/deploy/push to Hugging Face has been performed by Codex.

## Latest App State
Default data mode remains live public Binance/OKX market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes remain `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
OKX daily/weekly candle mappings now use UTC buckets: `1Dutc` and `1Wutc`.
Cross-provider coherence compares the latest common closed candle by close time and ignores non-equivalent/open candles.
If providers disagree and `UCPE_CROSS_PROVIDER_REQUIRED=false`, analysis can return one validated public live provider with explicit provider-state warning.
If `UCPE_CROSS_PROVIDER_REQUIRED=true`, disagreement still blocks with `DATA_CONFLICT`.
App shell now shows `Persistence: STATELESS/OK/UNAVAILABLE`, a `Re-analyze` button, and last refreshed time.
Dev Mode disabled deployments show “Dev Mode is disabled in this deployment.” and disable re-auth controls.

## Implemented Components
- api: `/v1/system_status` now includes dev-safe persistence diagnostics and Dev Mode availability/configuration flags.
- adapters: OKX interval mapping changed only for 1D/1W UTC candle buckets.
- validation: cross-provider coherence now aligns latest common closed candle buckets.
- provider selection: optional cross-provider conflict returns explicit single public-provider live fallback; required mode still blocks.
- frontend: global refresh, persistence status badge, detail provider-state fields, and Dev Mode disabled/configured UX.
- tests: validation, adapter/provider-selection, auth/system status, and frontend static regression coverage.
- quant/news/scoring/gates/deployment: unchanged.

## Files Changed By Area
- api: `src/crypto_probability_engine/api/app.py`, `src/crypto_probability_engine/api/health.py`
- adapters: `src/crypto_probability_engine/adapters/mappers.py`, `src/crypto_probability_engine/adapters/provider_selection.py`
- validation: `src/crypto_probability_engine/validation/market_data.py`
- frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- docs: `IMPLEMENTATION_DECISIONS.md`, `docs/source_verification_matrix.md`, `RELEASE_GATE.md`, `CHANGELOG.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/adapters/test_provider_selection.py`, `tests/adapters/test_public_market_adapters.py`, `tests/api/test_auth_health.py`, `tests/frontend/test_frontend_static.py`, `tests/validation/test_market_validation.py`

## Important Decisions
Cross-provider tolerance remains `price_disagreement_bps = 50`; it was not loosened.
Daily/weekly mismatch root cause was comparing potentially non-equivalent Binance UTC buckets against OKX local-aligned daily/weekly buckets and comparing latest rows directly.
OKX 1D/1W now use UTC mappings, while 1M remains `1Mutc`.
Coherence uses the latest common closed bucket; no fake data, no fixture fallback, and no averaging.
Single-provider live fallback is allowed only when `UCPE_CROSS_PROVIDER_REQUIRED=false` and at least one official public provider validates.
Provider state records `cross_provider_state`, `fallback_to_single_provider`, `disagreement_bps`, and reason.
Refresh reuses existing backend analyze/batch/watchlist analysis functions; frontend does not recompute backend-authoritative fields.
Persistence status visibility is dev-safe and never includes DB URL, host, username, password, Supabase key, or raw exception.

## Commands Run And Results
- `git branch --show-current`: PASS, `codex/wave1-1-stabilization-hotfix`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `PYTHONPATH=src python3 -m pytest tests/validation -q`: PASS, 12 passed.
- `PYTHONPATH=src python3 -m pytest tests/adapters/test_provider_selection.py tests/adapters/test_public_market_adapters.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest tests/api/test_auth_health.py tests/frontend/test_frontend_static.py -q`: PASS, 22 passed, 1 warning.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/adapters -q`: PASS, 27 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 26 passed, 1 warning.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 112 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Supabase frontend grep: PASS, no output.
- Forbidden capability grep: PASS, no output.
- Refresh/persistence/dev-mode grep: PASS, expected implementation/test hits only; ignored `__pycache__` binary matches also appeared.

## Known Blockers
No implementation blocker is known after the full offline check suite.

## Open Risks
Manual deployed UI smoke is not run by Codex in this local pass.
External provider availability/rate limits remain operational risks.
Optional single-provider live fallback is visible but still less strong than cross-provider coherent data.
Supabase can still be `UNAVAILABLE` until secrets/migrations/connectivity are configured correctly.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter may differ from Docker Python 3.11.

## Next Recommended Steps
1. User/Claude reviews the hotfix.
2. Merge to `dev` only after approval.
3. Deploy only through the release gate after merge approval.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change backend quant/scoring/gates/news math for Wave 1.1.
Do not deploy or push to Hugging Face without explicit approval.
