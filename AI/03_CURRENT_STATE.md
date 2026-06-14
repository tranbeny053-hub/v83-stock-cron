# Current State

Updated: 2026-06-14

## Branch / Worktree

- Branch: `codex/wave4a2-restore-card-probabilities`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 4A.2 Restore Card Probability Display.
- Current status: frontend display correction implemented and offline verification completed locally.
- Scope: frontend/display-layer only. No scoring, probability, gate, features, config/defaults, or news logic changed.

## What Changed

- Restored overview-card `Up`, `Down`, and `Timeout` percentage rows from backend `frontend_display`.
- Removed the Wave 4A.1 qualitative replacement rows: `Probability: ... uncalibrated — see Detail` and `Breakdown: Open Detail for full probability breakdown`.
- Kept the repeated per-card yellow explanatory note removed.
- Kept exactly one global uncalibrated legend.
- Kept model readiness label, Detail full probability breakdown, Download JSON, and Decision Brief unchanged.
- Updated frontend static tests for restored card percentages and no qualitative replacement rows.

## Checks Run / Attempted

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

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `RELEASE_GATE.md`
- `frontend/app.js`
- `tests/frontend/test_frontend_static.py`

## Current Blockers / Unknowns

- No local implementation blocker is known after offline verification.
- Manual browser UI smoke was not run in this Codex turn.
- Claude/User review is still required before merge/deploy.

## Next Steps

1. Send this Wave 4A.2 report to Claude final review.
2. After approval, merge `codex/wave4a2-restore-card-probabilities` into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.
