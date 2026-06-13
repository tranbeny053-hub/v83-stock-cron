# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4A.1 / Wave 4.2A Frontend Display Hotfix: declutter uncalibrated overview cards without changing analysis math. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave4a1-honesty-declutter` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R1 frontend/display-layer hotfix. No score, probability, gates, tail risk, horizon timeout, volatility/trend, config/defaults, news influence, provider, auth, persistence, deployment, migration, or schema behavior changed.

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

## Files Read But Not Changed
- `schemas/response.schema.json`
- `schemas/detail_view.schema.json`
- `src/crypto_probability_engine/detail/frontend_display.py`
- `src/crypto_probability_engine/detail/decision_brief.py`
- `tests/api/test_analysis_endpoints.py`

## Commands Run
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

## What Works Now
- The repeated per-card yellow explanatory block is gone.
- There is one global uncalibrated heuristic legend.
- Overview cards show qualitative uncalibrated copy such as `Watchlist · uncalibrated — see Detail`.
- Overview cards do not render fake-precise Up/Down/Timeout percentage rows while results are uncalibrated.
- Detail panel still renders full Up/Down/Timeout percentages.
- Download JSON and Decision Brief still render.

## What Is Still Broken / Unknown
- No browser/manual UI smoke was run in this turn.
- Claude/User review is still required before merge/deploy.
- Existing warnings remain: `jsonschema.RefResolver` deprecation and Starlette TestClient cookie deprecation warnings.
- Quant issues diagnosed from live feedback are intentionally deferred: tanh gain saturation, timeout cap behavior, realized-volatility scaling, tail CVaR broad breach behavior, and score ceiling/collapse artifacts.

## Next 3 Steps
1. User sends this report to Claude final review.
2. After approval, merge the branch into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not change scoring, probability, gates, execution realism, global risk, or news influence without Claude-approved spec.
- Do not change quant/config/defaults to make uncalibrated numbers look nicer in this branch.
- Do not store, render, scrape, or fetch full article bodies.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Hotfix này làm giao diện đỡ ồn và đỡ gây hiểu nhầm: thẻ tổng quan không còn lặp cảnh báo vàng và không còn show % quá chính xác khi mô hình vẫn chưa hiệu chuẩn. Nếu muốn xem số đầy đủ, bấm Detail.
