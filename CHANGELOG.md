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
