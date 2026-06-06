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
