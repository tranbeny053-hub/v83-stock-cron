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
| Persistence backend | Supabase REST for Hugging Face runtime; direct Postgres for local migrations/non-HF runtime | WAVE1_2_HOTFIX | Compact summaries only. If absent, run `STATELESS`; if failing, report `UNAVAILABLE` and keep analysis working. |
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
| OKX daily/weekly mapping | `1D -> 1Dutc`; `1W -> 1Wutc` | WAVE1_1_HOTFIX | UTC-aligned daily/weekly candles reduce Binance/OKX boundary mismatch without changing scoring, gates, probability, or provider auth behavior. |

## Wave 1.1 Stabilization Decisions

Status: Wave 1.1 hotfix only. It does not change Market Data v2, News Authority, calibration, scoring, probability, gates, news math, private provider endpoints, or deployment.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Cross-provider comparison bucket | Latest common closed candle by close time | WAVE1_1_HOTFIX | Avoids comparing non-equivalent open/closed provider candles, especially daily/weekly boundaries. |
| Optional cross-provider conflict handling | Explicit single public-provider live fallback when `UCPE_CROSS_PROVIDER_REQUIRED=false` | WAVE1_1_HOTFIX | No fixture fallback. Provider state records `cross_provider_state`, `fallback_to_single_provider`, `disagreement_bps`, and reason. |
| Required cross-provider conflict handling | Block with `DATA_CONFLICT` when `UCPE_CROSS_PROVIDER_REQUIRED=true` | WAVE1_1_HOTFIX | Existing tolerance remains unchanged. |
| App refresh control | Global `Re-analyze` button with cooldown | WAVE1_1_HOTFIX | Reuses existing analyze paths; frontend recomputes no score/probability/gate/news values. |
| Persistence visibility | Shell badge plus watchlist/detail/system status | WAVE1_1_HOTFIX | Shows `STATELESS`, `OK`, or `UNAVAILABLE`; no DB URL, host, username, password, or Supabase key. |
| Dev Mode disabled UX | Show clear disabled copy and disable re-auth controls | WAVE1_1_HOTFIX | Security semantics unchanged. |

## Wave 4A.1 Frontend Display Decisions

Status: frontend/display-layer hotfix only. It does not change scoring, probability, gates, tail risk, horizon timeout, volatility/trend formulas, config defaults, news influence, or provider behavior.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Overview-card probability display while uncalibrated | Hide precise Up/Down/Timeout percentages | WAVE4A_1_HOTFIX | Cards show qualitative status from existing `decision_brief.action` and direct users to Detail. |
| Detail probability display | Keep full percentages | WAVE4A_1_HOTFIX | Detail remains the place for full numeric inspection and raw/debug JSON. |
| Explanatory copy placement | One global legend | WAVE4A_1_HOTFIX | Removes repeated per-card yellow note to reduce visual noise. |
| Deferred math concerns | Do not change in Wave 4A.1 | DEFERRED | Tanh gain saturation, timeout cap behavior, realized-volatility scaling, tail CVaR universal breach behavior, and score ceiling/collapse artifacts require a later Claude-reviewed quant/calibration wave. |

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

## Wave 1.2 Supabase Runtime Connectivity Decision

Status: Wave 1.2 hotfix only. It does not change market data, news authority, calibration, scoring, probability, gates, provider behavior, or deployment automation.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Hugging Face runtime persistence | Prefer `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` via backend HTTPS REST | WAVE1_2_HOTFIX | Hugging Face may block outbound Postgres ports `5432`/`6543`; Supabase REST/PostgREST uses HTTPS `443`. |
| Direct Postgres persistence | Keep `SUPABASE_DB_URL` support for migrations/local direct DB or non-HF runtime | WAVE1_2_HOTFIX | `scripts/apply_migrations.py` still uses `SUPABASE_DB_URL` and never prints it. |
| Repository priority | `SUPABASE_REST` > `SUPABASE_POSTGRES` > `IN_MEMORY` | WAVE1_2_HOTFIX | If both REST and DB URL secrets exist, runtime uses REST. |
| Service role key handling | Backend-only secret | WAVE1_2_HOTFIX | Never exposed to frontend, status, debug export, logs, or docs as a value. |
| REST persistence failure | `persistence_status=UNAVAILABLE`, analysis still returns | WAVE1_2_HOTFIX | Same best-effort/circuit-breaker behavior as direct Postgres path. |

## Wave 2A Symbol Universe and Market Data v2 Decisions

Status: Wave 2A implements public REST market-data observability only. It does not change scoring, probability, gates, news math, calibration, private provider calls, WebSocket behavior, deployment automation, or trading capability.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Symbol universe | Public Binance `exchangeInfo` and OKX `public/instruments` for USDT spot pairs | WAVE2A_IMPLEMENTED | Cached by `UCPE_SYMBOL_UNIVERSE_CACHE_TTL_SECONDS`; no private keys; no per-analysis universe fetch while cache is fresh. |
| Symbol availability labels | `BOTH_PROVIDERS`, `BINANCE_ONLY`, `OKX_ONLY`, `UNSUPPORTED`, `TO_VERIFY` | WAVE2A_IMPLEMENTED | Single-provider symbols are allowed only when `UCPE_CROSS_PROVIDER_REQUIRED=false`; otherwise blocked. |
| Public resource expansion | Candles/depth remain required; ticker/trades are optional advisory resources | WAVE2A_IMPLEMENTED | Optional ticker/trade failures are visible in provider resources and do not fabricate values. |
| Derived market metrics | `spread_bps`, `mid_price`, `depth_imbalance`, shallow slippage estimate, recent trade pressure, freshness, cross-provider disagreement | WAVE2A_IMPLEMENTED | Formulaic evidence only; advisory unless explicitly wired in a later reviewed phase. |
| Frontend/detail behavior | Display backend `market_data_v2_detail`; recompute nothing | WAVE2A_IMPLEMENTED | Frontend remains a thin renderer. |
| WebSocket | Not implemented | OUT_OF_SCOPE_WAVE2A | REST-first only for this wave. |

## Wave 3A Advisory News Authority Foundation Decisions

Status: Wave 3A implements advisory/display-only metadata collection. It does not change scoring, probability, gates, disposition, calibration, trading capability, provider-private calls, or deployment automation.

| Decision | Default | Status | Notes |
|---|---|---|---|
| News authority mode | `influence_mode = ADVISORY_DISPLAY_ONLY` | WAVE3A_IMPLEMENTED | News context is displayed and persisted as metadata only. |
| News influence | `news_influence_frac = 0.0` | WAVE3A_IMPLEMENTED | No score/probability/gate/disposition influence in Wave 3A. |
| GDELT | Public DOC 2.0 JSON article-list metadata | WAVE3A_IMPLEMENTED | Tier 0, no key, fixed allow-listed host, no article URL fetch. |
| FRED | Public `series/observations` JSON macro observations | WAVE3A_IMPLEMENTED | Optional backend-only `FRED_API_KEY`; compact observations only. |
| NewsAPI | `/v2/everything` title/description metadata | WAVE3A_IMPLEMENTED | Optional backend-only `NEWSAPI_KEY`; provider text fields are ignored. |
| Dedup/entity/source authority | Deterministic title hash, conservative asset aliases, source-domain tier map | WAVE3A_IMPLEMENTED | Advisory scores use `_score` suffix and are bounded `[0,1]`; no sentiment-only action. |
| Persistence | `migrations/0002_news.sql` news metadata tables | WAVE3A_IMPLEMENTED | Compact metadata only; no full article text, no raw provider payloads, no secrets. |
| Live smoke | `UCPE_NEWS_LIVE_SMOKE_ENABLED=false` by default | WAVE3A_IMPLEMENTED | Optional manual script; never run in unit tests/CI by default. |

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

## Wave 4B0 Long-Timeframe Methodology Decisions

Status: Wave 4B0 is an R4 methodology patch. It does not change frontend display, providers, auth, news, migrations, dependencies, trading capability, calibration claims, reliability claims, or profitability claims.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Direction probability input | Bounded volatility-normalized signal before `tanh` | WAVE4B0_IMPLEMENTED_REVIEW_REQUIRED | Uses `net_signal / max(realized_vol, 0.02)`, cap `+/-2.0`, sensitivity `0.25`; probability invariant remains enforced. |
| Realized volatility | Per-bar log-return population standard deviation | WAVE4B0_IMPLEMENTED_REVIEW_REQUIRED | Removed sample-count multiplier so duplicating the same return distribution does not inflate `realized_vol`. |
| Timeout volatility term | Timeframe-aware vol reference | WAVE4B0_IMPLEMENTED_REVIEW_REQUIRED | References: `15m=0.02`, `1H=0.035`, `4H=0.06`, `1D=0.18`, `1W=0.45`, `1M=0.80`; timeout remains non-directional. |
| Tail CVaR gate | Threshold scales from 4H baseline by `sqrt(timeframe_seconds / 4H_seconds)` | WAVE4B0_IMPLEMENTED_REVIEW_REQUIRED | Uses existing `0.05` 4H baseline; extreme tails still hard-block. |
| Monthly sufficiency | Run minimum remains `24`; reliability threshold is `60` | WAVE4B0_IMPLEMENTED_REVIEW_REQUIRED | `1M` below 60 bars returns `LOW_SAMPLE` with `action=ALLOW`; it is not presented as fully sufficient. |
| Score stack | No direct score formula change | WAVE4B0_IMPLEMENTED_REVIEW_REQUIRED | Score changes only through corrected volatility/probability inputs and existing gates. |

## Wave 4B.1 Prediction Ledger Foundation Decisions

Status: Wave 4B.1 adds immutable prediction ledger writes only. It does not implement outcome resolution, calibration metrics, UI, API response changes, quant/probability/score/gate/news changes, or deployment automation.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Prediction ledger table | `predictions` via `migrations/0003_prediction_ledger.sql` | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | Idempotent `CREATE TABLE IF NOT EXISTS`; migration was not run by Codex. |
| Prediction identity | `prediction_id = "{run_id}:{timeframe}"` | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | One immutable prediction per analysis run/timeframe. |
| Immutability | Ignore duplicate `prediction_id` | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | Postgres `ON CONFLICT DO NOTHING`; REST `resolution=ignore-duplicates`; in-memory preserves first row. |
| Ledger write eligibility | Live data only with valid closed-candle reference time and price | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | Fixture/non-live/missing-anchor rows are skipped safely. |
| Reference anchor | Last closed candle close time and close price from selected snapshot | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | No open-candle, fabricated, or response-derived price anchor. |
| Horizon endpoint | `reference_close_utc + H_primary_bars * TIMEFRAME_SECONDS[timeframe]` | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | No resolver/outcome lookup in this wave. |
| Model/methodology versions | `phase1a-wave4b0`, `heuristic-v1-wave4b0` | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | Explicit constants; no calibration/reliability promotion. |
| API response contract | Unchanged | WAVE4B1_IMPLEMENTED_REVIEW_REQUIRED | Ledger row is internal persistence work only. |

## Wave 4B.2 Outcome Resolver Decisions

Status: Wave 4B.2 adds an offline no-lookahead outcome resolver only. It does not implement calibration metrics, UI, API endpoints, API response changes, quant/probability/score/gate/news changes, or deployment automation.

| Decision | Default | Status | Notes |
|---|---|---|---|
| Outcome table | `prediction_outcomes` via `migrations/0004_prediction_outcomes.sql` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Idempotent `CREATE TABLE IF NOT EXISTS`; migration was not run by Codex. |
| Outcome identity | `prediction_id` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | One immutable outcome per immutable prediction. |
| Due query | Live predictions where `horizon_end_utc < now_utc` and no existing outcome | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Ordered by `horizon_end_utc ASC`, limited by operator/script input. |
| Immutability | Ignore duplicate `prediction_id` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Postgres `ON CONFLICT DO NOTHING`; REST `resolution=ignore-duplicates`; in-memory preserves first row. |
| No-lookahead filter | Ignore all candles with `close_time_utc <= reference_close_utc` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Terminal and favorable/adverse calculations use post-anchor candles only. |
| Terminal candle | First closed candle with `close_time_utc >= horizon_end_utc` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | If absent, skip and write no outcome. |
| Stale-window guard | Skip if terminal candle overshoots horizon by more than one timeframe | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Prevents immutable mislabels when the true horizon candle has scrolled out of the fetched provider window. |
| Labeling | `UP` if terminal return is above band, `DOWN` below negative band, else `TIMEOUT` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Uses frozen `decision_band_frac`; fallback is `2 * taker_fee_frac`. |
| Resolver version | `resolver-v1-wave4b2` | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Explicit constant; no calibration/reliability promotion. |
| Runtime integration | Standalone script only | WAVE4B2_IMPLEMENTED_REVIEW_REQUIRED | Not imported by `api/**`; not called by `/v1/analyze`. |
| Bounded historical fetch | Deferred | WAVE4B2_FUTURE_IMPROVEMENT | The stale-window guard is the targeted safety fix; bounded provider fetch can be added later without widening this hotfix. |
| Operator repository selection | Prefer `SUPABASE_DB_URL` direct Postgres for resolver script | WAVE4B2_TARGETED_FIX_IMPLEMENTED | Fixes local/operator mismatch where the generic app builder preferred Supabase REST while operator SQL probes used direct Postgres. Generic app builder remains REST-first. |
| Postgres due query | `public.predictions` left join `public.prediction_outcomes` | WAVE4B2_TARGETED_FIX_IMPLEMENTED | Matches operator SQL probe; DB failure is surfaced as sanitized resolver failure instead of silent fallback to empty in-memory rows. |
| Postgres due-fetch wrapper | Direct psycopg connection for operator due fetch | WAVE4B2_TARGETED_FIX_IMPLEMENTED | Avoids `psycopg_pool` wrapper dependency for due rows; pooled `_run_db` remains available for existing best-effort write paths. |
| Postgres statement timeout | Internal integer literal for `SET LOCAL statement_timeout` | WAVE4B2_TARGETED_FIX_IMPLEMENTED | Fixes PostgreSQL syntax errors near `$1` caused by binding parameters into `SET LOCAL`. |
| Postgres outcome write path | Direct psycopg connection with `ON CONFLICT DO NOTHING` | WAVE4B2_TARGETED_FIX_IMPLEMENTED | Avoids `psycopg_pool` dependency for operator outcome writes while preserving immutable first-write-wins behavior. |

## Wave 4B.2A Resolver Automation Decisions

| Decision | Default | Status | Notes |
|---|---|---|---|
| Scheduler | GitHub Actions schedule, minute 17 hourly UTC | WAVE4B2A_IMPLEMENTED_REVIEW_REQUIRED | HF Free background scheduling is not relied on. |
| Manual run | `workflow_dispatch` with `limit` default `50` | WAVE4B2A_IMPLEMENTED_REVIEW_REQUIRED | Allows operator-triggered resolver runs without code changes. |
| Secret | GitHub repository secret `SUPABASE_DB_URL` | WAVE4B2A_IMPLEMENTED_REVIEW_REQUIRED | Secret is passed only as environment variable to the resolver step and is not printed. |
| Failure semantics | Nonzero if resolver output has `failed > 0` | WAVE4B2A_IMPLEMENTED_REVIEW_REQUIRED | Script now exits nonzero on prediction failures; workflow also greps summary output. |
| Scope | Resolver script only | WAVE4B2A_IMPLEMENTED_REVIEW_REQUIRED | No migrations, deployment, API, frontend, quant, score, gate, news, calibration, or trading path. |
