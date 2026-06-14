# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave4a2-restore-card-probabilities`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 4A.2 corrects the Wave 4A.1 product decision by restoring Up/Down/Timeout percentages on overview cards.
The repeated per-card yellow explanatory note remains removed, and the single global uncalibrated legend remains.
No quant/probability/score/gate/news/features/defaults logic changed.
No migrations, dependencies, merge, deploy, or Hugging Face push were performed by Codex.

## Latest App State
Overview cards display backend `frontend_display.prob_up_pct`, `prob_down_pct`, and `prob_timeout_pct`.
The qualitative Wave 4A.1 replacement rows are removed.
Detail Analysis still shows full probability breakdown.
Download JSON and Decision Brief remain unchanged.

## Implemented Components
- frontend: removed qualitative card probability helper path.
- frontend: restored direct Up/Down/Timeout rows in `overviewCard`.
- tests: updated frontend static coverage for restored card probability rows and no qualitative replacement.
- docs: changelog, release gate, current state, handoff, implementation memory.

## Files Changed By Area
- frontend: `frontend/app.js`
- tests: `tests/frontend/test_frontend_static.py`
- docs: `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `CHANGELOG.md`, `RELEASE_GATE.md`

## Important Decisions
Overview cards should show backend-provided Up/Down/Timeout percentages.
The global uncalibrated legend remains the honesty context.
The repeated per-card yellow explanatory note stays removed.
No backend/schema/math change is needed or allowed for this correction.

## Commands Run And Results
- `git checkout dev`: PASS.
- `git checkout -b codex/wave4a2-restore-card-probabilities`: PASS.
- `git branch --show-current`: PASS, `codex/wave4a2-restore-card-probabilities`.
- `git status --short --untracked-files=all -- .`: PASS before edits.
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
- Protected path diff: PASS, empty for quant, score_stack, gates, news, features, and `config/defaults.py`.

## Known Blockers
No local implementation blocker is known after offline verification.
No merge/deploy/push has been performed.
Manual browser UI smoke was not run in this Codex turn.

## Open Risks
Existing warnings remain: `jsonschema.RefResolver` and Starlette TestClient cookie deprecations.
Claude/User review is required before merge/deploy.

## Next Recommended Steps
1. Send this Wave 4A.2 report to Claude final review.
2. After approval, merge `codex/wave4a2-restore-card-probabilities` into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit secrets or env files.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not change quant/probability/score/gates/features/news/config defaults in this frontend correction branch.
Do not deploy or push to Hugging Face without explicit approval.
