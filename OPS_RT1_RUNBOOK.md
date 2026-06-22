# Ops-RT.1 Runtime Source/Serving Integrity Runbook

## Purpose

The scheduled guard compares the source-controlled release contract with the runtime-critical
files on Hugging Face `main`, public `/v1/build-info`, and the live frontend assets. It is
public-read-only and alert-only. It does not deploy, restart, mutate data, or call an analysis
route.

The workflow runs every two hours at minute 27 and can also be started with
`workflow_dispatch`. A divergence fails the workflow only when the same divergence class appears
in all three probe rounds.

Each round has one 30-second aggregate Git deadline and four HTTP resources with at most two
15-second attempts each. Three rounds plus two 20-second spacing intervals have a calculable
worst-case budget of 490 seconds, inside the 10-minute workflow timeout.

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

### STALE_RUNTIME

The public build contract differs from the intended release, milestone, or fingerprint. Inspect
the checked-out source and the deployment history. Do not blindly push source or reboot the Space.

### STALE_FRONTEND

The build contract is current, but the root asset tokens, fingerprint marker, or live JavaScript
or stylesheet hashes differ. Compare the reported token state and asset match, then inspect the
deployment/cache layer.

### SOURCE_DIVERGENCE

One or more runtime-critical files on Hugging Face `main` are missing or differ. Inspect the
reported path names and the Hugging Face commit history. The HF commit SHA is context only and is
never compared directly with the local `dev` SHA.

### CONTRACT_MISSING

Treat a reachable root with a missing or malformed `/v1/build-info` contract as a stale or
incorrect runtime. A required source contract file missing from HF `main` has the same severity.

## Persistent Divergence

For three matching `STALE_RUNTIME`, `STALE_FRONTEND`, `SOURCE_DIVERGENCE`, or `CONTRACT_MISSING`
rounds, stop release actions and follow `ROLLBACK_PLAN.md` and `DISASTER_RECOVERY_RUNBOOK.md`.
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
