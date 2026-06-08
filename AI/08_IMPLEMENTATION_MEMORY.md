# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave1-2-supabase-rest-runtime`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 1.2 fixes Hugging Face persistence runtime connectivity by adding backend-only Supabase REST/PostgREST persistence.
Root cause: Hugging Face may block outbound direct Postgres ports `5432`/`6543`; Supabase REST uses HTTPS `443`.
Runtime persistence now prefers `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`; `SUPABASE_DB_URL` remains for local migrations/direct Postgres or non-HF runtime.
No quant/scoring/probability/gates/news math, Market Data v2, News Authority, calibration, private provider calls, deployment, or trading capability was added.
Full offline checks passed locally. No merge/deploy/push to Hugging Face has been performed by Codex.

## Latest App State
Default data mode remains live public Binance/OKX market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes remain `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
Persistence repository priority is now `SUPABASE_REST` > `SUPABASE_POSTGRES` > `IN_MEMORY`.
`SUPABASE_REST` uses Supabase HTTPS REST with backend-only headers and compact payloads.
`SUPABASE_POSTGRES` remains available for direct DB URL runtime if REST secrets are absent.
`IN_MEMORY` remains the stateless fallback when no persistence config exists.
Analysis still returns normally if persistence is unavailable.
Frontend still never references Supabase values or calls Supabase directly.

## Implemented Components
- config: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_DB_URL` remain repr/log safe; external store detection includes REST secrets.
- persistence: added `SupabaseRestRepository` with best-effort writes, short timeout, circuit breaker, and in-memory fallback.
- api: system status can show `SUPABASE_REST`, `SUPABASE_POSTGRES`, or `IN_MEMORY` without secret values.
- tests: mocked `httpx` REST tests cover writes, watchlist CRUD, failure/circuit behavior, runtime selection priority, and analysis under REST outage.
- docs: README, deployment checklist, release gate, implementation decisions, source matrix, changelog, current state, and handoff updated.
- frontend / quant / news / scoring / provider market-data: unchanged.

## Files Changed By Area
- config: `src/crypto_probability_engine/config/settings.py`
- persistence: `src/crypto_probability_engine/persistence/repository.py`
- api: `src/crypto_probability_engine/api/health.py`
- docs: `README.md`, `DEPLOYMENT_CHECKLIST.md`, `IMPLEMENTATION_DECISIONS.md`, `RELEASE_GATE.md`, `CHANGELOG.md`, `docs/source_verification_matrix.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/persistence/test_persistence_foundation.py`, `tests/api/test_auth_health.py`, `tests/api/test_analysis_endpoints.py`

## Important Decisions
Use Supabase REST/PostgREST for Hugging Face runtime persistence because it uses HTTPS `443`.
Keep `SUPABASE_DB_URL` for `scripts/apply_migrations.py`, local admin, and non-HF direct Postgres runtime.
If both REST and DB URL secrets exist, runtime uses REST.
Service role key is backend-only and must never appear in frontend, status, debug export, logs, docs as a value, or committed files.
REST failures open the same style of circuit and return `UNAVAILABLE`; analysis remains best-effort and does not crash.
Migration SQL remains valid; no schema migration change was needed.

## Commands Run And Results
- `git checkout -b codex/wave1-2-supabase-rest-runtime`: PASS, branch created from `dev`.
- `git branch --show-current`: PASS, `codex/wave1-2-supabase-rest-runtime`.
- `git status --short --untracked-files=all -- .`: PASS, only expected Wave 1.2 modified files.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/persistence -q`: PASS, 9 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 28 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 119 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: initially FAIL on fake test `supabase_*` keyword assignments; after test-only syntax fix, PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Frontend Supabase-name grep: PASS, no output.
- Frontend `service_role`/`apikey`/`Authorization` grep: PASS, no output.
- Forbidden capability grep: PASS, no output.
- REST repository/status grep: PASS, expected backend/test/doc references only.

## Known Blockers
No implementation blocker is known after the full offline check suite.
Commit is still pending in this recovery pass.

## Open Risks
Hugging Face runtime persistence still needs live smoke after secrets are set.
Supabase service role key must be handled as a sensitive backend secret.
Supabase RLS/policies/API settings may still affect REST calls in the live project.
Supabase project rate limits and availability remain operational risks.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter may differ from Docker Python 3.11.

## Next Recommended Steps
1. Review and commit the Wave 1.2 diff when ready.
2. User sets HF `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
3. Redeploy/smoke only after approval; confirm `Persistence: OK`.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change backend quant/scoring/gates/news math for Wave 1.2.
Do not deploy or push to Hugging Face without explicit approval.
