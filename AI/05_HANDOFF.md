# Handoff Packet

## From
Codex

## To
Claude

## Current Goal
Production Build Sprint 1 WP0-WP8 plus Claude final-review fixes completed. Next step is Claude re-review; do not merge or deploy.

## Current Branch / Worktree
`codex/sprint1-prod-build` / repo root `v8-crypto-api-clean/`

## Risk Level
Overall sprint R3. WP2 auth/security, WP4 quant/financial logic, WP5 news authority, and WP8 Docker/deployment/checkers are implemented with final-review fixes and require Claude re-review.

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
- `src/crypto_probability_engine/features/**`
- `src/crypto_probability_engine/execution_realism/**`
- `src/crypto_probability_engine/quant/**`
- `src/crypto_probability_engine/gates/**`
- `src/crypto_probability_engine/score_stack/**`
- `src/crypto_probability_engine/global_risk/**`
- `src/crypto_probability_engine/news/**`
- `src/crypto_probability_engine/detail/**`
- `src/crypto_probability_engine/persistence/**`
- `src/crypto_probability_engine/telemetry/**`
- `src/crypto_probability_engine/adapters/fixtures.py`
- `src/crypto_probability_engine/api/analysis_service.py`
- `src/crypto_probability_engine/utils/sanitize.py`
- `frontend/**`
- `Dockerfile`
- `scripts/**`
- `.github/workflows/ci.yml`
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
- `tests/frontend/test_frontend_static.py`
- `tests/checkers/` directory created for checker tests but no tests added there.
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- Phase 0 operating docs listed in `AI/03_CURRENT_STATE.md`.

## Files Read But Not Changed
- `Ultimate_Crypto_Probability_Engine_Blueprint_v1_2_2.md`
- `role_knowledge_codex_claude_crypto_app.md`
- `THREAD_TRANSFER_KNOWLEDGE_CRYPTO_APP_BUILD_v1_2_2_ROLE_CORRECTED.md`
- `Claude Code Opus Production Build Sprint 1 Master Plan.md`
- Existing workspace listing, including `.claude/` presence, without editing forbidden files.

## Commands Run
- `git switch -c codex/sprint1-prod-build`: PASS.
- Sprint source/doc reads: PASS.
- `python --version`: FAIL, local command not found.
- `python3 --version`: PASS, Python 3.14.3.
- `python -c "import crypto_probability_engine"`: FAIL, local command not found.
- `PYTHONPATH=src python3 -c "import crypto_probability_engine; print(crypto_probability_engine.__version__)"`: PASS, `0.1.0`.
- `python3 -m pip install -r requirements.txt`: PASS, approved dependencies installed/satisfied; `ruff` installed.
- `ruff check .`: PASS after mechanical cleanup.
- `head -n 15 README.md`: PASS, HF metadata starts at line 1.
- `git status --short --untracked-files=all -- .`: PASS, expected untracked Sprint files.
- `PYTHONPATH=src python3 -m pytest tests/schemas`: PASS, 7 passed, 2 jsonschema deprecation warnings.
- `ruff check src tests`: PASS after WP1 and WP2 corrections.
- `PYTHONPATH=src python3 -m pytest tests/api`: initially FAIL during auth dependency correction; final result PASS, 8 passed, 1 TestClient cookie warning.
- `PYTHONPATH=src python3 -m pytest tests/adapters tests/validation`: initially FAIL on a `Protocol` import mistake; final result PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest tests/quant`: PASS, 7 passed.
- `PYTHONPATH=src python3 -m pytest tests/news`: PASS, 5 passed.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py`: PASS, 5 passed.
- `PYTHONPATH=src python3 -m pytest tests/schemas tests/api tests/adapters tests/validation tests/quant tests/news`: PASS, 49 passed, 3 warnings.
- `ruff check src tests`: PASS after WP6.
- `PYTHONPATH=src python3 -m pytest tests/frontend`: initially FAIL because heat legend fallback text was missing; final result PASS, 3 passed.
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
- `uvicorn crypto_probability_engine.api.app:app --host 0.0.0.0 --port 7860`: sandbox bind failed; elevated local run PASS.
- `curl /healthcheck`: PASS.
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

## What Works Now
WP0-WP8 and Claude final-review fixes are implemented locally. The app boots, healthcheck passes, authenticated analysis works in both modes, full pytest passes, checkers pass, manual smoke passes, Dockerfile exists, README metadata starts at line 1, static frontend mounts, fixture/demo data is clearly labeled, secure cookies default on, and access-code hashes use PBKDF2.

## What Is Still Broken / Unknown
- No deploy or merge has been performed.
- WP4 quant logic is uncalibrated and must remain labeled `DEFAULT_PHASE1A` / `INSUFFICIENT_SAMPLE`; Claude final review required.
- WP5 news behavior is no-op/unavailable in Sprint 1 and requires Claude final review.
- Live provider and news source details remain `TO_VERIFY`; Sprint 1 analysis uses deterministic fixture data.
- Local Python is 3.14.3; Docker target is Python 3.11.
- Sprint 1 H-primary/H-extended probability split is simplified; full horizon-specific modeling is Sprint 2.
- Full hard-gating for liquidity/tail/execution remains Sprint 2; Sprint 1 now has deterministic non-constructive guardrails.
- Binance/OKX live source details remain `TO_VERIFY`; public placeholders fail closed and fixture adapters support offline tests.
- Local `python` command is unavailable; use `python3` unless a venv provides `python`.
- WP1 tests emit jsonschema `RefResolver` deprecation warnings; not blocking.
- Provider/API/source details remain `TO_VERIFY`.
- Parent Git repo contains pre-existing sibling-project noise outside this workspace.

## Next 3 Steps
1. Claude re-review of final-review fixes on `codex/sprint1-prod-build`.
2. First Sprint 2 task after approval: wire live public Binance/OKX adapters plus real `data_quality`.
3. After approval, decide PR/merge path; do not deploy until deployment review is complete.

## Do Not Change
- External source Markdown files.
- `.env` or any secrets file.
- Main branch, merge state, or deployment state.
- Any architecture, financial, quant, news-authority, or deployment behavior beyond the approved Sprint 1 plan and Phase 0 specs.

## Notes for Non-Coder User
The app is now built locally for Sprint 1 with Claude’s first review fixes applied. It can run as a FastAPI app with a bundled static frontend, authenticate, analyze fixture-backed crypto data, return schema-valid probability/risk payloads, block constructive output under bad liquidity/tail/cost guardrails, keep news influence disabled/unavailable as required, label demo data, and export sanitized debug packs. It should not be deployed or merged until Claude re-reviews these fixes.
