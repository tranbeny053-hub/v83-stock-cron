# Current State

Updated: 2026-06-07

## Branch / Worktree

- Branch: `codex/wave1-1-stabilization-hotfix`
- Base branch: `dev`
- Worktree: `v8-crypto-api-clean/` under parent Git repo `/Users/kha/Documents/New project`
- Scope rule: inspect/edit only files inside `v8-crypto-api-clean/`
- Merge/deploy status: no merge, no deploy/push to Hugging Face

## Current Phase

- Phase: Wave 1.1 stabilization hotfix.
- Current status: targeted implementation complete; full offline check suite passed; ready for review handoff.
- Scope: 1D/1W provider alignment/fallback, visible refresh, persistence status visibility, Dev Mode disabled/configured UX.

## What Changed

- OKX 1D and 1W public candle mappings now use UTC buckets: `1Dutc` and `1Wutc`.
- Cross-provider coherence now compares the latest common closed candle by close time.
- Currently forming or non-equivalent latest candles are ignored for cross-provider disagreement comparison.
- If providers disagree and `UCPE_CROSS_PROVIDER_REQUIRED=false`, analysis can return one validated public live provider with explicit warning and provider-state metadata.
- If `UCPE_CROSS_PROVIDER_REQUIRED=true`, provider disagreement still blocks with `DATA_CONFLICT`.
- Provider state now reports `cross_provider_state`, `fallback_to_single_provider`, `disagreement_bps`, and conflict/fallback reason when relevant.
- App shell now includes a visible `Re-analyze` button, cooldown state, and last-refreshed timestamp.
- App shell now shows `Persistence: STATELESS/OK/UNAVAILABLE`.
- Watchlist persistence copy is explicit for `OK`, `STATELESS`, and `UNAVAILABLE`.
- Structured detail includes persistence status and provider-state disagreement/fallback details.
- `/v1/system_status` includes dev-safe persistence diagnostics and Dev Mode availability/configuration flags.
- Dev Mode disabled deployments show `Dev Mode is disabled in this deployment.` and disable re-auth controls.

## What Was Not Changed

- No quant/scoring/gates/probability/news math changed.
- No Binance/OKX private/authenticated endpoint or API key was added.
- No fixture fallback was added for live-mode provider failure.
- No live news fetching was added.
- No auth/session security semantics were changed.
- No Dockerfile/deployment logic changed.
- No secrets, env files, API keys, or access values added.
- No trading/order/withdraw/transfer/leverage/autonomous capability added.

## Checks Run / Attempted

- `git branch --show-current`: PASS, `codex/wave1-1-stabilization-hotfix`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/validation -q`: PASS, 12 passed.
- `PYTHONPATH=src python3 -m pytest tests/adapters/test_provider_selection.py tests/adapters/test_public_market_adapters.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest tests/api/test_auth_health.py tests/frontend/test_frontend_static.py -q`: PASS, 22 passed, 1 warning.
- `PYTHONPATH=src python3 -m pytest tests/adapters -q`: PASS, 27 passed.
- `PYTHONPATH=src python3 -m pytest tests/api -q`: PASS, 26 passed, 1 warning.
- `PYTHONPATH=src python3 -m pytest tests/frontend/test_frontend_static.py -q`: PASS, 14 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 112 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "SUPABASE_SERVICE_ROLE_KEY\|SUPABASE_DB_URL\|SUPABASE_URL" frontend || true`: PASS, no output.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R "Refresh\|Re-analyze\|last refreshed\|persistence_status\|Watchlist persistence\|Dev Mode is disabled" frontend src tests || true`: PASS, expected UI/status implementation and test hits only; ignored `__pycache__` binary matches also appeared.

## Files Changed

- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `docs/source_verification_matrix.md`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `src/crypto_probability_engine/adapters/mappers.py`
- `src/crypto_probability_engine/adapters/provider_selection.py`
- `src/crypto_probability_engine/api/app.py`
- `src/crypto_probability_engine/api/health.py`
- `src/crypto_probability_engine/persistence/repository.py`
- `src/crypto_probability_engine/validation/market_data.py`
- `tests/adapters/test_provider_selection.py`
- `tests/adapters/test_public_market_adapters.py`
- `tests/api/test_auth_health.py`
- `tests/frontend/test_frontend_static.py`
- `tests/validation/test_market_validation.py`

## Current Blockers / Unknowns

- No implementation blocker is known after the full offline suite.
- Manual deployed browser smoke is not run in this local pass.

## Next Steps

1. User/Claude reviews the hotfix.
2. Merge to `dev` only after approval.
3. Deploy only through the release gate after merge approval.
