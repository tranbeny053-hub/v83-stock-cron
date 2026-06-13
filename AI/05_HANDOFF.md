# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 4A Honesty & Decision Clarity: make existing analysis outputs clearer without changing analysis math. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave4a-honesty-decision-clarity` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R1/R2 presentation and response-contract change. `decision_brief` is backend-built but display-only. No score, probability, gates, disposition, news influence, provider, auth, persistence, deployment, or migration behavior changed.

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

## Files Read But Not Changed
- `AI/00_PROJECT_RULES.md`
- `IMPLEMENTATION_DECISIONS.md`
- `README.md`
- `DEPLOYMENT_CHECKLIST.md`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/quant/probability_three_state.py`
- `src/crypto_probability_engine/quant/calibration_metrics.py`
- `src/crypto_probability_engine/score_stack/score.py`
- `scripts/check_no_forbidden_scope.py`
- `scripts/check_no_secrets.py`
- `scripts/check_no_full_article_body.py`
- `scripts/validate_schemas.py`
- `scripts/manual_smoke.py`

## Commands Run
- `git branch --show-current`: PASS, `codex/wave4a-honesty-decision-clarity`.
- `git log --oneline --decorate -8`: PASS before branch creation; `dev` HEAD was `f53b9bb merge: wave3a news provider rate-limit diagnostics`.
- `git status --short --untracked-files=all -- .`: PASS, clean before branch creation; later only intended Wave 4A files before commit.
- `git checkout -b codex/wave4a-honesty-decision-clarity`: PASS, branch created from `dev`.
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
- Targeted forbidden setup grep: PASS, no hits.
- Targeted forbidden capability grep: PASS with expected negative UI copy: "No account actions or autonomous execution."
- Targeted secret-name grep: PASS with expected backend-only config/adapter/test references; no frontend secret exposure or real values.
- Targeted full-body grep: PASS with expected sanitizer/news-contract/test references; dedicated checker passed.
- Targeted confidence/model-readiness grep: PASS; frontend uses model readiness copy and does not reference `confidence_frac`.
- `git diff --check -- .`: PASS.

## What Works Now
- Analysis responses include schema-declared `decision_brief`.
- Detail view mirrors and renders `decision_brief`.
- Timeframe cards show setup timeframe plus approximate multi-bar horizon.
- The main UI shows an uncalibrated heuristic warning and Up/Down/Timeout explanation.
- The UI no longer presents placeholder `confidence_frac` as real confidence.
- Download JSON exports the current in-memory payload without a new backend endpoint.
- `decision_brief` actions are limited to `NO_TRADE`, `WATCHLIST`, and `SPOT_WATCH`.

## What Is Still Broken / Unknown
- No browser/manual UI smoke was run in this turn.
- Claude/User review is still required before merge/deploy.
- The existing warning set remains: `jsonschema.RefResolver` deprecation and Starlette TestClient cookie deprecation warnings.

## Next 3 Steps
1. User sends this report to Claude/light review.
2. After approval, merge the branch into `dev`.
3. Rerun pre-deploy checks before any Hugging Face push.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not change scoring, probability, gates, execution realism, global risk, or news influence without Claude-approved spec.
- Do not store, render, scrape, or fetch full article bodies.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Wave 4A giúp app nói rõ hơn rằng phần trăm hiện tại là ước lượng heuristic chưa hiệu chuẩn trong khoảng nhiều nến, không phải dự báo chắc chắn hay khuyến nghị giao dịch. App cũng có phần Decision Brief dễ đọc và nút tải JSON của kết quả hiện tại.
