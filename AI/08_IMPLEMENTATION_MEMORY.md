# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4b2a-github-resolver-cron`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4B.2 adds a standalone no-lookahead outcome resolver for immutable prediction-ledger rows.
The resolver writes immutable `prediction_outcomes` rows only; it does not mutate `predictions`.
No API route, frontend, schema-response, calibration metric, quant/probability/score/gate/news/provider/auth/dependency changes were made.
Wave 4B.2A adds a GitHub Actions workflow wrapper for the existing resolver only.
`migrations/0004_prediction_outcomes.sql` exists but was not run by Codex.

## Latest App State
Full local verification passes.
Outcome resolution is offline/standalone through `scripts/resolve_outcomes.py`.
The resolver fetches keyless public candles, filters strictly after `reference_close_utc`, and skips unfinished horizons.
The resolver now also skips stale-window overshoots when the first available candle is more than one timeframe after `horizon_end_utc`.
The operator resolver now prefers `SUPABASE_DB_URL` direct Postgres when both direct DB and Supabase REST settings are present.
The Supabase Postgres due fetch now matches the verified unresolved-row SQL and surfaces sanitized DB failures instead of fake empty `due=0`.
The Supabase Postgres due fetch now uses direct psycopg connection rather than the pooled `_run_db` wrapper, matching the standalone operator probe path.
Postgres `SET LOCAL statement_timeout` now uses an internal integer literal instead of bound parameters, fixing the SyntaxError before due SELECT.
Supabase Postgres outcome writes now use direct psycopg with `ON CONFLICT (prediction_id) DO NOTHING`, avoiding `psycopg_pool` dependency for operator outcome writes.
Outcome writes are best-effort through the selected repository and immutable by `prediction_id`.
GitHub Actions workflow `.github/workflows/resolve-outcomes.yml` runs the resolver hourly at minute 17 UTC and by manual dispatch.
The workflow requires repository secret `SUPABASE_DB_URL` and optional variable `RESOLVER_LIMIT`.
`scripts/resolve_outcomes.py` now exits nonzero if any prediction resolution fails.
Calibration/reliability/profitability/news influence remain unchanged.

## Implemented Components
- migration: `migrations/0004_prediction_outcomes.sql` idempotent `prediction_outcomes` table and realized-label index.
- config: `RESOLVER_VERSION = "resolver-v1-wave4b2"`.
- persistence: `fetch_due_unresolved_predictions(now_utc, limit)` and `save_prediction_outcome(row)` added to protocol, in-memory, direct Postgres, and Supabase REST repositories.
- resolver: `scripts/resolve_outcomes.py` standalone batch script with injectable candle fetcher for tests.
- operator wiring: resolver-specific repository builder prefers direct Postgres for operator runs; generic app builder remains unchanged.
- Postgres due query: `public.predictions` left join `public.prediction_outcomes`, mapping/tuple row conversion, and operator-visible DB failure.
- Postgres due wrapper: direct psycopg connection for due rows; `_run_db` callback behavior remains tested for other DB paths.
- Postgres timeout/outcome fix: no bind params for `SET LOCAL statement_timeout`; direct psycopg outcome write path with sanitized phase errors.
- workflow: `.github/workflows/resolve-outcomes.yml` scheduled/manual resolver automation.
- tests: migration safety, due-query filtering, immutable/idempotent outcome writes, REST/Postgres non-overwrite semantics, no-lookahead, unfinished-horizon skip, stale-window skip, UP/DOWN/TIMEOUT labels, failure isolation, and API isolation.

## Files Changed By Area
- persistence: `src/crypto_probability_engine/persistence/repository.py`
- config: `src/crypto_probability_engine/config/defaults.py`
- migrations: `migrations/0004_prediction_outcomes.sql`
- scripts: `scripts/resolve_outcomes.py`
- workflow: `.github/workflows/resolve-outcomes.yml`
- tests: `tests/persistence/test_persistence_foundation.py`, `tests/resolver/test_resolve_outcomes.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `IMPLEMENTATION_DECISIONS.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
- Outcome identity is `prediction_id`, matching the immutable prediction row.
- Due predictions are live predictions with `horizon_end_utc < now_utc` and no existing outcome row.
- Outcome rows are immutable: Postgres uses `ON CONFLICT (prediction_id) DO NOTHING`; REST uses `resolution=ignore-duplicates`; in-memory keeps the first row.
- No-lookahead rule: candles with `close_time_utc <= reference_close_utc` are filtered before any outcome calculation.
- The terminal candle is the first post-anchor closed candle with `close_time_utc >= horizon_end_utc`.
- If that terminal candle is more than one timeframe after `horizon_end_utc`, the resolver treats the window as stale/unresolvable and writes no outcome.
- Resolver repository selection is DB-first for operator runs: `SUPABASE_DB_URL` -> `SUPABASE_POSTGRES`, else Supabase REST, else in-memory.
- Resolver CLI output includes safe repository type and limit diagnostics only.
- Supabase Postgres due-query errors raise a sanitized `SUPABASE_POSTGRES due query failed or unavailable.` error instead of falling back to empty in-memory due rows.
- Supabase Postgres due fetch avoids `psycopg_pool`; this matches the operator's working standalone psycopg probe and prevents pool-wrapper failure from becoming fake `due=0`.
- Postgres statement timeout is set with an internal integer literal because PostgreSQL rejects bound parameters for `SET LOCAL`.
- Postgres outcome writes use direct psycopg and first-write-wins `ON CONFLICT DO NOTHING`; failures are surfaced with sanitized `connect` / `set_timeout` / `write` phase labels.
- Workflow uses minimal `contents: read` permissions, `resolve-outcomes` concurrency, 15-minute timeout, and never prints `SUPABASE_DB_URL`.
- Workflow does not run migrations and does not deploy anything.
- `terminal_return_frac = (outcome_close - reference_price) / reference_price`.
- Outcome label uses frozen `decision_band_frac`; if absent, fallback is `2 * DEFAULT_PHASE1A.taker_fee_frac`.
- `RESOLVER_VERSION` is `resolver-v1-wave4b2`.
- Calibration/reliability/profitability status remains unchanged: `DEFAULT_PHASE1A`, `INSUFFICIENT_SAMPLE`, `false`.
- `news_influence_frac` remains `0.0`.

## Commands Run And Results
- `git checkout dev`: PASS.
- `git status --short --untracked-files=all -- .`: PASS before branch creation, clean.
- `git checkout -b codex/wave4b2a-github-resolver-cron`: PASS.
- `git checkout -b codex/wave4b2-outcome-resolver`: PASS.
- `PYTHONPATH=src python3 -m pytest tests/resolver -q`: PASS, 10 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 29 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/resolver tests/persistence -q`: PASS, 33 passed after operator-wiring fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 36 passed after Postgres due-query fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 38 passed after direct Postgres due-fetch wrapper fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 40 passed after timeout-bind/outcome-write fix.
- `PYTHONPATH=src python3 -m pytest tests/resolver tests/persistence -q`: PASS, 42 passed after 4B.2A workflow/script-exit update.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 185 passed with 4 existing warnings after targeted fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 189 passed with 4 existing warnings after operator-wiring fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 192 passed with 4 existing warnings after Postgres due-query fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 194 passed with 4 existing warnings after direct Postgres due-fetch wrapper fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 196 passed with 4 existing warnings after timeout-bind/outcome-write fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 198 passed with 4 existing warnings after 4B.2A workflow/script-exit update.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS; offline smoke and served frontend bundle guard passed.
- Protected working-tree diff for API, quant, score stack, gates, news, frontend, and `api/schemas.py`: PASS, empty.
- Targeted greps: PASS; resolver/API import grep empty; destructive prediction mutation grep has only migration test assertions; secret/full-body/forbidden capability greps show existing backend/test/checker names only and no new unsafe implementation.

## Known Blockers
No implementation blocker is known.

## Open Risks
Migration must be reviewed/applied separately by the user/operator.
GitHub repository secret `SUPABASE_DB_URL` must be configured before scheduled resolver runs can work.
Bounded historical provider fetch is deferred; the stale-window guard is the targeted safety fix.
Calibration metrics and outcome UI/API display are intentionally not implemented in Wave 4B.2.

## Next Recommended Steps
1. Review/merge this branch after approval.
2. Configure GitHub repository secret `SUPABASE_DB_URL`.
3. Optionally configure repository variable `RESOLVER_LIMIT=50`.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit secrets or env files.
Do not run migrations from Codex.
Do not add calibration metrics, UI, API routes, response schema fields, endpoints, dependencies, or trading capability.
Do not change quant/probability/score/gate/news/provider/auth/frontend logic for Wave 4B.2.
