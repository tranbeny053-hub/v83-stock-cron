# Phase 2D.2G Cadence Activation Record

## 1. Decision status

APPROVED_FOR_SOURCE_IMPLEMENTATION_ONLY. This record does not represent a merge,
tag, push, deployment, dispatch, dry-run result, or production-write authorization.

## 2. Concrete T

The methodology cutover close is `2026-07-14T08:00:00Z`, which is
`2026-07-14 15:00 Asia/Ho_Chi_Minh`.

## 3. Strict-greater boundary semantics

A reference close at or before T is `REJECTED_METHODOLOGY_CUTOVER` with detail
`AT_OR_BEFORE_CUTOVER`. Only a reference close strictly after T proceeds to cadence-window
evaluation.

## 4. Last rejected closes

- 1H: `2026-07-14T08:00:00Z`
- 4H: `2026-07-14T08:00:00Z`

## 5. First potentially admitted closes

- 1H: `2026-07-14T09:00:00Z`
- 4H: `2026-07-14T12:00:00Z`

## 6. First joint admissible interval

The first joint guard interval is `2026-07-14T12:05:00Z-12:20:00Z`, or
`19:05-19:20 Asia/Ho_Chi_Minh`.

## 7. Frozen cadence windows

Policy `cadence-cutover-okx-v1` remains unchanged. The 1H window is 300-1200 seconds after close,
and the 4H window is 300-1800 seconds after close.

## 8. Affected lane

Scheduler only, and only after a separately authorized deployment.

## 9. Unaffected lanes

Hugging Face and the database are unaffected. The HF pin, runtime derivatives behavior, and
production data are unchanged.

## 10. Deployment deadline

The approved deployment deadline is `2026-07-14T06:00:00Z`, or
`2026-07-14 13:00 Asia/Ho_Chi_Minh`.

## 11. Abandonment condition

If the deployment deadline is missed, abandon this T. Do not deploy, select a replacement T, or
use the fallback interval without a new authorization.

## 12. Dry-run dispatch guidance

The operator dispatch band for a later separately authorized dry run is
`2026-07-14T12:06:00Z-12:10:00Z` (`19:06-19:10 Asia/Ho_Chi_Minh`). The hard dispatch stop is
`2026-07-14T12:12:00Z` (`19:12 Asia/Ho_Chi_Minh`). The guard evaluates after queueing, setup, and
live analysis, so this dispatch band is not the guard interval. A late dispatch can make the 1H
cell `TOO_LATE`; no retry is permitted after an abnormal result.

Planned later inputs are `matrix_scope=BTC_ONLY`, `enable_collector=true`, `dry_run=true`, and
empty `confirm_write`. The expected later result is BTC/USDT 1H and 4H using reference close
12:00Z, both admitted, `SKIPPED_DRY_RUN` per cell, `DRY_RUN_COMPLETE`, exit code 0, zero database
writes, and v1 row count remaining zero. This task does not run the dry run.

The timing-only fallback guard interval is `2026-07-14T20:05:00Z-20:20:00Z`. It is not
automatically authorized and still requires operator confirmation and deployment proofs.

## 13. First-write status

`NOT_AUTHORIZED`. `WRITE-EVIDENCE` remains unauthorized, and production v1 rows remain zero
according to the latest read-only proof.

## 14. Rollback-to-pause contract

After an abnormal activation result, do not retry or write. A separately reviewed scheduler
rollback must restore the fail-closed pause before any new timing proposal; HF and database lanes
remain untouched.

## 15. Next gate

Claude High merge-readiness review of the exact local commit. Deployment, dry-run dispatch, and
first-write authorization remain separate later gates.
