# Deployment Checklist

Status: Sprint 2 build exists locally. No deployment has been performed. This checklist is derived from Blueprint v1.2.2 and platform details remain `TO_VERIFY` against current official docs.

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
- [ ] Optional persistence secret configured only if external store is used.
- [ ] If durable watchlist/run summaries are wanted, set `SUPABASE_DB_URL` in Hugging Face Secrets only.
- [ ] Optional `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` remain server-side only and are unused in Wave 1.
- [ ] Supabase migrations applied before expecting durable watchlist/run summaries.
- [ ] Binance/OKX API keys are absent; Sprint 2 public market data requires no Binance/OKX secrets.
- [ ] Optional provider/news keys are absent or read-only/source-appropriate if introduced in a later reviewed phase.
- [ ] Private exchange keys, if used later, are read-only only.
- [ ] Secret presence in health/debug is masked as `set (****)`.

Clarifications:
- Type the plain access code into the UI login, not `APP_ACCESS_CODE_HASH`.
- `UCPE_ACCESS_CODE_SALT`, `SESSION_SIGNING_KEY`, and any Hugging Face upload token are not the app login code.
- No Binance/OKX API keys or exchange secrets are required for the current public market-data build.

## Optional Supabase Persistence Setup

- [ ] Create or select a Supabase Postgres project.
- [ ] Apply `migrations/0001_init.sql` in the Supabase SQL Editor, or run `PYTHONPATH=src python3 scripts/apply_migrations.py` locally with `SUPABASE_DB_URL` set only in the local shell.
- [ ] Confirm tables exist: `watchlist`, `analysis_runs`, `analysis_timeframe_results`, `provider_observations`, and `app_events`.
- [ ] Set `SUPABASE_DB_URL` in Hugging Face Secrets if durable persistence is required.
- [ ] Leave `SUPABASE_DB_URL` absent to run in stateless mode; analysis should still work and the watchlist UI uses browser fallback.
- [ ] Do not enter Supabase values in the frontend, README, debug export, logs, or code.

## Smoke Tests

- [ ] `/healthcheck` returns OK within documented cold-start budget.
- [ ] `/v1/system_status` returns runtime/system/provider/news-source/shelter state after session auth.
- [ ] `BTC` with `METRICS_ONLY` returns schema-valid payload and no news fetch.
- [ ] `BTC` with `NEWS_ADDON` returns schema-valid payload; if sources are not configured, `news_addon_state.status = UNAVAILABLE` and metrics are unaffected.
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
