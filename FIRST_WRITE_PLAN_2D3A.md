# Phase 2D.3A First-Write Plan

## 1. Identity and status

```text
phase = 2D.3A
status = PLAN_ONLY_NOT_EXECUTION_AUTHORIZED
source = dev @ a34aafa807a609e477d3fb8950c94567087046e3
source tag = wave-4d3-ops-2d2g-cadence-activation-t
scheduler = github-cron/main @ 676fafbe74235ba3d051e03c6165810ef78030df
HF = origin/main @ 30d4982903e6f44e063616bc3f03f334bd2544e2
```

The successful dry run was accepted for first-write planning. The accepted review found no
source defect. This record is a plan only and grants no execution authority.

## 2. Candidate supervised window

```text
reference close Vietnam = 2026-07-17 11:00 Asia/Ho_Chi_Minh
reference close UTC = 2026-07-17T04:00:00Z

guard-admissible capture band Vietnam = 2026-07-17 11:05-11:20 Asia/Ho_Chi_Minh
guard-admissible capture band UTC = 2026-07-17T04:05:00Z-04:20:00Z

provisional dispatch band Vietnam = 2026-07-17 11:06-11:10 Asia/Ho_Chi_Minh
provisional dispatch band UTC = 2026-07-17T04:06:00Z-04:10:00Z

hard dispatch stop Vietnam = 2026-07-17 11:12 Asia/Ho_Chi_Minh
hard dispatch stop UTC = 2026-07-17T04:12:00Z
```

This is a candidate window for review, not authorization. The reference close is 4H-aligned and
is therefore shared by the 1H and 4H cells. The 1H maximum-lateness boundary is binding. No run
may be created at or after the hard dispatch stop; an already-started run is not automatically
cancelled at that time. Any different date, close, SHA, scope, or time band requires new review.

## 3. Smallest safe scope

```text
matrix scope = BTC_ONLY
cells = BTC/USDT 1H and BTC/USDT 4H
maximum new predictions = 2
maximum new derivatives snapshots = 2
```

A single-cell write is not expressible without a separately reviewed source change.

## 4. Mandatory pre-write proof

Every clause below must pass immediately before a separate execution authorization. Any failed
clause voids the candidate window.

### Source and lane identity

- Local branch, SHA, and tag are exact.
- Scheduler live SHA is exact.
- The workflow remains manual-only.
- HF SHA and the derivatives flag are unchanged.
- No unreviewed source or workflow drift exists.

### Authoritative database proof

A bypass-RLS, `REPEATABLE READ`, read-only recount must establish:

```text
v1 snapshots = 0
v1 distinct predictions = 0
v1 scheduled-shadow snapshots = 0
v1 orphans = 0
v0 snapshots = 8
v0 scheduled-shadow snapshots = 2
v0/v1 semantic overlap = 0
```

The proof must also confirm:

- Migrations `0006` and `0007` are applied.
- Append-only update, delete, and truncate rejection triggers are enabled.
- The write role has only the required `SELECT` and `INSERT` privileges.
- `SCHEDULED_SHADOW_EVIDENCE` remains a valid prediction origin.

### Live OKX proof

Current public OKX evidence for `BTC-USDT-SWAP` must show:

- Expected instrument identity.
- Complete current funding and open-interest data.
- Finite required values.
- Fresh and ordered timestamps.
- No-lookahead safety.
- All four required v1 metric IDs.
- Provider status `ACTIVE`.
- No funding settlement or unsafe boundary in the protected interval.
- Funding timing derived from live fields, never an assumed fixed interval.
- No Binance request or access workaround.

### Operator readiness

- anh Kha is present for dispatch and immediate verification.
- The post-run SQL packet is ready.
- No parallel source, scheduler, HF, or database mutation is active.
- The locked confirmation token remains intentionally omitted from this record.

## 5. Dispatch contract - still locked

```text
workflow UI name = UCPE Derivatives Evidence Collector
ref = main
collector enable = true
dry run = false
matrix scope = BTC_ONLY
write confirmation = LOCKED_AND_OMITTED
```

**DO NOT DISPATCH FROM THIS RECORD.**

The write-confirmation value is neither disclosed nor authorized here.

## 6. No-retry and rollback-to-pause

1. Create at most one run, and only after separate exact execution authorization.
2. Never use "Re-run jobs."
3. UI delay is not permission to click again.
4. Any non-ideal result means no retry.
5. Pause by creating no further dispatch.
6. Keep the write confirmation withheld.
7. Do not modify HF, force-push scheduler source, or repair rows manually.
8. Any durable source rollback is a separately reviewed phase.
9. Preserve all produced evidence, including partial or degraded rows.

## 7. Immediate authoritative post-run proof

After workflow success or failure, authoritative database proof must verify:

- Exact delta in v1 predictions and snapshots, with no more than two of each.
- Exact symbol, timeframe, and canonical close.
- Deterministic prediction identity.
- Origin `SCHEDULED_SHADOW_EVIDENCE`.
- v1 schema, methodology, and provider-policy identity.
- Only `OKX_SWAP`.
- Exactly four required metric IDs.
- `SHADOW_ONLY` and zero decision influence.
- Valid snapshot hash.
- No orphan or duplicate group.
- Historical v0 remains unchanged.

```text
IDEAL:
exactly the expected rows and zero anomalies

PARTIAL_PERSISTENCE:
pause, preserve rows, no retry, Claude incident review

ZERO_PERSISTENCE:
prove zero authoritatively, investigate, no retry

DUPLICATE_OR_CONFLICT:
pause, inspect existing deterministic identity, never overwrite

UNRECOGNIZED_RESULT:
pause and escalate
```

Workflow status must never be treated as database proof.

## 8. Authorization matrix

```text
documentation edit = YES
local feature-branch commit = YES

local merge = NO
tag = NO
push = NO
scheduler deployment = NO
HF deployment = NO
workflow dispatch or rerun = NO
production write = NO
database mutation or migration = NO
Decision influence = NO
```

## 9. Stop conditions

Stop before execution if:

- Identity differs.
- Source or workflow drift exists.
- Database proof is unavailable or unexpected.
- Live provider or funding proof fails.
- Timing is outside the reviewed band.
- An unexpected provider or cell appears.
- A secret may be exposed.
- Any action would require expanding authorization.

## 10. Next gate

```text
Claude HIGH, PLAN / REVIEW ONLY:
review the exact committed FIRST_WRITE_PLAN_2D3A.md and decide whether
execution may be authorized for the exact candidate window.

The record itself grants no execution authority.
```
