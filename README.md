---
title: Ultimate Crypto Probability Engine
emoji: 📈
colorFrom: purple
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Deterministic crypto probability and risk analysis app. Analysis-only; no trading.
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
| Variable | `UCPE_COOKIE_SECURE` | `true` | Secure production cookies | yes | Use `false` only for local HTTP smoke. |
| Variable | `UCPE_DEV_MODE_ENABLED` | `false` | Disable Dev Mode by default | yes | Enable only if Dev Mode secret is configured. |
| Variable | `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` | `210000` | Access-code KDF work factor | yes | Must match hash generation. |
| Secret | `APP_ACCESS_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Operator login code hash | yes | Generate with `UCPE_ACCESS_CODE_SALT=<salt> PYTHONPATH=src python3 -c 'from crypto_probability_engine.api.auth import pbkdf2_hash_code; import getpass, os; print(pbkdf2_hash_code(getpass.getpass("Access code: "), salt=os.environ["UCPE_ACCESS_CODE_SALT"], iterations=int(os.environ.get("UCPE_ACCESS_CODE_PBKDF2_ITERATIONS", "210000"))))'`. |
| Secret | `DEV_MODE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Dev Mode re-auth code hash | later | Required only if `UCPE_DEV_MODE_ENABLED=true`; use the same hash command with the Dev Mode code. |
| Secret | `SESSION_SIGNING_KEY` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Sign session cookies | yes | Generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. |
| Secret | `UCPE_ACCESS_CODE_SALT` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Per-deploy PBKDF2 salt | yes | Generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. |
| Secret | Binance/OKX API keys | not required | Public market data only | no | No Binance/OKX secrets required for Sprint 2. |
