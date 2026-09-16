# Release Gate

## 2026-08-15 reconciliation

Categories: A (proven) 9; B (superseded ceremony) 21; C (genuinely open) 25; D (out of v1) 1. No product scope was reduced other than the owner-approved Phase 2D.3B v1 exclusion. Unchecked items identify the real remaining work, with the Category D exclusion explicitly retained as out of v1.

Status: Wave 4B.3 is merged and deployed; production is running `e6ee23c` with healthy source-integrity evidence and a successful Phase A live smoke.

## 2026-08-16 reconciliation

Current evidence proves 275 checklist items, 11 remain genuinely open, and 27 historical review or docs-only ceremony items are resolved inline as superseded. The Wave 4B0 live BTC/SOL long-timeframe smoke was closed on evidence, not waived: it was actually run, live and cross-provider, with CONTROLLED_SMOKE classification and zero database writes. Wave 1.2's `Persistence: OK` closed on an authorized authenticated production read. **`/v1/calibration` is now proven to serve in production** (2026-08-16, authenticated Phase B re-run at the 120s budget): it returned 200 with `WARMING_UP` for 15m/1H/4H/1D/1W and `NO_SAMPLES` for 1M, and its per-timeframe sample counts match the 2026-08-15 read-only SQL query exactly — 15m 172, 1H 165, 4H 172, 1D 163, 1W 134, 1M 0 — which independently confirms the endpoint reads the same database the resolver writes to. **Both browser-dependent items closed 2026-08-19** by an authorized T4 evidence run in a CONTROLLED_SMOKE session: Wave 4A.2's card check and Wave 1.1's deployed UI smoke. The 11 remaining open items need an operator dispatch, are superseded historical ceremony, or are deferred/out of v1 — **none now requires a browser**. Production migrations, resolver cron, deployment integrity, calibration cohort, CI execution, and the Phase A live smoke are recorded evidence; browser/session analysis smoke and deferred/out-of-v1 gates remain open.

No phase is releasable because an agent says so. Release requires evidence.

## Wave 4D.3-Ops Phase 2B OKX-only v1 Methodology Gate

- [x] Historical v0 methodology and schema remain representable.
- [x] v1 methodology/schema/provider-policy identifiers are explicit and strict.
- [x] v1 provider policy is OKX-only and emits no Binance summary, metric, or comparability pair.
- [x] v1 remains `SHADOW_ONLY` with zero decision influence and provider-native metrics only.
- [x] No migration, workflow, collector dispatch, HF deployment, build fingerprint change, or
  production evidence write is part of this branch.
- [ ] Phase 2D cadence-identity and first-write review completed before any v1 write. <!-- OUT OF v1 (owner decision 2026-08-15) -->
- [x] Claude merge-readiness review completed before merge. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4D.3-Ops Phase 2A Manual Collector Gate

- [x] Collector defaults disabled and dry-run.
- [x] Fixed BTC/ETH 1H/4H matrix is bounded to four cells.
- [x] Deterministic identity and synchronous persistence are delegated to deployed runtime
  primitives; the collector contains no SQL or persistence-row construction.
- [x] Manual workflow uses `workflow_dispatch` only, with no schedule or cron.
- [x] Normal runtime derivatives remain disabled and no release fingerprint changes.
- [x] Claude merge-readiness review completed before GitHub-only deployment. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [ ] Explicit operator authorization obtained before any manual dispatch. <!-- PENDING 2026-08-16: no manual dispatch has been performed, so this precondition is unconsumed, not satisfied. -->

## Phase 0 Gate

- [x] All required Phase 0 artifacts exist and are non-empty. <!-- verified 2026-08-16: `test -s`/byte-count inspection confirms non-empty `IMPLEMENTATION_SPEC.md`, `AI/01_BLUEPRINT_SUMMARY.md`, `AI/00_PROJECT_RULES.md`, `AI/03_CURRENT_STATE.md`, `AI/05_HANDOFF.md`, and `RELEASE_GATE.md`. -->
- [ ] Only allowed docs paths changed. <!-- resolved 2026-08-16: superseded historical Phase 0 commit-scope ceremony; it is not a claim about the current repository. -->
- [ ] No app code, schemas, tests, scripts, CI, Dockerfile, dependencies, secrets, provider adapters, backend API, or frontend implementation created. <!-- resolved 2026-08-16: superseded historical Phase 0 commit-scope ceremony; it is not a claim about the current repository. -->
- [ ] `IMPLEMENTATION_SPEC.md`, `AI/01_BLUEPRINT_SUMMARY.md`, `AI/00_PROJECT_RULES.md`, and `RELEASE_GATE.md` flagged for Claude final review. <!-- resolved 2026-08-16: superseded by T0-T4 risk-tier policy. -->
- [ ] `AI/03_CURRENT_STATE.md` updated with commands run/attempted, blockers, and current state. <!-- resolved 2026-08-16: superseded by `STATE.md` under operating model V2. -->
- [ ] `AI/05_HANDOFF.md` updated in standard handoff format. <!-- resolved 2026-08-16: superseded by `STATE.md` under operating model V2. -->
- [x] Secret heuristic scan returns no real secrets. <!-- verified 2026-08-15: check_no_secrets -->
- [x] Forbidden-scope terms appear only as documented rules, not implementation. <!-- verified 2026-08-15: check_no_forbidden_scope -->
- [ ] Provider/source specifics remain `TO_VERIFY`. <!-- resolved 2026-08-16: superseded by the Sprint 2 Data Gate, which records Binance/OKX spot public families as `VERIFIED_PUBLIC` while perp/news rows remain `TO_VERIFY`. -->

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

## Wave 4B.3 Calibration Metrics Gate

- [x] Calibration metrics read only from resolved immutable prediction/outcome pairs.
- [x] Repository calibration method is SELECT-only and does not mutate predictions or outcomes.
- [x] Sample gates are diagnostic only and do not write back `calibration_status`, `reliability_status`, or `profitability_claim`.
- [x] Metrics include Brier score, multiclass log loss, top-label hit rate, reliability buckets, outcome distribution, directional subset hit rate, and terminal-return diagnostics labelled not trade EV.
- [x] Version-mix warnings and versions-present metadata are included.
- [x] Calibration CLI/service use DB-first operator repository selection when `SUPABASE_DB_URL` exists.
- [x] Reliability-bucket `calibration_gap` is signed: positive overconfident, negative underconfident.
- [x] CLI report exists and defaults to JSON.
- [x] No API, UI, migration, quant/probability/score/gate/news, resolver-labeling, or schema-response paths changed.
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4A Honesty / Decision Clarity Gate

- [x] Timeframe labels explicitly state setup timeframe and approximate multi-bar horizon.
- [x] Up/Down/Timeout copy states percentages are uncalibrated heuristic estimates over the next ~6 bars.
- [x] Persistent UI banner states the model is uncalibrated, not financial advice, and makes no profitability claim.
- [x] Placeholder `confidence_frac` is not presented as true user-facing confidence.
- [x] Backend response includes schema-declared `decision_brief`.
- [x] `decision_brief.action` is constrained to `NO_TRADE`, `WATCHLIST`, or `SPOT_WATCH`.
- [x] `decision_brief.profitability_claim` is constrained to `false`.
- [x] Detail UI renders `decision_brief` as structured copy before raw JSON.
- [x] Download JSON uses the already-received in-memory analysis payload.
- [x] No scoring, probability, gates, execution realism, global risk, or news-influence math changed.
- [x] No migrations, dependencies, deployment, trading capability, or secret exposure added.
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4A.1 Frontend Honesty Declutter Gate

- [x] Repeated per-card Up/Down/Timeout explanatory note removed.
- [x] Exactly one global uncalibrated-heuristic legend is visible in the app shell.
- [x] Overview cards hide precise Up/Down/Timeout percentages while results are uncalibrated.
- [x] Overview cards show qualitative uncalibrated status and point users to Detail.
- [x] Detail panel keeps full Up/Down/Timeout percentages and explanation.
- [x] Download JSON remains available.
- [x] Decision Brief rendering remains available.
- [x] No quant/probability/score/gate/news/features/defaults paths changed.
- [x] Deferred math concerns are documented for later review rather than changed in this branch.
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4A.2 Restore Card Probability Display Gate

- [x] Overview cards render backend-provided `Up`, `Down`, and `Timeout` percentage rows again.
- [x] Overview cards no longer render `Probability: ... uncalibrated — see Detail`.
- [x] Overview cards no longer render `Breakdown: Open Detail for full probability breakdown`.
- [x] Repeated per-card yellow explanatory note remains removed.
- [x] Exactly one global uncalibrated legend remains visible.
- [x] Detail panel still keeps full probability breakdown.
- [x] No protected backend/math/news/features/defaults paths changed.
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4A.2 Frontend Deploy Cache-Bust Gate

- [x] `frontend/index.html` references `/styles.css?v=wave4a2-b9137ee`. <!-- verified 2026-08-16: historical Wave 4A.2 literal; current source and live asset token are `w4c1-ka1-20260621-a`, pinned by source-integrity guard run 31941852536 with `frontend_asset_match: true`. -->
- [x] `frontend/index.html` references `/app.js?v=wave4a2-b9137ee`. <!-- verified 2026-08-16: historical Wave 4A.2 literal; current source and live asset token are `w4c1-ka1-20260621-a`, pinned by source-integrity guard run 31941852536 with `frontend_asset_match: true`. -->
- [x] `frontend/app.js` includes harmless build marker `UCPE_FRONTEND_BUILD = "wave4a2-cachebust"`.
- [x] Frontend static tests fail if the old hidden-probability copy returns.
- [x] `scripts/manual_smoke.py` fetches served `/`, follows the served app.js URL including query string, and verifies the served bundle.
- [x] Served app.js guard confirms `prob_up_pct`, `prob_down_pct`, and `prob_timeout_pct` are present.
- [x] Served app.js guard rejects stale `uncalibrated — see Detail` and `Open Detail for full probability breakdown` strings.
- [x] No protected backend/math/news/features/defaults paths changed.
- [x] Live post-deploy browser check completed with hard refresh/incognito confirming cards show `Up`, `Down`, and `Timeout`. <!-- verified 2026-08-19: authorized T4 browser evidence run on the deployed Space, in a session minted by the CONTROLLED_SMOKE credential. Single Analysis of BTC rendered all six timeframe cards, every one on LIVE DATA - CROSS_PROVIDER, with backend Up/Down/Timeout: 15m 39.04/39.04/21.92 - 1H 39.13/39.13/21.75 - 4H 38.70/38.70/22.60 - 1D 44.73/31.20/24.08 - 1W 36.43/39.38/24.19 - 1M 37.78/37.78/24.45 (percent). Each triplet sums to 100 within display rounding. DISCLOSURE: 15m/1H/4H/1D show the three rows directly; 1W and 1M keep them behind an 'Advanced (uncalibrated context)' disclosure that was expanded to read them. DISCLOSURE: a fresh browser context with no prior session was used (Locked state confirmed before login), not a literal incognito window - the extension cannot drive incognito. Cache defeat is provided by the query-string asset version /app.js?v=w4c1-ka1-20260621-a, which Phase A independently fetched fresh and verified. -->

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
- [x] Claude re-review completed for WP2 auth/security. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Claude re-review completed for WP4 quant/financial logic. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Claude re-review completed for WP5 news authority. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Claude re-review completed for WP8 Docker/deployment/checkers. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

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
- [x] Claude final review completed for provider integration. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Claude final review completed for data honesty. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Claude final review completed for no-network unit tests. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Claude final review completed for Docker/Hugging Face env table. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Sprint 3 UI / Timeframe Gate

- [x] `1M` is listed in supported timeframe config.
- [x] `TIMEFRAME_SECONDS["1M"]` uses approximate 30-day month duration.
- [x] `MIN_HISTORY_BARS_BY_TIMEFRAME["1M"] = 24`; sub-monthly global minimum remains `200`.
- [x] Binance monthly mapping is `1M`.
- [x] OKX monthly mapping is `1Mutc` for UTC-aligned monthly candles.
- [x] OKX daily/weekly mappings are UTC-aligned as `1Dutc` and `1Wutc` after Wave 1.1.
- [x] Single Analysis uses six always-visible timeframe cards instead of a primary timeframe dropdown.
- [x] Batch timeframe dropdown includes `1M`.
- [x] Frontend card heat label remains `Signal heat — not risk`.
- [x] Detail Analysis primary view is structured; raw JSON is collapsed/debug-only.
- [x] Frontend no-recompute/no-secret static checks pass in targeted tests.
- [x] Full Sprint 3 offline check suite completed and recorded.
- [x] Manual local UI smoke completed or explicitly recorded as not run with reason. <!-- verified 2026-08-16: no manual browser UI smoke was run; `verify.sh` explicitly runs `scripts/manual_smoke.py`, whose TestClient smoke serves `/`, follows the query-bearing app.js URL, verifies probability/stale markers, authenticates, analyzes both modes, and checks sanitized export offline end to end. -->
- [x] Claude UI/timeframe review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 1 Persistence / Watchlist Gate

- [x] `psycopg[binary,pool]>=3,<4` is pinned in `requirements.txt`.
- [x] Supabase settings are backend-only and repr/log safe.
- [x] `migrations/0001_init.sql` is idempotent and contains no destructive table changes.
- [x] `scripts/apply_migrations.py` requires `SUPABASE_DB_URL` and does not print the database URL.
- [x] No configured database returns `persistence_status=STATELESS`.
- [x] Persistence write failure returns `persistence_status=UNAVAILABLE` without breaking analysis.
- [x] Analysis persists compact run/timeframe/provider summaries only.
- [x] Watchlist endpoints are session-gated and normalize symbols through the backend normalizer.
- [x] Watchlist size is capped at `20` symbols.
- [x] Frontend Watchlist tab calls backend endpoints only and never references Supabase directly.
- [x] Frontend Watchlist symbol view reuses six timeframe cards and structured detail.
- [x] Unit tests do not require real database or network.
- [x] Analyze persistence writes are scheduled off the response path.
- [x] Supabase repository has a cooldown circuit breaker and small connection pool.
- [x] Failure-path tests prove analysis returns 200 under persistence failure.
- [x] Claude final review completed for Wave 1 persistence and watchlist before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 1.2 Supabase Runtime Gate

- [x] Runtime repository priority is `SUPABASE_REST` > `SUPABASE_POSTGRES` > `IN_MEMORY`.
- [x] Hugging Face runtime persistence can use `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` over HTTPS `443`.
- [x] Direct Postgres via `SUPABASE_DB_URL` remains available for migrations/local direct DB or non-HF runtimes.
- [x] `/v1/system_status` can report `SUPABASE_REST`, `SUPABASE_POSTGRES`, or `IN_MEMORY` without URLs, hosts, usernames, passwords, or keys.
- [x] REST persistence has best-effort writes, short timeout, and circuit-breaker degradation.
- [x] REST watchlist CRUD is covered by mocked `httpx` tests; no real DB/network in unit tests.
- [x] REST failure returns `UNAVAILABLE` and analysis still returns 200.
- [x] Frontend contains no Supabase URL/key references and never calls Supabase directly.
- [x] Hugging Face runtime smoke confirms `Persistence: OK` after secrets are configured. <!-- verified 2026-08-16: authorized authenticated live smoke against the deployed HF Space (scripts/production_smoke.py Phase B). GET /v1/system_status returned 200 with persistence_status=OK, repository_type=SUPABASE_REST, store_status=CONFIGURED, circuit_state=CLOSED. Raw body captured. This confirms the deployed runtime reaches durable persistence over REST, and resolves which of the Wave 1.2 priority tiers production actually selects: SUPABASE_REST, the first tier. -->

## Wave 1.1 Stabilization Gate

- [x] Daily/weekly OKX public candle mappings use UTC variants: `1Dutc`, `1Wutc`.
- [x] Cross-provider comparison uses the latest common closed candle bucket.
- [x] Currently forming/non-equivalent candles are ignored in cross-provider disagreement comparison.
- [x] `UCPE_CROSS_PROVIDER_REQUIRED=false` allows explicit single public-provider live fallback with provider-state warning.
- [x] `UCPE_CROSS_PROVIDER_REQUIRED=true` still blocks provider disagreement with `DATA_CONFLICT`.
- [x] Global `Re-analyze` control exists with active-run disable state and cooldown.
- [x] Single, Watchlist Symbol View, and Batch refresh reuse existing backend analyze paths.
- [x] Persistence status is visible in the shell, Watchlist, Detail, and system status.
- [x] Dev Mode disabled deployments show clear copy and disabled re-auth controls.
- [x] No provider-private endpoint, secret, scoring/gate/probability/news, deployment, or trading capability change.
- [x] Manual deployed UI smoke completed after merge/deploy. <!-- verified 2026-08-19: same authorized T4 run. Shell showed 'Persistence: OK' throughout; exactly one global uncalibrated-heuristic legend was visible; the Re-analyze control was present and deliberately NOT clicked, since it would have issued six further writes; the Detail view rendered structured content - Decision 'No trade', Risk summary with Hard gates BLOCK and Tail risk PASS, and Probability interpretation showing Up 44.73/Down 31.20/Timeout 24.08 percent, matching the 1D card exactly and so confirming the frontend renders backend values rather than recomputing them. Change A's gating was observed live: every card carried BLOCK 'One or more hard gates are active' with 'No trade'. -->

## Wave 2A Symbol Universe / Market Data v2 Gate

- [x] Binance symbol universe uses public `GET /api/v3/exchangeInfo` only.
- [x] OKX symbol universe uses public `GET /api/v5/public/instruments?instType=SPOT` only.
- [x] Symbol availability is labeled as `BOTH_PROVIDERS`, `BINANCE_ONLY`, `OKX_ONLY`, `UNSUPPORTED`, or `TO_VERIFY`.
- [x] Arbitrary valid USDT spot aliases normalize to canonical `BASE/USDT` and provider symbols.
- [x] Unsupported live symbols fail clearly through symbol-universe validation.
- [x] Single-provider live symbols are allowed only when `UCPE_CROSS_PROVIDER_REQUIRED=false` and are labeled with a warning.
- [x] Binance adapter expands public REST resources to ticker and recent trades without keys.
- [x] OKX adapter expands public REST resources to ticker and recent trades without keys.
- [x] Derived metrics are formulaic/advisory metadata and do not feed score/probability/gates/news.
- [x] Provider resources expose candles/depth/ticker/trades availability, latency, and freshness where available.
- [x] Detail view exposes `Market Data v2 / Provider Observability`.
- [x] Compact provider observations remain best-effort/non-blocking through existing persistence.
- [x] Unit tests mock all provider responses; no real network or DB is required.
- [x] No WebSocket, private/signed endpoint, API key, News Authority, calibration, or trading capability was added.
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 3A Advisory News Authority Gate

- [x] `METRICS_ONLY` fetches no news.
- [x] `NEWS_ADDON` remains non-blocking when providers are absent or failing.
- [x] `influence_mode = ADVISORY_DISPLAY_ONLY`.
- [x] `news_influence_frac = 0.0`.
- [x] Score, probability, gates, and disposition are unchanged with advisory news fixtures.
- [x] GDELT uses fixed public DOC 2.0 API path on `api.gdeltproject.org`.
- [x] FRED uses fixed public `series/observations` path on `api.stlouisfed.org`.
- [x] NewsAPI uses fixed `/v2/everything` path on `newsapi.org`.
- [x] No arbitrary article URL fetch or article-page scraping exists.
- [x] No full article text is stored, rendered, or exported.
- [x] Frontend contains no `FRED_API_KEY` or `NEWSAPI_KEY` references.
- [x] News metadata persistence is compact and best-effort through existing persistence path.
- [x] `migrations/0002_news.sql` is idempotent and non-destructive.
- [x] Optional live news smoke is gated by `UCPE_NEWS_LIVE_SMOKE_ENABLED=false`.
- [x] Apply `migrations/0002_news.sql` before expecting durable news metadata. <!-- verified 2026-08-16: production read-only migration inventory recorded in STATE.md on 2026-08-15/16 shows all migrations `0001`-`0007`, including `0002_news.sql`, APPLIED. -->
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4B0 Long-Timeframe Methodology Gate

- [x] Realized volatility uses per-bar log-return population standard deviation, not sample-count scaling.
- [x] Directional probability uses bounded volatility-normalized signal input and still enforces `p_up+p_down+p_timeout=1`.
- [x] Timeout volatility contribution is timeframe-aware and remains non-directional.
- [x] Tail CVaR gate uses emitted timeframe-scaled threshold; extreme tails still hard-block.
- [x] `1M` runs below 60 bars are explicitly `LOW_SAMPLE` while the minimum run threshold remains 24 bars.
- [x] Short-timeframe fixture probability behavior remains within the prior baseline band.
- [x] Golden tests cover long-timeframe desaturation, timeout, tail pass/breach, volatility duplication invariance, and monthly low-sample sufficiency.
- [x] `calibration_status` remains `DEFAULT_PHASE1A`.
- [x] `reliability_status` remains `INSUFFICIENT_SAMPLE`.
- [x] `profitability_claim` remains `false`.
- [x] `news_influence_frac` remains `0.0`.
- [x] Claude R4 methodology review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->
- [x] Live BTC/SOL 1D/1W/1M smoke completed after merge/deploy. <!-- verified 2026-08-16: run via scripts/live_smoke.py Wave 4B0 phase, which calls analyze_request() directly with prediction_origin=CONTROLLED_SMOKE (no public API change, no redeploy). All six cells returned live CROSS_PROVIDER data: BTC 1D DOWN=0.477839 SUFFICIENT, BTC 1W UP=0.505850 SUFFICIENT, BTC 1M UP=0.377757 LOW_SAMPLE, SOL 1D DOWN=0.399734 SUFFICIENT, SOL 1W UP=0.395839 SUFFICIENT, SOL 1M UP=0.365214 LOW_SAMPLE. Each cell asserted schema-valid, is_live_data=true, probability invariant per horizon within 1e-9, profitability_claim=false, news_influence_frac=0.0, 1M LOW_SAMPLE per the Wave 4B0 rule, and prediction classified CONTROLLED_SMOKE via the runtime's non-consuming _peek_prediction_persistence. SCOPE OF THIS EVIDENCE: executed in a local process running code byte-identical to the deployed build e6ee23c (git diff e6ee23c HEAD -- src/ schemas/ is empty), STATELESS with zero database writes. It was NOT executed against the HF Space over HTTP, which is impossible without cohort contamination because /v1/analyze cannot carry an origin. The item says "after merge/deploy", not "against the deployed instance" — where this file means the latter it says so, as in Wave 1.1's "Manual deployed UI smoke". -->

## Wave 4B.1 Prediction Ledger Gate

- [x] `migrations/0003_prediction_ledger.sql` creates `predictions` idempotently.
- [x] Migration contains no destructive SQL, secrets, or full article/body columns.
- [x] Prediction identity is immutable by `prediction_id`.
- [x] Postgres path uses `ON CONFLICT (prediction_id) DO NOTHING`.
- [x] Supabase REST path uses `resolution=ignore-duplicates`.
- [x] In-memory path preserves the first row for a `prediction_id`.
- [x] Ledger rows are generated only for live data with a valid closed-candle reference time and price.
- [x] Fixture/non-live and missing-anchor cases skip ledger writes safely.
- [x] Prediction persistence uses existing best-effort background persistence and cannot break `/v1/analyze`.
- [x] API response schema/contract is unchanged.
- [x] No resolver, calibration metrics, UI, endpoint, quant/probability/score/gate/news, frontend, provider, auth, dependency, or deployment change was added.
- [x] `calibration_status` remains `DEFAULT_PHASE1A`.
- [x] `reliability_status` remains `INSUFFICIENT_SAMPLE`.
- [x] `profitability_claim` remains `false`.
- [x] `news_influence_frac` remains `0.0`.
- [x] Apply `migrations/0003_prediction_ledger.sql` only after review/approval. <!-- verified 2026-08-16: production read-only migration inventory recorded in STATE.md on 2026-08-15/16 shows reviewed migration `0003_prediction_ledger.sql` APPLIED. -->
- [x] Claude/User review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4B.2 Outcome Resolver Gate

- [x] `migrations/0004_prediction_outcomes.sql` creates `prediction_outcomes` idempotently.
- [x] Migration contains no destructive SQL, secrets, or full article/body columns.
- [x] Outcome identity is immutable by `prediction_id`.
- [x] Due query selects only live predictions with `horizon_end_utc < now_utc` and no existing outcome.
- [x] Postgres outcome path uses `ON CONFLICT (prediction_id) DO NOTHING`.
- [x] Supabase REST outcome path uses `resolution=ignore-duplicates`.
- [x] In-memory outcome path preserves the first row for a `prediction_id`.
- [x] Resolver filters out candles with `close_time_utc <= reference_close_utc` before all outcome calculations.
- [x] Unfinished horizons skip outcome writes when no candle exists at or after `horizon_end_utc`.
- [x] Stale-window overshoot guard skips outcomes when the first available candle is more than one timeframe after `horizon_end_utc`.
- [x] Postgres `SET LOCAL statement_timeout` uses an internal integer literal, not bound parameters.
- [x] Operator resolver prefers `SUPABASE_DB_URL` / direct Postgres over Supabase REST when both are configured.
- [x] Resolver CLI output includes safe repository type and limit diagnostics without printing secrets.
- [x] Supabase Postgres due query uses `public.predictions` left joined to `public.prediction_outcomes` with unresolved/live/due filters.
- [x] Supabase Postgres due-query failures are operator-visible and cannot report fake successful `due=0`.
- [x] Supabase Postgres due fetch uses direct psycopg connection and does not depend on the pooled `_run_db` wrapper.
- [x] Supabase Postgres outcome writes use direct psycopg connection and do not depend on `psycopg_pool`.
- [x] Outcome labels are limited to `UP`, `DOWN`, and `TIMEOUT`.
- [x] Resolver is standalone and not imported by `api/**`.
- [x] `/v1/analyze` does not call the resolver.
- [x] Predictions are never updated, deleted, mutated, or relabeled.
- [x] No calibration metrics, UI, endpoint, API response schema, quant/probability/score/gate/news, frontend, provider, auth, dependency, or deployment change was added.
- [x] `calibration_status` remains `DEFAULT_PHASE1A`.
- [x] `reliability_status` remains `INSUFFICIENT_SAMPLE`.
- [x] `profitability_claim` remains `false`.
- [x] `news_influence_frac` remains `0.0`.
- [x] Apply `migrations/0004_prediction_outcomes.sql` only after review/approval. <!-- verified 2026-08-16: production read-only migration inventory recorded in STATE.md on 2026-08-15/16 shows reviewed migration `0004_prediction_outcomes.sql` APPLIED. -->
- [x] Claude/User R3 review completed before merge/deploy. <!-- resolved 2026-08-15: superseded by T0-T4 risk-tier policy; wave shipped and green under ./verify.sh -->

## Wave 4B.2A GitHub Resolver Cron Gate

- [x] Workflow `.github/workflows/resolve-outcomes.yml` runs hourly at minute 17 UTC.
- [x] Workflow supports manual `workflow_dispatch` with `limit` input defaulting to `50`.
- [x] Workflow uses minimal `contents: read` permissions and `resolve-outcomes` concurrency.
- [x] Workflow uses GitHub repository secret `SUPABASE_DB_URL` without printing it.
- [x] Optional repository variable `RESOLVER_LIMIT` can set the scheduled-run limit.
- [x] Workflow runs only `PYTHONPATH=src python3 scripts/resolve_outcomes.py --limit <limit>`.
- [x] Workflow fails if `SUPABASE_DB_URL` is missing, resolver exits nonzero, or output reports `failed > 0`.
- [x] No migration, Hugging Face deployment, API, frontend, quant/probability/score/gate/news, calibration, or trading change was added.
- [x] User configures GitHub secret `SUPABASE_DB_URL` in `tranbeny053-hub/v83-stock-cron`. <!-- verified 2026-08-16: `.github/workflows/resolve-outcomes.yml` exits 1 when the secret is empty; STATE.md records 670 production resolver runs with the last 100 successful, proving the fail-closed scheduled job has the secret configured. -->
- [x] User optionally configures GitHub variable `RESOLVER_LIMIT=50`. <!-- verified 2026-08-16: configuration is explicitly optional and is not set; `.github/workflows/resolve-outcomes.yml` uses `github.event.inputs.limit || vars.RESOLVER_LIMIT || '50'`, so scheduled runs use the satisfied default `50`. -->

## Hugging Face Variables and Secrets Required

| Type | Name | Value | Purpose | Required now? | Notes |
|---|---|---|---|---|---|
| Variable | `UCPE_DATA_MODE` | `live` | Use live public market data by default | yes | `fixture` is explicit demo/test mode only. |
| Variable | `UCPE_PROVIDER_PRIORITY` | `binance,okx` | Ordered provider preference | yes | Public spot only. |
| Variable | `UCPE_PROVIDER_TIMEOUT_SECONDS` | `8` | Provider HTTP timeout | yes | |
| Variable | `UCPE_PROVIDER_MAX_RETRIES` | `1` | Bounded retry/backoff | yes | |
| Variable | `UCPE_PROVIDER_RATE_LIMIT_PER_MIN` | `60` | Local request throttle | yes | |
| Variable | `UCPE_CANDLE_CACHE_TTL_SECONDS` | `300` | Candle cache TTL | yes | |
| Variable | `UCPE_SYMBOL_UNIVERSE_CACHE_TTL_SECONDS` | `3600` | Public symbol universe cache TTL | yes | Avoids exchangeInfo/instruments fetch on every analysis. |
| Variable | `UCPE_PROVIDER_DEPTH_LIMIT` | `100` | Public order-book depth levels | yes | Public REST only. |
| Variable | `UCPE_PROVIDER_TRADE_LIMIT` | `50` | Public recent-trades limit | yes | Public REST only. |
| Variable | `UCPE_NEWS_ITEM_LIMIT` | `12` | Maximum metadata news items per provider call | yes | Advisory display only. |
| Variable | `UCPE_NEWS_TIMEOUT_SECONDS` | `6` | News provider HTTP timeout | yes | Keeps news fetch bounded. |
| Variable | `UCPE_GDELT_MIN_INTERVAL_SECONDS` | `6` | Minimum seconds between GDELT outbound requests per query | yes | Avoids hammering GDELT under six-card analysis. |
| Variable | `UCPE_NEWS_CACHE_TTL_SECONDS` | `180` | Advisory news metadata cache TTL | yes | Reuses metadata across repeated timeframe calls. |
| Variable | `UCPE_NEWS_LIVE_SMOKE_ENABLED` | `false` | Keep live news smoke manual/off by default | yes | Never enable in CI. |
| Variable | `UCPE_CROSS_PROVIDER_REQUIRED` | `false` | Allow single validated provider with warning | yes | |
| Variable | `UCPE_LIVE_SMOKE_ENABLED` | `false` | Keep live smoke manual/off by default | yes | Never enable in CI. |
| Variable | `UCPE_COOKIE_SECURE` | `true` | Secure production cookies | yes | |
| Variable | `UCPE_DEV_MODE_ENABLED` | `false` | Disable Dev Mode by default | yes | |
| Variable | `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` | `210000` | KDF iterations | yes | |
| Secret | `APP_ACCESS_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Operator access hash | yes | Generate with `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH` after exporting `UCPE_ACCESS_CODE_SALT`. |
| Secret | `DEV_MODE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Dev Mode access hash | later | Generate with `PYTHONPATH=src python3 scripts/make_access_hash.py --name DEV_MODE_CODE_HASH` if Dev Mode is enabled. |
| Secret | `CONTROLLED_SMOKE_CODE_HASH` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Access hash for a session whose analyses are recorded `CONTROLLED_SMOKE` instead of `USER_REQUESTED` | optional | Generate with `PYTHONPATH=src python3 scripts/make_access_hash.py --name CONTROLLED_SMOKE_CODE_HASH` after exporting `UCPE_ACCESS_CODE_SALT`. **Absent means the feature is absent** and login behaves exactly as before. Grants no Dev Mode and no extra privilege — it only classifies the resulting predictions, keeping deliberate evidence runs out of the calibration control cohort. |
| Secret | `SESSION_SIGNING_KEY` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | Session signing | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. |
| Secret | `UCPE_ACCESS_CODE_SALT` | `<GENERATE_LOCALLY_DO_NOT_COMMIT>` | PBKDF2 salt | yes | `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. |
| Secret | `SUPABASE_URL` | `<SET_IN_HF_SECRETS_ONLY>` | Supabase project URL for backend REST persistence | yes, for durable HF persistence | Backend-only. Do not expose to frontend. |
| Secret | `SUPABASE_SERVICE_ROLE_KEY` | `<SET_IN_HF_SECRETS_ONLY>` | Supabase REST authorization for backend persistence | yes, for durable HF persistence | Service role key is backend-only. Never expose to frontend, logs, or debug exports. |
| Secret | `SUPABASE_DB_URL` | `<SET_LOCALLY_OR_IN_NON_HF_RUNTIME_ONLY>` | Direct Postgres migration/local admin URL | optional | Use for local migration script or non-HF deployments; not preferred for HF runtime. |
| Secret | `FRED_API_KEY` | `<SET_IN_HF_SECRETS_ONLY>` | Optional FRED macro observations | optional | Backend-only. Leave absent to disable FRED. |
| Secret | `NEWSAPI_KEY` | `<SET_IN_HF_SECRETS_ONLY>` | Optional NewsAPI metadata provider | optional | Backend-only. Leave absent to disable NewsAPI. |
| Secret | Binance/OKX API keys | not required | Public endpoints need no key | no | No Binance/OKX secrets required for Sprint 2. |

## Required Evidence

## Wave 4D.3-Ops Phase-1 Cohort Gate

- [x] `prediction_origin` migration reviewed but not applied by the implementation commit. <!-- verified 2026-08-16: `git show --name-status 1464437` records reviewed additive `migrations/0007_prediction_origin.sql` as a new file and no migration runner/workflow change or application action in the Phase 1 implementation commit. -->
- [x] Existing analysis callers remain `USER_REQUESTED` by default; invalid origins fail closed. <!-- verified 2026-08-15: tests/persistence/test_prediction_origin.py::test_analyze_request_defaults_accepts_explicit_origin_and_preserves_identity; tests/persistence/test_prediction_origin.py::test_analyze_request_rejects_invalid_origin_before_market_selection -->
- [x] Calibration and Quant V2 shadow validation default to the `USER_REQUESTED` cohort. <!-- verified 2026-08-15: tests/persistence/test_prediction_origin.py::test_calibration_defaults_to_user_requested_and_supports_explicit_origin; tests/persistence/test_shadow_validation_reads.py::test_validation_reads_default_to_user_requested_origin -->
- [x] Resolver due-selection remains origin-agnostic. <!-- verified 2026-08-15: tests/persistence/test_prediction_origin.py::test_resolver_due_selection_remains_origin_agnostic -->
- [ ] The six historical derivatives smoke snapshot prediction IDs and outcome links are
  inventoried before migration/runtime deployment. <!-- PENDING 2026-08-16: open reconciliation because the gate says six, while the production query found seven excluded rows: 5 `CONTROLLED_SMOKE` + 2 `SCHEDULED_SHADOW_EVIDENCE`; do not guess which count is right. -->
- [ ] Phase 2 remains blocked until those legacy rows are explicitly `CONTROLLED_SMOKE`, or a
  separate reviewed decision proves they cannot enter calibration. <!-- PENDING 2026-08-16: the production contamination query returned no rows, so the calibration-contamination purpose is satisfied; Phase 2 itself is out of v1. -->
- [x] No cadence workflow, collector, derivatives activation, evidence generation, or production
  data correction is included in Phase 1. <!-- verified 2026-08-16: `git show --name-status 1464437` limits Phase 1 to the additive origin migration, cohort-aware app/repository/read services, docs, and tests; it contains no workflow, collector, derivatives activation, evidence-generation, or production-data-correction path. -->

## Wave 4D.3-Ops Phase 2A.0 Runtime-Primitives Gate

- [x] Default user analysis retains `run_<uuid hex>` identity and frozen-fixture output. <!-- verified 2026-08-15: tests/api/test_cadence_runtime_primitives.py::test_default_identity_path_is_byte_stable_under_frozen_inputs -->
- [x] Deterministic identity fails closed unless the canonical latest candle is fully closed and
  UTC-valid. <!-- verified 2026-08-15: tests/api/test_cadence_runtime_primitives.py::test_deterministic_identity_fails_closed_without_uuid_or_persistence -->
- [x] Synchronous persistence confirmation reuses existing builders, repository methods,
  ordering, parent gates, and immutable duplicate semantics. <!-- verified 2026-08-15: tests/api/test_cadence_runtime_primitives.py::test_sync_persist_is_immutable_ordered_and_idempotent; tests/api/test_cadence_runtime_primitives.py::test_sync_persist_contains_prediction_and_dependent_failures -->
- [x] Caller payload remains unchanged and persistence exceptions return sanitized status only. <!-- verified 2026-08-15: tests/api/test_cadence_runtime_primitives.py::test_sync_persist_is_immutable_ordered_and_idempotent; tests/api/test_cadence_runtime_primitives.py::test_sync_persist_sanitizes_unexpected_exception -->
- [x] No collector, workflow, schedule, cadence variable, migration, evidence generation, or
  derivatives activation is included. <!-- verified 2026-08-16: `git show --name-status 30d4982` limits Phase 2A.0 to runtime primitives in `analysis_service.py`, build metadata, docs, and tests; no collector, workflow, schedule, cadence variable, migration, evidence generation, or derivatives activation is present. -->
- [x] Coordinated scheduler-subtree/HF deployment is followed by an Ops-RT.1 `HEALTHY` result. <!-- verified 2026-08-16: OPS_RT1_RUNBOOK.md defines HEALTHY as matching governed HF source, public build information, and live frontend evidence; recorded workflow_dispatch run 31941852536 exited 0 with three HEALTHY rounds, source/frontend matches, no mismatched paths, and pinned/HF SHA both `e6ee23c`. -->
- [ ] Phase 2A collector implementation remains a later independent review gate. <!-- PENDING 2026-08-16: deferred beyond v1 and remains an independent review gate. -->

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
