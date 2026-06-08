# Test Commands

Status: Sprint 1 local commands finalized. Use `python3` locally unless a virtual environment provides `python`.

## Install

- `python3 -m pip install -r requirements.txt`

## Local Dev

- `PYTHONPATH=src uvicorn crypto_probability_engine.api.app:app --host 0.0.0.0 --port 7860`
- Requires `APP_ACCESS_CODE_HASH`, `SESSION_SIGNING_KEY`, and optionally `DEV_MODE_CODE_HASH` / `UCPE_DEV_MODE_ENABLED` from the runtime environment or Hugging Face Space Settings.
- Do not commit `.env` files or plaintext access values.

## Build

- `docker build -t ultimate-crypto-probability-engine .`

## Lint

- `ruff check src tests scripts`

## Typecheck

- `mypy src` if mypy is installed and low friction.

## Test

- `PYTHONPATH=src python3 -m pytest`
- Sprint 2 unit tests include an autouse socket guard; real network must be blocked in pytest.

## Safety / Schema Checks

- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`
- `PYTHONPATH=src python3 scripts/live_smoke.py` skips unless `UCPE_LIVE_SMOKE_ENABLED=true`; do not run in CI or unit tests.
- `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH` generates an access-code hash only when `UCPE_ACCESS_CODE_SALT` is set locally; it prompts for the code without printing it.
- `PYTHONPATH=src python3 scripts/apply_migrations.py` applies Supabase migrations only when `SUPABASE_DB_URL` is set locally; it must never run in unit tests or print the URL.

## Manual Live Smoke

- Default: `PYTHONPATH=src python3 scripts/live_smoke.py` returns SKIP and makes no real network call.
- Manual real-network run only after Claude/User approval: `UCPE_LIVE_SMOKE_ENABLED=true PYTHONPATH=src python3 scripts/live_smoke.py`
- Volatile-symbol manual run: `UCPE_LIVE_SMOKE_ENABLED=true UCPE_LIVE_SMOKE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT PYTHONPATH=src python3 scripts/live_smoke.py`
- Expected Sprint 2 behavior when enabled: listed symbols in `METRICS_ONLY` / `NEWS_ADDON` return schema-valid live public data; `NEWS_ADDON` news state remains `UNAVAILABLE`; no Binance/OKX secrets are required.

## HTTP Smoke

- Start local server with dummy or real deployment-secret-backed env values:
  - `PYTHONPATH=src uvicorn crypto_probability_engine.api.app:app --host 0.0.0.0 --port 7860`
- `curl http://localhost:7860/healthcheck`
- Login first, then call `/v1/system_status`, `/v1/analyze` with `METRICS_ONLY`, and `/v1/analyze` with `NEWS_ADDON`.
- Expected Sprint 1 `NEWS_ADDON` status without configured sources: `UNAVAILABLE`; probability and score remain unaffected by news.

## Sprint 1 Required Checks

- `python --version` (may fail locally if only `python3` exists)
- `python3 --version`
- `python3 -m pip install -r requirements.txt`
- `PYTHONPATH=src python3 -m pytest`
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`
- `git status --short --untracked-files=all -- .`

## Sprint 2 Required Checks

- `git branch --show-current`
- `git status --short --untracked-files=all -- .`
- `python3 --version`
- `PYTHONPATH=src python3 -m pytest -q`
- `ruff check src tests scripts`
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`
- `PYTHONPATH=src python3 scripts/live_smoke.py` (expected SKIP unless `UCPE_LIVE_SMOKE_ENABLED=true`)
- `UCPE_LIVE_SMOKE_ENABLED=true UCPE_LIVE_SMOKE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT PYTHONPATH=src python3 scripts/live_smoke.py` (manual real-network smoke; never run in CI)
- `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH` (deployment helper; requires local `UCPE_ACCESS_CODE_SALT`)
- Confirm socket guard with `PYTHONPATH=src python3 -m pytest tests/test_no_network_guard.py -q`

## Sprint 3 Required Checks

- `git branch --show-current`
- `git status --short --untracked-files=all -- .`
- `python3 --version`
- `PYTHONPATH=src python3 -m pytest -q`
- `ruff check src tests scripts`
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`
- `rg -n '"1M"|1Mutc|MIN_HISTORY_BARS_BY_TIMEFRAME|min_history_for' src/crypto_probability_engine/config src/crypto_probability_engine/adapters src/crypto_probability_engine/validation src/crypto_probability_engine/quant tests frontend`
- `PYTHONPATH=src python3 -m pytest tests/adapters/test_public_market_adapters.py tests/validation/test_market_validation.py tests/api/test_analysis_endpoints.py tests/quant/test_quant_pipeline.py tests/frontend/test_frontend_static.py -q`
- Manual UI smoke, if feasible: local server, login, Single Analysis `BTC/USDT` `METRICS_ONLY`, confirm six cards, click `1M`, confirm structured detail and collapsed raw JSON.
- Optional 1M live smoke: not supported by `scripts/live_smoke.py` unless timeframe targeting is added; rely on adapter/API tests when not run.

## Wave 1 Required Checks

- `git branch --show-current`
- `git status --short --untracked-files=all -- .`
- `python3 --version`
- `PYTHONPATH=src python3 -m pytest -q`
- `ruff check src tests scripts`
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`
- Optional migration application only after user approval and only with local secret env configured: `PYTHONPATH=src python3 scripts/apply_migrations.py`.

## Wave 3A Required Checks

- `git branch --show-current`
- `git status --short --untracked-files=all -- .`
- `python3 --version`
- `PYTHONPATH=src python3 -m pytest tests/news -q`
- `PYTHONPATH=src python3 -m pytest tests/api -q`
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`
- `PYTHONPATH=src python3 -m pytest -q`
- `ruff check src tests scripts`
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`
- `PYTHONPATH=src python3 scripts/news_live_smoke.py` (expected SKIP unless `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`; never run in CI by default)
- `git diff --stat dev..HEAD -- src/crypto_probability_engine/quant src/crypto_probability_engine/score_stack src/crypto_probability_engine/gates`
- `grep -R "FRED_API_KEY\|NEWSAPI_KEY" frontend || true`
- `grep -R "content\|body\|article_body\|full_text" src/crypto_probability_engine/news tests/news frontend || true` (review generic `body` false positives; authoritative check is `check_no_full_article_body.py`)
- `grep -R "news_influence_frac" src tests schemas frontend || true`
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`

## Definition of Done

A task is complete only when relevant commands were run or attempted, results were recorded in `AI/03_CURRENT_STATE.md` and `AI/05_HANDOFF.md`, risks are listed, and the user receives a non-technical summary.
