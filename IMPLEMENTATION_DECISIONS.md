# Implementation Decisions

Canonical source: Ultimate_Crypto_Probability_Engine_Blueprint_v1_2_2.md (v1.2.2, locked; held by the operator, not in this repo).

Status: Phase 0 defaults extracted from Blueprint section 2.2. Sprint 1 rows promoted to `DEFAULT_PHASE1A` reflect Claude-approved Sprint 1 implementation defaults and remain visible config, not silent hardcoding.

Defaults must be visible config, never silent hardcoding. R4 behavior remains subject to Claude final review before merge/deploy.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Supported timeframes | `15m, 1H, 4H, 1D, 1W, 1M`; primary default `4H`; trend set `{1H, 4H, 1D}` | DEFAULT_PHASE1A + SPRINT3_APPROVED | Sprint 3 adds monthly analysis support. Trend timeframes remain unchanged. |
| Analysis horizons | `H_primary = 6 bars`; `H_extended = 24 bars` | DEFAULT_PHASE1A | Claude-approved Sprint 1 default; labels remain horizon names in responses. |
| Analysis-mode default | `METRICS_ONLY` | DEFAULT_PHASE1A | Claude-approved Sprint 1 default; `NEWS_ADDON` remains opt-in per request. |
| News source set | Provider-agnostic adapters; none mandatory | DEFAULT_PROPOSED | Configure at least one reliable source to enable live `NEWS_ADDON`; otherwise return `UNAVAILABLE`. Specific sources remain `TO_VERIFY`. |
| News freshness budgets | `freshness budget = 1.5x timeframe interval` for Sprint 1 market-data freshness | DEFAULT_PHASE1A | Claude-approved Sprint 1 default; future news-specific category budgets remain `TO_VERIFY`. |
| News snippet policy | Short, sanitized, attributed, linked | DEFAULT_PROPOSED | Never store or display full copyrighted bodies; store title/url hash plus metadata. |
| Persistence backend | Supabase Postgres direct database URL, optional | WAVE1_IMPLEMENTED | Compact summaries only. If absent, run `STATELESS`; if failing, report `UNAVAILABLE` and keep analysis working. |
| Detail-view delivery | Embed in single mode; fetch-on-click in batch | DEFAULT_PROPOSED | Follow the blueprint detail delivery contract; frontend still recomputes nothing. |
| Access-code storage | PBKDF2-HMAC-SHA256 hash in env/secret with env-configurable iterations and per-deploy salt | DEFAULT_PHASE1A | Claude final-review fix; no plaintext production passcode in frontend or repo. |
| Perp venue | OKX swaps + Binance USD-M candidates | DEFAULT_PROPOSED | Phase 3 only, gated behind `CRYPTO_PERP`; venue/source details remain `TO_VERIFY`. |
| Cross-provider tolerance | `price_disagreement_bps = 50` | DEFAULT_PHASE1A | Claude-approved Sprint 1 default; fail closed on conflicts above tolerance. |

Additional `DEFAULT_PHASE1A` config values from the Sprint 1 plan:

- `min_history_bars = 200`; otherwise `INSUFFICIENT_DATA`.
- Fees: `taker_fee_frac = 0.001`, `maker_fee_frac = 0.001`; net-of-cost is binding.
- Slippage model: depth-aware Sprint 1 baseline.
- Arbiter weights: `w_alpha = 1.0`, `w_omega = 1.0`, `w_sigma = 1.5`; `risk_arbiter_version = risk_arbiter_v1`.
- News evidence: `0.0`.
- Probability: `probability_v1_phase1a`; `p_timeout` clamp `[0.10, 0.80]`; up/down via bounded transform; shrink toward 0.5 when epistemic is below `SUFFICIENT`; normalize to enforce invariant.
- Tail: `HISTORICAL_CVAR` at `99%`; EVT disabled.
- `calibration_status = DEFAULT_PHASE1A`; `reliability_status = INSUFFICIENT_SAMPLE`.
- Probability constants now live in config: signal sensitivity, tilt midpoint/scale, and extended-horizon confidence multiplier.
- Timeout constants now live in config: base timeout, volatility cap, spread multiplier, and spread cap.
- Score constants now live in config: base score, directional-edge multiplier, score bounds, constructive/elevated-risk thresholds, and risk-pressure cap.
- Sprint 1 risk-guard thresholds now live in config: liquidity max spread, liquidity minimum depth, tail CVaR breach, and execution cost hard-gate threshold.
- Sprint 1 limitation: `H_primary` and `H_extended` share the same directional split, with only extended-horizon confidence scaled. Full horizon-specific modeling is Sprint 2.
- Sprint 1 limitation: liquidity/tail/execution hard gating is deterministic guardrail coverage only. Full hard-gating depth for these areas is a Sprint 2 item.
- Sprint 2 first task: wire live public Binance/OKX adapters plus real `data_quality`; keep fixture/demo labeling until live data is actually verified.

## Sprint 3 1M Timeframe Decision

Status: `SAFE_TO_IMPLEMENT` from Claude Sprint 3 plan; R2 because it touches data validation/min-history but not scoring, gate, probability, or news math.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Monthly timeframe support | Add `1M` to supported timeframes | SPRINT3_APPROVED | Single and batch analysis may request monthly analysis. |
| Monthly duration | `TIMEFRAME_SECONDS["1M"] = 30 * 24 * 60 * 60` | SPRINT3_APPROVED | Approximate calendar-month duration for validation/freshness windows. |
| Monthly min history | `MIN_HISTORY_BARS_BY_TIMEFRAME["1M"] = 24` | SPRINT3_APPROVED | Global `min_history_bars = 200` remains unchanged for sub-monthly timeframes. |
| Binance monthly mapping | `1M -> 1M` | SPRINT3_APPROVED | Public spot kline monthly interval. |
| OKX monthly mapping | `1M -> 1Mutc` | SPRINT3_APPROVED | UTC-aligned monthly candles reduce provider boundary mismatch for monthly analysis. |
| Existing OKX 1D/1W alignment mismatch | Future item | DEFERRED | Pre-existing HK alignment mismatch remains out of scope for Sprint 3. |

## Wave 1 Persistence Decisions

Status: Wave 1 implemented as persistence foundation only. It does not change market data, news authority, calibration, scoring, probability, gates, provider behavior, or deployment.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Database adapter | Supabase Postgres via `SUPABASE_DB_URL` | WAVE1_IMPLEMENTED | Uses backend-only `psycopg`; frontend never references Supabase. |
| Optional Supabase URL/key settings | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | WAVE1_DECLARED_UNUSED | Names exist for future backend-only use; unused in Wave 1. |
| No configured DB | `persistence_status=STATELESS` | WAVE1_IMPLEMENTED | Analysis returns normally; watchlist can use in-memory backend and browser fallback. |
| DB operation failure | `persistence_status=UNAVAILABLE` | WAVE1_IMPLEMENTED | Persistence errors are caught and never raised into the analysis hot path. |
| Stored analysis data | Compact run/timeframe/provider summaries only | WAVE1_IMPLEMENTED | Full analysis payloads and full article bodies are not stored. |
| Watchlist limit | `20` symbols per operator | WAVE1_IMPLEMENTED | Symbols are validated through the existing normalizer. |

## `_frac` Field Audit

Decision: `_frac` suffix is reserved for values that are bounded to `[0,1]` before they are emitted. Signed ratios and unbounded magnitudes must not use `_frac`.

| Field | Classification | Kept/Renamed | Reason | Test coverage |
|---|---|---|---|---|
| `p_up_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Probability mass; invariant-validated. | Probability invariant tests; recursive response `_frac` test. |
| `p_down_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Probability mass; invariant-validated. | Probability invariant tests; recursive response `_frac` test. |
| `p_timeout_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Probability mass; invariant-validated and timeout is non-directional. | Probability invariant tests; recursive response `_frac` test. |
| `p_up_user_norm_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | User-normalized directional probability. | Schema/model validation; recursive response `_frac` test. |
| `p_down_user_norm_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | User-normalized directional probability. | Schema/model validation; recursive response `_frac` test. |
| `confidence_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Displayed model confidence placeholder. | Schema/model validation; recursive response `_frac` test. |
| `news_confidence_adj_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Sprint 2 remains no-op at `0.0`. | Schema/model validation; recursive response `_frac` test. |
| `spread_frac` | COST_OR_SPREAD_FRACTION_BOUNDED_BY_CONSTRUCTION | Kept | Order-book spread is emitted only when within `[0,1]`; otherwise liquidity degrades and value is `null`. | Wide-spread degradation test; recursive response `_frac` test. |
| `taker_fee_frac` | COST_OR_SPREAD_FRACTION_BOUNDED_BY_CONSTRUCTION | Kept | Configured fee fraction. | Recursive response `_frac` test. |
| `maker_fee_frac` | COST_OR_SPREAD_FRACTION_BOUNDED_BY_CONSTRUCTION | Kept | Configured fee fraction. | Recursive response `_frac` test. |
| `slippage_frac` | COST_OR_SPREAD_FRACTION_BOUNDED_BY_CONSTRUCTION | Kept | Derived only from bounded spread; invalid spread degrades before emission. | Wide-spread degradation test; recursive response `_frac` test. |
| `round_trip_cost_frac` | COST_OR_SPREAD_FRACTION_BOUNDED_BY_CONSTRUCTION | Kept | Fee plus bounded slippage remains within `[0,1]`; invalid spread degrades. | Wide-spread degradation test; recursive response `_frac` test. |
| `tail_confidence_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | CVaR confidence level, not loss magnitude. | Quant tests; recursive response `_frac` test. |
| `cvar_loss_frac` / `cvar_loss` | UNBOUNDED_MAGNITUDE | Renamed to `cvar_loss` | Historical log-loss magnitude can exceed `1.0`. | High-volatility fixture test; recursive response `_frac` test. |
| `realized_vol_frac` / `realized_vol` | UNBOUNDED_MAGNITUDE | Renamed to `realized_vol` | Realized volatility magnitude can exceed `1.0`. | High-volatility fixture test; live smoke. |
| `risk_pressure_frac` / `risk_pressure` | UNBOUNDED_MAGNITUDE | Renamed to `risk_pressure` | Weighted risk pressure can exceed `1.0`. | High-volatility fixture test; live smoke. |
| `primary_return` | SIGNED_RATIO_OR_SIGNAL | Kept non-`_frac` | Signed return can be negative. | Down-market fixture test. |
| `extended_return` | SIGNED_RATIO_OR_SIGNAL | Kept non-`_frac` | Signed return can be negative. | Down-market fixture test. |
| `alpha_signal` | SIGNED_RATIO_OR_SIGNAL | Kept non-`_frac` | Signed signal can be negative. | Down-market fixture test. |
| `net_signal` | SIGNED_RATIO_OR_SIGNAL | Kept non-`_frac` | Signed net signal can be negative. | Down-market fixture test. |
| `directional_edge` | SIGNED_RATIO_OR_SIGNAL | Kept non-`_frac` | Up/down edge can be negative. | Down-market fixture test. |
| `news_evidence_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Sprint 2 news evidence is no-op at `0.0`. | News contract tests; recursive response `_frac` test. |
| `news_influence_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Sprint 2 news influence is no-op at `0.0`. | News contract/frontend no-recompute tests; recursive response `_frac` test. |
| `influence_frac` | TRUE_FRACTION_BOUNDED_0_1 | Kept | Placeholder feature influence values are no-op at `0.0`. | Recursive response `_frac` test. |
