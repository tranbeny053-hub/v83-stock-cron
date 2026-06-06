# Current State

Updated: 2026-06-07

## Sprint 2 Update

- Branch: `codex/sprint2-live-market-data`
- Current package: WP2.6 complete; commit and Claude review next.
- WP2.0 created `docs/source_verification_matrix.md`.
- WP2.0 added env-driven config flags for `UCPE_DATA_MODE`, provider priority, timeout, retries, local rate limit, candle cache TTL, cross-provider requirement, and live-smoke gating.
- Binance/OKX spot endpoint families are documented as public/keyless and `VERIFIED_PUBLIC`; perp/news remain `TO_VERIFY`.
- Binance and OKX public adapters plus the shared safe HTTP client are implemented with mocked offline tests.
- Provider selection now implements `CROSS_PROVIDER`, single-source live warning, `DATA_CONFLICT` fail-closed behavior, `UNAVAILABLE` all-provider failure, explicit fixture mode, cache TTL, and no silent live-to-fixture substitution.
- `analysis_service` now uses provider selection by `UCPE_DATA_MODE`; API tests cover fixture mode, live data-quality propagation, live failure errors without fixture substitution, and batch partial failure.
- Frontend banner now distinguishes live, fixture demo, degraded, and unavailable data sources using backend `frontend_display`.
- `scripts/live_smoke.py` exists and skips unless `UCPE_LIVE_SMOKE_ENABLED=true`.
- Unit tests have an autouse socket guard that blocks real sockets.
- CI is offline-only and does not run live smoke.
- README and RELEASE_GATE include Hugging Face Variables/Secrets requirements; no Binance/OKX secrets are required.
- No deploy, merge, private provider call, live news fetch, or secret file was performed.
- WP2.0 checks: settings load PASS; Ruff PASS after import-order fix; full pytest PASS, 56 passed and 3 existing warnings.

## Branch / Worktree

- Branch: `codex/sprint2-live-market-data`
- Base branch: Sprint 1 approved demo baseline / `codex/sprint1-prod-build` history
- Worktree: repo root for this package, `v8-crypto-api-clean/`
- Git root is the parent folder; sibling project noise exists outside this workspace.

## Phase

- Current phase: Sprint 2 live public market-data integration.
- Current work package: WP2.6 complete; commit and Claude review next.
- Overall sprint risk: R2/R3 provider integration and data honesty. Quant/scoring/gate/news authority remained unchanged.
- App build status: Sprint 1 app plus Sprint 2 live public Binance/OKX provider integration exists locally. No deploy, merge, private provider call, live news fetch, or secret file was performed.

## What Exists Now

- Sprint branch `codex/sprint2-live-market-data` exists.
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

- Sprint 2 WP2.0:
  - `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
  - `git status --short --untracked-files=all -- .`: PASS before edits, clean.
  - Required Sprint 2 source/doc/code reads: PASS.
  - `PYTHONPATH=src python3 -c 'from crypto_probability_engine.config.settings import Settings; ...'`: PASS, default live-provider settings loaded.
  - `ruff check src tests scripts`: initially FAIL on import ordering in `settings.py`; after `ruff check src/crypto_probability_engine/config/settings.py --fix`, PASS.
  - `PYTHONPATH=src python3 -m pytest -q`: PASS, 56 passed, 3 warnings.
- Sprint 2 WP2.1:
  - `PYTHONPATH=src python3 -m pytest tests/adapters/test_public_market_adapters.py -q`: initially FAIL on malformed test setup; final PASS, 6 passed.
  - `ruff check src tests scripts`: initially FAIL on line length and pending OKX imports; final PASS.
  - `git status --short --untracked-files=all -- .`: PASS, only in-project Sprint 2 paths changed/untracked.
- Sprint 2 WP2.2:
  - `PYTHONPATH=src python3 -m pytest tests/adapters/test_public_market_adapters.py -q`: PASS, 9 passed.
  - `ruff check src tests scripts`: PASS.
- Sprint 2 WP2.3:
  - `PYTHONPATH=src python3 -m pytest tests/adapters/test_provider_selection.py -q`: PASS, 6 passed.
  - `ruff check src tests scripts`: initially FAIL on formatting/line length in `provider_selection.py`; final PASS.
- Sprint 2 WP2.4:
  - `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 17 passed, 1 warning.
  - `ruff check src tests scripts`: PASS.
- Sprint 2 WP2.5:
  - `PYTHONPATH=src python3 -m pytest tests/frontend -q`: PASS, 4 passed.
  - `PYTHONPATH=src python3 scripts/live_smoke.py`: PASS/SKIP, `UCPE_LIVE_SMOKE_ENABLED` not true.
  - `ruff check src tests scripts`: PASS.
- Sprint 2 WP2.6 / global verification:
  - `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
  - `git status --short --untracked-files=all -- .`: PASS, only in-project Sprint 2 paths changed/untracked before staging.
  - `python3 --version`: PASS, Python 3.14.3.
  - `PYTHONPATH=src python3 -m pytest -q`: PASS, 76 passed, 3 warnings.
  - `ruff check src tests scripts`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
  - `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
  - `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
  - `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
  - `PYTHONPATH=src python3 scripts/live_smoke.py`: PASS/SKIP, `UCPE_LIVE_SMOKE_ENABLED` not true.
  - `PYTHONPATH=src python3 -m pytest tests/test_no_network_guard.py -q`: PASS.
  - Fixture fallback grep: PASS, live failure tests assert `FIXTURE_DEMO` is not returned.
  - `git diff -- .`: PASS, reviewed app-project diff.

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
