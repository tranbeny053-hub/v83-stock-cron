# Implementation Memory

## Context-Resume Summary
The app is on branch `codex/wave3a-news-authority`, based on `dev`.
Worktree scope is `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`; do not touch sibling folders.
Wave 3A adds a live News Authority foundation that is advisory/display-only.
News must not change score, probability, gates, disposition, hard warnings, or quant inputs.
`news_influence_frac` remains `0.0`; `influence_mode` remains `ADVISORY_DISPLAY_ONLY`.
GDELT is public/no-key; FRED and NewsAPI are optional backend-only secrets.
No full article bodies, scraping, arbitrary article URL fetches, trading capability, merge, deploy, or Hugging Face push were added by Codex.

## Latest App State
Default market-data behavior remains live public Binance/OKX with explicit fixture mode.
Wave 2A provider observability and symbol-universe behavior remain intact.
`METRICS_ONLY` fetches no news.
`NEWS_ADDON` returns unavailable/degraded advisory news state if no provider is configured or healthy, while analysis still returns normally.
News data is metadata-only and compact: title/snippet/url/domain/source/timestamps/scores/clusters.
Optional `scripts/news_live_smoke.py` skips unless `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`.

## Implemented Components
- config: `FRED_API_KEY`, `NEWSAPI_KEY`, news item limit, timeout, and live-smoke flag.
- http client: fixed host allow-list expanded for GDELT, FRED, and NewsAPI.
- news models: metadata-only news items, macro observations, clusters, stable hashes, no full body/content field.
- news adapters: GDELT DOC 2.0, FRED series observations, optional NewsAPI `/v2/everything`.
- news engine: advisory provider status, macro/micro contexts, deterministic clustering, conservative entity relevance, source authority, freshness scoring, and news evidence.
- api/detail/frontend: `news_evidence` response field and `News Authority / Macro & Micro Context` section.
- persistence: idempotent `migrations/0002_news.sql` and compact news item/cluster/evidence writes through existing best-effort repositories.
- tests: offline coverage for provider normalization/failure, no-fetch `METRICS_ONLY`, advisory-only invariants, entity relevance, clustering, persistence rows, frontend rendering, schema payloads, and no frontend secret exposure.

## Files Changed By Area
- api: `src/crypto_probability_engine/api/analysis_service.py`, `api/app.py`, `api/schemas.py`
- adapters/http: `src/crypto_probability_engine/adapters/http_client.py`
- news: `src/crypto_probability_engine/news/models.py`, `authority.py`, `contract.py`, `news_influence.py`, `source_adapters.py`, `news/adapters/*`
- frontend/detail: `frontend/app.js`, `src/crypto_probability_engine/detail/builder.py`
- config: `src/crypto_probability_engine/config/defaults.py`, `settings.py`
- persistence: `src/crypto_probability_engine/persistence/repository.py`, `migrations/0002_news.sql`
- schemas: `schemas/news.schema.json`, `schemas/response.schema.json`
- scripts: `scripts/check_no_secrets.py`, `scripts/news_live_smoke.py`
- docs: `README.md`, `DEPLOYMENT_CHECKLIST.md`, `RELEASE_GATE.md`, `IMPLEMENTATION_DECISIONS.md`, `docs/source_verification_matrix.md`, `CHANGELOG.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, `AI/06_TEST_COMMANDS.md`, `AI/07_DECISION_LOG.md`, `AI/08_IMPLEMENTATION_MEMORY.md`
- tests: `tests/news/test_news_authority_engine.py`, `tests/api/test_analysis_endpoints.py`, `tests/persistence/test_persistence_foundation.py`, `tests/frontend/test_frontend_static.py`, `tests/fixtures/sample_payloads.py`

## Important Decisions
Wave 3A news is advisory/display-only: `news_influence_frac=0.0`, `influence_mode=ADVISORY_DISPLAY_ONLY`, and news is not passed into the quant pipeline.
`METRICS_ONLY` must fetch no news.
GDELT is configured without a key; FRED and NewsAPI are optional backend-only providers when `FRED_API_KEY` / `NEWSAPI_KEY` exist.
Host allow-list is fixed to known public provider hosts; article URLs are stored as strings only and never fetched.
News item scores use `_score` fields bounded `[0,1]`; no new unbounded `_frac` fields were added.
News persistence stores compact metadata only and remains best-effort/non-blocking.
Source authority and entity relevance are conservative metadata and are not calibrated trading evidence.

## Commands Run And Results
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

## Known Blockers
No local implementation blocker is known after final offline verification.
No merge/deploy/push has been performed.

## Open Risks
Optional live news smoke was not run by Codex; provider behavior should be verified after backend-only secrets are present.
FRED and NewsAPI quotas, terms, and temporary outages remain operational risks.
NewsAPI free/dev-tier behavior may differ by deployment environment.
Entity relevance, source authority, and freshness scores are simple deterministic advisory metadata, not calibrated financial evidence.
Local interpreter may differ from Docker Python 3.11.

## Next Recommended Steps
1. Commit the branch if final status remains clean.
2. User/Claude reviews Wave 3A before merge/deploy.
3. If approved, apply `migrations/0002_news.sql` in Supabase SQL Editor and deploy only from the app root.

## Do Not Change
Do not touch sibling folders outside `v8-crypto-api-clean/`.
Do not edit external source Markdown files.
Do not commit `.env`, salts, access codes, real hashes, signing keys, database URLs, service role keys, FRED/NewsAPI keys, exchange API keys, or full env dumps.
Do not add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
Do not add Binance/OKX private/authenticated calls, signed endpoints, API keys, WebSocket, or provider-keyed exchange access.
Do not silently fall back from live mode to fixture mode.
Do not store, render, scrape, or fetch full article bodies.
Do not let news affect score, probability, gates, disposition, or hard warnings in Wave 3A.
Do not deploy or push to Hugging Face without explicit approval.
