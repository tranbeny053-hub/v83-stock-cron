# Current State

Updated: 2026-06-14

## Branch / Worktree

- Branch: `codex/wave4a1-honesty-declutter`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 4A.1 / Wave 4.2A Frontend Display Hotfix.
- Current status: frontend declutter hotfix implemented and offline verification completed locally; Claude/User review required before merge/deploy.
- Scope: frontend/display-layer only. No scoring, probability, gate, tail-risk, horizon-timeout, volatility/trend, config/defaults, or news-influence logic changed.

## What Changed

- Removed the repeated per-card Up/Down/Timeout explanatory block.
- Replaced card-level precise Up/Down/Timeout percentages with qualitative uncalibrated copy derived from existing `decision_brief.action`.
- Added one compact global legend near the app shell/header explaining uncalibrated Up/Down/Timeout behavior and pointing users to Detail.
- Kept full Up/Down/Timeout percentages in the structured Detail panel.
- Kept Download JSON and Decision Brief rendering intact.
- Updated frontend static tests to assert card declutter behavior, exactly one global legend, Detail-only percentages, and preserved export/brief hooks.
- Documented deferred math concerns for later reviewed work: tanh gain saturation, timeout cap behavior, realized-volatility scaling, tail CVaR broad breach behavior, and score ceiling/collapse artifacts.

## What Was Not Changed

- No quant/probability math changed.
- No score stack changed.
- No gates changed.
- No news logic or `news_influence_frac` changed.
- No features formulas changed.
- No `src/crypto_probability_engine/config/defaults.py` constants changed.
- No migrations, dependencies, provider endpoints, auth/session behavior, Docker/deployment behavior, or database schema changed.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.
- No secrets or full article bodies were added.

## Checks Run / Attempted

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
- `git diff --stat dev -- src/crypto_probability_engine/quant src/crypto_probability_engine/score_stack src/crypto_probability_engine/gates src/crypto_probability_engine/news src/crypto_probability_engine/features src/crypto_probability_engine/config/defaults.py`: PASS, empty.
- `grep -rniE "LONG_SETUP|SHORT_SETUP|REAL_LONG|REAL_SHORT" src frontend tests schemas || true`: PASS, no hits.
- Forbidden capability grep: PASS with expected negative-scope UI copy: "No account actions or autonomous execution."
- Secret-name grep: PASS with expected backend-only settings/adapter/test references; no frontend secret exposure and no real secret values.
- Full-body grep: PASS with expected sanitizer/news-contract/tests references; dedicated checker passed.
- Old per-card note grep: PASS with expected fixture/detail payload references only; no frontend hits.
- Probability display grep: PASS with Detail-only Up/Down/Timeout percentage rows and static tests proving `overviewCard` does not render precise probability triplets while uncalibrated.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/frontend/test_frontend_static.py`

## Current Blockers / Unknowns

- No local implementation blocker is known after offline verification.
- Manual browser UI smoke was not run in this Codex turn.
- Claude/User review is still required before merge/deploy.

## Next Steps

1. Send this Wave 4A.1 report to Claude final review.
2. After approval, merge `codex/wave4a1-honesty-declutter` into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.
