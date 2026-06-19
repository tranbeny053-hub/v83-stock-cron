# Handoff Packet

## From / To

Codex to User / Claude

## Goal

UI-D1.3: reorganize stored single/watchlist timeframe payloads into a Tactical Horizon
Matrix and Regime Context without adding frontend decision logic.

## Branch / Risk

- Branch: `codex/ui-d1-3-tactical-matrix`
- Base: `dev` at `a5b0ddd`
- Risk: frontend render-only; review before merge.

## Implementation

- Tactical group: `15m`, `1H`, `4H` in fixed display order.
- Regime group: `1D`, `1W`, `1M` in fixed display order and quieter styling.
- Grouping prefers backend `timeframe_role.tactical`, with approved timeframe fallback.
- Cards render backend role/context, decision label, permissions, interpretation,
  directional edge, actionability concern, reliability, and informational-only state.
- Any backend BLOCK creates a dominant card banner and probability remains muted.
- 1W/1M raw Up/Down/Timeout values are collapsed under advanced uncalibrated context.
- Tactical alignment uses only backend labels, BLOCK statuses, and reliability state;
  it never uses probability math and never emits an action.
- Missing/errored tactical payloads preserve the card slot and force unavailable alignment.
- Existing Detail click behavior and Decision-first Detail view are unchanged.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/frontend/test_frontend_static.py`

## Verification

- Frontend tests: PASS, 32 passed.
- Full tests: PASS, 255 passed with 6 existing deprecation warnings.
- Ruff, syntax parse, forbidden-scope, secret, full-article-body, schema, and manual
  smoke checks: PASS.
- Normal visual QA: exact group order, 1W/1M collapsed, alignment `insufficient`.
- Hard-gated visual QA: alignment `blocked`, BLOCK dominance, muted informational-only
  probability, all entry/chase permissions `No`, no raw null.
- Protected backend/schema diffs: empty.
- Unsafe-wording and client-inference greps: empty; grouping/version grep has hits.

## Boundaries Confirmed

- No backend, schema, endpoint, migration, dependency, lockfile, secret, deployment,
  methodology, navigation, or Detail-flow change.
- No raw-probability alignment math, decision-label inference, permission inference,
  cross-timeframe readiness borrowing, or numeric trade-plan rendering.
- No merge, deploy, push, or migration performed.

## Risks / Next Steps

- Probabilities remain heuristic and reliability remains insufficient.
- Regime cards are context, not equal tactical forecasts.
- Next: Claude reviews the single commit; merge remains user-approved and separate.
