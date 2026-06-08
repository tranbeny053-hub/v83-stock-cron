# Decision Log

## 2026-06-06 - Blueprint v1.2.2 Locked for Phase 0

Decision: Treat `Ultimate_Crypto_Probability_Engine_Blueprint_v1_2_2.md` as the highest product, architecture, security, quant, news, deployment, and governance source of truth.

Rationale: The blueprint states the app is locked for Phase 0 artifact extraction and that future improvements should come from implementation evidence, tests, source verification, reviews, and release gates rather than feature expansion.

Impact: No app code or new product features are created during Phase 0.

## 2026-06-06 - Correct Claude/Codex Role Model

Decision: Use the corrected role split:

```text
Claude Code Opus = CTO / System Architect / Blueprint Interpreter / Critical Debugger / Refactor Planner / Security-Risk Reviewer / Final Technical Reviewer / Recovery Agent
Codex            = Implementation Engineer / Scoped Feature Builder / QA Engineer / Test Runner / Regression Checker / Codebase Explorer / Documentation-Handoff Maintainer / Parallel Executor
User             = non-coder approver/operator
```

Rationale: The transfer package explicitly rejects the old Codex-planner / Claude-builder model.

Impact: Claude owns high-risk architecture, financial, security, deployment, recovery, and final review. Codex owns scoped implementation, tests, QA, and docs.

## 2026-06-06 - Phase 0 Artifact Extraction Only

Decision: Create only the requested Phase 0 operating artifacts and no app code.

Rationale: The delegation packet is R1 docs-only, with some R4 safety content requiring Claude final review.

Impact: `README.md` and `IMPLEMENTATION_DECISIONS.md` were not created or edited in this run because they were not explicitly approved in the final requested artifact list.

## 2026-06-06 - Routine Prompts Must Not Paste Full Blueprint

Decision: Future Claude/Codex prompts should reference `IMPLEMENTATION_SPEC.md` and `/AI` docs instead of pasting the full blueprint.

Rationale: Token-efficient implementation contract requires layered context and file-backed state.

Impact: `AI/03_CURRENT_STATE.md`, `AI/04_TASK_BOARD.md`, and `AI/05_HANDOFF.md` become routine context for future sessions.

## 2026-06-06 - Provider and Source Details Stay TO_VERIFY

Decision: All provider/API/news/macro/source specifics remain `TO_VERIFY` until verified against current official documentation.

Rationale: Blueprint Source Verification Matrix requires official docs before provider/source implementation becomes production-critical.

Impact: Phase 1A may use abstract/stub/disabled paths. No source-specific production adapter should be implemented until verification fields are complete.

## 2026-06-06 - Phase 0 Claude Review Fixes Applied

Decision: Apply the Phase 0 docs-only Claude review fix pass without touching app code.

Rationale: The fix pass tightens source references, records Blueprint section 2.2 defaults in `IMPLEMENTATION_DECISIONS.md`, restores the full Codex role wording, updates changelog metadata, ignores `.DS_Store`, and re-records verification evidence.

Impact: Phase 0 remains docs-only. `IMPLEMENTATION_SPEC.md` still carries R4 financial-safety content and remains pending Claude + User approval.

## 2026-06-06 - Sprint 1 DEFAULT_PHASE1A Values Implemented

Decision: Promote the Claude-approved Sprint 1 default values into visible config and implement the WP4 deterministic baseline against those config values.

Rationale: The Sprint 1 Master Plan explicitly approves the Phase 1A defaults for timeframes, horizons, freshness, history, costs, arbiter weights, probability clamps, tail method, and calibration/reliability status.

Impact: `IMPLEMENTATION_DECISIONS.md` now marks matching rows as `DEFAULT_PHASE1A`; WP4 remains R4 and requires Claude final review before merge/deploy.

## 2026-06-06 - Claude Final Review Fixes Applied

Decision: Apply Claude final-review fixes for Sprint 1 without new product scope: blueprint disposition vocabulary, deterministic liquidity/tail/execution guardrails, config-owned constants, secure-cookie default, PBKDF2 access-code hashing, fixture-demo labeling, Docker ignore hardening, and Sprint 2 limitation/backlog documentation.

Rationale: Claude identified merge-blocking and deploy-blocking safety gaps before merge/deploy.

Impact: Sprint 1 remains analysis-only and fixture-backed. `codex/sprint1-prod-build` requires Claude re-review before merge/deploy.

## 2026-06-07 - Sprint 2 Public Market Data Integration

Decision: Implement live Binance/OKX spot market data through public unauthenticated endpoints only, with `UCPE_DATA_MODE=live` default and explicit `UCPE_DATA_MODE=fixture` for demo/test fixture mode.

Rationale: Claude Sprint 2 plan verified the Binance/OKX spot endpoint families for keyless public market data and required truthful `is_live_data` / `data_source` behavior.

Impact: Live-mode failures or cross-provider conflicts fail closed as visible degraded/unavailable errors and never silently return fixture data. No Binance/OKX API keys, private exchange calls, live news fetching, quant/scoring/gate/news authority changes, merge, or deploy are included.

## 2026-06-07 - Sprint 2 Targeted Fixes Applied

Decision: Apply Claude `APPROVE_WITH_TARGETED_FIXES` without redesigning Sprint 2: rename signed return/signal/edge fields to non-`_frac` names, add down-market fixture coverage, add a PBKDF2 access-hash helper, and fetch a small provider candle margin.

Rationale: Real live data can produce negative signed ratios; `_frac` is reserved for bounded `[0,1]` values and is enforced by sentinel validation. Non-coder deployment also needed a safe hash-generation path.

Impact: Live smoke now passes for BTC and ETH in both modes with schema-valid `CROSS_PROVIDER` payloads. No quant math, provider architecture, trading capability, private provider call, live news fetch, merge, or deploy was added.

## 2026-06-07 - Sprint 2 Final `_frac` Defect-Class Fix

Decision: Close the remaining unbounded `_frac` defect class by renaming `realized_vol_frac` to `realized_vol`, `risk_pressure_frac` to `risk_pressure`, and `cvar_loss_frac` to `cvar_loss`; keep the strict `_frac` sentinel unchanged.

Rationale: Realized volatility, risk pressure, and historical CVaR loss are unbounded magnitudes and can exceed `1.0` during volatile markets. The `_frac` suffix must only identify values that are guaranteed within `[0,1]`.

Impact: High-volatility offline responses and volatile-symbol live smoke validate without sentinel failures. Remaining emitted `_frac` fields are recursively tested as numeric `[0,1]` values. No trading capability, private exchange calls, live news fetching, merge, or deploy was added.

## 2026-06-08 - Wave 3A Advisory News Authority Foundation

Decision: Add a live news authority foundation that is advisory/display-only: `news_influence_frac=0.0`, `influence_mode=ADVISORY_DISPLAY_ONLY`, and no news path feeds score, probability, gates, disposition, or hard warnings.

Rationale: The user already configured optional FRED and NewsAPI Hugging Face secrets, and GDELT is public/no-key. Wave 3A needs visible macro/micro context without creating decision authority, body scraping, arbitrary URL fetching, or secret exposure.

Impact: GDELT, FRED, and optional NewsAPI are implemented as metadata-only providers behind fixed host allow-lists. Compact news metadata persistence is added with `migrations/0002_news.sql`. Detail Analysis can display `News Authority / Macro & Micro Context`; `METRICS_ONLY` still fetches no news and `NEWS_ADDON` remains unavailable/degraded when providers are absent or unhealthy. No full article body, scoring/probability/gate/news influence change, trading capability, merge, deploy, or Hugging Face push was added.
