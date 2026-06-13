# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4a-honesty-decision-clarity`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4A adds honesty and decision-clarity presentation over existing backend outputs.
No analysis math changed: scoring, probability, gates, execution realism, global risk, and news influence are untouched.
`news_influence_frac` remains `0.0`; news stays advisory-only.
No migrations, dependencies, merge, deploy, or Hugging Face push were performed by Codex.

## Latest App State
Backend analysis responses now include horizon labels and a schema-declared `decision_brief`.
Frontend cards show setup timeframe plus approximate multi-bar horizon.
The main UI shows an uncalibrated heuristic banner and Up/Down/Timeout explanation.
Detail Analysis renders `decision_brief` near the top and keeps raw JSON collapsed/debug-only.
The UI labels model readiness instead of presenting placeholder `confidence_frac` as true confidence.
Download JSON exports the already-received in-memory analysis payload.

## Implemented Components
- backend/detail: `build_horizon_context` and `build_decision_brief`.
- api/schema: `decision_brief` declared in Pydantic models and JSON Schema.
- detail: `decision_brief` mirrored into detail view sections.
- frontend: horizon labels, heuristic banner, probability explanation, structured decision brief renderer, Download JSON button.
- tests: API/schema checks for decision brief and frontend static checks for Wave 4A copy/export/no-confidence-display.
- docs: changelog, release gate, current state, handoff, implementation memory.

## Files Changed By Area
- api/schema: `src/crypto_probability_engine/api/analysis_service.py`, `src/crypto_probability_engine/api/schemas.py`, `schemas/response.schema.json`, `schemas/detail_view.schema.json`
- detail/frontend display: `src/crypto_probability_engine/detail/decision_brief.py`, `builder.py`, `frontend_display.py`
- frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- tests: `tests/api/test_analysis_endpoints.py`, `tests/fixtures/sample_payloads.py`, `tests/frontend/test_frontend_static.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
Wave 4A is display/clarity only; no score/probability/gate/news math changes.
`decision_brief.action` may only be `NO_TRADE`, `WATCHLIST`, or `SPOT_WATCH`.
`decision_brief.profitability_claim` is constrained to `false`.
The UI must not present `confidence_frac` as measured confidence while reliability is not measured.
Download JSON uses the current in-memory payload and does not create a new backend endpoint.
Raw JSON remains available only as collapsed/debug-only detail.

## Commands Run And Results
- `git branch --show-current`: PASS, `codex/wave4a-honesty-decision-clarity`.
- `git log --oneline --decorate -8`: PASS before branch creation; `dev` HEAD was `f53b9bb merge: wave3a news provider rate-limit diagnostics`.
- `git status --short --untracked-files=all -- .`: PASS, clean before branch creation; later only intended Wave 4A files before commit.
- `git checkout -b codex/wave4a-honesty-decision-clarity`: PASS, branch created from `dev`.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 32 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 16 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 154 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `git diff --stat dev -- src/crypto_probability_engine/quant src/crypto_probability_engine/score_stack src/crypto_probability_engine/gates src/crypto_probability_engine/news`: PASS, empty.
- Targeted forbidden setup grep: PASS, no hits.
- Targeted forbidden capability grep: PASS with expected negative UI copy: "No account actions or autonomous execution."
- Targeted secret-name grep: PASS with expected backend-only config/adapter/test references; no frontend secret exposure or real values.
- Targeted full-body grep: PASS with expected sanitizer/news-contract/test references; dedicated checker passed.
- Targeted confidence/model-readiness grep: PASS; frontend uses model readiness copy and does not reference `confidence_frac`.
- `git diff --check -- .`: PASS.

## Known Blockers
No local implementation blocker is known after offline verification.
No merge/deploy/push has been performed.
Manual browser UI smoke was not run in this Codex turn.

## Open Risks
Wave 4A changes the response contract by adding `decision_brief`, so consumers should be reviewed before merge.
The existing warning set remains: `jsonschema.RefResolver` and Starlette TestClient cookie deprecations.
The app remains heuristic and uncalibrated; Wave 4A clarifies that but does not add calibration.

## Next Recommended Steps
1. Send this Wave 4A report to Claude/light review.
2. After approval, merge `codex/wave4a-honesty-decision-clarity` into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not change scoring, probability, gates, execution realism, global risk, or news influence without Claude-approved spec.
Do not store, render, scrape, or fetch full article bodies.
Do not deploy or push to Hugging Face without explicit approval.
