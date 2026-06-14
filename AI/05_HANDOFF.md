# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4A.2 Restore Card Probability Display: restore overview-card Up/Down/Timeout percentages while keeping the per-card yellow note removed and one global uncalibrated legend.

## Current Branch / Worktree
`codex/wave4a2-restore-card-probabilities` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R1 frontend/display-layer correction. No score, probability, gates, features, config/defaults, news, schema, persistence, deployment, or migration behavior changed.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `RELEASE_GATE.md`
- `frontend/app.js`
- `tests/frontend/test_frontend_static.py`

## Commands Run
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

## What Works Now
- Overview cards show `Up`, `Down`, and `Timeout` percentages again.
- Overview cards no longer show the qualitative replacement text from Wave 4A.1.
- The repeated per-card yellow explanatory note remains removed.
- The single global uncalibrated legend remains visible.
- Detail full probability breakdown remains unchanged.
- Download JSON and Decision Brief remain unchanged.

## What Is Still Broken / Unknown
- No browser/manual UI smoke was run in this turn.
- Claude/User review is still required before merge/deploy.
- Existing warnings remain: `jsonschema.RefResolver` deprecation and Starlette TestClient cookie deprecation warnings.

## Next 3 Steps
1. User sends this report to Claude final review.
2. After approval, merge the branch into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not change quant/probability/score/gates/features/news/config defaults in this frontend correction branch.
- Do not deploy or push to Hugging Face without explicit approval.
