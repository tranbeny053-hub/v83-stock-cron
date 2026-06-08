# Current State

Updated: 2026-06-08

## Branch / Worktree

- Branch: `codex/wave3a-news-provider-hotfix`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 3A News Provider Hotfix.
- Current status: provider hotfix implemented; required offline tests, safety checks, schema validation, manual smoke, and targeted greps passed.
- Scope: GDELT rate-limit/cache handling, NewsAPI invalid-key/rate-limit diagnostics, sanitized provider status fields, gated live-smoke output, docs, and regression tests.

## What Changed

- Added `UCPE_GDELT_MIN_INTERVAL_SECONDS` with default `6` seconds.
- Added `UCPE_NEWS_CACHE_TTL_SECONDS` with default `180` seconds.
- Added safe HTTP/provider error metadata for HTTP status, provider error code, error type, retry-after seconds, and operation.
- Added GDELT shared in-process cache keyed by normalized query, local throttle, and 429 cooldown behavior.
- GDELT now reports `RATE_LIMITED`, HTTP 429, retry/cooldown, cache status, and safe warnings; if cached metadata exists it returns cached headlines with degraded-with-cache diagnostics.
- NewsAPI now reports absent key as `UNCONFIGURED`, invalid key as `apiKeyInvalid` / `AUTH`, rate limits as `rateLimited`, and parameter errors as request diagnostics.
- FRED/GDELT/NewsAPI provider statuses now expose sanitized configured/healthy/status/count/failure/retry/cache/latency fields.
- `NEWS_ADDON` remains `DEGRADED` when FRED is OK and GDELT/NewsAPI fail; analysis still returns 200.
- `scripts/news_live_smoke.py` now prints sanitized provider status fields only.

## What Was Not Changed

- No quant/scoring/gates/probability/disposition logic changed.
- No news influence was added; `news_influence_frac` remains `0.0` and `influence_mode` remains `ADVISORY_DISPLAY_ONLY`.
- No Wave 3B, calibration, WebSocket, deployment automation, Docker change, or Hugging Face push was implemented.
- No full article body/content storage, rendering, scraping, or arbitrary article URL fetching was added.
- No frontend provider secret exposure was added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git checkout -b codex/wave3a-news-provider-hotfix`: PASS, branch created from clean `dev`.
- `git branch --show-current`: PASS, `codex/wave3a-news-provider-hotfix`.
- `git status --short --untracked-files=all -- .`: PASS, only intended app-root hotfix changes before commit.
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

## Current Blockers / Unknowns

- No local implementation blocker is known after final offline verification.
- Live news smoke was not run by Codex because it is intentionally gated by `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`.
- The user's actual NewsAPI key may still be invalid/inactive; the app now reports that safely instead of a generic unavailable state.
- GDELT may still rate-limit live use, but repeated timeframe calls now throttle/cache and report safe retry/cache diagnostics.

## Next Steps

1. Review and merge `codex/wave3a-news-provider-hotfix` only after user/Claude approval.
2. Set or confirm Hugging Face Variables `UCPE_GDELT_MIN_INTERVAL_SECONDS=6` and `UCPE_NEWS_CACHE_TTL_SECONDS=180`.
3. If desired, run gated live news smoke after deployment with `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`, then turn it back off.
