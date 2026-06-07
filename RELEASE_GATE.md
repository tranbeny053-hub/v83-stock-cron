# Release Gate

Status: Sprint 2 targeted fixes applied locally. Claude re-review is required before merge/deploy.

No phase is releasable because an agent says so. Release requires evidence.

## Phase 0 Gate

- [ ] All required Phase 0 artifacts exist and are non-empty.
- [ ] Only allowed docs paths changed.
- [ ] No app code, schemas, tests, scripts, CI, Dockerfile, dependencies, secrets, provider adapters, backend API, or frontend implementation created.
- [ ] `IMPLEMENTATION_SPEC.md`, `AI/01_BLUEPRINT_SUMMARY.md`, `AI/00_PROJECT_RULES.md`, and `RELEASE_GATE.md` flagged for Claude final review.
- [ ] `AI/03_CURRENT_STATE.md` updated with commands run/attempted, blockers, and current state.
- [ ] `AI/05_HANDOFF.md` updated in standard handoff format.
- [ ] Secret heuristic scan returns no real secrets.
- [ ] Forbidden-scope terms appear only as documented rules, not implementation.
- [ ] Provider/source specifics remain `TO_VERIFY`.

## Blocking Gates for Future Phases

| Gate | Pass Criteria | Blocks Release |
|---|---|---|
| Schema | Stable response/quant/news/detail schemas valid; probability invariant holds | Yes |
| Data | Provider fetch/validation/failover visible; no silent substitution | Yes |
| Security | No secret leak; Dev Mode server-gated; forbidden-scope clean; no full body | Yes |
| UX | Input to cards to detail works; heat labeled as signal intensity not risk; frontend recomputes nothing | Yes |
| Dev Mode | Re-auth gated, masked, sanitized export including news audit | Yes |
| News | `METRICS_ONLY` fetches none; `NEWS_ADDON` advisory/bounded; no sentiment-only action | Yes |
| Quant | Deterministic, fail-closed, invariant, hard-gate seniority | Yes |
| Calibration | Sample threshold, no false-confidence regression, shadow-first, manual promotion | For promotion |
| Deployment | Cold start, both-mode smoke, no secret/body leak, restart drill | Yes |
| Rollback | Last-known-good identified; revert drill documented | Yes |
| Non-Coder Verification | Operator can follow report/runbook without reading code | Yes |

## Sprint 1 Gate

- [x] README Hugging Face Docker metadata starts at line 1.
- [x] Dockerfile targets port `7860`, uses slim Python, non-root UID `1000`, and binds `0.0.0.0:7860`.
- [x] `/healthcheck` returns OK in local curl smoke.
- [x] `/v1/system_status` returns OK with authenticated session in local curl smoke.
- [x] `/v1/analyze` returns schema-valid `METRICS_ONLY` payload in tests and local curl smoke.
- [x] `/v1/analyze` returns schema-valid `NEWS_ADDON` payload with `news_addon_state=UNAVAILABLE` and zero news influence in tests and local curl smoke.
- [x] Batch analysis isolates invalid-symbol failure in tests.
- [x] Detail endpoint returns stored detail view in tests.
- [x] Dev Mode debug export requires re-auth and sanitizes output in tests.
- [x] Probability invariant tests pass.
- [x] Hard-gate seniority tests pass.
- [x] Forbidden-scope checker passes.
- [x] No-secret checker passes.
- [x] No-full-article-body checker passes.
- [x] Frontend static no-recompute/no-secret checks pass.
- [x] Full pytest passes.
- [x] Claude fix pass pytest passes: 56 passed, 3 warnings.
- [x] Rejected score label removed from implementation paths.
- [x] Secure cookie default uses setting; no `secure=False` literal in `src`.
- [x] Liquidity/tail/execution guardrail tests pass.
- [x] PBKDF2 access-code hashing implemented.
- [x] Fixture/demo data labeling implemented.
- [x] `.dockerignore` added.
- [x] Sprint 2 limitations/backlog documented.
- [x] No deploy, no merge, no main-branch commit.
- [ ] Claude re-review completed for WP2 auth/security.
- [ ] Claude re-review completed for WP4 quant/financial logic.
- [ ] Claude re-review completed for WP5 news authority.
- [ ] Claude re-review completed for WP8 Docker/deployment/checkers.

## Sprint 2 Data Gate

- [x] Binance spot public endpoint families documented as `VERIFIED_PUBLIC` in `docs/source_verification_matrix.md`.
- [x] OKX spot public endpoint families documented as `VERIFIED_PUBLIC` in `docs/source_verification_matrix.md`.
- [x] Perp/news rows remain `TO_VERIFY`.
- [x] Public provider HTTP client uses allow-listed hosts only.
- [x] Binance/OKX adapters use public unauthenticated endpoints only.
- [x] Unit tests use mocked provider responses and do not require live network.
- [x] Socket guard blocks real unit-test network probes.
- [x] Live provider selection enforces `CROSS_PROVIDER`, single-source warning, `DATA_CONFLICT`, `UNAVAILABLE`, and explicit `FIXTURE_DEMO` semantics.
- [x] Live-mode provider failure does not return fixture data.
- [x] `is_live_data=true` is only returned from validated live-provider selection.
- [x] Frontend hides demo/degraded banner only when backend `is_live_data` is true.
- [x] Manual live smoke script exists and skips unless `UCPE_LIVE_SMOKE_ENABLED=true`.
- [x] Signed return/signal/edge fields no longer use `_frac` names.
- [x] Unbounded volatility/risk-pressure/CVaR-loss magnitude fields no longer use `_frac` names.
- [x] Down-market fixture covers negative signed fields and schema validation.
- [x] High-volatility fixture covers unbounded magnitudes and recursive `_frac` bounds.
- [x] Manual real-network live smoke run completed by Codex for BTC and ETH in `METRICS_ONLY` and `NEWS_ADDON`.
- [x] Manual volatile-symbol live smoke run completed for BTC/ETH plus SOL before deploy.
- [ ] Claude final review completed for provider integration.
- [ ] Claude final review completed for data honesty.
- [ ] Claude final review completed for no-network unit tests.
- [ ] Claude final review completed for Docker/Hugging Face env table.

## Hugging Face Variables and Secrets Required

| Type | Name | Value | Purpose | Required now? | Notes |
|---|---|---|---|---|---|
| Variable | `UCPE_DATA_MODE` | `live` | Use live public market data by default | yes | `fixture` is explicit demo/test mode only. |
| Variable | `UCPE_PROVIDER_PRIORITY` | `binance,okx` | Ordered provider preference | yes | Public spot only. |
| Variable | `UCPE_PROVIDER_TIMEOUT_SECONDS` | `8` | Provider HTTP timeout | yes | |
| Variable | `UCPE_PROVIDER_MAX_RETRIES` | `1` | Bounded retry/backoff | yes | |
| Variable | `UCPE_PROVIDER_RATE_LIMIT_PER_MIN` | `60` | Local request throttle | yes | |
| Variable | `UCPE_CANDLE_CACHE_TTL_SECONDS` | `300` | Candle cache TTL | yes | |
| Variable | `UCPE_CROSS_PROVIDER_REQUIRED` | `false` | Allow single validated provider with warning | yes | |
| Variable | `UCPE_LIVE_SMOKE_ENABLED` | `false` | Keep live smoke manual/off by default | yes | Never enable in CI. |
| Variable | `UCPE_COOKIE_SECURE` | `true` | Secure production cookies | yes | |
| Variable | `UCPE_DEV_MODE_ENABLED` | `false` | Disable Dev Mode by default | yes | |
| Variable | `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` | `210000` | KDF iterations | yes | |
| Secret | `APP_ACCESS_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Operator access hash | yes | Generate with `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH` after exporting `UCPE_ACCESS_CODE_SALT`. |
| Secret | `DEV_MODE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Dev Mode access hash | later | Generate with `PYTHONPATH=src python3 scripts/make_access_hash.py --name DEV_MODE_CODE_HASH` if Dev Mode is enabled. |
| Secret | `SESSION_SIGNING_KEY` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Session signing | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. |
| Secret | `UCPE_ACCESS_CODE_SALT` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | PBKDF2 salt | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. |
| Secret | Binance/OKX API keys | not required | Public endpoints need no key | no | No Binance/OKX secrets required for Sprint 2. |

## Required Evidence

- Commands run or attempted.
- Pass/fail/not-run result for each relevant command.
- Files changed.
- Files read but not changed.
- Risks and unknowns.
- Next 3 steps.
- Non-coder summary.
- Claude final review for R2/R3/R4 or production-impacting changes.
- User approval before merge/deploy.

## Automatic Release Blockers

- Any secret or plaintext access value in repo/log/debug/export.
- Any implementation path containing forbidden execution capability.
- Any frontend recomputation of score, probability, trend, disposition, or news influence.
- Any news path that can override hard gates, fabricate news, or act on sentiment alone.
- Any probability invariant violation.
- Any provider/source made production-critical while still `TO_VERIFY`.
- Any full copyrighted article body stored or exported.
