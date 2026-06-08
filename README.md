---
title: Ultimate Crypto Probability Engine
emoji: 📈
colorFrom: purple
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Crypto probability risk analysis only.
tags:
  - crypto
  - fastapi
  - docker
  - analysis
  - risk
---

# Ultimate Crypto Probability Engine

Deterministic crypto probability and risk analysis app for a single operator.

This app is analysis-only. It does not include trading, order execution, fund movement, leverage-changing, or autonomous execution capability. It does not provide a profitability guarantee.

The target runtime is a Hugging Face Docker Space on port `7860`, serving a FastAPI backend with a bundled static cyberpunk frontend.

Secrets must be configured only in Hugging Face Space Settings or local environment variables. Secrets must never be committed, printed, exposed to the frontend, or included in debug exports.

Local disk is ephemeral on the deployment target. Durable state requires an optional external store; without one, the app runs in stateless mode with in-memory recent runs only.

Governance and source-of-truth documents:
- `IMPLEMENTATION_SPEC.md`
- `CLAUDE.md`
- `AGENTS.md`
- `AI/` operating docs

## Sprint 2 Live Public Data

Sprint 2 adds public, keyless Binance/OKX spot market data. No Binance/OKX API keys are required. Fixture/demo mode remains available only when `UCPE_DATA_MODE=fixture`.

If live providers fail or disagree, the app must show degraded/unavailable data and must not silently substitute fixture data.

## Wave 1 Persistence and Watchlist

Wave 1 adds an optional Supabase persistence foundation for compact run summaries, timeframe result summaries, provider observations, app events, and the operator watchlist. On Hugging Face, runtime persistence should use `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` through backend-only HTTPS REST on port `443`. Direct Postgres via `SUPABASE_DB_URL` remains supported for local migrations or non-Hugging-Face deployments, but Hugging Face may block outbound Postgres ports `5432`/`6543`.

If Supabase runtime persistence is absent or unavailable, analysis still returns normally and the app reports stateless or unavailable persistence. The frontend never talks to Supabase directly; it uses backend watchlist endpoints and browser storage fallback when persistence is not OK.

Apply `migrations/0001_init.sql` in Supabase SQL Editor or run `PYTHONPATH=src python3 scripts/apply_migrations.py` locally with `SUPABASE_DB_URL` set in the local environment. The script never prints the database URL.

## Wave 3A Advisory News Authority

Wave 3A adds metadata-only news and macro context for `NEWS_ADDON`. It is advisory/display-only: `influence_mode=ADVISORY_DISPLAY_ONLY` and `news_influence_frac=0.0`. News does not change score, probability, gates, disposition, warnings, or any trading-like recommendation.

GDELT uses a public no-key API. FRED and NewsAPI are optional backend-only providers enabled only when `FRED_API_KEY` or `NEWSAPI_KEY` is set in Hugging Face Secrets. The app stores and renders titles, snippets/descriptions, source/domain, URLs, hashes, timestamps, and compact scores only. It never stores full article text, scrapes article pages, or fetches arbitrary article URLs.

Apply `migrations/0002_news.sql` in Supabase SQL Editor before expecting durable news metadata.

## Hugging Face Variables and Secrets Required

| Type | Name | Value | Purpose | Required now? | Notes |
|---|---|---|---|---|---|
| Variable | `UCPE_DATA_MODE` | `live` | Use live public market data by default | yes | Set `fixture` only for explicit demo/testing. |
| Variable | `UCPE_PROVIDER_PRIORITY` | `binance,okx` | Ordered live provider preference | yes | Public spot only. |
| Variable | `UCPE_PROVIDER_TIMEOUT_SECONDS` | `8` | Public provider timeout | yes | No unbounded waits. |
| Variable | `UCPE_PROVIDER_MAX_RETRIES` | `1` | Retry/backoff limit | yes | Handles timeout/throttle once. |
| Variable | `UCPE_PROVIDER_RATE_LIMIT_PER_MIN` | `60` | Local provider throttle | yes | Conservative public limit. |
| Variable | `UCPE_CANDLE_CACHE_TTL_SECONDS` | `300` | Avoid repeated provider hits | yes | Must stay within freshness budgets. |
| Variable | `UCPE_CROSS_PROVIDER_REQUIRED` | `false` | Allow one validated provider with warning | yes | Set `true` only after review. |
| Variable | `UCPE_LIVE_SMOKE_ENABLED` | `false` | Keep manual live smoke disabled by default | yes | Do not enable in CI. |
| Variable | `UCPE_NEWS_ITEM_LIMIT` | `12` | Advisory news item cap per provider call | yes | Display-only; tune cautiously. |
| Variable | `UCPE_NEWS_TIMEOUT_SECONDS` | `6` | News provider timeout | yes | Bounded best-effort news fetch. |
| Variable | `UCPE_NEWS_LIVE_SMOKE_ENABLED` | `false` | Optional live news smoke gate | yes | Do not enable in CI. |
| Variable | `UCPE_COOKIE_SECURE` | `true` | Secure production cookies | yes | Use `false` only for local HTTP smoke. |
| Variable | `UCPE_DEV_MODE_ENABLED` | `false` | Disable Dev Mode by default | yes | Enable only if Dev Mode secret is configured. |
| Variable | `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` | `210000` | Access-code KDF work factor | yes | Must match hash generation. |
| Secret | `APP_ACCESS_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Operator login code hash | yes | Generate salt first, export `UCPE_ACCESS_CODE_SALT`, then run `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH`; enter the code at the hidden prompt. |
| Secret | `DEV_MODE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Dev Mode re-auth code hash | later | Required only if `UCPE_DEV_MODE_ENABLED=true`; use `PYTHONPATH=src python3 scripts/make_access_hash.py --name DEV_MODE_CODE_HASH`. |
| Secret | `SESSION_SIGNING_KEY` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Sign session cookies | yes | Generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. |
| Secret | `UCPE_ACCESS_CODE_SALT` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Per-deploy PBKDF2 salt | yes | Generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. |
| Secret | `SUPABASE_URL` | `<SET_IN_HF_SECRETS_ONLY>` | Supabase project URL for backend REST persistence | yes, for durable HF persistence | Backend-only. Do not expose to frontend. |
| Secret | `SUPABASE_SERVICE_ROLE_KEY` | `<SET_IN_HF_SECRETS_ONLY>` | Supabase REST authorization for backend persistence | yes, for durable HF persistence | Service role key is backend-only. Never expose to frontend, logs, or debug exports. |
| Secret | `SUPABASE_DB_URL` | `<SET_LOCALLY_OR_IN_NON_HF_RUNTIME_ONLY>` | Direct Postgres migration/local admin URL | optional | Use for `scripts/apply_migrations.py` locally or non-HF deployments; not preferred for HF runtime. |
| Secret | `FRED_API_KEY` | `<SET_IN_HF_SECRETS_ONLY>` | Optional FRED macro observations | optional | Backend-only. Never expose to frontend. |
| Secret | `NEWSAPI_KEY` | `<SET_IN_HF_SECRETS_ONLY>` | Optional NewsAPI metadata provider | optional | Backend-only. Never expose to frontend. |
| Secret | Binance/OKX API keys | not required | Public market data only | no | No Binance/OKX secrets required for Sprint 2. |

## Login Code vs Deployment Secrets

- The UI login uses the plain access code chosen by the operator.
- `APP_ACCESS_CODE_HASH` is the generated hash of that code and is never typed into the UI.
- `UCPE_ACCESS_CODE_SALT` is a PBKDF2 salt, not the login code.
- `SESSION_SIGNING_KEY` signs sessions, not the login code.
- A Hugging Face token, if used for repository upload outside this app, is not the app login code.
- No Binance/OKX API keys or exchange secrets are required for the current public market-data build.
- GDELT requires no key; FRED and NewsAPI keys are optional backend-only secrets.
