# Runbook: roll production back (H2-safe)

A rollback is a separate T4, decided by the owner. It is never automatic. "The previous commit" is
not a safe rollback definition (governing plan §11.3).

## What makes a target H2-safe

`scripts/release.py rollback-check <target>` passes only when all of these hold:
1. the target is a registered release in `ops/release/releases.json`;
2. it carries the H2 fail-closed hold, by both registry and code: `LEGACY_PASS_LIFTS_HARD_BLOCK: bool =
   False` in `calibration/skill.py` at the target;
3. its build identity matches its registry entry;
4. it is an older ancestor of current production (read from the `hf` remote), so the push is a real
   step back;
5. every migration applied after the target is marked additive in the registry.

The pre-hold `00705c55` (`UCPE-PROD-SAFE-3-20260915-A`) is registered with `h2_hold: false`. The tool
refuses it: restoring it would reopen the legacy skill gate.

## Steps

1. **Validate the target** (read-only):
   ```bash
   python scripts/release.py rollback-check <target>
   ```
   It prints the exact force-with-lease command.
2. **Roll back (T4, owner card below).**
3. **Settle at the target:** `python scripts/release.py settle <target>`.
4. **Decide the follow-up** (owner). Until one lands, the guard reports PIN_DRIFT, because the baseline
   still names the newer release. That is expected. Either:
   - fix forward: a new release through `RELEASE.md`; or
   - re-pin the baseline to the target in a reviewed PR. This is a manual step: the tool does not
     automate it yet.

## Owner card: the rollback (T4)

- **ACTION_ID:** ROLLBACK-to-`<target release id>`.
- **WHY:** production misbehaves after a deploy, and the owner chose to restore a validated release.
- **WHERE:** a terminal in the main checkout.
- **EXACT_STEPS:**
  ```bash
  python scripts/release.py rollback <target> --authorize <target> --expected-current <production sha> --release-id <target release id>
  ```
- **DO_NOT_DO:**
  - never roll back to an unregistered or pre-hold commit;
  - never use a plain `--force`;
  - never rerun it (a CONSUMED marker blocks a rerun).
- **EXPECTED_RESULT:** `ROLLBACK=PASS`. The push moved hf main from `<production sha>` to `<target>`
  under the lease.
- **HOW_VERIFIED:** step 3 (settle at the target), then a guard run, expecting PIN_DRIFT until the
  follow-up.
- **RESUME:** "rolled back, follow-up next".

Without `--authorize`, the same command runs only the check and prints what it would do (a dry run).
