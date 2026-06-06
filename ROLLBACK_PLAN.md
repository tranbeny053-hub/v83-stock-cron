# Rollback Plan

Status: Phase 0 docs-only. No deployable app exists yet.

## Triggers

Rollback is required or considered when any of these occur:
- failed deployment;
- repeated runtime crash;
- broken schema or probability invariant;
- data-integrity incident or silent substitution;
- secret exposure suspected;
- full article body or restricted content exposure;
- forbidden execution capability found;
- calibration regression or false-confidence regression after promotion;
- news influence overrides hard gates or sentiment-only action occurs;
- Dev Mode exposes secrets or unsanitized payloads.

## Safe Procedure

1. Stop feature work.
2. Identify last-known-good commit/build/tag.
3. Revert deployment to last-known-good.
4. Verify `/healthcheck`.
5. Run `BTC` smoke in `METRICS_ONLY`.
6. Run `BTC` smoke in `NEWS_ADDON`; if no sources are configured, expect `UNAVAILABLE` and metrics unaffected.
7. Confirm no secrets, full env dump, provider keys, database URLs, or full article bodies appear in response/log/export.
8. If secret exposure is suspected, rotate all secrets before redeploying.
9. Record incident, rollback action, verification result, and residual risk in `CHANGELOG.md`, `AI/03_CURRENT_STATE.md`, and `AI/05_HANDOFF.md`.
10. Claude reviews root cause and recovery plan before new work resumes.

## Phase 0 Rollback

Docs-only rollback is a Git revert or removal of Phase 0 docs on the feature branch only, after user approval. Do not use destructive Git commands without explicit approval.

## Do Not Do

- Do not hot-patch financial logic without Claude review.
- Do not disable safety gates to make a release pass.
- Do not reuse exposed secrets.
- Do not roll forward from an unknown state without recording evidence.

