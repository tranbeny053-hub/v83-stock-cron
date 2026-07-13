# Ops-RT.1 Runtime Source/Serving Integrity Runbook

## Purpose

The scheduled guard evaluates two separate questions:

- Q1 is the safety judgment. It compares the committed, schema-validated HF production baseline
  with Hugging Face `main`, public `/v1/build-info`, and live frontend assets.
- Q2 is a non-failing deployment-delta advisory. Only after fully healthy Q1 evidence, it compares
  the scheduler checkout SHA and eleven governed checkout files with the pin.

The guard is public-read-only and alert-only. It does not deploy, restart, mutate data, or call an
analysis route. Scheduler checkout source is never Q1 production intent.

The workflow runs every two hours at minute 27 and can also be started with
`workflow_dispatch`. A divergence fails the workflow only when the same divergence class appears
in all three probe rounds.

Each round has one 30-second aggregate Git deadline and four HTTP resources with at most two
15-second attempts each. Three rounds plus two 20-second spacing intervals have a calculable
worst-case budget of 490 seconds, inside the 10-minute workflow timeout.

## Governed Production Baseline

`ops/hf_runtime_baseline.json` owns intended HF production identity. Its schema is
`schemas/hf_runtime_baseline.schema.json`. The current authorized pin is release 2A.0,
`30d4982903e6f44e063616bc3f03f334bd2544e2`.

The manifest must be regenerated mechanically from the exact authorized app-root HF Git objects.
A scheduler commit or checkout change does not advance production intent. Any pin change requires
separate reviewed deployment authorization; do not edit the manifest merely to clear an alert.

Missing, unreadable, malformed, unsupported, or internally inconsistent pin/schema state is
`PIN_MISSING`. It fails immediately before network access or probe rounds.

## Classification Response

### HEALTHY or HEALTHY_WITH_METADATA_ANOMALY

No action. Runtime-stage metadata is soft context; unusual stage metadata does not override
matching source, build information, and frontend evidence.

### TRANSITIONING

Evidence changed between rounds or fewer than three rounds agreed. Confirm that the next scheduled
or manual run clears before taking corrective action.

### PROBE_UNAVAILABLE

Check the Space and public network path. Allow the Space to warm, then rerun the workflow manually.
Do not treat an unavailable probe as proof of source divergence.

### PIN_MISSING

The local governed baseline or schema is unavailable or invalid. No probe round was started.
Restore the reviewed committed pin/schema; do not contact or modify HF to clear this state.

### PIN_DRIFT

The observed HF `main` SHA differs from the pinned production SHA. The round stops before critical
blob or live-runtime fetches. Three identical evidence signatures are required before failure,
preserving transition protection.

### STALE_RUNTIME

The public build contract differs from the intended release, milestone, or fingerprint. Inspect
the checked-out source and the deployment history. Do not blindly push source or reboot the Space.

### STALE_FRONTEND

The build contract is current, but the root asset tokens, fingerprint marker, or live JavaScript
or stylesheet hashes differ. Compare the reported token state and asset match, then inspect the
deployment/cache layer.

### SOURCE_DIVERGENCE

One or more runtime-critical files on Hugging Face `main` are missing or differ. Inspect the
reported path names and the Hugging Face commit history. Digests are compared with the committed
pin, never with scheduler checkout bytes.

### CONTRACT_MISSING

Treat a reachable root with a missing or malformed `/v1/build-info` contract as a stale or
incorrect runtime. A required source contract file missing from HF `main` has the same severity.

## Deployment-Delta Advisory

Q2 reports `NONE`, `SCHEDULER_AHEAD_OF_PIN`, or `SCHEDULER_DIVERGENT_FROM_PIN` only after Q1 is
fully `HEALTHY`. Every other Q1 state reports `NOT_EVALUATED`.

Q2 reads only local Git objects and current governed checkout bytes. It never fetches a remote.
When the pinned commit is absent in a shallow checkout, changed paths are still derived from raw
checkout bytes, `scheduler_ahead_count` is null, and the advisory remains non-failing. Q2 cannot
alter Q1 classification or exit code.

## Persistent Divergence

For three matching `PIN_DRIFT`, `STALE_RUNTIME`, `STALE_FRONTEND`, `SOURCE_DIVERGENCE`, or
`CONTRACT_MISSING` rounds, stop release actions and follow `ROLLBACK_PLAN.md` and
`DISASTER_RECOVERY_RUNBOOK.md`.
Preserve the guard JSON summary for review, but never copy private configuration into an incident
record.

## Missing Scheduled Runs

Inspect GitHub Actions in `tranbeny053-hub/v83-stock-cron`. Use `workflow_dispatch` to run
`Runtime Source Integrity Guard` after confirming the default branch contains
`.github/workflows/source-integrity-guard.yml`.

## Safety Boundary

- Public Git reads and four public GET resources only: root, build information, JavaScript, and
  stylesheet.
- No login/session, calibration, watchlist, or analysis request.
- No repository credential, application secret, cookie, request body, database, migration,
  deployment, restart, or workflow dispatch performed by the guard.
- Output is limited to release identity, aggregate match state, HTTP status codes, timestamps,
  classifications, HF main SHA, and mismatched path names. Response bodies are never printed.
- The existing two-hour schedule, three-round confirmation, transport limits, forbidden routes,
  and failure matrix are unchanged. Cadence freeze remains a separate later gate.

The prior red result caused by comparing HF production with the scheduler checkout was a
baseline-model defect, not evidence of an HF production defect. No HF deployment was performed to
implement this correction.
