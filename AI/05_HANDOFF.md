# Handoff Packet

## From
Codex

## To
Claude

## Current Goal
Sprint 2 targeted fixes after Claude `APPROVE_WITH_TARGETED_FIXES`. FIX-S2-1 through FIX-S2-4 are applied and verified. Commit on `codex/sprint2-live-market-data`, then Claude re-review. Do not merge or deploy.

## Current Branch / Worktree
`codex/sprint2-live-market-data` / `v8-crypto-api-clean/` inside parent Git repo `/Users/kha/Documents/New project`.

## Risk Level
R2/R3 provider/data-honesty targeted fix pass. Signed-field schema fix touches API payload semantics but not quant math. Access-hash helper touches deployment operations, not runtime secrets. Claude re-review required before merge/deploy.

## Files Changed
- `AI/03_CURRENT_STATE.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `AI/08_IMPLEMENTATION_MEMORY.md`
- `CHANGELOG.md`
- `DEPLOYMENT_CHECKLIST.md`
- `README.md`
- `RELEASE_GATE.md`
- `scripts/live_smoke.py`
- `scripts/make_access_hash.py`
- `src/crypto_probability_engine/adapters/public_market.py`
- `src/crypto_probability_engine/features/trend_mtf.py`
- `src/crypto_probability_engine/quant/pipeline.py`
- `src/crypto_probability_engine/quant/probability_three_state.py`
- `src/crypto_probability_engine/quant/risk_arbiter.py`
- `src/crypto_probability_engine/score_stack/score.py`
- `tests/api/test_analysis_live_data_wiring.py`
- `tests/fixtures/market_data.py`
- `tests/quant/test_quant_pipeline.py`
- `tests/scripts/test_make_access_hash.py`

## Files Read But Not Changed
- `IMPLEMENTATION_SPEC.md`
- `IMPLEMENTATION_DECISIONS.md`
- `RELEASE_GATE.md`
- `CHANGELOG.md`
- `docs/source_verification_matrix.md`
- `src/crypto_probability_engine/api/schemas.py`
- `schemas/quant.schema.json`
- `schemas/response.schema.json`
- Existing Sprint 2 code/tests/scripts needed for targeted fixes

## Commands Run
- `git branch --show-current`: PASS, `codex/sprint2-live-market-data`.
- `git status --short --untracked-files=all -- .`: PASS before edits, clean; after edits, only targeted in-project files changed/untracked.
- `python3 --version`: PASS, Python 3.14.3.
- `PYTHONPATH=src python3 -m pytest tests/quant/test_quant_pipeline.py tests/api/test_analysis_live_data_wiring.py tests/scripts/test_make_access_hash.py -q`: PASS, 17 passed.
- `PYTHONPATH=src python3 -m pytest -q`: PASS, 80 passed, 3 warnings.
- `ruff check src tests scripts`: initially FAIL on two line-length issues; PASS after wrapping.
- `PYTHONPATH=src python3 scripts/check_no_forbidden_scope.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_secrets.py`: PASS.
- `PYTHONPATH=src python3 scripts/check_no_full_article_body.py`: PASS.
- `PYTHONPATH=src python3 scripts/validate_schemas.py`: PASS with existing `jsonschema.RefResolver` deprecation warning.
- `PYTHONPATH=src python3 scripts/manual_smoke.py`: PASS.
- `grep -R "primary_return_frac\|extended_return_frac\|alpha_signal_frac\|net_signal_frac\|directional_edge_frac" src schemas tests || true`: PASS, no output.
- `grep -R "_frac" src/crypto_probability_engine schemas tests`: REVIEWED; remaining `_frac` fields are true bounded fractions/probabilities/confidence/cost/risk fields.
- `grep -R "hashlib.sha256" src scripts tests || true`: PASS_WITH_NOTE; remaining hits are analysis hash and session HMAC signing, not access-code hashing.
- `grep -R "APP_ACCESS_CODE_HASH\|DEV_MODE_CODE_HASH\|UCPE_ACCESS_CODE_SALT\|SESSION_SIGNING_KEY" README.md DEPLOYMENT_CHECKLIST.md RELEASE_GATE.md AI || true`: PASS, HF secrets documented.
- `UCPE_LIVE_SMOKE_ENABLED=true PYTHONPATH=src python3 scripts/live_smoke.py`: PASS, BTC/ETH both modes returned schema-valid `CROSS_PROVIDER` live payloads.

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
| Secret | `APP_ACCESS_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Operator auth hash | yes | Generate salt first, export `UCPE_ACCESS_CODE_SALT`, then run `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH`. |
| Secret | `DEV_MODE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Dev Mode auth hash | later | Required only if Dev Mode enabled; run helper with `--name DEV_MODE_CODE_HASH`. |
| Secret | `SESSION_SIGNING_KEY` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Session signing | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. |
| Secret | `UCPE_ACCESS_CODE_SALT` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | PBKDF2 salt | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. |
| Secret | Binance/OKX API keys | not required | Public endpoints need no key | no | No Binance/OKX secrets required. |

## What Works Now
- Live BTC/ETH smoke passes through Binance/OKX public providers with `CROSS_PROVIDER`.
- Negative signed down-market fields validate because they no longer use `_frac`.
- Offline down-market fixture proves schema validation and invariant checks pass.
- Hash helper generates PBKDF2 access-code hashes without printing plaintext.
- Fetch margin avoids losing required candle count after dropping in-progress/unconfirmed candles.
- Safety checkers pass; no secrets/full bodies/forbidden capabilities detected.

## What Is Still Broken / Unknown
- No merge or deploy has been performed.
- Claude re-review is required before merge/deploy.
- External provider availability and rate limits remain operational risks.
- Local tests ran on Python 3.14.3; Docker target is Python 3.11.
- `jsonschema.RefResolver` warning remains non-blocking.

## Next 3 Steps
1. Commit targeted fixes on `codex/sprint2-live-market-data`.
2. Claude re-review for signed field schema fix, down-market coverage, live smoke pass, access hash helper, and HF variables/secrets table.
3. After approval, separately decide merge/deploy path; do not deploy from this branch yet.

## Do Not Change
- Do not touch sibling folders outside `v8-crypto-api-clean/`.
- Do not edit external source Markdown files.
- Do not commit `.env`, salts, codes, real hashes, signing keys, API keys, or env dumps.
- Do not add trading/order/withdraw/transfer/leverage/autonomous capability.
- Do not add private exchange calls, live news fetching, or live-to-fixture silent fallback.
- Do not merge or deploy without approval.

## Notes for Non-Coder User
Các lỗi Claude chỉ ra đã được sửa theo đúng phạm vi: tên trường dữ liệu âm đã an toàn hơn, test thị trường giảm đã có, công cụ tạo hash đăng nhập đã có, và live smoke đã chạy thật với Binance/OKX cho BTC và ETH. Ứng dụng vẫn chỉ phân tích, không có chức năng giao dịch, và chưa được merge hay deploy.
