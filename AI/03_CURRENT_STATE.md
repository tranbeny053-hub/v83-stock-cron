# Current State

Updated: 2026-06-20

## Branch / Scope

- Branch: `codex/ui-d1-4a-calibration-endpoint`
- Base: `dev` at merged UI-D1.4-FE milestone `3d30c8b`
- Scope: read-only calibration API adapter, response schemas, API tests, and handoff docs
- Status: implemented and locally verified; not merged, deployed, or pushed
- Migration status: none added or run

## UI-D1.4A Implementation

- Added session-guarded `GET /v1/calibration` using the same app-session dependency as
  `/v1/analyze`.
- Supports optional timeframe (`15m`, `1H`, `4H`, `1D`, `1W`, `1M`), model version,
  methodology version, bounded limit (`1..5000`), and opt-in reliability buckets.
- Omitting timeframe returns all six timeframes in the approved order.
- Reuses `calibration.service.build_calibration_report` unchanged and maps only known
  diagnostic fields into strict response models.
- Requires the service report source to be `SUPABASE_POSTGRES`; missing/unavailable or
  unsupported repository paths return controlled HTTP 200 `UNAVAILABLE`.
- Added a 60-second in-process monotonic TTL cache keyed by timeframe/all, model version,
  methodology version, limit, and bucket inclusion, plus a test clear helper.
- Exceptions expose only their class name. Messages, connection strings, environment
  values, SQL, and stack details are never returned.

## Safety Invariants

- Backend-only and read-only; no frontend, migration, dependency, or persistence change.
- No calibration math, metrics, repository, resolver, outcome, scoring, probability, gate,
  news, Quant V2, or `/v1/analyze` methodology-path change.
- No prediction or outcome write path is called or referenced by the endpoint.
- The response labels `top_label_hit_rate` as an early diagnostic, never as accuracy.
- All reliability/profitability/EV wording is explicitly negated.
- Expected calibration unavailability returns HTTP 200 with sanitized `UNAVAILABLE`.

## Verification

- Endpoint tests: PASS, 10 passed with 1 existing TestClient cookie warning.
- Full suite: PASS, 270 passed with 7 existing deprecation warnings.
- Ruff: PASS.
- Forbidden-scope, secret, full-article-body, schema, and manual smoke checks: PASS.
- Protected calibration/repository/quant/gate/score/features/detail/news/resolver/migration/
  frontend diff: empty.
- Secret, forbidden-wording, and mutation greps: empty.
- Quality-wording grep contains only the intended negated safety sentence/assertions.
- Service/auth reuse grep confirms `build_calibration_report` and `require_app_session`.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/calibration_endpoint.py`
- `src/crypto_probability_engine/api/schemas.py`
- `tests/api/test_calibration_endpoint.py`

## Files Read but Not Changed

- `AGENTS.md`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/04_TASK_BOARD.md`
- `AI/06_TEST_COMMANDS.md`
- `IMPLEMENTATION_SPEC.md`
- `src/crypto_probability_engine/calibration/service.py`
- `src/crypto_probability_engine/calibration/schemas.py`
- `src/crypto_probability_engine/calibration/metrics.py`
- `src/crypto_probability_engine/persistence/repository.py`
- Existing API/auth/calibration tests and shared test fixtures

## Operations / Risks / Next Step

- Hugging Face Space needs `SUPABASE_DB_URL` for real `SUPABASE_POSTGRES` diagnostics.
  The value must remain secret and must never be logged or returned.
- If database configuration or access is absent/unavailable, the endpoint safely returns
  `UNAVAILABLE`; existing heuristic UI status remains the fallback.
- The endpoint performs synchronous diagnostic reads only on its dedicated cached route;
  `/v1/analyze` remains DB-light.
- Next: Claude reviews the single commit before any merge or UI-D1.4B work.
