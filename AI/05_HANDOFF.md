# Handoff Packet

## From
Codex

## To
Claude / User

## Current Goal
Sprint 2 final comprehensive `_frac` fix after Claude latest `APPROVE_WITH_TARGETED_FIXES`. FIX-S2-5 is applied and verified. Commit on `codex/sprint2-live-market-data`, then seek approval to merge. Do not deploy.

## Current Branch / Worktree
`codex/sprint2-live-market-data` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 response schema/data-honesty fix. Quant math values are unchanged; unbounded fields were renamed away from `_frac`, and retained `_frac` fields are bounded/tested. Merge/deploy still require approval.

## Files Changed
- `IMPLEMENTATION_DECISIONS.md`
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `RELEASE_GATE.md`
- `scripts/live_smoke.py`
- `src/crypto_probability_engine/execution_realism/realism.py`
- `src/crypto_probability_engine/features/liquidity_depth.py`
- `src/crypto_probability_engine/features/regime_2state.py`
- `src/crypto_probability_engine/features/volatility.py`
- `src/crypto_probability_engine/gates/composite.py`
- `src/crypto_probability_engine/quant/horizon_timeout.py`
- `src/crypto_probability_engine/quant/risk_arbiter.py`
- `src/crypto_probability_engine/quant/tail_cvar.py`
- `src/crypto_probability_engine/score_stack/score.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `tests/fixtures/market_data.py`
- `tests/quant/test_quant_pipeline.py`

## Files Read But Not Changed
- `IMPLEMENTATION_SPEC.md`
- `RELEASE_GATE.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `README.md`
- `docs/source_verification_matrix.md`
- `src/crypto_probability_engine/api/schemas.py`
- `src/crypto_probability_engine/adapters/**`
- `schemas/**`
- `scripts/make_access_hash.py`

## Commands Run
- `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean.
- `python3 --version`: PASS, Python 3.14.3.
- Required read-first docs/code scan: PASS.
- `PYTHONPATH=src python3 -m pytest tests/quant/test_quant_pipeline.py tests/api/test_analysis_live_data_wiring.py -q`: PASS, 18 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 83 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "realized_vol_frac\|risk_pressure_frac" src schemas tests || true`: PASS, no output.
- `grep -R "_frac" src/crypto_probability_engine schemas tests`: REVIEWED; remaining emitted `_frac` fields are bounded and covered.
- `grep -R "place_order\|create_order\|submit_order\|cancel_order\|withdraw\|transfer_funds\|leverage_set\|auto_trade" src tests schemas .github || true`: PASS, no output.
- `grep -R "apiKey\|api_key\|secretKey\|private endpoint\|signed endpoint" src/crypto_probability_engine/adapters tests || true`: PASS, no output.
- `grep -R "hashlib.sha256" src scripts tests || true`: PASS_WITH_NOTE; remaining hits are analysis hash and session HMAC signing, not access-code hashing.
- `UCPE_LIVE_SMOKE_ENABLED=true UCPE_LIVE_SMOKE_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT PYTHONPATH=src python3 scripts/live_smoke.py`: PASS, all six symbol/mode runs returned schema-valid `CROSS_PROVIDER` live payloads.

## Hugging Face Variables and Secrets Required

| Type | Name | Value | Purpose | Required now? | Notes |
|---|---|---|---|---|---|
| Variable | `UCPE_DATA_MODE` | `live` | Live public providers | yes | Use `fixture` only for explicit demo/test. |
| Variable | `UCPE_PROVIDER_PRIORITY` | `binance,okx` | Provider order | yes | Public spot only. |
| Variable | `UCPE_PROVIDER_TIMEOUT_SECONDS` | `8` | Provider timeout | yes | |
| Variable | `UCPE_PROVIDER_MAX_RETRIES` | `1` | Bounded retry | yes | |
| Variable | `UCPE_PROVIDER_RATE_LIMIT_PER_MIN` | `60` | Local throttle | yes | |
| Variable | `UCPE_CANDLE_CACHE_TTL_SECONDS` | `300` | Candle cache TTL | yes | |
| Variable | `UCPE_CROSS_PROVIDER_REQUIRED` | `false` | Allow one validated provider with warning | yes | |
| Variable | `UCPE_LIVE_SMOKE_ENABLED` | `false` | Keep live smoke manual | yes | Do not enable in CI. |
| Variable | `UCPE_COOKIE_SECURE` | `true` | Secure cookies | yes | |
| Variable | `UCPE_DEV_MODE_ENABLED` | `false` | Disable Dev Mode by default | yes | |
| Variable | `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` | `210000` | KDF iterations | yes | Must match helper output. |
| Secret | `UCPE_ACCESS_CODE_SALT` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | PBKDF2 salt | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. |
| Secret | `APP_ACCESS_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Operator auth hash | yes | Export salt, then run `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH`. |
| Secret | `DEV_MODE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Dev Mode auth hash | later | Required only if Dev Mode enabled; run helper with `--name DEV_MODE_CODE_HASH`. |
| Secret | `SESSION_SIGNING_KEY` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Session signing | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. |
| Secret | Binance/OKX API keys | not required | Public endpoints need no key | no | No Binance/OKX secrets required. |

## What Works Now
- Unbounded volatility, risk-pressure, and CVaR-loss magnitudes validate under non-`_frac` names.
- Every emitted `_frac` field in a high-volatility full response is recursively checked as numeric `[0,1]`.
- BTC/ETH/SOL live smoke passes in `METRICS_ONLY` and `NEWS_ADDON`.
- NEWS_ADDON remains unavailable/no-op without live news fetching.
- Safety checkers pass; no secrets/full bodies/forbidden/private exchange capability detected.

## What Is Still Broken / Unknown
- No merge or deploy has been performed.
- Deployment still requires pre-deploy checklist execution.
- External provider availability and rate limits remain operational risks.
- Local tests ran on Python 3.14.3; Docker target is Python 3.11.
- `jsonschema.RefResolver` warning remains non-blocking.

## Next 3 Steps
1. Commit FIX-S2-5 on `codex/sprint2-live-market-data`.
2. Ask user/Claude for approval to merge.
3. If merge is approved, run the pre-deploy checklist before any Hugging Face deployment.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not edit external source Markdown files.
- Do not commit `.env`, salts, codes, real hashes, signing keys, API keys, or env dumps.
- Do not add trading/order/withdraw/transfer/leverage/autonomous capability.
- Do not add private exchange calls, live news fetching, or live-to-fixture silent fallback.
- Do not merge or deploy without approval.

## Notes for Non-Coder User
Đợt sửa cuối này xử lý cả nhóm lỗi `_frac`: các giá trị có thể lớn hơn 1 như biến động, áp lực rủi ro, và CVaR loss đã đổi tên an toàn. Test offline và live smoke với BTC/ETH/SOL đều qua. Ứng dụng vẫn chỉ phân tích, không có giao dịch, và chưa deploy.
