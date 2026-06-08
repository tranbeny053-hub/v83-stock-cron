# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave3a-news-provider-hotfix`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 3A advisory news foundation is already present on `dev`.
This hotfix improves GDELT rate-limit/cache behavior and NewsAPI invalid-key diagnostics.
News remains advisory-only: `news_influence_frac=0.0`, `influence_mode=ADVISORY_DISPLAY_ONLY`, and no score/probability/gate/disposition path changes.
No deploy, merge, push, full article body fetch/storage, scraping, trading capability, or secret exposure was performed by Codex.

## Latest App State
GDELT has per-query shared in-process throttle and cache.
Default `UCPE_GDELT_MIN_INTERVAL_SECONDS=6`; default `UCPE_NEWS_CACHE_TTL_SECONDS=180`.
GDELT 429 is reported as `RATE_LIMITED` with HTTP status, retry/cooldown, operation, cache status, and safe warning.
NewsAPI absent key is `UNCONFIGURED`; invalid key is reported as `apiKeyInvalid` / `AUTH` without exposing the key.
FRED OK plus GDELT/NewsAPI failures yields `NEWS_ADDON` `DEGRADED`, not generic failed/unavailable.
Gated live news smoke prints sanitized provider diagnostics only.

## Implemented Components
- config: GDELT min interval and news cache TTL settings/env parsing.
- HTTP/provider errors: optional safe fields for HTTP status, provider error code, type, retry-after, operation.
- GDELT adapter: shared cache, local throttle, 429 cooldown, cached degraded fallback.
- NewsAPI adapter: invalid-key/rate-limit/parameter diagnostics and unconfigured state.
- FRED adapter: safe provider status shape.
- news contract: provider_status includes configured/unconfigured sources and sanitized failure/cache/latency fields.
- tests: GDELT 429/cache/throttle/zero-item OK, NewsAPI 401/429/unconfigured, mixed FRED-OK degraded analysis 200.
- docs: changelog, release/deploy/readme env rows, decision log, current state, handoff, test command notes.

## Files Changed By Area
- config: `src/crypto_probability_engine/config/defaults.py`, `settings.py`
- provider/http: `src/crypto_probability_engine/adapters/types.py`, `adapters/http_client.py`
- news: `src/crypto_probability_engine/news/adapters/common.py`, `fred.py`, `gdelt.py`, `newsapi.py`, `news/contract.py`
- scripts: `scripts/news_live_smoke.py`
- docs: `README.md`, `DEPLOYMENT_CHECKLIST.md`, `RELEASE_GATE.md`, `CHANGELOG.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/06_TEST_COMMANDS.md`, `AI/07_DECISION_LOG.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/news/test_news_authority_engine.py`, `tests/api/test_analysis_endpoints.py`

## Important Decisions
Do not hide provider-specific failures as generic unavailable when safe diagnostics are available.
Do not expose API keys, request headers, URLs containing secrets, or raw provider response bodies.
GDELT rate-limit handling must avoid immediate retry loops and should reuse cached metadata if available.
NewsAPI `apiKeyInvalid` is an operator configuration issue and should be shown safely as `AUTH`.
Unconfigured NewsAPI is `UNCONFIGURED`, not invalid.
News provider diagnostics remain display/observability metadata only and do not influence scoring.

## Commands Run And Results
- `git checkout -b codex/wave3a-news-provider-hotfix`: PASS, branch created from clean `dev`.
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
- Targeted full-body pattern grep: PASS with expected HTML/JS/test false positives; dedicated checker passed.
- Targeted `news_influence_frac` grep: PASS, value remains fixed at `0.0`.
- Targeted forbidden-capability grep: PASS, no hits.
- `git diff --check -- .`: PASS.

## Known Blockers
No local implementation blocker is known after final offline verification.
No merge/deploy/push has been performed.

## Open Risks
The actual NewsAPI key may still be invalid/inactive until the operator replaces it.
GDELT can still rate-limit live traffic; the app now throttles/caches and reports it.
Live news smoke was not run locally because it is intentionally gated.
Provider quotas/outages remain operational risks.

## Next Recommended Steps
1. User/Claude reviews the hotfix branch.
2. Merge/deploy only after approval from the app root.
3. Confirm HF variables `UCPE_GDELT_MIN_INTERVAL_SECONDS=6`, `UCPE_NEWS_CACHE_TTL_SECONDS=180`; replace NewsAPI key if diagnostics still show `apiKeyInvalid`.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls, signed endpoints, API keys, WebSocket, or provider-keyed exchange access.
Do not store, render, scrape, or fetch full article bodies.
Do not let news affect score, probability, gates, disposition, or hard warnings.
Do not deploy or push to Hugging Face without explicit approval.
