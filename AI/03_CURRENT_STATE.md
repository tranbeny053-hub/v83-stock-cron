# Current State

Updated: 2026-06-06

## Branch / Worktree

- Branch: `codex/sprint1-prod-build`
- Base branch: `codex/phase0-artifacts`
- Worktree: repo root for this package, `v8-crypto-api-clean/`
- Git root is the parent folder; sibling project noise exists outside this workspace.

## Phase

- Current phase: Production Build Sprint 1.
- Current work package: Claude final-review fixes applied; Claude re-review next.
- Overall sprint risk: R3, with WP2/WP4/WP5/WP8 requiring Claude final review before merge/deploy.
- App build status: end-to-end Sprint 1 app exists locally with Claude final-review fixes: FastAPI backend, stable schemas/models, auth/session, health/status, fixture-backed analysis pipeline, deterministic DEFAULT_PHASE1A quant/gates/score, no-op news stubs, detail/debug export, in-memory run store, static frontend, Dockerfile, CI, safety/schema/smoke checkers, PBKDF2 access-code hashing, secure-cookie default, fixture-demo labeling, and non-constructive liquidity/tail/execution guards. No deploy, merge, private provider call, live news fetch, or secret file was performed.

## What Exists Now

- Sprint branch `codex/sprint1-prod-build` exists.
- `AI/08_IMPLEMENTATION_MEMORY.md` exists and is the resume source for implementation state.
- WP0 created package skeleton, toolchain files, README metadata, and config defaults.
- WP1 created JSON schemas, Pydantic models, invariant validators, sentinel checks, fixtures, and schema tests.
- WP2 created FastAPI app wiring, public healthcheck, authenticated system status, login/dev auth endpoints, signed session cookies, basic rate limiting, and error envelopes.
- WP3 created public-only provider adapter interfaces/placeholders, fixture adapters, symbol normalization, candle/order-book/coherence validation, and provider failover/quarantine state.
- WP4 created deterministic feature modules, execution realism, epistemic sufficiency, probability invariant enforcement, timeout state, risk arbiter, tail CVaR, calibration state, hard gates, score stack, and quant pipeline hashing.
- WP5 created news contract blocks, unconfigured source stubs, no-op news influence, and authority-limit tests.
- WP6 created detail view and frontend-display builders, fixture-backed analyze service, `/v1/analyze`, `/v1/analyze_batch`, `/v1/analyze/detail/{run_id}`, `/v1/debug/runs`, `/v1/debug/runs/{run_id}`, `/v1/debug/export/{run_id}`, in-memory recent-run store, best-effort telemetry, and sanitized debug export.
- WP7 created static frontend files for login, single analysis, batch analysis, Dev Mode, detail view, loading states, reduced motion, and backend-field-only rendering checks.
- WP8 created Dockerfile, checker scripts, manual smoke script, schema validator, optional CI workflow, updated `AI/06_TEST_COMMANDS.md`, `CHANGELOG.md`, and `RELEASE_GATE.md`, and ran final verification.
- Claude final-review fix pass replaced the rejected score label, added deterministic liquidity/tail/execution guardrails, moved hardcoded constants into config, added `.dockerignore`, expanded `.gitignore`, added secure-cookie setting, implemented PBKDF2 access-code hashing, labeled fixture demo data, and documented Sprint 2 limitations/backlog.
- Phase 0 operating artifacts exist under the approved paths.
- README begins at line 1 with the required Hugging Face Docker metadata.
- No app deployment, merge, private exchange call, live news fetch, or secret file has been created.

## Claude Final Review Required

Before merge/deploy, Claude must review:
- WP2 auth/security behavior.
- WP4 quant/financial logic once implemented.
- WP5 news authority behavior.
- WP8 Docker/deployment/checkers.

## Checks Run / Attempted

- Sprint 1 WP0 checks:
  - `git switch -c codex/sprint1-prod-build`: PASS.
  - `python --version`: FAIL, local command not found.
  - `python3 --version`: PASS, Python 3.14.3.
  - `python -c "import crypto_probability_engine"`: FAIL, local command not found.
  - `PYTHONPATH=src python3 -c "import crypto_probability_engine; print(crypto_probability_engine.__version__)"`: PASS, `0.1.0`.
  - `python3 -m pip install -r requirements.txt`: PASS, approved dependencies installed/satisfied; `ruff` installed.
  - `ruff check .`: initially FAIL with three mechanical style issues; after cleanup, PASS.
  - `head -n 15 README.md`: PASS, Hugging Face metadata starts at line 1.
  - `git status --short --untracked-files=all -- .`: PASS, shows expected untracked Sprint files.
- Sprint 1 WP1 checks:
  - `PYTHONPATH=src python3 -m pytest tests/schemas`: PASS, 7 passed, 2 jsonschema deprecation warnings.
  - `ruff check src tests`: initially FAIL on one import-format issue; after `ruff check ... --fix`, PASS.
- Sprint 1 WP2 checks:
  - `PYTHONPATH=src python3 -m pytest tests/api`: initially FAIL during auth dependency correction; final result PASS, 8 passed, 1 TestClient cookie warning.
  - `ruff check src tests`: PASS after WP2 corrections.
- Sprint 1 WP3 checks:
  - `PYTHONPATH=src python3 -m pytest tests/adapters tests/validation`: initially FAIL on a `Protocol` import mistake; final result PASS, 17 passed.
  - `ruff check src tests`: PASS after WP3 corrections.
- Sprint 1 WP4 checks:
  - `PYTHONPATH=src python3 -m pytest tests/quant`: PASS, 7 passed.
  - `ruff check src tests`: PASS after WP4.
- Sprint 1 WP5 checks:
  - `PYTHONPATH=src python3 -m pytest tests/news`: PASS, 5 passed.
  - `ruff check src tests`: PASS after WP5 import-order cleanup.
- Sprint 1 WP6 checks:
  - `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py`: PASS, 5 passed.
  - `PYTHONPATH=src python3 -m pytest tests/schemas tests/api tests/adapters tests/validation tests/quant tests/news`: PASS, 49 passed, 3 warnings.
  - `ruff check src tests`: PASS after WP6 import cleanup.
- Sprint 1 WP7 checks:
  - `PYTHONPATH=src python3 -m pytest tests/frontend`: initially FAIL because heat legend fallback text was not present in JS; final result PASS, 3 passed.
  - `ruff check src tests`: PASS after WP7.
- Sprint 1 WP8 / final checks:
  - `python --version`: FAIL, local command not found.
  - `python3 --version`: PASS, Python 3.14.3.
  - `python3 -m pip install -r requirements.txt`: PASS, dependencies already satisfied.
  - `ruff check src tests scripts`: PASS.
  - `PYTHONPATH=src python3 -m pytest`: PASS, 53 passed, 3 warnings.
  - `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
  - `PYTHONPATH=src python3 scripts/validate_schemas.py`: initially FAIL on standalone fixture import; final result PASS with jsonschema deprecation warning.
  - `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
  - `uvicorn crypto_probability_engine.api.app:app --host 0.0.0.0 --port 7860`: sandbox run failed to bind; elevated local run PASS.
  - `curl http://localhost:7860/healthcheck`: PASS.
  - Authenticated curl `/v1/system_status`: PASS, `OK STATELESS`.
  - Authenticated curl `/v1/analyze` `METRICS_ONLY`: PASS, `DISABLED_METRICS_ONLY`, `DEFAULT_PHASE1A`, hard gate passed.
  - Authenticated curl `/v1/analyze` `NEWS_ADDON`: PASS, `UNAVAILABLE`, news influence `0.0`.
- Claude final-review fix verification:
  - `ruff check src tests scripts`: PASS.
  - `PYTHONPATH=src python3 -m pytest`: PASS, 56 passed, 3 warnings.
  - `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
  - `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with jsonschema deprecation warning.
  - `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
  - `grep -rn '"AVOID"' src`: PASS, no output.
  - `grep -rn "secure=False" src`: PASS, no output.

## Current Blockers / Unknowns

- Local `python` command is absent; use `python3` unless a venv provides `python`.
- Local interpreter is Python 3.14.3; deployment target remains Python 3.11 in Docker later.
- `jsonschema.RefResolver` emits a deprecation warning in WP1 tests; not blocking.
- Provider/API/source details remain `TO_VERIFY` against current official docs before production-critical implementation.
- Binance/OKX live public adapter details remain `TO_VERIFY`; Sprint 1 has public placeholders plus fixture-backed offline behavior.
- The parent Git repo has large pre-existing sibling-project status noise; verification scopes changed paths to this workspace.
- Local interpreter is Python 3.14.3 while Docker targets Python 3.11; tests pass locally but Claude should review deployment target assumptions.
- Live providers/news remain intentionally unverified/stubbed; Sprint 1 uses fixture market data and unavailable news without configured sources.
- Sprint 1 limitation: `H_primary` and `H_extended` share the same directional split; full horizon-specific modeling is Sprint 2.
- Sprint 1 limitation: liquidity/tail/execution guardrails are deterministic safety coverage only; full hard-gating is Sprint 2.
- Sprint 2 first task: wire live public Binance/OKX adapters plus real `data_quality`.

## Files Changed

- `IMPLEMENTATION_SPEC.md`
- `IMPLEMENTATION_DECISIONS.md`
- `.gitignore`
- `README.md`
- `requirements.txt`
- `pyproject.toml`
- `src/crypto_probability_engine/__init__.py`
- `src/crypto_probability_engine/config/__init__.py`
- `src/crypto_probability_engine/config/defaults.py`
- `src/crypto_probability_engine/config/env_flags.py`
- `src/crypto_probability_engine/config/news_weights.py`
- `src/crypto_probability_engine/config/settings.py`
- `src/crypto_probability_engine/config/unit_discipline.py`
- `src/crypto_probability_engine/api/__init__.py`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/auth.py`
- `src/crypto_probability_engine/api/errors.py`
- `src/crypto_probability_engine/api/health.py`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/adapters/__init__.py`
- `src/crypto_probability_engine/adapters/public_market.py`
- `src/crypto_probability_engine/adapters/types.py`
- `src/crypto_probability_engine/normalizers/__init__.py`
- `src/crypto_probability_engine/normalizers/symbols.py`
- `src/crypto_probability_engine/validation/__init__.py`
- `src/crypto_probability_engine/validation/market_data.py`
- `src/crypto_probability_engine/features/__init__.py`
- `src/crypto_probability_engine/features/trend_mtf.py`
- `src/crypto_probability_engine/features/volatility.py`
- `src/crypto_probability_engine/features/liquidity_depth.py`
- `src/crypto_probability_engine/features/volume_anomaly.py`
- `src/crypto_probability_engine/features/btc_eth_context.py`
- `src/crypto_probability_engine/features/correlation_beta.py`
- `src/crypto_probability_engine/features/memory_features.py`
- `src/crypto_probability_engine/features/regime_2state.py`
- `src/crypto_probability_engine/execution_realism/__init__.py`
- `src/crypto_probability_engine/execution_realism/realism.py`
- `src/crypto_probability_engine/quant/__init__.py`
- `src/crypto_probability_engine/quant/epistemic_sufficiency.py`
- `src/crypto_probability_engine/quant/horizon_timeout.py`
- `src/crypto_probability_engine/quant/probability_three_state.py`
- `src/crypto_probability_engine/quant/risk_arbiter.py`
- `src/crypto_probability_engine/quant/tail_cvar.py`
- `src/crypto_probability_engine/quant/calibration_metrics.py`
- `src/crypto_probability_engine/quant/pipeline.py`
- `src/crypto_probability_engine/gates/__init__.py`
- `src/crypto_probability_engine/gates/composite.py`
- `src/crypto_probability_engine/score_stack/__init__.py`
- `src/crypto_probability_engine/score_stack/score.py`
- `src/crypto_probability_engine/global_risk/__init__.py`
- `src/crypto_probability_engine/global_risk/state.py`
- `src/crypto_probability_engine/news/__init__.py`
- `src/crypto_probability_engine/news/contract.py`
- `src/crypto_probability_engine/news/news_influence.py`
- `src/crypto_probability_engine/news/source_adapters.py`
- `src/crypto_probability_engine/detail/__init__.py`
- `src/crypto_probability_engine/detail/builder.py`
- `src/crypto_probability_engine/detail/frontend_display.py`
- `src/crypto_probability_engine/persistence/__init__.py`
- `src/crypto_probability_engine/persistence/run_store.py`
- `src/crypto_probability_engine/telemetry/__init__.py`
- `src/crypto_probability_engine/telemetry/events.py`
- `src/crypto_probability_engine/adapters/fixtures.py`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/utils/sanitize.py`
- `src/crypto_probability_engine/utils/__init__.py`
- `src/crypto_probability_engine/utils/invariants.py`
- `src/crypto_probability_engine/utils/validation.py`
- `schemas/response.schema.json`
- `schemas/quant.schema.json`
- `schemas/news.schema.json`
- `schemas/detail_view.schema.json`
- `tests/fixtures/sample_payloads.py`
- `tests/fixtures/market_data.py`
- `tests/schemas/test_schema_contract.py`
- `tests/api/test_auth_health.py`
- `tests/adapters/test_provider_failover.py`
- `tests/adapters/test_symbol_normalization.py`
- `tests/validation/test_market_validation.py`
- `tests/quant/test_quant_pipeline.py`
- `tests/news/test_news_contract.py`
- `tests/api/test_analysis_endpoints.py`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`
- `frontend/assets/grid.svg`
- `tests/frontend/test_frontend_static.py`
- `Dockerfile`
- `scripts/check_no_forbidden_scope.py`
- `scripts/check_no_full_article_body.py`
- `scripts/check_no_secrets.py`
- `scripts/manual_smoke.py`
- `scripts/validate_schemas.py`
- `.github/workflows/ci.yml`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CLAUDE.md`
- `AGENTS.md`
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
