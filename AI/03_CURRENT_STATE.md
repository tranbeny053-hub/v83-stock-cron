# Current State

Updated: 2026-06-08

## Branch / Worktree

- Branch: `codex/wave3a-news-authority`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 3A Live News Authority Engine Foundation.
- Current status: implementation complete in working tree; final verification gates are being run before commit.
- Scope: advisory/display-only metadata news foundation for GDELT, FRED, optional NewsAPI, compact news persistence, detail UI, docs, and tests.

## What Changed

- Added metadata-only news models with title/url hashes, source/domain, timestamps, language, entity tags, source authority score, relevance score, freshness score, confidence score, and cluster ID.
- Added GDELT DOC 2.0, FRED macro observation, and optional NewsAPI adapters using fixed public HTTPS hosts only.
- Extended the public HTTP allow-list for `api.gdeltproject.org`, `api.stlouisfed.org`, and `newsapi.org`.
- Added deterministic advisory news normalization, conservative entity relevance, source authority scoring, freshness scoring, and title/domain/time clustering.
- Added `news_evidence`, provider status, macro observations, and `influence_mode=ADVISORY_DISPLAY_ONLY` to `NEWS_ADDON` payloads.
- Kept `news_influence_frac=0.0`; Wave 3A news does not alter score, probability, gates, disposition, hard warnings, or quant pipeline inputs.
- Added `migrations/0002_news.sql` with idempotent compact metadata tables: `news_items`, `news_clusters`, and `news_evidence_links`.
- Extended in-memory, Supabase Postgres, and Supabase REST repositories with best-effort news metadata persistence through the existing non-blocking path.
- Added `News Authority / Macro & Micro Context` to structured Detail Analysis.
- Added optional gated `scripts/news_live_smoke.py`; it skips unless `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`.

## What Was Not Changed

- No quant/scoring/gates/probability math changed.
- No Wave 3B, calibration, WebSocket, deployment automation, Docker change, or Hugging Face push was implemented.
- No Binance/OKX private/authenticated endpoint or exchange API key was added.
- No full article body/content storage, rendering, scraping, or arbitrary article URL fetching was added.
- No frontend news relevance/sentiment/score recomputation was added.
- No secrets, env files, API keys, service role values, or access values added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git checkout -b codex/wave3a-news-authority`: PASS, branch created from clean `dev`.
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

## Current Blockers / Unknowns

- No local implementation blocker is known after final offline verification.
- Optional live news smoke was not run; the script is gated and skips unless `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`.
- FRED and NewsAPI behavior depends on backend-only Hugging Face secret configuration and provider availability.
- News provider terms, quotas, and temporary outages remain operational risks.
- Wave 3A authority scores are advisory metadata only and are not calibrated decision evidence.

## Next Steps

1. Finish final safety/schema/smoke/grep verification, then commit `feat: add advisory live news authority engine` if all checks pass.
2. User/Claude reviews `codex/wave3a-news-authority` before merge/deploy.
3. If approved, apply `migrations/0002_news.sql` in Supabase SQL Editor, then deploy only from the app root after user approval.
