# Implementation Memory

## Context-Resume Summary
Production Build Sprint 1 is on `codex/sprint1-prod-build`, based from `codex/phase0-artifacts`.
The sprint is governed by the Claude Code Opus Production Build Sprint 1 Master Plan and Phase 0 artifacts.
Work must proceed sequentially WP0 through WP8 with memory/state/handoff updates after each package.
The app remains analysis-only: no trading, no private exchange calls, no live news fetching, no secrets.
Provider/source details remain `TO_VERIFY`; Sprint 1 news influence is no-op.
WP0, WP1, WP2, WP3, WP4, WP5, WP6, WP7, and WP8 are complete.
WP2 added FastAPI app creation, health/status endpoints, hashed-code auth, signed cookies, rate limiting, and error envelopes.
WP3 added public-only adapter interfaces/placeholders, fixture adapters, symbol normalization, market-data validation, and provider failover/quarantine tests.
WP4 added deterministic DEFAULT_PHASE1A features, quant, probability, gates, score, and tests; WP4 requires Claude final review.
WP5 added schema-valid news contract stubs, no-op influence, no-fetch metrics behavior, unavailable news-addon behavior, and authority tests; WP5 requires Claude final review.
WP6 added analyze/batch/detail/debug endpoints, response/detail/display builders, in-memory run store, telemetry sink, and sanitized debug export.
WP7 added static cyberpunk frontend files and static no-recompute/no-secret checks.
WP8 added Dockerfile, checkers, optional CI, final docs, full test/checker runs, and local curl smoke.
Claude final-review fixes are applied: blueprint disposition vocabulary, liquidity/tail/execution guardrails, config-owned constants, secure-cookie default, PBKDF2 hashing, fixture-demo labeling, `.dockerignore`, and Sprint 2 limitation docs.
Resume with Claude re-review; do not merge or deploy yet.

## Latest App State
The package imports with `PYTHONPATH=src python3`.
Schema/model tests pass for both `METRICS_ONLY` and `NEWS_ADDON` fixtures.
FastAPI boots in tests; `/healthcheck`, `/v1/system_status`, `/v1/auth/login`, and `/v1/auth/dev` are implemented.
Session checks are server-side and use PBKDF2-HMAC-SHA256 env-code comparison; attempted codes are not stored.
README begins with the required Hugging Face Docker metadata.
Dockerfile and checkers exist; no deploy was performed.
Provider adapters remain public-only and fixture-first; Binance/OKX live source details remain `TO_VERIFY` and fail closed.
Quant is deterministic and hashable, but uncalibrated; it exposes `DEFAULT_PHASE1A` and `INSUFFICIENT_SAMPLE`.
News blocks are schema-valid stubs: `METRICS_ONLY` does not fetch; `NEWS_ADDON` without configured sources returns `UNAVAILABLE`; news influence remains `0.0`.
End-to-end fixture analysis returns schema-valid payloads in both modes; batch isolates item failures; detail/debug endpoints use in-memory recent runs.
Static frontend exists under `frontend/` with login, single/batch analysis, Dev Mode, loading states, details, and export UI.
Local uvicorn/curl smoke passed after elevated bind permission.
Final-review fix verification passes locally: pytest, Ruff, checkers, schema validation, manual smoke, and requested greps.

## Implemented Components
- config: done
- api: partial; schema, auth, health/status, analysis, batch, detail, and debug endpoints done
- adapters: partial; public interface, fixture adapter, Binance/OKX `TO_VERIFY` placeholders, and router done
- validation: partial; candle/book/coherence validation done
- quant: partial; deterministic DEFAULT_PHASE1A baseline done
- features: partial; Sprint 1 deterministic feature states done
- gates: partial; hard-gate seniority done
- score: partial; backend-only baseline done
- news: partial; Sprint 1 contract/stubs/no-op influence done
- detail: partial; backend detail/display builders done
- persistence: partial; in-memory recent-run store done
- telemetry: partial; best-effort in-memory sink done
- frontend: partial; static thin renderer done
- scripts/checkers: done for Sprint 1
- tests: partial; schema and auth/health tests pass
- deployment: Dockerfile present; not deployed

## Files Changed By Area
- docs: `README.md`, `AI/08_IMPLEMENTATION_MEMORY.md`, `AI/06_TEST_COMMANDS.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`
- api: `src/crypto_probability_engine/api/**`
- adapters: `src/crypto_probability_engine/adapters/**`
- validation: `src/crypto_probability_engine/validation/**`, `src/crypto_probability_engine/normalizers/**`
- quant: `src/crypto_probability_engine/quant/**`
- features: `src/crypto_probability_engine/features/**`
- execution_realism: `src/crypto_probability_engine/execution_realism/**`
- gates: `src/crypto_probability_engine/gates/**`
- score_stack: `src/crypto_probability_engine/score_stack/**`
- global_risk: `src/crypto_probability_engine/global_risk/**`
- news: `src/crypto_probability_engine/news/**`
- detail: `src/crypto_probability_engine/detail/**`
- persistence: `src/crypto_probability_engine/persistence/**`
- telemetry: `src/crypto_probability_engine/telemetry/**`
- frontend: `frontend/**`
- scripts: `scripts/**`
- ci: `.github/workflows/ci.yml`
- frontend: none
- config: `src/crypto_probability_engine/config/**`
- tests: `tests/schemas/**`, `tests/api/**`, `tests/adapters/**`, `tests/validation/**`, `tests/quant/**`, `tests/news/**`, `tests/frontend/**`, `tests/fixtures/**`
- deployment: none
- deployment: `Dockerfile`

## Important Decisions
DEFAULT_PHASE1A values are approved by the Sprint 1 Master Plan and must live in config, not silent hardcoding.
`CRYPTO_SPOT` remains default; `CRYPTO_PERP` requires env flag and per-request opt-in.
News evidence remains `0.0` in Sprint 1.
WP2 auth/security, WP4 quant/financial logic, and WP5 news authority require Claude final review before merge/deploy.
Final-review fix decisions: score fallback is `ELEVATED_RISK_AVOID`; bad liquidity, high tail CVaR, or excessive round-trip cost forces `NO_TRADE`; constants live in config; cookies default secure; access codes use PBKDF2 with env-configurable salt/iterations; Sprint 1 data is labeled `FIXTURE_DEMO`; `H_primary`/`H_extended` share one directional split until Sprint 2; full liquidity/tail/execution hard-gating is Sprint 2.
See `AI/07_DECISION_LOG.md` for governance and source-verification decisions.

## Commands Run And Results
- `git switch -c codex/sprint1-prod-build`: PASS.
- Sprint source/doc reads: PASS.
- `python --version`: FAIL, `python` command not found.
- `python3 --version`: PASS, Python 3.14.3 available.
- `python -c "import crypto_probability_engine"`: FAIL, `python` command not found.
- `PYTHONPATH=src python3 -c "import crypto_probability_engine; print(crypto_probability_engine.__version__)"`: PASS, prints `0.1.0`.
- `python3 -m pip install -r requirements.txt`: PASS, approved dependencies installed/satisfied; `ruff` installed.
- `ruff check .`: PASS after mechanical cleanup.
- `PYTHONPATH=src python3 -m pytest tests/schemas`: PASS, 7 passed, 2 jsonschema deprecation warnings.
- `ruff check src tests`: PASS after Ruff fixed one import-format issue in `utils/invariants.py`.
- `PYTHONPATH=src python3 -m pytest tests/api`: initially FAIL while app-factory settings and limiter state were being corrected; final result PASS, 8 passed, 1 TestClient cookie warning.
- `ruff check src tests`: PASS after WP2 corrections.
- `PYTHONPATH=src python3 -m pytest tests/adapters tests/validation`: initially FAIL on a `Protocol` import mistake; final result PASS, 17 passed.
- `ruff check src tests`: PASS after WP3 mechanical cleanup.
- `PYTHONPATH=src python3 -m pytest tests/quant`: PASS, 7 passed.
- `ruff check src tests`: PASS after WP4.
- `PYTHONPATH=src python3 -m pytest tests/news`: PASS, 5 passed.
- `ruff check src tests`: PASS after WP5 import-order cleanup.
- `PYTHONPATH=src python3 -m pytest tests/api/test_analysis_endpoints.py`: PASS, 5 passed.
- `PYTHONPATH=src python3 -m pytest tests/schemas tests/api tests/adapters tests/validation tests/quant tests/news`: PASS, 49 passed, 3 warnings.
- `ruff check src tests`: PASS after WP6 import cleanup.
- `PYTHONPATH=src python3 -m pytest tests/frontend`: initially FAIL because heat legend fallback text was not present in JS; final result PASS, 3 passed.
- `ruff check src tests`: PASS after WP7.
- `python --version`: FAIL, `python` command not found.
- `python3 --version`: PASS, Python 3.14.3.
- `python3 -m pip install -r requirements.txt`: PASS, dependencies already satisfied.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 -m pytest`: PASS, 53 passed, 3 warnings.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: initially FAIL because standalone import of test fixture failed; final result PASS with jsonschema deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `uvicorn ... --host 0.0.0.0 --port 7860`: sandbox run failed to bind; elevated local run PASS.
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
- `git status --short --untracked-files=all -- .`: PASS, shows expected untracked sprint files.

## Known Blockers
No WP0-WP8 blocker. Approved dependency installation and local smoke succeeded.

## Open Risks
- Parent Git repository has unrelated sibling-project noise.
- Local default `python` command is missing; use `python3` unless a venv provides `python`.
- Current local interpreter is Python 3.14.3, not Python 3.11. Docker will target Python 3.11 later.
- Provider/source details remain `TO_VERIFY`.
- Quant baseline is uncalibrated and must expose `DEFAULT_PHASE1A` / `INSUFFICIENT_SAMPLE`.
- WP2, WP4, WP5, and WP8 require Claude final review before merge/deploy. WP2, WP4, and WP5 are now implemented and still pending review.
- WP8 Docker/deployment/checkers are implemented and pending Claude final review.
- Sprint 1 remains fixture-backed. First Sprint 2 task is live public Binance/OKX adapters plus real `data_quality`.

## Next Recommended Steps
1. Claude re-review of final-review fixes on `codex/sprint1-prod-build`.
2. First Sprint 2 task after approval: wire live public Binance/OKX adapters plus real `data_quality`.
3. Only after approval, decide whether to prepare a PR/merge path; do not deploy yet.

## Do Not Change
- Do not edit external source Markdown files.
- Do not touch `.env` or secrets.
- Do not add trading, order, fund-movement, leverage-changing, or autonomous execution capability.
- Do not deploy or merge to main.
- Do not make provider/source details production-critical while still `TO_VERIFY`.
