# Deployment Checklist

Status: Wave 3A build exists locally. No deployment has been performed by Codex. This checklist is derived from Blueprint v1.2.2 and platform details remain `TO_VERIFY` against current official docs.

## Pre-Deploy Review

- [ ] Claude final review completed for security, deployment, auth/session, persistence, and financial/news safety boundaries.
- [ ] Source Verification Matrix rows required for the phase are complete; unverified provider/source specifics remain `TO_VERIFY`.
- [ ] No app code contains forbidden execution capability.
- [ ] No secrets are committed.
- [ ] No full article bodies are stored/exported.
- [ ] `CHANGELOG.md` updated with blueprint/schema/app versions.
- [ ] Last-known-good commit/build identified before deploy.

## Hugging Face Docker Space

- [ ] Space uses Docker SDK.
- [ ] Runtime binds FastAPI to `0.0.0.0:7860`.
- [ ] Static frontend is served by the same app.
- [ ] Runtime user is non-root where platform requires.
- [ ] Cache/temp writes go to `/tmp` or another documented ephemeral path.
- [ ] Local disk is treated as ephemeral.
- [ ] Secrets are configured only in Space settings.
- [ ] Public repo/log exposure assumed; no secrets in code or logs.

## Environment and Secrets

- [ ] Choose the plain UI login access code locally. This is what the operator types into the app login screen.
- [ ] Generate access-code salt locally: `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`.
- [ ] Set `UCPE_ACCESS_CODE_SALT` in Hugging Face Secrets.
- [ ] Generate `APP_ACCESS_CODE_HASH`: `PYTHONPATH=src python3 scripts/make_access_hash.py --name APP_ACCESS_CODE_HASH` with `UCPE_ACCESS_CODE_SALT` exported locally; enter the access code only at the hidden prompt or via a local-only env var.
- [ ] Generate `DEV_MODE_CODE_HASH` the same way with `--name DEV_MODE_CODE_HASH` if Dev Mode is enabled.
- [ ] Generate `SESSION_SIGNING_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
- [ ] Set `SESSION_SIGNING_KEY` in Hugging Face Secrets.
- [ ] Access-code hash configured in secrets.
- [ ] Dev Mode code hash configured separately if Dev Mode is enabled.
- [ ] `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` matches the helper iteration count.
- [ ] Optional persistence secrets configured only if external store is used.
- [ ] For Hugging Face durable persistence, set `SUPABASE_URL` in Hugging Face Secrets only.
- [ ] For Hugging Face durable persistence, set `SUPABASE_SERVICE_ROLE_KEY` in Hugging Face Secrets only.
- [ ] Keep the Supabase service role key backend-only; never enter it in frontend code, browser console, chat, logs, or debug exports.
- [ ] Use `SUPABASE_DB_URL` for local migration/direct Postgres admin only, or for non-Hugging-Face runtimes where outbound Postgres is allowed.
- [ ] Supabase migrations applied before expecting durable watchlist/run summaries.
- [ ] Set `UCPE_SYMBOL_UNIVERSE_CACHE_TTL_SECONDS=3600` unless intentionally tuning public symbol cache freshness.
- [ ] Set `UCPE_PROVIDER_DEPTH_LIMIT=100` unless intentionally tuning public order-book depth.
- [ ] Set `UCPE_PROVIDER_TRADE_LIMIT=50` unless intentionally tuning public recent-trades sampling.
- [ ] Binance/OKX API keys are absent; Wave 2A public REST market data requires no Binance/OKX secrets.
- [ ] Set `UCPE_NEWS_ITEM_LIMIT=12` unless intentionally tuning advisory display volume.
- [ ] Set `UCPE_NEWS_TIMEOUT_SECONDS=6` unless intentionally tuning bounded news waits.
- [ ] Set `UCPE_GDELT_MIN_INTERVAL_SECONDS=6` to respect GDELT rate-limit guidance.
- [ ] Set `UCPE_NEWS_CACHE_TTL_SECONDS=180` so repeated timeframe requests can reuse advisory metadata.
- [ ] Keep `UCPE_NEWS_LIVE_SMOKE_ENABLED=false` except for explicit manual smoke.
- [ ] Optional `FRED_API_KEY` is set only in Hugging Face Secrets if FRED macro context is desired.
- [ ] Optional `NEWSAPI_KEY` is set only in Hugging Face Secrets if NewsAPI metadata is desired.
- [ ] Private exchange keys, if used later, are read-only only.
- [ ] Secret presence in health/debug is masked as `set (****)`.

Clarifications:
- Type the plain access code into the UI login, not `APP_ACCESS_CODE_HASH`.
- `UCPE_ACCESS_CODE_SALT`, `SESSION_SIGNING_KEY`, and any Hugging Face upload token are not the app login code.
- No Binance/OKX API keys or exchange secrets are required for the current public market-data build.
- Wave 2A remains REST-only; WebSocket is not enabled in this deployment checklist.
- GDELT requires no key. FRED and NewsAPI are optional and backend-only.
- Wave 3A news is advisory display only; `news_influence_frac` remains `0.0`.

## Optional Supabase Persistence Setup

### Wave 4D.3-Ops prediction-origin provenance gate

Before applying `0007_prediction_origin.sql` or deploying its Phase-1 runtime:

- [ ] Query and record the prediction IDs linked to the six historical derivatives smoke
  snapshots without changing any row.
- [ ] Confirm that no scheduled-cadence prediction rows exist.
- [ ] Confirm the current outcome-linkage state for each of those six prediction IDs.
- [ ] Keep Phase 2 disabled until the legacy smoke predictions are explicitly classified as
  `CONTROLLED_SMOKE`, or a separately reviewed decision proves they cannot enter calibration.
- [ ] Treat the migration default as backward compatibility only; do not conceal legacy smoke
  provenance by assuming those rows were genuinely `USER_REQUESTED`.

Any classification correction is a separate reviewed production-data operation. This change
does not perform it and does not enable a cadence collector.

- [ ] Create or select a Supabase Postgres project.
- [ ] Apply `migrations/0001_init.sql` in the Supabase SQL Editor, or run `PYTHONPATH=src python3 scripts/apply_migrations.py` locally with `SUPABASE_DB_URL` set only in the local shell.
- [ ] Apply `migrations/0002_news.sql` in the Supabase SQL Editor before expecting durable news metadata.
- [ ] Confirm tables exist: `watchlist`, `analysis_runs`, `analysis_timeframe_results`, `provider_observations`, and `app_events`.
- [ ] Confirm news tables exist if Wave 3A metadata persistence is enabled: `news_items`, `news_clusters`, and `news_evidence_links`.
- [ ] For Hugging Face runtime, set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in Hugging Face Secrets so the backend uses HTTPS REST on port `443`.
- [ ] Use `SUPABASE_DB_URL` only for local migration/admin or non-Hugging-Face direct Postgres runtime.
- [ ] Leave all Supabase secrets absent to run in stateless mode; analysis should still work and the watchlist UI uses browser fallback.
- [ ] If `Persistence: UNAVAILABLE` appears on Hugging Face with only `SUPABASE_DB_URL`, configure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`; Hugging Face may block outbound Postgres ports `5432`/`6543`.
- [ ] Do not enter Supabase values in the frontend, README, debug export, logs, or code.

## Smoke Tests

- [ ] `Runtime Source Integrity Guard` exists on the default branch of
  `tranbeny053-hub/v83-stock-cron` and its latest result is reviewed.
- [ ] A healthy integrity result confirms the intended release contract, HF runtime-critical
  source, public build information, frontend tokens, fingerprint marker, and live asset hashes.
- [ ] Any persistent divergence is resolved through `OPS_RT1_RUNBOOK.md`; do not use a blind push
  or restart as the first response.
- [ ] `/healthcheck` returns OK within documented cold-start budget.
- [ ] `/v1/system_status` returns runtime/system/provider/news-source/shelter state after session auth.
- [ ] `BTC` with `METRICS_ONLY` returns schema-valid payload and no news fetch.
- [ ] `BTC` with `NEWS_ADDON` returns schema-valid payload; if sources are not configured, `news_addon_state.status = UNAVAILABLE` and metrics are unaffected.
- [ ] `BTC` with `NEWS_ADDON` shows `influence_mode=ADVISORY_DISPLAY_ONLY` and `news_influence_frac=0.0`.
- [ ] Volatile-symbol live smoke, for example `BTC/USDT,ETH/USDT,SOL/USDT`, returns schema-valid payloads and no `_frac` sentinel failures.
- [ ] Detail endpoint returns correct recent `run_id` detail or `RUN_NOT_FOUND`.
- [ ] Dev Mode requires re-auth and exports sanitized debug pack.
- [ ] No response/log/export contains secrets, full env dump, or full article body.

## Restart Drill

- [ ] Restart Space.
- [ ] `/healthcheck` recovers.
- [ ] If external store is configured, durable state reloads.
- [ ] If no external store is configured, stateless mode is clearly labeled.
- [ ] Re-run both-mode `BTC` smoke.

## Release Blockers

- [ ] Failed schema/invariant check.
- [ ] Secret leak or unmasked env output.
- [ ] Forbidden execution capability in implementation paths.
- [ ] News overriding gates, sentiment-only action, fabricated news, or full article body.
- [ ] Frontend recomputing backend authority fields.
- [ ] Missing rollback plan or last-known-good build.
