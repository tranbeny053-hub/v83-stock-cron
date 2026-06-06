# Intended Architecture

Status: Phase 0 docs-only extraction. No app code exists yet in this repo.

## Runtime

- One Hugging Face Docker Space, platform details `TO_VERIFY`.
- FastAPI backend and bundled static frontend served from one deployable app.
- Port target: `7860`.
- Optional external persistence: Supabase or equivalent, configured via env secrets.
- Local disk is ephemeral and disposable.

## Frontend

Cyberpunk English-only UI:
- access-code login;
- main menu with Single Crypto Analysis, Batch Crypto Analysis, Dev Mode;
- input stage with symbol(s), timeframe, and analysis mode;
- overview cards;
- click/tap card to detail view;
- reduced-motion support;
- Dev Mode re-auth.

Frontend is a thin renderer. It recomputes nothing.

## Backend Endpoints

```text
GET  /healthcheck
GET  /v1/system_status
POST /v1/analyze
POST /v1/analyze_batch
GET  /v1/analyze/detail/{run_id}
GET  /v1/debug/runs
GET  /v1/debug/runs/{run_id}
GET  /v1/debug/export/{run_id}
POST /v1/auth/login
POST /v1/auth/dev
```

## Analysis Modes

- `METRICS_ONLY`: default, no news fetch, disabled news blocks.
- `NEWS_ADDON`: metrics plus time-boxed macro/micro/news context; failures isolate to `news_addon_state`.

## Provider Layer

Intended market providers: Binance and OKX, public market data first. All concrete provider/API details are `TO_VERIFY`; no provider implementation may become production-critical until source verification is complete.

Adapters normalize symbols and provider responses into one internal schema, use typed failures, respect rate limits, and surface failover in `provider_state`.

## Pipeline

```text
auth/session
-> normalize symbol(s), mode, asset class
-> cache/provider fetch
-> schema/coherence/freshness/conflict validation
-> hard gates
-> feature engineering
-> quant compute
-> probability + timeout + risk arbiter
-> NEWS_ADDON context and bounded advisory influence, if selected
-> execution realism
-> liquidity/tail/perp/portfolio gates
-> score stack and final disposition
-> frontend_display + detail_view + analysis_hash
-> async telemetry, if configured
```

## Hard Gates

```text
DATA INTEGRITY (schema/coherence/freshness/quote-asset peg)
  > PROVIDER HEALTH + CROSS-PROVIDER CONFLICT
  > EPISTEMIC SUFFICIENCY
  > EXCHANGE / SYSTEM HEALTH (maintenance/halt/kill-switch/shelter)
  > LIQUIDITY / DEPTH / SPREAD VIABILITY
  > ABNORMAL VOLATILITY / TAIL RISK
  > DERIVATIVES RISK (only if CRYPTO_PERP)
  > EXECUTION REALISM
  > PORTFOLIO / RISK ASSUMPTIONS (if provided)
  > QUANT PROBABILITY + NEWS-MODULATED SCORE STACK
  > FINAL DISPOSITION
```

## Dev Mode

Server-side gated, hidden/locked by default, re-auth required. It shows system/provider/news health, sanitized run data, audit fields, masked environment health, Debug Pack export, and News Add-on Export Pack. It must never expose secrets or full article bodies.

## Deployment

Phase 0 does not create deployment config. Future deployment must pass Hugging Face Docker Space checks, secret masking, cold-start budget, `/healthcheck`, both-mode `BTC` smoke, restart drill, and no secret/body leak.

