# Current State

Updated: 2026-06-20

## Branch / Scope

- Branch: `codex/ui-d1-4b-calibration-metrics`
- Base: `dev` at merged UI-D1.4A milestone `e947ab3`
- Scope: frontend calibration rendering/static tests plus required handoff docs
- Status: implemented and locally verified; not merged, deployed, or pushed
- Migration status: none added or run

## UI-D1.4B Implementation

- Existing Decision section remains first and renders synchronously.
- Existing payload-only Model Quality summary and education layer remain intact.
- Model Quality now mounts a loading placeholder, then requests `GET /v1/calibration` once
  for the endpoint's all-timeframe response after Detail is rendered.
- Added a module-level 60-second cache for the full endpoint response and one shared
  in-flight request; safe unavailable responses are cached to prevent aggressive retries.
- Added backend-driven per-timeframe cards with dominant sample-gate badges, resolved and
  valid sample counts, reliability status, Brier score, log loss, diagnostic top-label hit
  rate, outcome distribution, version-mix warning, advanced version context, and warning.
- Null/non-numeric metrics render as an em dash; zero is shown only when supplied as a
  numeric backend value.
- Network, session, API, empty, and `UNAVAILABLE` states render a quiet heuristic fallback
  without exposing error details.
- Asset version is `ui-d1-4b-calibration-metrics`.

## Safety Invariants

- Frontend-only; no backend, schema, endpoint, calibration, scoring, probability, gate,
  resolver, outcome, prediction, migration, dependency, or secret change.
- Calibration fields are referenced only in the isolated diagnostics renderer; they never
  enter decision labels, permissions, candidates, gate actions, tactical alignment, or
  probability presentation.
- No timeframe samples are pooled and no timeframe borrows readiness from another.
- Hard gates and backend Decision remain authoritative.
- Diagnostic wording explicitly says not accuracy, not profitability evidence, and not EV.
- No direct database client, connection string, environment name, or credential is present
  in frontend code.
- Existing text-containment rules are extended to diagnostics cards and mobile layouts;
  important text is wrapped rather than clipped.

## Current Backend-Reported State

The renderer does not hardcode these values. With the currently observed endpoint payload,
it displays: `15m` 93 insufficient, `1H` 83 insufficient, `4H` 72 insufficient, `1D` 8
insufficient, `1W` 0 no samples, and `1M` 0 no samples. No timeframe is measured yet.

## Verification

- Frontend static tests: PASS, 44 passed.
- Full suite: PASS, 277 passed with 7 existing deprecation warnings.
- Bundled Node syntax check: PASS.
- Ruff: PASS.
- Forbidden-scope, secret, full-article-body, schema, and manual smoke checks: PASS.
- Manual smoke confirmed the versioned frontend bundle.
- Protected `src`, `scripts`, `migrations`, and `schemas` diffs: empty.
- Targeted unsafe-wording and frontend database/secret greps: empty.
- Accuracy grep contains only explicitly negated safety copy.
- Calibration field/fetch and version greps contain expected references.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/frontend/test_frontend_static.py`

## Files Read but Not Changed

- `AGENTS.md`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/04_TASK_BOARD.md`
- `AI/06_TEST_COMMANDS.md`
- `IMPLEMENTATION_SPEC.md`

## Risks / Next Step

- Diagnostics can be up to 60 seconds old by design; they remain informational only.
- An unavailable/expired session displays heuristic fallback and does not disturb Detail.
- Live endpoint rendering was not exercised with real credentials; static, full-suite, and
  offline smoke verification passed without secrets.
- Next: Claude reviews the single commit before merge/deployment.
