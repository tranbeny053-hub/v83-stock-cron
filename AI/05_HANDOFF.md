# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4A.2 Frontend Deploy/Cache Correctness: make stale frontend bundles detectable and force browsers/CDN to fetch the corrected card probability renderer.

## Current Branch / Worktree
`codex/wave4a2-deploy-cachebust` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R1 frontend/deploy-cache hotfix. No score, probability, gates, features, config/defaults, news, schema, persistence, deployment automation, or migration behavior changed.

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

## Commands Run
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

## What Works Now
- HTML requests versioned CSS and JS assets.
- Served app.js guard checks the exact bundle returned by the FastAPI static mount.
- Manual smoke fails if served app.js lacks `prob_up_pct`, `prob_down_pct`, or `prob_timeout_pct`.
- Manual smoke fails if served app.js contains the stale hidden-probability copy.
- Overview card renderer still displays `Up`, `Down`, and `Timeout` rows.

## What Is Still Unknown
- Live HF browser/CDN verification is still needed after deploy.
- Existing warnings remain: `jsonschema.RefResolver` and Starlette TestClient cookie deprecation warnings.

## Next 3 Steps
1. Review and merge this branch into `dev`.
2. Deploy/push the app root to Hugging Face.
3. Hard refresh/incognito the live app and confirm overview cards show `Up`, `Down`, and `Timeout`.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not add trading/order/withdraw/transfer/leverage/autonomous capability.
- Do not change quant/probability/score/gates/features/news/config defaults for this cache fix.
- Do not expose secrets or full article bodies.
