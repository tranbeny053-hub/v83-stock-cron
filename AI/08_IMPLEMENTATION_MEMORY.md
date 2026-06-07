# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave1-supabase-watchlist`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 1 optional Supabase persistence and Watchlist are implemented.
Claude reviewed Wave 1 as `APPROVE_WITH_TARGETED_FIXES`.
This pass applies only the targeted fixes: non-blocking persistence writes, Supabase circuit breaker/pool, and explicit failure-path tests.
No quant/scoring/gates/probability/news math, provider behavior, Docker/deploy logic, or trading capability was changed.
Full offline pytest passed at 106 tests before final post-doc safety rerun.
No merge/deploy/push to Hugging Face has been performed by Codex.

## Latest App State
Default data mode remains live public market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes remain `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
Optional Supabase persistence is selected only when `SUPABASE_DB_URL` exists.
Analysis builds and stores the response in the in-memory run store immediately.
DB persistence work is scheduled after response construction and submitted to a bounded worker pool.
Responses report current known `persistence_status`; open-circuit/unavailable repositories report `UNAVAILABLE` immediately.
Supabase repository uses a small `psycopg_pool.ConnectionPool`.
Circuit breaker skips DB attempts during cooldown so Supabase down does not cost connect timeout on every write.
Watchlist backend endpoints still use in-memory fallback and degrade quickly.

## Implemented Components
- api: analyze/analyze_batch now inject `BackgroundTasks` and schedule persistence outside the response path.
- adapters: unchanged.
- validation: unchanged.
- quant: unchanged.
- news: unchanged; no live fetching added.
- frontend: unchanged in this fix pass.
- config: unchanged in this fix pass.
- docs: current state, handoff, memory, release gate, and changelog updated.
- tests: non-blocking analyze, persistence failure path, circuit breaker, and degraded watchlist coverage.
- deployment: unchanged; no deploy/push.
- persistence: Supabase pool/circuit breaker, defensive wrapper, compact background work object.

## Files Changed By Area
- api: `src/crypto_probability_engine/api/app.py`, `src/crypto_probability_engine/api/analysis_service.py`
- persistence: `src/crypto_probability_engine/persistence/repository.py`
- config: `requirements.txt`
- docs: `CHANGELOG.md`, `RELEASE_GATE.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/api/test_analysis_endpoints.py`, `tests/api/test_watchlist_endpoints.py`, `tests/persistence/test_persistence_foundation.py`
- adapters / quant / news / frontend / deployment: none

## Important Decisions
Analyze responses must not wait for Supabase writes.
FastAPI `BackgroundTasks` is used only to submit compact work to a `ThreadPoolExecutor`; actual DB work is off the response path.
Background persistence receives compact summaries only, not the full response payload.
Circuit breaker uses monotonic time and a lock.
Failure opens the circuit for 60 seconds.
Open circuit returns `UNAVAILABLE` immediately and skips DB attempts.
After cooldown, one trial attempt is allowed; success closes the circuit, failure reopens it.
Connection pooling uses `psycopg_pool.ConnectionPool` with small bounds and `prepare_threshold=None`.
No secret values are logged, printed, or returned.

## Commands Run And Results
- `git branch --show-current`: PASS, `codex/wave1-supabase-watchlist`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/persistence -q`: PASS, 4 passed.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py -q`: PASS, 9 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 106 passed, 3 warnings.
- First `ruff check src tests scripts`: FAIL, import formatting; fixed.
- Second `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Supabase frontend grep: PASS, no output.
- Forbidden capability grep: PASS, no output.
- Pool/circuit grep: PASS, source/test hits confirm implementation; generated ignored `__pycache__` binary matches also appeared.

## Known Blockers
No implementation blocker remains.
Supabase live connectivity is not verified because no live database operation was requested.

## Open Risks
Supabase migrations must be applied before durable persistence is expected.
Database availability and Supabase limits remain operational risks, now degraded by circuit breaker.
First DB failure after a healthy status can still be discovered asynchronously; subsequent requests see `UNAVAILABLE` while circuit is open.
Browser visual smoke for Watchlist was not run in this pass.
External provider availability/rate limits remain operational risks.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter is Python 3.14.3 while Docker targets Python 3.11.
`jsonschema.RefResolver` warning remains non-blocking technical debt.

## Next Recommended Steps
1. Commit targeted fix on `codex/wave1-supabase-watchlist`.
2. Claude/User reviews; if approved, apply Supabase migrations.
3. Proceed through release gate before merge/deploy.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change backend quant/scoring/gates/news/provider behavior for Wave 1.
Do not deploy or push to Hugging Face without explicit approval.
