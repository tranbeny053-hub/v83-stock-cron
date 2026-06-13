# Current State

Updated: 2026-06-14

## Branch / Worktree

- Branch: `codex/wave4a-honesty-decision-clarity`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 4A Honesty & Decision Clarity.
- Current status: implementation and offline verification completed locally; Claude/User review required before merge/deploy.
- Scope: presentation and response-contract clarity only. No scoring, probability, gate, execution-realism, global-risk, or news-influence math changed.

## What Changed

- Added horizon-explicit backend labels for each timeframe, for example `4H setup / ~24H horizon`.
- Added user-visible Up/Down/Timeout explanation and persistent uncalibrated heuristic banner.
- Added backend-built `decision_brief` with constrained actions: `NO_TRADE`, `WATCHLIST`, `SPOT_WATCH`.
- Declared `decision_brief` in Pydantic response models and JSON Schema to satisfy `extra="forbid"`.
- Mirrored `decision_brief` into Detail Analysis and rendered it as structured frontend copy.
- Stopped presenting placeholder `confidence_frac` as real user-facing confidence; UI now says model readiness is heuristic/uncalibrated.
- Added a frontend `Download JSON` button that serializes the current in-memory analysis payload.
- Added API/schema/frontend regression tests for Wave 4A honesty fields.

## What Was Not Changed

- No scoring, probability, gates, execution realism, global risk, or news-influence logic changed.
- No News Authority behavior changed; `news_influence_frac` remains `0.0`.
- No migrations, dependencies, provider endpoints, auth/session behavior, Docker/deployment behavior, or database schema changed.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.
- No secrets or full article bodies were added.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/wave4a-honesty-decision-clarity`.
- `git status --short --untracked-files=all -- .`: PASS, only intended Wave 4A files before commit.
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
- `grep -rniE "LONG_SETUP|SHORT_SETUP|REAL_LONG|REAL_SHORT" src frontend tests schemas || true`: PASS, no hits.
- `grep -rniE "place_order|create_order|submit_order|cancel_order|withdraw|transfer_funds|leverage|auto_trade|autonomous" src tests schemas frontend || true`: PASS with expected negative-scope UI copy: "No account actions or autonomous execution."
- Secret-name grep: PASS with expected backend-only settings/adapter/test references; no frontend secret exposure and no real secret values.
- Full-body grep: PASS with expected sanitizer/news-contract/tests references; dedicated checker passed.
- Confidence/model-readiness grep: PASS; frontend shows model readiness and does not reference `confidence_frac`.
- `git diff --check -- .`: PASS.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `RELEASE_GATE.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `schemas/detail_view.schema.json`
- `schemas/response.schema.json`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/detail/builder.py`
- `src/crypto_probability_engine/detail/decision_brief.py`
- `src/crypto_probability_engine/detail/frontend_display.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/fixtures/sample_payloads.py`
- `tests/frontend/test_frontend_static.py`

## Current Blockers / Unknowns

- No local implementation blocker is known after offline verification.
- Manual browser UI smoke was not run in this Codex turn.
- Claude/User review is still required before merge/deploy.

## Next Steps

1. Send this Wave 4A report to Claude/light review.
2. After approval, merge `codex/wave4a-honesty-decision-clarity` into `dev`.
3. Deploy/push only after the normal pre-deploy checklist is rerun and approved.
