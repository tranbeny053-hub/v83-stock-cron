# Changelog

All notable changes to this project are recorded here.

## 2026-06-06 - Blueprint v1.2.2 Phase 0 Artifact Extraction

Blueprint version: `v1.2.2`
schema_version: `TBD`
app_version: `TBD`

Phase: Phase 0 docs-only operating artifacts.

Added draft artifacts:
- `IMPLEMENTATION_SPEC.md`
- `IMPLEMENTATION_DECISIONS.md`
- `CLAUDE.md`
- `AGENTS.md`
- `.gitignore`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/02_ARCHITECTURE.md`
- `AI/03_CURRENT_STATE.md`
- `AI/04_TASK_BOARD.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `DEBUG_PACK_EXAMPLE.md`
- `DEPLOYMENT_CHECKLIST.md`
- `RELEASE_GATE.md`
- `ROLLBACK_PLAN.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `CHANGELOG.md`

Notes:
- No app code was implemented.
- No deployment config, schema, CI, provider adapter, backend API, frontend implementation, dependency file, secret, or README update was created.
- Provider/API/news/macro/source details remain `TO_VERIFY`.
- `IMPLEMENTATION_SPEC.md`, `AI/01_BLUEPRINT_SUMMARY.md`, `AI/00_PROJECT_RULES.md`, and `RELEASE_GATE.md` need Claude final review before becoming canonical.

## 2026-06-06 - Phase 0 Claude Review Fix Pass

Changed:
- Replaced home-directory source references with filename-only source references in committed docs.
- Added `UNSUPPORTED_ASSET_CLASS` to `IMPLEMENTATION_SPEC.md`.
- Added `IMPLEMENTATION_DECISIONS.md` for Blueprint section 2.2 defaults.
- Restored the full Codex role wording in `AGENTS.md`.
- Added timeframe and metric-group summary to `AI/01_BLUEPRINT_SUMMARY.md`.
- Added `.gitignore` with `.DS_Store`.
- Updated `AI/03_CURRENT_STATE.md` and `AI/05_HANDOFF.md` with fix-pass verification.

Notes:
- No app code was implemented.
- `IMPLEMENTATION_SPEC.md` still carries R4 financial-safety content and remains flagged for Claude review.

## 2026-06-06 - Production Build Sprint 1

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Added:
- FastAPI app factory, auth/session endpoints, health/status endpoints, analysis/detail/debug endpoints.
- Stable JSON Schemas and Pydantic response/request models.
- Public-only fixture-backed market-data boundary, symbol normalization, validation, and provider failover/quarantine state.
- Deterministic `DEFAULT_PHASE1A` quant baseline with invariant validation, hard gates, score stack, tail CVaR, and calibration/reliability labels.
- News contract stubs with `METRICS_ONLY` no-fetch behavior, `NEWS_ADDON` unavailable fallback, and no-op influence.
- Static cyberpunk frontend thin renderer.
- In-memory recent-run store, sanitized debug export, best-effort telemetry sink.
- Dockerfile for Hugging Face Docker Space target on port `7860`.
- Checkers for forbidden capability strings, secret-like assignments, full article bodies, and schema validation.
- Optional GitHub Actions CI workflow.

Verification:
- `PYTHONPATH=src python3 -m pytest`: PASS, 53 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- Safety/schema/manual-smoke scripts: PASS.
- Local uvicorn/curl smoke: PASS after elevated local bind permission; `/healthcheck`, `/v1/system_status`, `METRICS_ONLY`, and `NEWS_ADDON` verified.

Notes:
- No deploy and no merge performed.
- Live Binance/OKX/news provider source details remain `TO_VERIFY`; runtime analysis uses deterministic fixture data in Sprint 1.
- WP2 auth/security, WP4 quant/financial logic, WP5 news authority, and WP8 Docker/deployment/checkers require Claude final review before merge/deploy.

## 2026-06-06 - Claude Final Review Fix Pass

Changed:
- Replaced the non-blueprint score disposition with `ELEVATED_RISK_AVOID`.
- Added deterministic guardrails so bad liquidity, tail breach, or excessive execution cost force non-constructive output.
- Moved probability, timeout, score, and risk-guard constants into visible `DEFAULT_PHASE1A` config.
- Added `.dockerignore` and expanded `.gitignore` for env/key/secret-like files.
- Added secure-cookie runtime setting with secure default.
- Added PBKDF2-HMAC-SHA256 access-code hashing with configurable iterations and salt.
- Marked Sprint 1 responses and frontend with `FIXTURE_DEMO` / non-live data labeling.
- Documented Sprint 1 limitations for H-primary/H-extended split simplification and incomplete full hard-gating.

Notes:
- No deploy and no merge performed.
- Sprint 2 first task is live public Binance/OKX adapters plus real `data_quality`.
- Claude re-review is required before merge/deploy.

## 2026-06-07 - Sprint 2 Live Public Market Data

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Added:
- `docs/source_verification_matrix.md` with Binance/OKX spot public endpoint rows marked `VERIFIED_PUBLIC`.
- Env-driven live data config: `UCPE_DATA_MODE`, provider priority, timeout, retries, rate limit, candle cache TTL, cross-provider requirement, and live-smoke gate.
- Safe public HTTP client with host allow-list, bounded timeout/retries, local throttle, and typed provider errors.
- Binance and OKX public spot adapters for candles and books using keyless endpoints only.
- Provider selection layer with cross-provider coherence, single-source warning, `DATA_CONFLICT` fail-closed behavior, all-provider `UNAVAILABLE`, explicit fixture mode, and no silent live-to-fixture fallback.
- Analysis-service data-quality wiring and frontend data-source honesty banner.
- `scripts/live_smoke.py`, gated by `UCPE_LIVE_SMOKE_ENABLED=true`.
- Pytest socket guard blocking real network in unit tests.

Verification:
- Full pytest with socket guard: PASS, 76 passed, 3 warnings.
- Ruff: PASS after package fixes.

Notes:
- No deploy and no merge performed.
- No Binance/OKX API keys or private/authenticated exchange calls were added.
- Live smoke was not run because `UCPE_LIVE_SMOKE_ENABLED` was not enabled.
- Claude final review is required for provider integration, data honesty, no-network tests, HF env table, and release gate.

## 2026-06-07 - Sprint 2 Targeted Fix Pass

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Changed:
- Renamed signed fields from `_frac` names to `primary_return`, `extended_return`, `alpha_signal`, `net_signal`, and `directional_edge`.
- Added down-market fixture and regression tests for negative signed fields, schema validation, and probability invariant.
- Added `scripts/make_access_hash.py` for PBKDF2-HMAC-SHA256 access-code hash generation with local `UCPE_ACCESS_CODE_SALT`.
- Added Binance/OKX candle fetch margin before closed-candle validation.
- Updated live smoke to test BTC and ETH in both `METRICS_ONLY` and `NEWS_ADDON`.
- Updated deployment docs, release gate, test commands, memory, current state, handoff, and decision log.

Verification:
- Full pytest: PASS, 80 passed, 3 warnings.
- Ruff: PASS.
- Safety/schema/manual smoke scripts: PASS.
- Live smoke with `UCPE_LIVE_SMOKE_ENABLED=true`: PASS for BTC/ETH in both modes, all `CROSS_PROVIDER`.

Notes:
- No deploy and no merge performed.
- No Binance/OKX API keys, private exchange calls, live news fetching, or trading capability were added.
- Claude re-review is required before merge/deploy.

## 2026-06-07 - Sprint 2 Final `_frac` Defect-Class Fix

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Changed:
- Renamed unbounded magnitude fields from `realized_vol_frac`, `risk_pressure_frac`, and `cvar_loss_frac` to `realized_vol`, `risk_pressure`, and `cvar_loss`.
- Kept `_frac` sentinel validation strict and unchanged.
- Added high-volatility offline fixture coverage proving unbounded magnitudes can exceed `1.0` without schema failure.
- Added recursive full-response test that every emitted `_frac` field is numeric and within `[0,1]`.
- Extended live smoke to support `UCPE_LIVE_SMOKE_SYMBOLS`.
- Documented the systematic `_frac` field audit in `IMPLEMENTATION_DECISIONS.md`.

Notes:
- No deploy and no merge performed.
- No Binance/OKX API keys, private exchange calls, live news fetching, or trading capability were added.

## 2026-06-07 - Sprint 3 UI and 1M Timeframe Polish

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Changed:
- Added `1M` monthly timeframe support with Binance `1M` and OKX `1Mutc` public candle mappings.
- Added timeframe-aware minimum history: `1M` requires `24` candles while sub-monthly timeframes keep the `200`-bar default.
- Updated live public adapter fetch limits to request the timeframe-specific minimum plus a small closed-candle margin.
- Replaced Single Analysis timeframe dropdown with six progressive timeframe cards: `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
- Added red-to-grey signal heat styling and preserved the required `Signal heat — not risk` label.
- Replaced raw JSON as the primary detail experience with structured Overview, Probability, Risk/Gates, Market Data Quality, Provider State, Quant Signals, News Add-on, and collapsed Debug/Raw JSON sections.
- Added frontend static checks plus backend validation/API/quant tests for `1M`.

Notes:
- No deploy and no merge performed.
- No auth/security, Docker, provider HTTP client internals, scoring/gate/probability/news math, private exchange calls, live news fetching, or trading capability were added.

## 2026-06-07 - Deployed Frontend Polish Hotfix

Changed:
- Replaced continuous red/grey card heat styling with six discrete backend-score heat bands.
- Fixed Batch Analysis cards so Detail opens the same structured Detail Analysis renderer used by Single Analysis.
- Added a site-wide footer signature: `Copyright © 2026 by Kha`.
- Added frontend static tests for heat bands, batch detail wiring, collapsed raw JSON, no-recompute boundary, and signature visibility.

Notes:
- Frontend-only hotfix.
- No backend quant/scoring/gates/news/auth/deploy/provider logic was changed.
- No deploy or Hugging Face push was performed.

## 2026-06-07 - Wave 1 Supabase Persistence and Watchlist Foundation

Changed:
- Added optional Supabase Postgres persistence foundation with idempotent `migrations/0001_init.sql`.
- Added `scripts/apply_migrations.py` for local, URL-safe migration application.
- Added backend persistence repository layer with stateless in-memory fallback and Supabase adapter.
- Added best-effort compact persistence for analysis runs, timeframe results, and provider observations.
- Added `persistence_status` to debug-safe response data.
- Added session-gated watchlist backend endpoints and a frontend Watchlist tab with browser storage fallback.
- Added `psycopg[binary]>=3,<4` to backend requirements.
- Added tests for stateless analysis, persistence outage degradation, watchlist CRUD, migration safety, and frontend watchlist hooks.

Notes:
- No backend quant/scoring/gates/news math was changed.
- No provider adapter behavior, Binance/OKX keys, private exchange calls, live news fetching, or trading capability was added.
- No deploy or Hugging Face push was performed.

## 2026-06-07 - Wave 1 Targeted Persistence Fixes

Changed:
- Moved analysis persistence writes out of the HTTP response path.
- Added FastAPI background scheduling that submits compact persistence work to a bounded worker pool.
- Added Supabase repository circuit breaker with cooldown and fast skip while unavailable.
- Replaced connect-per-operation behavior with a small `psycopg_pool.ConnectionPool`.
- Added defensive persistence wrapper behavior for unexpected repository exceptions.
- Added tests for non-blocking analyze response, raising repository failure path, circuit breaker transitions, and degraded watchlist behavior.
- Updated requirements to `psycopg[binary,pool]>=3,<4`.

Notes:
- No quant/scoring/probability/gates/news math changed.
- No Binance/OKX provider logic, private exchange calls, live news fetching, or trading capability was added.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-07 - Wave 1.1 Stabilization Hotfix

Changed:
- Mapped OKX daily and weekly public candles to UTC intervals: `1Dutc` and `1Wutc`.
- Changed cross-provider coherence to compare the latest common closed candle bucket instead of each provider's latest row.
- Preserved the existing cross-provider tolerance while allowing explicit single public-provider live fallback when `UCPE_CROSS_PROVIDER_REQUIRED=false`.
- Added provider-state details for cross-provider state, disagreement basis, fallback flag, and fallback reason.
- Added a visible app-shell `Re-analyze` control with cooldown and last-refreshed timestamp.
- Added app-shell persistence status visibility and surfaced persistence status in Detail/System status.
- Clarified Dev Mode disabled/configuration UX without changing security semantics.
- Added regression tests for 1D/1W alignment, open-candle exclusion, optional/required cross-provider conflict behavior, refresh/static UI hooks, persistence status, and Dev Mode disabled copy.

Notes:
- Cross-provider tolerance was not loosened.
- Live mode still never falls back to fixture data.
- No quant/scoring/probability/gates/news math, private provider endpoints, secrets, deployment logic, or trading capability changed.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-08 - Wave 1.2 Supabase REST Runtime Hotfix

Changed:
- Added backend-only `SupabaseRestRepository` using Supabase PostgREST over HTTPS for Hugging Face runtime persistence.
- Runtime repository priority is now `SUPABASE_REST` when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` exist, then `SUPABASE_POSTGRES` via `SUPABASE_DB_URL`, then `IN_MEMORY`.
- Kept direct Postgres support for local migrations/direct DB or non-Hugging-Face runtimes.
- Added REST persistence support for compact run, timeframe, provider-observation, recent-run, get-run, and watchlist methods.
- Added mocked `httpx` tests for REST writes, watchlist CRUD, circuit breaker failure, runtime selection priority, status diagnostics, and analysis continuing under REST outage.
- Updated deployment docs to clarify that Hugging Face should use REST secrets and that Postgres ports `5432`/`6543` may be blocked.

Notes:
- No quant/scoring/probability/gates/news math changed.
- No market-data provider behavior, private exchange calls, live news fetching, or trading capability was added.
- No Supabase values are exposed to frontend/status/debug; only secret names are documented.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-08 - Wave 2A Symbol Universe and Market Data v2

Changed:
- Added public symbol-universe resolution from Binance `exchangeInfo` and OKX `public/instruments` for spot USDT pairs.
- Relaxed static symbol normalization so valid `BASE/USDT`, `BASE-USDT`, and `BASEUSDT` aliases can be resolved by provider universe instead of a hardcoded base list.
- Expanded Binance public REST collection to include ticker and recent trades alongside existing klines/depth.
- Expanded OKX public REST collection to include ticker and recent trades alongside existing candles/books.
- Added compact provider resource observability: candles/depth/ticker/trades availability, latency, freshness, and warnings.
- Added advisory derived market metrics from real public data only: spread bps, mid price, depth imbalance, shallow slippage estimate, recent trade pressure, freshness, and cross-provider disagreement.
- Added `Market Data v2 / Provider Observability` to structured Detail Analysis.
- Added tests for symbol aliases/universe availability, provider-only fallback/blocking, unsupported symbols, universe cache, resource parsers, derived metrics, detail payload, and frontend render hooks.

Notes:
- Derived market metrics are formulaic metadata only and do not affect scoring, probability, gates, or news influence.
- No WebSocket, News Authority Engine, calibration, private/signed exchange endpoints, Binance/OKX API keys, deployment, or trading capability was added.
- No deploy, merge, or Hugging Face push was performed.
