# Current State

Updated: 2026-06-15

## Branch / Worktree

- Branch: `codex/wave4b2-outcome-resolver`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face
- Migration status: `migrations/0004_prediction_outcomes.sql` created but not run by Codex

## Current Phase

- Phase: Wave 4B.2 Outcome Resolver.
- Risk: standalone persistence/resolver foundation; no API route, UI, schema-response, calibration metric, or quant/news change.
- Current status: implementation complete, full local verification passed, not merged/deployed.

## What Changed

- Added idempotent `prediction_outcomes` migration with immutable `prediction_id` primary key and outcome lookup index.
- Added `RESOLVER_VERSION = "resolver-v1-wave4b2"`.
- Added `fetch_due_unresolved_predictions(now_utc, limit)` and `save_prediction_outcome(row)` to in-memory, direct Postgres, and Supabase REST repositories.
- Outcome writes are immutable/idempotent: in-memory does not overwrite, Postgres uses `ON CONFLICT (prediction_id) DO NOTHING`, REST uses `resolution=ignore-duplicates`.
- Added standalone `scripts/resolve_outcomes.py`; it is not imported by `api/**` and is not called by `/v1/analyze`.
- Resolver labels due predictions as `UP`, `DOWN`, or `TIMEOUT` from post-anchor closed candles only, using frozen `decision_band_frac` or fallback `2 * taker_fee_frac`.
- Added Claude targeted-fix stale-window guard: if the first available outcome candle is more than one timeframe after `horizon_end_utc`, the resolver skips and writes no outcome.
- Added operator-wiring bugfix: `scripts/resolve_outcomes.py` now uses a resolver-specific repository builder that prefers `SUPABASE_DB_URL` / direct Postgres over Supabase REST when both are configured.
- Resolver CLI output now includes safe diagnostics: `repository=...` and `limit=...`; it does not print connection strings or keys.
- Added Postgres due-query bugfix: direct Postgres due fetch now uses the verified `public.predictions` left join `public.prediction_outcomes` query, supports mapping/tuple rows, and surfaces sanitized DB failure instead of fake empty `due=0`.
- Added final repository wrapper bugfix: Postgres due fetch now uses a direct psycopg connection instead of the `psycopg_pool`-backed `_run_db` wrapper, matching the standalone operator probe path.
- Added final timeout-bind bugfix: Postgres `SET LOCAL statement_timeout` now uses an internal integer literal instead of bound parameters in both `_run_db` and resolver due-fetch paths.
- Added direct outcome-write bugfix: `SupabasePersistenceRepository.save_prediction_outcome` now uses direct psycopg with `ON CONFLICT (prediction_id) DO NOTHING` and sanitized phase-labelled failures instead of relying on `psycopg_pool`.
- Added offline tests for due query behavior, no-lookahead filtering, unfinished-horizon skip, UP/DOWN/TIMEOUT labeling, immutable writes, REST/Postgres non-overwrite semantics, failure isolation, and API isolation.

## Checks Run / Attempted

- `git checkout dev`: PASS.
- `git status --short --untracked-files=all -- .`: PASS before branch creation, clean.
- `git checkout -b codex/wave4b2-outcome-resolver`: PASS.
- `PYTHONPATH=src python3 -m pytest tests/resolver -q`: PASS, 10 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 29 passed after targeted fix.
- `PYTHONPATH=src python3 -m pytest tests/resolver tests/persistence -q`: PASS, 33 passed after operator-wiring fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 36 passed after Postgres due-query fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 38 passed after direct Postgres due-fetch wrapper fix.
- `PYTHONPATH=src python3 -m pytest tests/persistence tests/resolver -q`: PASS, 40 passed after timeout-bind/outcome-write fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 185 passed with 4 existing warnings after targeted fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 189 passed with 4 existing warnings after operator-wiring fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 192 passed with 4 existing warnings after Postgres due-query fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 194 passed with 4 existing warnings after direct Postgres due-fetch wrapper fix.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 196 passed with 4 existing warnings after timeout-bind/outcome-write fix.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS; offline smoke and served frontend bundle guard passed.
- Protected working-tree diff for API, quant, score stack, gates, news, frontend, and `api/schemas.py`: PASS, empty.
- Targeted greps: PASS; resolver/API import grep empty; destructive prediction mutation grep has only migration test assertions; secret/full-body/forbidden capability greps show existing backend/test/checker names only and no new unsafe implementation.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `migrations/0004_prediction_outcomes.sql`
- `scripts/resolve_outcomes.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/persistence/test_persistence_foundation.py`
- `tests/resolver/test_resolve_outcomes.py`

## Current Blockers / Unknowns

- No local implementation blocker is known.
- Bounded historical provider fetch was deferred to avoid widening the targeted fix; stale-window skip prevents wrong immutable labels.
- Migration was created but not applied.
- Wave 4B calibration metrics, resolver scheduling, and UI/API display are intentionally not implemented.

## Next Steps

1. Commit `fix: fetch due rows correctly from postgres repository`.
2. Run the operator resolver locally with `PYTHONPATH=src python3 scripts/resolve_outcomes.py --limit 10`.
3. Apply `migrations/0004_prediction_outcomes.sql` only after approval.
