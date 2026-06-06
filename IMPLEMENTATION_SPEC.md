# Ultimate Crypto Probability Engine - Implementation Spec

Canonical source: Ultimate_Crypto_Probability_Engine_Blueprint_v1_2_2.md (v1.2.2, locked; held by the operator, not in this repo).

Status: Phase 0 artifact extraction. This document needs CLAUDE FINAL REVIEW before it becomes canonical.

## 1. Product Contract

The Ultimate Crypto Probability Engine is an analysis-only crypto market-data probability, risk, and decision-support app for a single non-coder operator. It is not a trading bot, broker integration, order manager, portfolio manager, licensed financial adviser, backend-LLM decision system, institutional terminal, multi-user compliance platform, or news republisher.

Default asset class: `CRYPTO_SPOT`.

Optional future asset class: `CRYPTO_PERP`, off by default and allowed only when both a server env flag and per-request opt-in are present. Perp-only metrics are disabled/null in spot mode with `DISABLED_SPOT_MODE` and must never affect spot analysis.

Analysis modes:
- `METRICS_ONLY`: default, market-data and quant only, no news source fetch.
- `NEWS_ADDON`: metrics pipeline plus macro/micro/news context when reliable sources are available. News is advisory, bounded, deterministic, and never a standalone driver.

Execution boundary: no execution capability exists. Manual action happens outside the system.

Honesty rule: when data or context is weak, the system must prefer `NO_TRADE`, `ABORT_*`, `INSUFFICIENT_DATA`, or explicit degraded states over false confidence.

## 2. Forbidden Scope

These capability-bearing terms MUST NOT appear in implementation paths (`src/`, `tests/`, `schemas/`, `.github/workflows/`, runtime/job config), except inside explicit documentation-only scope sections or isolated checker-test fixtures that are excluded from the production scan:

```text
place_order
create_order
submit_order
cancel_order
order_manager
order_router
execution_engine
autonomous_execution
auto_trade
withdraw
withdrawal
transfer_funds
internal_transfer
sapi_withdraw
enable_trading
trade_permission
margin_borrow
leverage_set
```

Rationale: this app is analysis-only. Private exchange calls, if any are later approved, must be read-only and must never move funds or create executable actions.

## 3. Backend Authority

Backend JSON is authoritative. The frontend, Dev Mode, detail view, and any narration layer may only display what the backend returns. They MUST NOT recompute score, probability, trend, disposition, or news influence. If a display conflicts with `gate_result.action`, the backend wins.

Quant authority: deterministic backend Python modules only. No backend LLM call may compute score, probability, news influence, gate state, or disposition.

## 4. Intended Architecture

Runtime target: one Hugging Face Docker Space serving a FastAPI backend and bundled static frontend on port `7860`.

High-level flow:

```text
frontend login/menu/input/cards/detail/dev mode
  -> FastAPI session/auth + /v1 endpoints
  -> deterministic per-symbol analysis pipeline
  -> public-first market providers and optional persistence
  -> backend-produced JSON, frontend display only
```

Hot-path order:
1. Resolve session/auth.
2. Normalize symbol(s) and read `analysis_mode`, default `METRICS_ONLY`.
3. Cache read / market provider fetch.
4. Schema, coherence, freshness, and conflict validation.
5. Data-integrity, epistemic, exchange/system health gates.
6. Feature engineering.
7. Quant compute, three-state probability, timeout, risk arbiter, tail/calibration state.
8. In `NEWS_ADDON` only: run news/macro/micro layer under a strict time box; failure isolates to `news_addon_state`.
9. Execution realism, liquidity/depth/spread viability, tail risk, optional perp gates, portfolio guard.
10. Advisory gates and score stack.
11. Final disposition, `trend_summary`, `frontend_display`, `detail_view`, `analysis_hash`.
12. Async telemetry insert if configured; response must not block on persistence.

In `METRICS_ONLY`, the news layer is skipped entirely, no news sources are fetched, and news blocks are disabled/omitted with `DISABLED_METRICS_ONLY`.

## 5. API Contract

Required endpoints:

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/healthcheck` | runtime liveness/cache readiness | none |
| GET | `/v1/system_status` | runtime + system + provider + news-source + shelter | session |
| POST | `/v1/analyze` | one-symbol analysis, mode-aware | session |
| POST | `/v1/analyze_batch` | up to 5 symbols, mode-aware | session |
| GET | `/v1/analyze/detail/{run_id}` | drill-down detail view | session |
| GET | `/v1/debug/runs` | recent run summaries | Dev Mode re-auth |
| GET | `/v1/debug/runs/{run_id}` | one run sanitized detail | Dev Mode re-auth |
| GET | `/v1/debug/export/{run_id}` | sanitized debug pack | Dev Mode re-auth |
| POST | `/v1/auth/login` | access code to session | rate-limited |
| POST | `/v1/auth/dev` | Dev Mode re-auth | rate-limited |

Request rules:
- `analysis_mode` defaults to `METRICS_ONLY`; allowed values are `METRICS_ONLY` and `NEWS_ADDON`.
- `asset_class` defaults to `CRYPTO_SPOT`.
- `CRYPTO_PERP` is rejected unless derivatives are enabled by server flag and request opt-in.
- Batch size is maximum 5 symbols. Each symbol fails independently.
- Missing book/sizing is labeled `DEFAULT_PAPER_BOOK`; missing portfolio is labeled `NO_PORTFOLIO_PROVIDED`.

Error envelope codes are limited to the blueprint-defined set, including `INVALID_SYMBOL`, `UNSUPPORTED_ASSET_CLASS`, `PROVIDER_DEGRADED`, `DATA_CONFLICT`, `STALE_CANDLES`, `INSUFFICIENT_DATA`, `QUANT_COMPUTE_FAILED`, `EPISTEMIC_VOID`, `EXCHANGE_HEALTH_BLOCK`, `SHELTER_MODE_BLOCK`, `SCHEMA_VALIDATION_FAILED`, `BACKEND_TIMEOUT`, `BATCH_LIMIT_EXCEEDED`, `RUN_NOT_FOUND`, and `UNAUTHORIZED`. News problems are represented in `news_addon_state`, not as fatal metrics errors.

## 6. Stable Response Schema

Every successful `/v1/analyze` element must include:

```text
schema_version
run_id
symbol
normalized_symbol
asset_class
analysis_mode
timeframes
as_of_utc
provider_state
data_quality
market_features
liquidity_state
execution_realism
quant_compute_state
epistemic_sufficiency_state
probability_state
horizon_timeout_state
risk_arbiter_state
tail_risk_state
calibration_state
macro_context
micro_news_context
news_addon_state
news_materiality_state
event_horizon_state
narrative_state
novelty_surprise_state
source_confidence_state
information_state
catalyst_state
score_stack
trend_summary
frontend_display
detail_view
gate_result
debug
analysis_hash
```

Sentinel rules:
- Missing decision-relevant values use JSON `null` plus `status` or `null_reason`.
- NaN, Inf, and magic sentinels are forbidden.
- Datetimes are timezone-aware UTC only.
- Fractions are bounded `[0, 1]` and end in `_frac`; percentages exist only in display fields.
- News influence fields are bounded by config and `0.0` when news is disabled or unavailable.
- Every response carries `analysis_hash`; quant and news-influence outputs are hashable and auditable.

Probability invariant:

```text
p_up_frac + p_down_frac + p_timeout_frac = 1.0   (within tolerance)
```

This invariant holds per horizon, per symbol/timeframe, in both modes, and after any news adjustment. News adjusts confidence, timeout risk, and arbiter evidence within bounds; it does not rewrite the three-state split.

## 7. Data Providers and Source Verification

Primary market providers: Binance and OKX, market-data-first, public endpoints preferred.

All provider and news-source details are `TO_VERIFY` until verified against current official documentation. No provider/source may become production-critical unless its Source Verification Matrix row has official documentation URL, verified date, auth/secret requirement, rate limit/quota, freshness budget, adapter contract, fallback, fixture requirement, and production status.

Adapter contracts remain abstract until verification is complete. Provider-specific endpoints, rate limits, auth details, news providers, and macro sources must not be treated as production-locked facts in Phase 0.

Market adapters must normalize provider data into one internal schema, fail with typed status, respect rate limits, surface throttling/degradation, and make failover visible in `provider_state`.

Symbol normalization must be pure and deterministic. Accepted examples include `BTC`, `ETH`, `SOL`, `BTCUSDT`, `ETH-USDT`, and lowercase variants. Canonical internal form is `BASE/QUOTE` plus `asset_class`.

## 8. Data Validation and Failure Behavior

Required validation includes:
- positive prices; coherent OHLC; nonnegative volume;
- strictly increasing timestamps; no duplicate open times; visible gap flags;
- freshness budget per timeframe;
- minimum history per module;
- provider clock skew checks;
- quote-asset peg sanity;
- cross-provider disagreement detection;
- order-book quality checks;
- exchange health status.

No silent substitution. Every fallback is visible in `provider_state`, `data_quality`, or `news_addon_state`.

News source validation in `NEWS_ADDON` must validate normalized item shape, freshness, timestamps, deduplication, and source status. A failing news source degrades the news layer only and never crashes metrics.

## 9. Feature and Quant Contract

Phase 1A feature groups are limited to blueprint-defined requirements:
- multi-timeframe trend/momentum;
- volatility and vol-of-vol;
- liquidity, spread, and depth;
- volume anomaly and persistence;
- BTC/ETH regime context;
- correlation/beta to BTC/ETH;
- cross-provider agreement;
- deterministic regime detection with explicit fallback;
- memory features;
- event/catalyst risk only in `NEWS_ADDON` when reliable sources exist;
- derivatives metrics only when `CRYPTO_PERP` is enabled and requested.

Quant modules are deterministic backend Python, not narration and not LLM output. Insufficient data yields skipped/insufficient statuses. Unexpected failure yields `COMPUTE_FAILED`. Hard gates dominate quant and news outputs. Outputs are hashable and deterministic under fixed inputs.

`probability_three_state` models `UP`, `DOWN`, and `TIMEOUT_OR_UNRESOLVED`. Timeout is neither bullish nor bearish; it means the horizon may not produce a decisive, actionable move.

Sprint 1 limitation: `H_primary` and `H_extended` currently share the same three-state directional split, with only confidence scaled for the extended horizon. Full horizon-specific probability modeling is a Sprint 2 item and must remain config-governed, deterministic, and invariant-preserving.

Risk arbiter evidence terms:
- Alpha evidence from trend, momentum, regime fit, probability edge, and bounded news alpha evidence in `NEWS_ADDON`.
- Omega pressure from downside, reversal, data degradation, timeout, and bounded news omega pressure.
- Sigma veto pressure from tail, liquidity, spread/slippage, exchange health, portfolio heat, optional derivatives risk, and bounded verified-incident news sigma pressure.

Weights live in config, are versioned, and must not be magic numbers. Phase 2 tuning requires shadow calibration and manual promotion.

## 10. Gate Hierarchy

Hard gates override score AND news:

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

No score, probability, catalyst, news item, narrative, arbiter modifier, or display may override a failed hard gate. Hard gates are evaluated independently of news.

Disposition vocabulary is analysis-only: `ABORT_INSUFFICIENT_DATA`, `ABORT_PROVIDER_DEGRADED`, `ABORT_SYSTEM_RISK`, `NO_TRADE`, `WATCH`, `CONSTRUCTIVE_CAUTIOUS`, `CONSTRUCTIVE`, `ELEVATED_RISK_AVOID`, and `DIRECTIONAL_SHORT_CONTEXT`. These are not executable instructions. News alone can never produce `CONSTRUCTIVE` or `CONSTRUCTIVE_CAUTIOUS`.

Shelter mode blocks new constructive dispositions. Auto-recovery is forbidden; manual unlock requires trigger review, provider review, operator name, and audit write. News never lifts shelter mode.

Sprint 1 final-review guard: non-viable liquidity, configured tail-risk breach, or execution round-trip cost above the configured threshold forces a non-constructive result (`NO_TRADE` final action with `ELEVATED_RISK_AVOID` score disposition). These guards can never yield `CONSTRUCTIVE` or `CONSTRUCTIVE_CAUTIOUS`.

Sprint 2 limitation: the full hard-gating model for liquidity/depth/spread viability, abnormal volatility/tail risk, and execution realism remains incomplete. Sprint 1 includes deterministic guardrails only; full module-specific gate severity, thresholds, and provider-real data validation require Claude-scoped Sprint 2 work.

## 11. Execution Realism

Execution realism is analysis-only. It models cost and tradability constraints but creates no executable path.

Required inputs/defaults:
- `book_value`: default `10000`.
- `book_ccy`: default `USDT`.
- `intended_position_frac`: default `0.02`.
- `side`: default `LONG` for spot baseline.

Depth modes: `MARKET_DEPTH_AVAILABLE`, `BEST_BID_ASK_ONLY`, `QUOTE_LITE_FALLBACK`, `NO_QUOTE_ABORT`.

Never fabricate depth. Net-of-cost result is binding. Gross signal cannot override cost, liquidity, depth, exchange health, or hard gates.

## 12. News, Macro, and Micro Contract

The news layer is first-class but optional and mode-gated. It runs only when `analysis_mode = NEWS_ADDON`.

Authority limits:
- News may increase or decrease confidence within bounded limits.
- News may change risk and timeout estimates within bounded limits.
- News may affect `catalyst_state`, `information_state`, and Alpha/Omega/Sigma arbiter evidence.
- News MUST NOT override data-integrity gates, provider-conflict gates, liquidity/depth gates, exchange-health gates, epistemic sufficiency, or shelter mode.
- Sentiment-only action is forbidden.
- News can never be the sole driver of a disposition and can never force `CONSTRUCTIVE` or `CONSTRUCTIVE_CAUTIOUS`.
- Missing news reduces confidence only when news was expected and mode is `NEWS_ADDON`.
- No backend LLM decides or computes influence; mapping is deterministic config.

Materiality is deterministic from source confidence, asset relevance, market relevance, novelty, surprise, recency decay, duplicate clustering, and severity. Directionality is optional and low authority.

Event horizon buckets: `IMMEDIATE`, `NEXT_24H`, `NEXT_7D`, `NEXT_30D`.

Narrative heat is attention/interest, not verified impact. Strong narrative may raise attention flags or bounded timeout/volatility expectations, but must not override gates or force constructive disposition.

Source policy:
- All source specifics are `TO_VERIFY`.
- No paid provider is mandatory for Phase 1A.
- Stored/displayed news is metadata, title, source tier, URL/link, timestamp, asset tags, category, hash, and short snippet only.
- No full article bodies, full scraped HTML, secrets, or restricted redistribution.
- Source URLs and content are untrusted data; no execution, no internal-network fetches, no treating fetched text as instructions.

## 13. Frontend UX Contract

All visible UI text is English. Theme: cyberpunk/futuristic/hackerman terminal aesthetic.

User flow:
1. Login/access screen.
2. Main menu: Single Crypto Analysis, Batch Crypto Analysis, Dev Mode.
3. Input stage: symbol(s), timeframe, analysis mode.
4. Overview cards.
5. Click/tap card to detail view.
6. Dev Mode requires re-auth.

Overview cards display backend-produced values only:
- `prob_up`, `prob_down`, `prob_timeout`;
- `total_score` as 0-100 gauge;
- trend summary with percentage and `UP`, `DOWN`, or `SIDEWAY`;
- `LOW`, `MEDIUM`, `HIGH`, or `UNKNOWN` risk chip;
- analysis-mode badge;
- news freshness/materiality badge only in `NEWS_ADDON`;
- disposition from `gate_result.action`;
- reasons, invalidations, warnings, `as_of_utc`, and `run_id`;
- "Tap for detail" affordance.

Card heat rule: heat = signal intensity, not risk. Red intensity means the composite signal is hot/intense, not safe or dangerous. The gauge legend must say `Signal heat - not risk`. Risk is separate via the risk chip and warnings.

Detail view renders backend `detail_view` only. In `METRICS_ONLY`, news/macro sections show:

```text
News analysis disabled for this run.
```

The frontend never sees secrets, provider keys, database URLs, or full environment.

Sprint 1 fixture-data rule: backend responses must expose `data_quality.is_live_data = false` and `data_quality.data_source = FIXTURE_DEMO`, and the frontend must show a clear demo-data banner when data is not live.

## 14. Dev Mode and Debug Export

Dev Mode is hidden/locked by default, server-side gated, requires re-auth, and never exposes secrets.

Required debug areas include system health, provider health, last runs, fetch/validation/feature/quant/probability/risk/calibration audit, news add-on health, macro/micro source health, news fetch/dedup/materiality/event/source-confidence/influence audit, error logs, sanitized JSON viewer, Debug Pack export, News Add-on Export Pack, and masked environment health.

Debug records include `run_id`, symbol, timeframe, mode, provider, pipeline step, status, latency, warnings, error summary, and sanitized payload hash. News debug adds source statuses, item counts, dropped duplicate/low-confidence counts, top material events, stale/unavailable warnings, bounded influence adjustments, and sanitized source metadata. No full article bodies or API keys.

Sensitive values are shown only as presence/length, for example `BINANCE_KEY: set (****)`.

## 15. Persistence, Telemetry, and Calibration

Local disk is ephemeral. Durable state, if enabled, uses Supabase or equivalent external store via env secrets. If no external store is configured, app runs stateless and Dev Mode clearly labels in-memory recent runs as non-durable.

Telemetry is async and must not block responses. Logs are compact, sanitized, and include mode, provider state, gate states, disposition, score stack, execution estimates, quant/probability/arbiter/tail/calibration states, and news aggregate metadata/influence in `NEWS_ADDON`.

Calibration is sample-gated. Phase 1A logs defaults. Phase 2 uses walk-forward reliability testing, no-lookahead, Brier/log-loss/reliability curves, drift, regime/liquidity buckets, and manual promotion only. Shadow modules and news influence cannot affect production until validated and approved.

## 16. Security and OpSec

Secrets only via environment variables / Hugging Face Secrets. Never in code, logs, frontend, debug exports, URLs, query strings, or full env dumps.

Private exchange keys, if ever approved, must be read-only only and preferably IP-allowlisted. Public market data is preferred because it needs no secrets.

Dev Mode is server-side gated, not CSS-hidden. Session/auth must be rate-limited and auditable without logging plaintext access values.

Access-code hashes use PBKDF2-HMAC-SHA256 with env-configurable iterations and per-deploy salt. `UCPE_ACCESS_CODE_SALT` and `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` are deployment configuration, never frontend data. Production cookies default to secure; `UCPE_COOKIE_SECURE=false` is only for local HTTP smoke/development.

Security threat controls include secret-leak scans, forbidden-scope checks, no-full-body checks, CORS/CSRF/session tests, brute-force protection, SSRF/news URL allow-listing, dependency audits, env masking, source-poisoning fixtures, prompt/news injection safeguards if narration is ever added, and no backend LLM decision path.

## 17. Hugging Face Deployment Contract

Deployment target is a single Hugging Face Docker Space. Platform details remain `TO_VERIFY` until checked against current official docs.

Checklist requirements:
- FastAPI and static frontend served by one app.
- Bind to `0.0.0.0:7860`.
- Secrets configured in Space settings, never committed.
- Non-root runtime user and writable temp/cache paths under `/tmp`.
- Local disk treated as ephemeral.
- Optional external persistence via env-configured store.
- Cold start and `/healthcheck` budget documented.
- `BTC` smoke in `METRICS_ONLY` and `NEWS_ADDON` must return schema-valid payloads without secret/body leaks. If no news source is configured, `NEWS_ADDON` returns `UNAVAILABLE` and metrics remain unaffected.

No Dockerfile or deployment config is created in Phase 0.

## 18. Testing and Gates

Required future checks include lint/format, type checks where practical, pytest with coverage target, schema validation, unit/discipline checks, latency checks, no backend LLM decision path, forbidden-scope scan, no network calls in unit tests, no full article body fixture/export, auth/session tests, Dev Mode masking, card-to-detail, both analysis modes, batch partial failure, news freshness/degradation, news authority, hard-gate seniority, and probability invariant.

Phase gates are release-blocking. A phase is complete only when applicable gates pass and results are recorded:
- Schema
- Data
- Security
- UX
- Dev Mode
- News
- Quant
- Calibration
- Deployment
- Rollback
- Non-Coder Verification

## 19. Governance

Role model:

```text
Claude Code Opus = CTO / System Architect / Blueprint Interpreter / Critical Debugger / Refactor Planner / Security-Risk Reviewer / Final Technical Reviewer / Recovery Agent
Codex            = Implementation Engineer / Scoped Feature Builder / QA Engineer / Test Runner / Regression Checker / Codebase Explorer / Documentation-Handoff Maintainer / Parallel Executor
User             = non-coder approver/operator
```

Claude owns high-risk planning, architecture, product/blueprint interpretation, financial logic review, root-cause debugging, recovery planning, security/deployment review, and final high-risk review.

Codex owns scoped implementation, tests, lint/type/build fixes, QA/regression review, documentation, handoff maintenance, and parallel work in isolated branches/worktrees.

User approves merge/deploy only after verification evidence is visible.

Blueprint v1.2.2 is locked for Phase 0 artifact extraction. New requests must be classified as `CRITICAL SAFETY GAP`, `IMPLEMENTATION CLARIFICATION`, `FUTURE BACKLOG`, or `REJECTED SCOPE CREEP`.

Do not paste the full blueprint into routine prompts. Use layered context: `CLAUDE.md` / `AGENTS.md`, `/AI` docs, `IMPLEMENTATION_SPEC.md`, current task packet, handoff evidence.

## 20. Phase Boundaries

Phase 0: docs-only artifact extraction and repo operating docs. No app code.

Phase 1A: after Claude review, create Hugging Face-deployable skeleton with FastAPI/static frontend, auth shell, menu, mode selector, loading states, stable schema stub, core endpoints, and disabled news blocks. No live providers until source verification permits.

Sprint 2 first task: wire live public Binance/OKX adapters plus real `data_quality` while preserving fail-closed validation and `TO_VERIFY` source-governance rules.

Phase 1B and later: only after Claude-scoped plans and verification gates, add public market adapters, validation, quant baseline, frontend detail, Dev Mode, CI/security/deployment docs, news contract/stubs, calibration, live news adapters, and optional derivatives.
