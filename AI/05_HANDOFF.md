# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 3A Live News Authority Engine Foundation: add advisory/display-only metadata news support for GDELT, FRED, and optional NewsAPI without changing score, probability, gates, disposition, quant math, or trading scope. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave3a-news-authority` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R3/R4 authority surface because provider news metadata can affect user interpretation, but Wave 3A is hard-gated as advisory display only. `news_influence_frac` remains `0.0` and `influence_mode` remains `ADVISORY_DISPLAY_ONLY`.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `IMPLEMENTATION_DECISIONS.md`
- `README.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `frontend/app.js`
- `migrations/0002_news.sql`
- `schemas/news.schema.json`
- `schemas/response.schema.json`
- `scripts/check_no_secrets.py`
- `scripts/news_live_smoke.py`
- `src/crypto_probability_engine/adapters/http_client.py`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/config/settings.py`
- `src/crypto_probability_engine/detail/builder.py`
- `src/crypto_probability_engine/news/adapters/__init__.py`
- `src/crypto_probability_engine/news/adapters/common.py`
- `src/crypto_probability_engine/news/adapters/fred.py`
- `src/crypto_probability_engine/news/adapters/gdelt.py`
- `src/crypto_probability_engine/news/adapters/newsapi.py`
- `src/crypto_probability_engine/news/authority.py`
- `src/crypto_probability_engine/news/contract.py`
- `src/crypto_probability_engine/news/models.py`
- `src/crypto_probability_engine/news/news_influence.py`
- `src/crypto_probability_engine/news/source_adapters.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/fixtures/sample_payloads.py`
- `tests/frontend/test_frontend_static.py`
- `tests/news/test_news_authority_engine.py`
- `tests/persistence/test_persistence_foundation.py`

## Files Read But Not Changed
- `AGENTS.md`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/04_TASK_BOARD.md`
- `IMPLEMENTATION_SPEC.md`
- existing Wave 2A adapter/validation/API/detail/frontend/test files not listed above
- Official provider references for GDELT DOC 2.0, FRED series observations, and NewsAPI `/v2/everything`

## Commands Run
- `git checkout -b codex/wave3a-news-authority`: PASS, branch created from `dev`.
- `git branch --show-current`: PASS, `codex/wave3a-news-authority`.
- `git status --short --untracked-files=all -- .`: PASS, only Wave 3A app-root changes present before commit.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/news -q`: PASS, 15 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 30 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest tests/persistence -q`: PASS, 10 passed.
- `PYTHONPATH=src python3 -m pytest tests/schemas -q`: PASS, 7 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 142 passed, 4 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS, existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `PYTHONPATH=src python3 scripts/news_live_smoke.py`: SKIP, expected because `UCPE_NEWS_LIVE_SMOKE_ENABLED` is not set.
- Targeted quant/score/gates diff: PASS, no working-tree changes in those paths.
- Targeted frontend `FRED_API_KEY` / `NEWSAPI_KEY` grep: PASS, no hits.
- Targeted full-body pattern grep: PASS with expected false positives from HTML/JS generic `body` usage and tests that assert forbidden body fields are absent; dedicated checker passed.
- Targeted forbidden-capability grep: PASS, no hits.
- Targeted `news_influence_frac` grep: PASS, implementation/tests keep the value fixed at `0.0`; no frontend usage.
- `git diff --check -- .`: PASS.

## What Works Now
- `METRICS_ONLY` fetches no news and returns “News analysis disabled for this run.”
- `NEWS_ADDON` can assemble advisory metadata-only news context from configured providers.
- GDELT is public/no-key; FRED and NewsAPI are backend-only optional secrets.
- If providers are absent or unhealthy, analysis still returns 200 with `UNAVAILABLE` or degraded news state.
- `news_influence_frac` remains `0.0`.
- `influence_mode` remains `ADVISORY_DISPLAY_ONLY`.
- Score, probability, gates, and disposition remain unchanged between metrics-only and advisory-news fixture tests.
- News items never include full article body fields; only title/snippet/url/domain/source/timestamps/scores/clusters are used.
- Compact news metadata persistence uses existing best-effort non-blocking persistence behavior.
- Structured Detail Analysis includes `News Authority / Macro & Micro Context`.

## What Is Still Broken / Unknown
- Final post-doc safety command suite passed.
- Optional live news smoke was not run; it is gated by `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`.
- FRED and NewsAPI require backend-only Hugging Face secrets and may be unavailable due to provider quotas/outages.
- Source authority and relevance scores are simple advisory metadata, not calibrated financial evidence.
- No merge/deploy/push was performed.

## Next 3 Steps
1. Finish final verification and commit `feat: add advisory live news authority engine` if all gates pass.
2. User/Claude reviews `codex/wave3a-news-authority` before merge/deploy.
3. If approved, apply `migrations/0002_news.sql` in Supabase SQL Editor, then deploy only from the app root after user approval.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not add Binance/OKX private/authenticated calls, signed endpoints, API keys, WebSocket, or provider-keyed exchange access.
- Do not store, render, scrape, or fetch full article bodies.
- Do not let news change score, probability, gates, disposition, or hard warnings in Wave 3A.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Wave 3A thêm phần tin tức dạng tham khảo: app có thể lấy tiêu đề/tóm tắt ngắn/nguồn/thời gian từ GDELT, FRED và NewsAPI nếu được cấu hình, rồi hiển thị trong Detail. Tin tức này chỉ để xem thêm, không thay đổi điểm số, xác suất, cảnh báo cứng, hay quyết định của app. App vẫn không có chức năng giao dịch.
