# Handoff Packet

## Goal / Branch

- Goal: UI-D1.4A session-guarded, cached, read-only calibration diagnostics endpoint.
- Branch: `codex/ui-d1-4a-calibration-endpoint`
- Base: `dev` at `3d30c8b`
- Risk: backend read-only DB diagnostic; review before merge.

## Endpoint Contract

- `GET /v1/calibration`, protected by the existing app session guard.
- Filters: timeframe, model version, methodology version, bounded limit, bucket opt-in.
- No timeframe returns `15m`, `1H`, `4H`, `1D`, `1W`, `1M` in order.
- Success returns strict sanitized per-timeframe sample gates, quality metrics, optional
  buckets, outcome distribution, and version context from `build_calibration_report`.
- Failure/non-Postgres source returns HTTP 200 `UNAVAILABLE`, empty timeframe data, one
  safe warning, and exception class name only.
- Cache: in-process, 60-second monotonic TTL; key includes every query input.

## Boundaries Confirmed

- Calibration service/metrics and persistence repository are unchanged.
- No prediction/outcome mutation, resolver call, migration, frontend change, dependency,
  endpoint expansion, or `/v1/analyze` read was added.
- No connection string, environment value, exception message, SQL, or stack detail is
  exposed.
- `top_label_hit_rate` remains a diagnostic field and is not relabeled.

## Verification

- Endpoint tests: PASS, 10 passed.
- Full pytest: PASS, 270 passed; 7 existing warnings.
- Ruff and all requested safeguards/schema/manual-smoke commands: PASS.
- Protected diff: empty.
- Secret/unsafe/mutation greps: empty; diagnostic wording hits are safely negated.
- Service/auth reuse grep: expected hits.

## Operations / Next Step

- HF needs `SUPABASE_DB_URL` for live `SUPABASE_POSTGRES` diagnostics; never expose its
  value. Missing/unavailable configuration safely yields `UNAVAILABLE`.
- No merge, deploy, push, or migration performed.
- Next: Claude review, then separately scoped UI-D1.4B frontend consumption.
