# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4a2-deploy-cachebust`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4A.2 deploy/cache fix addresses stale deployed frontend assets after restoring card probabilities.
Root cause is stale served/cached `app.js`, not backend JSON.
No quant/probability/score/gate/news/features/defaults logic changed.
No migrations, dependencies, merge, deploy, or Hugging Face push were performed by Codex.

## Latest App State
`frontend/index.html` references `/styles.css?v=wave4a2-b9137ee` and `/app.js?v=wave4a2-b9137ee`.
`frontend/app.js` includes `UCPE_FRONTEND_BUILD = "wave4a2-cachebust"`.
Overview cards render `Up`, `Down`, and `Timeout` percentage rows from `frontend_display`.
Manual smoke now verifies the actually served app.js bundle from the TestClient app.

## Implemented Components
- frontend cache bust: versioned CSS and JS URLs in `index.html`.
- frontend marker: harmless `UCPE_FRONTEND_BUILD` constant.
- tests: static asset version checks and stale-copy regression checks.
- smoke: served HTML/app.js fetch with query-string preservation and stale-copy rejection.
- docs: changelog, release gate, current state, handoff, implementation memory.

## Files Changed By Area
- frontend: `frontend/index.html`, `frontend/app.js`
- scripts: `scripts/manual_smoke.py`
- tests: `tests/frontend/test_frontend_static.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
Use a static version string, not runtime env/secret injection.
Manual smoke must verify the served asset, not only source files or API routes.
Do not change backend math or schemas for this cache/deploy correctness fix.
Live deploy validation should use hard refresh/incognito and confirm cards show `Up`, `Down`, and `Timeout`.

## Commands Run And Results
- `git checkout dev`: PASS.
- `git checkout -b codex/wave4a2-deploy-cachebust`: PASS.
- `git branch --show-current`: PASS, `codex/wave4a2-deploy-cachebust`.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 18 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 156 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS, served frontend bundle verified at `/app.js?v=wave4a2-b9137ee`.
- Protected path diff: PASS, empty for quant, score_stack, gates, news, features, and `config/defaults.py`.
- Targeted stale-string grep: PASS, no exact stale-string hits in frontend/tests/scripts after source cleanup.
- Targeted probability-marker grep: PASS, markers present in app.js, frontend tests, and manual smoke.

## Known Blockers
No local implementation blocker is known after offline verification.
No merge/deploy/push has been performed.

## Open Risks
Live HF/browser cache must still be verified after deployment.
Existing warnings remain: `jsonschema.RefResolver` and Starlette TestClient cookie deprecations.

## Next Recommended Steps
1. Review and merge this branch into `dev`.
2. Deploy/push the app root to Hugging Face.
3. Hard refresh/incognito the live app and confirm overview cards show `Up`, `Down`, and `Timeout`.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit secrets or env files.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not change quant/probability/score/gates/features/news/config defaults for this cache fix.
Do not deploy or push to Hugging Face without explicit approval.
