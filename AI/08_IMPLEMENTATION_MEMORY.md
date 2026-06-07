# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave1-supabase-watchlist`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 1 adds optional Supabase Postgres persistence and a Watchlist feature.
No quant/scoring/gates/probability/news math, provider behavior, Docker/deploy logic, or trading capability was changed.
The app still runs without Supabase and reports `persistence_status=STATELESS`.
Persistence failure is degraded-safe: analysis returns normally and reports `UNAVAILABLE`.
Full offline pytest, ruff, safety scripts, schema validation, and manual smoke pass.
No merge/deploy/push to Hugging Face has been performed by Codex.

## Latest App State
Default data mode remains live public market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes remain `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
Optional Supabase persistence is selected only when `SUPABASE_DB_URL` exists.
Without Supabase, recent-run detail remains in memory and Watchlist can use browser storage fallback.
Analysis responses include debug-safe `persistence_status`.
Watchlist backend endpoints are session-gated.
Watchlist frontend tab can add/remove/list symbols and run six-timeframe analysis for a selected symbol.
Supabase migrations exist but were not applied to a live database in this pass.

## Implemented Components
- api: partial/done for Wave 1 watchlist routes and persistence wiring.
- adapters: unchanged.
- validation: unchanged.
- quant: unchanged.
- news: unchanged; no live fetching added.
- frontend: Watchlist tab, localStorage fallback, six-timeframe Watchlist Symbol View, Detail reuse.
- config: Supabase env settings added; repr/log safe.
- docs: Wave 1 entries added to README, deployment checklist, release gate, source matrix, decisions, changelog, current state, handoff, and test commands.
- tests: stateless analysis, persistence outage, watchlist CRUD, migration safety, and frontend static coverage.
- deployment: unchanged; no deploy/push.

## Files Changed By Area
- api: `src/crypto_probability_engine/api/app.py`, `src/crypto_probability_engine/api/analysis_service.py`, `src/crypto_probability_engine/api/schemas.py`
- adapters: none
- quant: none
- news: none
- frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- config: `src/crypto_probability_engine/config/settings.py`, `requirements.txt`
- docs: `README.md`, `DEPLOYMENT_CHECKLIST.md`, `RELEASE_GATE.md`, `IMPLEMENTATION_DECISIONS.md`, `CHANGELOG.md`, `docs/source_verification_matrix.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/06_TEST_COMMANDS.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/api/test_analysis_endpoints.py`, `tests/api/test_watchlist_endpoints.py`, `tests/frontend/test_frontend_static.py`, `tests/persistence/test_persistence_foundation.py`
- deployment: none
- persistence: `migrations/0001_init.sql`, `scripts/apply_migrations.py`, `scripts/check_no_secrets.py`, `src/crypto_probability_engine/persistence/repository.py`

## Important Decisions
Supabase persistence is optional and backend-only.
`SUPABASE_DB_URL` enables the Supabase repository; absence means `STATELESS`.
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are declared backend settings but unused in Wave 1.
Only compact summaries are persisted; full analysis payloads and article bodies are not stored.
Persistence operations are best-effort and never raise into the analysis hot path.
Watchlist symbols are normalized through the existing backend normalizer and capped at `20`.
Frontend Watchlist uses backend endpoints only; no direct Supabase calls or secret names appear in frontend files.

## Commands Run And Results
- `git branch --show-current`: PASS, `codex/wave1-supabase-watchlist`.
- `git status --short --untracked-files=all -- .`: PASS, only Wave 1 app-root files modified/untracked before commit.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py tests/api/test_watchlist_endpoints.py tests/persistence/test_persistence_foundation.py tests/frontend/test_frontend_static.py -q`: PASS, 25 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 102 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- First `PYTHONPATH=src python3 scripts/check_no_secrets.py`: FAIL, false positive on safe settings env reads; checker updated.
- Second `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Supabase frontend grep: PASS, no output.
- Forbidden capability grep: PASS, no output.

## Known Blockers
No implementation blocker remains.
Supabase live connectivity is not verified because no live database operation was requested.

## Open Risks
Supabase migrations must be applied before durable persistence is expected.
Database availability and Supabase limits remain operational risks.
Browser visual smoke for Watchlist was not run in this pass.
External provider availability/rate limits remain operational risks.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter is Python 3.14.3 while Docker targets Python 3.11.
`jsonschema.RefResolver` warning remains non-blocking technical debt.

## Next Recommended Steps
1. Commit Wave 1 on `codex/wave1-supabase-watchlist`.
2. Claude/User reviews persistence and Watchlist implementation.
3. If approved, apply Supabase migrations and proceed through release gate before merge/deploy.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change backend quant/scoring/gates/news/provider behavior for Wave 1.
Do not deploy or push to Hugging Face without explicit approval.
