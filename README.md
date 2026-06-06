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

