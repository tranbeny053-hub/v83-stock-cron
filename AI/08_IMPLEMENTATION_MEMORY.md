# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4a1-honesty-declutter`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4A.1 is a frontend/display-layer hotfix after Wave 4A live feedback.
The hotfix removes repeated per-card explanatory noise and hides fake-precise card probability triplets while the model is uncalibrated.
Full percentages remain available in Detail.
No quant/probability/score/gate/news/features/defaults logic changed.
No migrations, dependencies, merge, deploy, or Hugging Face push were performed by Codex.

## Latest App State
The app shell has one compact global uncalibrated heuristic legend.
Single, Batch, and Watchlist cards reuse `overviewCard`, which now shows qualitative uncalibrated status from existing `decision_brief.action`.
Overview cards do not show precise Up/Down/Timeout rows while `calibration_status=DEFAULT_PHASE1A`, `reliability_status=INSUFFICIENT_SAMPLE`, or `model_readiness=HEURISTIC_UNCALIBRATED`.
Detail Analysis still shows full Up/Down/Timeout percentages and explanation.
Download JSON and Decision Brief are unchanged and still visible.

## Implemented Components
- frontend: global legend copy in `index.html`.
- frontend: card-level `isUncalibratedPayload`, `qualitativeCardLean`, and `cardProbabilityRows` helpers in `app.js`.
- frontend: removed per-card `probability-explainer compact` append.
- styling: reduced card minimum height and simplified legend styling.
- tests: frontend static coverage for exactly one legend, no per-card note, qualitative uncalibrated copy, Detail-only percentages, Download JSON, and Decision Brief.
- docs: changelog, release gate, implementation decisions, current state, handoff, implementation memory.

## Files Changed By Area
- frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- tests: `tests/frontend/test_frontend_static.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `IMPLEMENTATION_DECISIONS.md`, `RELEASE_GATE.md`

## Important Decisions
Wave 4A.1 is display-only; do not change math to make uncalibrated numbers look nicer.
Overview cards hide precise probability triplets while uncalibrated, but Detail keeps full numeric inspection.
Qualitative card text is derived from existing `decision_brief.action`.
Deferred to later reviewed work: tanh gain saturation, timeout cap behavior, realized-volatility scaling, tail CVaR broad breach behavior, and score ceiling/collapse artifacts.

## Commands Run And Results
- `git checkout dev`: PASS.
- `git status --short --untracked-files=all -- .`: PASS, clean before branch creation.
- `git checkout -b codex/wave4a1-honesty-declutter`: PASS.
- `git branch --show-current`: PASS, `codex/wave4a1-honesty-declutter`.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 32 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 155 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Protected path scope diff: PASS, no diff in quant, score_stack, gates, news, features, or `config/defaults.py`.
- Targeted forbidden setup grep: PASS, no hits.
- Targeted forbidden capability grep: PASS with expected negative UI copy: "No account actions or autonomous execution."
- Targeted secret-name grep: PASS with expected backend-only config/adapter/test references; no frontend secret exposure or real values.
- Targeted full-body grep: PASS with expected sanitizer/news-contract/test references; dedicated checker passed.
- Targeted old-note grep: PASS with expected fixture/detail payload references only; no frontend hits.
- Targeted probability display grep: PASS with Detail-only percentage rows and frontend tests proving cards hide precise triplets while uncalibrated.

## Known Blockers
No local implementation blocker is known after offline verification.
No merge/deploy/push has been performed.
Manual browser UI smoke was not run in this Codex turn.

## Open Risks
This hotfix improves display honesty but does not solve underlying uncalibrated quant artifacts.
Existing warnings remain: `jsonschema.RefResolver` and Starlette TestClient cookie deprecations.
Claude/User review is required before merge/deploy.

## Next Recommended Steps
1. Send this Wave 4A.1 report to Claude final review.
2. After approval, merge `codex/wave4a1-honesty-declutter` into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not change scoring, probability, gates, execution realism, global risk, or news influence without Claude-approved spec.
Do not change quant/config/defaults to make uncalibrated numbers look nicer in this branch.
Do not store, render, scrape, or fetch full article bodies.
Do not deploy or push to Hugging Face without explicit approval.
