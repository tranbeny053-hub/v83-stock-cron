# Handoff Packet

## Goal / Branch

- Goal: UI-D1.4B render real endpoint calibration diagnostics in Model Quality.
- Branch: `codex/ui-d1-4b-calibration-metrics`
- Base: `dev` at `e947ab3`
- Risk: frontend render-only; review before merge.

## Implementation

- Calls `api("/v1/calibration")` once for all timeframes when Detail mounts.
- Decision and the existing Model Quality summary render before the asynchronous request.
- Full responses and safe failure states use a 60-second frontend cache; concurrent Detail
  opens share one in-flight request.
- `OK` renders one backend-driven card per returned timeframe with sample-gate dominance,
  metrics, outcomes, optional valid count, version warning/context, and backend warning.
- `UNAVAILABLE` or request failure renders: calibration diagnostics unavailable; keep using
  heuristic status. Error class/message details are not displayed.
- Null metrics render as an em dash, while backend numeric zero remains visible.
- Asset query strings and app build stamp are `ui-d1-4b-calibration-metrics`.

## Boundaries Confirmed

- No backend/schema/calibration/math/score/probability/gate/resolver/persistence/frontend-
  secret contract change and no new endpoint.
- Calibration diagnostics do not affect Decision, hard gates, permissions, candidates,
  probability, or cross-timeframe readiness.
- No per-timeframe request fan-out, bucket request, sample pooling, direct database access,
  embedded secret, or error-detail rendering.
- Diagnostic top-label hit rate is not relabeled as accuracy.

## Verification

- Frontend tests: PASS, 44 passed.
- Full pytest: PASS, 277 passed; 7 existing warnings.
- JavaScript syntax, Ruff, safeguards, schema validation, and manual smoke: PASS.
- Protected backend/schema/script/migration diffs: empty.
- Unsafe wording and direct database/secret greps: empty; expected fetch/field/version hits.

## Current Endpoint Display / Next Step

- Current reported rows: 15m 93 insufficient; 1H 83 insufficient; 4H 72 insufficient;
  1D 8 insufficient; 1W and 1M 0/no samples. Values are fetched, never hardcoded.
- No merge, deploy, push, or migration performed.
- Next: Claude review before the user separately approves merge/deployment.
