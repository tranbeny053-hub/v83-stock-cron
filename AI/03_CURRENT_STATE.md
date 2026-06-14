# Current State

Updated: 2026-06-14

## Branch / Worktree

- Branch: `codex/wave4a2-deploy-cachebust`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 4A.2 Frontend Deploy/Cache Correctness.
- Current status: cache-bust and served-asset guard implemented and offline verification completed locally.
- Root cause: live browser/CDN/Hugging Face was serving a stale frontend bundle, not stale backend JSON.

## What Changed

- Added version query strings: `/styles.css?v=wave4a2-b9137ee` and `/app.js?v=wave4a2-b9137ee`.
- Added harmless frontend build marker: `UCPE_FRONTEND_BUILD = "wave4a2-cachebust"`.
- Strengthened frontend static tests for versioned assets, card probability rows, and absence of stale hidden-probability copy.
- Strengthened `scripts/manual_smoke.py` to GET `/`, parse the served app.js URL, fetch that URL including query string, and verify served app.js contents.
- Kept overview cards rendering `Up`, `Down`, and `Timeout` from backend `frontend_display`.
- Kept one global uncalibrated legend and no repeated per-card yellow note.

## Checks Run / Attempted

- `git checkout dev`: PASS.
- `git checkout -b codex/wave4a2-deploy-cachebust`: PASS.
- `git branch --show-current`: PASS, `codex/wave4a2-deploy-cachebust`.
- `git status --short --untracked-files=all -- .`: PASS before edits.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 18 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 156 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS, served frontend bundle verified at `/app.js?v=wave4a2-b9137ee`.
- Protected path diff: PASS, empty for quant, score_stack, gates, news, features, and `config/defaults.py`.
- Stale-string grep: PASS, no hits for the exact stale strings in frontend/tests/scripts after source cleanup.
- Probability-marker grep: PASS, markers present in `frontend/app.js`, frontend static tests, and manual smoke.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `RELEASE_GATE.md`
- `frontend/app.js`
- `frontend/index.html`
- `scripts/manual_smoke.py`
- `tests/frontend/test_frontend_static.py`

## Current Blockers / Unknowns

- No local implementation blocker is known after offline verification.
- Live Hugging Face deployment/browser hard-refresh verification still needs to be performed after merge/deploy.

## Next Steps

1. Send this cache-bust report for review.
2. After approval, merge into `dev` and deploy from the app root.
3. In live HF, use hard refresh/incognito and confirm cards show `Up`, `Down`, and `Timeout`.
