# Handoff Packet

## From / To

Codex to User / Claude

## Goal

UI-D1.1: add one deterministic, read-only top-level `decision_synthesis` block to
the analyze response so a later frontend task can render backend truth.

## Branch / Risk

- Branch: `codex/ui-d1-1-decision-synthesis`
- Base: `dev`
- Risk: additive response contract only; review before merge.

## Implementation

- Pure builder reads existing timeframe, probability, score/disposition, gate,
  epistemic, provider/data-quality, liquidity/execution, tail-risk, trend/regime,
  decision-brief, and in-payload reliability fields.
- Labels are limited to `AVOID`, `NO_TRADE`, `WAIT`, `WATCH`, `LONG_CANDIDATE`,
  and `SHORT_CANDIDATE`.
- Candidates are planning context only. Entry/chase permissions are always false;
  all numeric plan geometry is null with a required disabled reason.
- Model-quality output defaults to unavailable/null diagnostics without any database read.
- Future quant hooks are shadow-only with zero decision influence.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `schemas/response.schema.json`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/detail/decision_synthesis.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/detail/test_decision_synthesis.py`

## Verification

- Targeted tests: PASS, 19 passed.
- API tests: PASS, 36 passed.
- Full tests: PASS, 241 passed.
- Ruff, forbidden-scope, secret, full-article-body, schema, and manual smoke checks: PASS.
- Protected working-tree diff: empty.
- Targeted greps: reviewed and safe; forbidden-wording and mutation greps are empty.

## Boundaries Confirmed

- No frontend, endpoint, migration, dependency, lockfile, secret, or deployment change.
- No score, probability, gate, calibration, resolver, outcome, news-influence, or
  persistence mutation/read-path change.
- No merge, deploy, push, or migration performed.

## Risks / Next Steps

- Reliability remains insufficient and probabilities remain heuristic.
- Numeric trade-plan geometry remains intentionally unavailable.
- Next: Claude reviews the single commit; frontend rendering is a separately scoped task.
