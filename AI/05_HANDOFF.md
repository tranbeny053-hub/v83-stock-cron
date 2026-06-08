# Handoff Packet

## From
Codex

## To
User / Claude

## Current Goal
Wave 3A News Provider Hotfix: improve GDELT rate-limit/cache behavior and NewsAPI invalid-key diagnostics while keeping news advisory-only. Do not merge, deploy, or push to Hugging Face from Codex.

## Current Branch / Worktree
`codex/wave3a-news-provider-hotfix` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 provider-connectivity hotfix. No score, probability, gates, disposition, trading, deployment, or article-body behavior changed.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `README.md`
- `RELEASE_GATE.md`
- `scripts/news_live_smoke.py`
- `src/crypto_probability_engine/adapters/http_client.py`
- `src/crypto_probability_engine/adapters/types.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/config/settings.py`
- `src/crypto_probability_engine/news/adapters/common.py`
- `src/crypto_probability_engine/news/adapters/fred.py`
- `src/crypto_probability_engine/news/adapters/gdelt.py`
- `src/crypto_probability_engine/news/adapters/newsapi.py`
- `src/crypto_probability_engine/news/contract.py`
- `tests/api/test_analysis_endpoints.py`
- `tests/news/test_news_authority_engine.py`

## Files Read But Not Changed
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/detail/builder.py`
- `frontend/app.js`
- `tests/frontend/test_frontend_static.py`
- `scripts/check_no_secrets.py`
- `scripts/check_no_full_article_body.py`

## Commands Run
- `git checkout -b codex/wave3a-news-provider-hotfix`: PASS, branch created from `dev`.
- `git branch --show-current`: PASS, `codex/wave3a-news-provider-hotfix`.
- `git status --short --untracked-files=all -- .`: PASS, only intended hotfix files before commit.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/news -q`: PASS, 23 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 31 passed, 2 warnings.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 151 passed, 4 warnings.
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
- Targeted `news_influence_frac` grep: PASS, implementation/tests keep the value fixed at `0.0`.
- Targeted forbidden-capability grep: PASS, no hits.
- `git diff --check -- .`: PASS.

## What Works Now
- GDELT outbound calls are throttled per normalized query with default 6 seconds.
- GDELT successful metadata responses are cached for default 180 seconds.
- GDELT 429 now reports HTTP 429, `RATE_LIMITED`, retry/cooldown, operation, cache status, and safe warning.
- If GDELT is rate-limited and cached metadata exists, the adapter returns cached headlines with degraded-with-cache diagnostics instead of hammering the provider.
- NewsAPI missing key is `UNCONFIGURED`, not invalid.
- NewsAPI invalid key is visible as `apiKeyInvalid` / `AUTH` with safe copy: `newsapi: api key invalid or inactive`.
- NewsAPI 429 and bad parameter cases have sanitized error-code/type diagnostics.
- FRED OK plus GDELT/NewsAPI failures yields `NEWS_ADDON` `DEGRADED` while analysis remains 200.
- Gated live news smoke prints sanitized provider status fields only.

## What Is Still Broken / Unknown
- The actual NewsAPI key may still be invalid/inactive; this hotfix makes the problem visible and safe.
- GDELT can still rate-limit live traffic; the app now throttles/caches and reports it.
- Live news smoke was not run locally because it is gated and should only be enabled intentionally.
- No merge/deploy/push was performed.

## Next 3 Steps
1. User/Claude reviews `codex/wave3a-news-provider-hotfix`.
2. After approval, merge and deploy from the app root only.
3. Confirm HF variables `UCPE_GDELT_MIN_INTERVAL_SECONDS=6`, `UCPE_NEWS_CACHE_TTL_SECONDS=180`; replace the NewsAPI key if provider status reports `apiKeyInvalid`.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not commit `.env`, real API keys, service role keys, access codes, database URLs, or full env dumps.
- Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
- Do not store, render, scrape, or fetch full article bodies.
- Do not let news affect score, probability, gates, disposition, or hard warnings.
- Do not deploy or push to Hugging Face without explicit approval.

## Notes for Non-Coder User
Hotfix này không làm app “tin tức quyết định giao dịch”. Nó chỉ giúp app nói rõ hơn: GDELT đang bị giới hạn tốc độ, NewsAPI key bị sai/hết hiệu lực, hoặc provider nào đang OK. Nếu FRED vẫn OK thì phần News Add-on chỉ bị DEGRADED, app vẫn phân tích bình thường và điểm/xác suất không đổi.
