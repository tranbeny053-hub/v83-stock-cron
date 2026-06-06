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

## Safety / Schema Checks

- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`
- `PYTHONPATH=src python3 scripts/validate_schemas.py`
- `PYTHONPATH=src python3 scripts/manual_smoke.py`

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

## Definition of Done

A task is complete only when relevant commands were run or attempted, results were recorded in `AI/03_CURRENT_STATE.md` and `AI/05_HANDOFF.md`, risks are listed, and the user receives a non-technical summary.
