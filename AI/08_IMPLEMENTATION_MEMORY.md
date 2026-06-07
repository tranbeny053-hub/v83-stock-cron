# Implementation Memory

## Context-Resume Summary
The app is on `dev` after Sprint 3 and a deployed frontend polish hotfix.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Hugging Face deployment smoke had succeeded before this pass.
This hotfix is frontend-only: six heat bands, Batch Detail visibility, and site-wide Kha signature.
No backend quant/scoring/gates/news/auth/deploy/provider logic was changed.
Full offline pytest, ruff, safety scripts, schema validation, and manual smoke pass after the hotfix.
No deploy/push to Hugging Face was performed by Codex.
Next step is user approval, then push only the app root to the HF Space.

## Latest App State
Default data mode remains live public market data, with explicit fixture mode only through `UCPE_DATA_MODE=fixture`.
Supported timeframes remain `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
Single Analysis still renders six progressive timeframe cards.
Card heat styling now uses six discrete backend-score bands from `frontend_display.total_score`.
Batch Analysis cards now open structured Detail Analysis through the shared detail panel.
Detail fetch uses `/v1/analyze/detail/{run_id}` and falls back to embedded `detail_view`.
Raw JSON remains collapsed/debug-only.
Footer signature is visible in normal page flow: `Copyright © 2026 by Kha`.

## Implemented Components
- api: unchanged.
- adapters: unchanged.
- validation: unchanged.
- quant: unchanged.
- news: unchanged; no live fetching added.
- frontend: score heat bands, shared detail panel outside Single tab, batch detail fallback behavior, footer signature.
- config: unchanged.
- docs: current state, handoff, memory, changelog updated for hotfix.
- tests: frontend static tests updated for heat bands, batch detail wiring, raw JSON collapsed state, no-recompute, and signature.
- deployment: unchanged; no deploy/push.

## Files Changed By Area
- frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- tests: `tests/frontend/test_frontend_static.py`
- docs: `CHANGELOG.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- api: none
- adapters: none
- quant: none
- news: none
- config: none
- deployment: none

## Important Decisions
Heat display remains frontend-only and uses backend `frontend_display.total_score`; it does not recompute score or any analysis field.
Scores `86-100`, `71-85`, `56-70`, `41-55`, `21-40`, and `0-20` map to the requested six red/grey bands.
Score `0`, `null`, `undefined`, nonnumeric, or out-of-range values fall back safely through the Cold / Neutral band after clamping.
Batch and Single use the same structured detail renderer.
Footer signature is normal document flow, not fixed, to avoid covering content.

## Commands Run And Results
- `git branch --show-current`: PASS, `dev`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits only allowed hotfix files modified.
- `python3 --version`: PASS, Python 3.14.3.
- Required read-first docs/frontend/tests scan: PASS.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 10 passed.
- First `ruff check tests/frontend/test_frontend_static.py`: FAIL, one E501 long test line; fixed.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 94 passed, 3 warnings.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- Signature grep: PASS.
- Six-band threshold/color grep: PASS.
- `/v1/analyze/detail` frontend grep: PASS.
- Forbidden capability grep: PASS, no output.
- Frontend no-recompute grep: PASS, no output.

## Known Blockers
No hotfix blocker remains.

## Open Risks
No local browser visual smoke was run in this pass.
Hugging Face Space still needs to be resynced/pushed by the user after approval.
External provider availability/rate limits remain operational risks.
Quant remains `DEFAULT_PHASE1A` and uncalibrated; no profitability/reliability claim is allowed.
Local interpreter is Python 3.14.3 while Docker targets Python 3.11.
`jsonschema.RefResolver` warning remains non-blocking technical debt.

## Next Recommended Steps
1. Commit hotfix on `dev`.
2. User approves the frontend polish.
3. Push/sync only `/Users/kha/Documents/New project/v8-crypto-api-clean` to the Hugging Face Space.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, hashes from real codes, signing keys, API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls or live news fetching.
Do not silently fall back from live mode to fixture mode.
Do not change backend quant/scoring/gates/news/auth/deploy/provider behavior for this hotfix.
Do not deploy or push to Hugging Face without explicit approval.
