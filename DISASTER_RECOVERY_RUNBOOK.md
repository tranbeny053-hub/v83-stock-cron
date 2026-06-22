# Disaster Recovery Runbook

Status: Phase 0 docs-only. Written for a non-coder operator.

## When To Use This

Use this if the Hugging Face Space is broken, secrets may have leaked, external persistence is lost, or the app cannot be trusted.

## First Response

1. Stop feature work.
2. Do not paste secrets into chat.
3. Export a sanitized Debug Pack if the app can still open Dev Mode.
4. Record the visible failure in `AI/03_CURRENT_STATE.md` or ask Codex/Claude to do it.
5. Ask Claude to enter Recovery Mode.

If `Runtime Source Integrity Guard` reports persistent divergence, retain its allowlisted JSON
summary, follow `OPS_RT1_RUNBOOK.md`, and verify the reported mismatch paths before approving a
rollback or redeploy. Do not infer divergence by comparing the Hugging Face deployment SHA with the
local `dev` SHA.

## Restore Drill

1. Rebuild the Space from the repo at the last-known-good commit/build.
2. Reattach secrets through Hugging Face Space settings only.
3. Verify `/healthcheck`.
4. Log in and check `/v1/system_status`.
5. Run `BTC` in `METRICS_ONLY`.
6. Run `BTC` in `NEWS_ADDON`; if no news source is configured, `news_addon_state.status = UNAVAILABLE` is acceptable.
7. Open Dev Mode after re-auth and export a sanitized Debug Pack.
8. Confirm there are no secrets, full env dumps, database URLs, provider keys, private headers, or full article bodies.
9. Confirm durable state reloads from the external store, if configured.
10. If no external store is configured, confirm stateless mode is clearly labeled.

## Secret Rotation

Rotate secrets after any suspected exposure or restore. Never reuse leaked credentials.

Rotate, as applicable:
- app access-code hash;
- Dev Mode code hash;
- session signing key;
- persistence restricted key;
- optional read-only provider keys;
- optional news/macro source keys.

Record only that each secret was rotated. Do not record actual values.

## Recovery Roles

- Claude: recovery architect, root-cause debugger, security/deployment reviewer, final reviewer.
- Codex: reproduction steps, checks, docs/handoff updates, scoped fixes only after Claude plan.
- User: approves rollback, redeploy, and secret rotation.

## RTO / RPO

- RTO target: `TBD - finalized before first deployment`.
- RPO target: `TBD - finalized when external persistence is chosen`.
- Backup cadence: `TBD - finalized when external persistence is chosen`.

## Safety Checks Before Resuming Work

- [ ] App responds to `/healthcheck`.
- [ ] Both analysis modes smoke-tested.
- [ ] Dev Mode remains re-auth gated.
- [ ] Debug export is sanitized.
- [ ] No secret or full article body leak.
- [ ] `AI/03_CURRENT_STATE.md` updated.
- [ ] `AI/05_HANDOFF.md` updated.
- [ ] Claude reviewed the recovery result.
