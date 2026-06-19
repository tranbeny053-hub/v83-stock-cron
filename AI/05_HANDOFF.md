# Handoff Packet

## From / To

Codex to User / Claude

## Goal

UI-D1.2: render the existing top-level `decision_synthesis` block first inside the
shared structured Detail view, without frontend decision inference.

## Branch / Risk

- Branch: `codex/ui-d1-2-decision-tab`
- Base: `dev` at `d2046e9`
- Risk: frontend presentation only; review before merge.

## Implementation

- The first Detail block is now `Decision`; all prior Overview, Decision Brief,
  Probability, Risk, data, provider, quant, news, and debug sections remain below it.
- Final card renders the backend label/strength/explanation and explicit entry, plan,
  and chase permissions.
- Primary reason is the first priority-ordered backend `BLOCK`, then `WARN`, then
  backend source action/disposition.
- Actionability rows render all backend checks, with BLOCK rows visually dominant.
- Probability is secondary, supports hide-by-default raw values, and displays the
  backend informational-only/reliability warning.
- Reliability uses backend explanation/status fields and only displays non-null sample
  metadata.
- Disabled plan rendering never reads or displays numeric zone fields.
- Missing synthesis renders a safe unavailable note plus existing brief fields.
- No overview chip was added; this keeps the change limited to Detail rendering.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/frontend/test_frontend_static.py`

## Verification

- Frontend tests: PASS, 25 passed.
- Full tests: PASS, 248 passed with 6 existing deprecation warnings.
- Ruff, syntax parse, forbidden-scope, secret, full-article-body, schema, and manual
  smoke checks: PASS.
- Visual QA: PASS for normal and hard-gated local fixtures.
- Hard-gated fixture: `No trade`; permissions `No / Observe only / No`; hard-gate and
  tail-risk BLOCK rows dominant; probability informational-only; no raw null display.
- Protected backend/schema diffs: empty.
- Unsafe-wording and client-inference greps: empty; contract grep has required hits.

## Boundaries Confirmed

- No backend, schema, endpoint, migration, dependency, lockfile, secret, deployment,
  methodology, navigation-tab, or analyze-flow change.
- No decision label, enter-now permission, chase permission, risk number, or trade zone
  is inferred in the client.
- No merge, deploy, push, or migration performed.

## Risks / Next Steps

- Probabilities remain heuristic and reliability remains insufficient.
- Numeric plan geometry remains intentionally disabled.
- Next: Claude reviews the single commit; merge remains user-approved and separate.
