# Blueprint Summary

Status: Phase 0 artifact extraction. This file needs CLAUDE FINAL REVIEW before it becomes canonical.

## App Identity

Ultimate Crypto Probability Engine is a deterministic, analysis-only crypto probability/risk/decision-support app for a single non-coder operator. It answers whether a symbol is analyzable, whether market and event context are safe enough for a read, what the backend-estimated `UP`, `DOWN`, and `TIMEOUT_OR_UNRESOLVED` probabilities are, and what decision-support disposition is safest under current information.

It is not a trading bot, order router, withdrawal tool, licensed adviser, news republisher, or backend-LLM decision system.

## Defaults

- Asset class: `CRYPTO_SPOT`.
- Optional future asset class: `CRYPTO_PERP`, gated by env flag plus request opt-in.
- Analysis mode: `METRICS_ONLY`.
- Optional mode: `NEWS_ADDON`, adding macro/micro/news context under strict advisory limits.
- Supported timeframes: `15m`, `1H`, `4H`, `1D`, `1W`; default multi-timeframe trend set `{1H, 4H, 1D}`.
- Runtime target: Hugging Face Docker Space, FastAPI backend, bundled static frontend, port `7860`.
- Persistence: optional Supabase or equivalent external store; local disk is ephemeral.
- Required metric groups: multi-timeframe trend/momentum, volatility/vol-of-vol, liquidity/spread/depth, volume anomaly/persistence, BTC/ETH regime context, correlation/beta, cross-provider agreement, deterministic regime fallback, memory features, execution realism, epistemic sufficiency, risk arbiter, tail CVaR, and calibration telemetry.

## Core User Flow

1. Login with access code.
2. Choose Single Crypto Analysis, Batch Crypto Analysis, or Dev Mode.
3. Enter one symbol or up to 5 symbols.
4. Select timeframe and mode: Metrics Based or News Add-on.
5. View overview cards.
6. Click/tap a card for the backend-produced detail view.
7. Use Dev Mode only after re-auth for sanitized debug/export data.

## Backend Authority

Backend JSON is source of truth. The frontend displays only backend fields and recomputes no score, probability, trend, disposition, or news influence.

## Probability

Per horizon:

```text
p_up_frac + p_down_frac + p_timeout_frac = 1.0
```

Timeout is neither bullish nor bearish; it means unresolved/actionability risk.

## News Authority

`NEWS_ADDON` may add macro/micro context and bounded adjustments to confidence, timeout, risk, and arbiter evidence. Sentiment-only action is forbidden. News cannot override hard gates, cannot fabricate catalysts, cannot force `CONSTRUCTIVE`, and cannot make metrics fail when news sources fail.

## Heat and Risk

Card heat uses the score gradient as signal intensity. heat = signal intensity, not risk. Risk is separate via risk chip and warnings.

## Provider and Source Policy

Binance and OKX are intended primary public-first market providers, but provider/API details remain `TO_VERIFY` until current official docs are verified. News and macro sources are optional and provider-agnostic. No paid provider is mandatory for Phase 1A.

## Safety-Critical Gates

Hard gates override score and news:

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

## Governance

```text
Claude Code Opus = CTO / System Architect / Blueprint Interpreter / Critical Debugger / Refactor Planner / Security-Risk Reviewer / Final Technical Reviewer / Recovery Agent
Codex            = Implementation Engineer / Scoped Feature Builder / QA Engineer / Test Runner / Regression Checker / Codebase Explorer / Documentation-Handoff Maintainer / Parallel Executor
User             = non-coder approver/operator
```

Claude plans/reviews high-risk architecture, financial, security, deployment, and recovery work. Codex implements scoped tasks, tests, QA, and docs. User approves merge/deploy after evidence.
