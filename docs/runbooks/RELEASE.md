# Runbook: release a new production build

The proven W26/F1 release chain, driven by `scripts/release.py`. Every step captures raw evidence
under `.work/release/` before judging it.

**Tiers:**
- Merging a PR is a T3.
- The deploy (a push to `hf`) is a T4.
- The re-pin PR is a T3.
- The tool never performs a T3 or T4 on its own.

## The chain

Names used below:
- `D`: the release commit, the merge of the identity PR.
- `P0`: the currently deployed commit, which the baseline names.
- `R`: the merge of the re-pin PR.

1. **Identity.** In a clean worktree made from `origin/main`:
   ```bash
   python scripts/release.py identity --worktree <wt> --release-id UCPE-PROD-<NAME>-<YYYYMMDD>-A
   ```
   - It edits exactly `config/build_info.py`, `tests/api/test_build_info.py`, and the guard test's
     `CURRENT_DELTA_PATHS` mirror, which it recomputes from the baseline.
   - Then run `./verify.sh` in that worktree and commit.
   - Push and open the PR, CI, then merge with an exact-head merge commit (T3). The merge is `D`.
2. **Guard on D.** Dispatch the source-integrity guard once on `main`, then:
   ```bash
   python scripts/release.py guard-verify <run_id> --expect-head D --expect-pin P0 \
     --expect-release <live release id> --expect-delta '<the delta mirror, as JSON>'
   ```
3. **Preflight.** It is read-only, and runs right before the deploy:
   ```bash
   python scripts/release.py preflight D --dry-push --accept-runtime-delta <sha256>
   ```
   - The first run without `--accept-runtime-delta` prints the runtime delta and its sha256, and stops.
   - Review the delta, then rerun with that digest.
   - It must end `PREFLIGHT=PASS`. Its eight checks:
     1. D is `origin/main` with green push CI;
     2. hf main is `P0`;
     3. the Space is RUNNING at `P0`, serving the live identity, with health 200;
     4. the push is a fast-forward;
     5. the runtime delta is the reviewed one;
     5b. every changed `app.js` or `styles.css` ships a new `?v=` token in `index.html`, so no
        browser keeps the old file;
     6. the guard is explicitly HEALTHY on D, with nothing queued;
     7. the dry run authenticates.
4. **Deploy (T4, owner card below).**
5. **Settle:**
   ```bash
   python scripts/release.py settle D [--probe "POST /path STATUS key.path=value"]
   ```
   - It waits until the Space is RUNNING at D. An error stage stops at once.
   - Then it requires health 200, build-info equal to D's identity, and the served `/`, `app.js` and
     `styles.css` byte-identical to D's files.
   - Any STOP: see `ROLLBACK.md`. Never act automatically.
6. **Re-pin.** In a clean worktree at D:
   ```bash
   python scripts/release.py repin D --worktree <wt>
   ```
   - It builds one deterministic commit touching exactly three files: the baseline, the guard test and
     `ops/release/releases.json`.
   - Then `./verify.sh`, push, PR, CI and an exact-head merge (T3). The merge is `R`.
7. **Guard on R.** Dispatch once, then:
   ```bash
   python scripts/release.py guard-verify <run_id> --expect-head R --expect-pin D \
     --expect-release <new release id> --expect-delta '[]'
   ```
   - The advisory `SCHEDULER_DIVERGENT_FROM_PIN` comes from the guard's shallow checkout. It is
     expected.
8. **Record** the release in STATE (a T3 PR).

## Owner card: the deploy (T4)

- **ACTION_ID:** DEPLOY-`<release id>`.
- **WHY:** publish `D`, already merged and preflighted, to production.
- **WHERE:** a terminal in the main checkout.
- **EXACT_STEPS:**
  ```bash
  python scripts/release.py deploy D --authorize D --release-id <release id>
  ```
- **DO_NOT_DO:**
  - never `--force`;
  - never rerun after it has started (a CONSUMED marker blocks a rerun);
  - never deploy a commit whose preflight is older than 30 minutes or did not pass.
- **EXPECTED_RESULT:** `DEPLOY=PASS`, and the raw push shows `P0short..Dshort  D -> main`.
- **HOW_VERIFIED:** step 5 (settle), then step 7 (the guard on R).
- **RESUME:** "deploy done, settle next".

## What the tool refuses

- A deploy without the exact `--authorize D`, or with a release id that is not D's.
- A deploy with no fresh, passing `--dry-push` preflight.
- A second deploy of the same D.
- An identity step in a dirty worktree, or one that keeps the release id unchanged.
- A re-pin whose release id did not change, or whose digests would not equal D's bytes.
- An evidence directory that already exists: evidence is never overwritten.

## Build inputs and the reproducibility proof (B3)

What makes the build reproducible:
- **The base image** is pinned by its index digest in the `Dockerfile`, never by a floating tag alone.
- **The dependencies:** `requirements.txt` is a generated lock. It holds exact versions and every
  distribution's sha256, and `pip install --require-hashes` enforces them. CI installs the same file.
- **Timestamps and bytecode:** `SOURCE_DATE_EPOCH` (the commit time) makes pip's bytecode hash-based, and
  `PYTHONHASHSEED=0` on the install step alone fixes pip's hash seed. The running app keeps Python's default
  hash randomization.
- **The runtime user** is written directly, with no date stamp.

**The proof** is `.github/workflows/reproducible-build.yml`, on every PR and on main.
- Two clean builds of the same commit run on independent runners. On a PR, that commit is the PR's head itself,
  not GitHub's merge commit. Each build uses a digest-pinned BuildKit, no cache, rewritten layer timestamps,
  and no provenance or SBOM attestation.
- The two must produce the same image manifest digest (`REPRODUCIBLE=PASS`).
- Build A's image is then smoke-tested in fixture mode: health 200, and the commit's own release id.

**To change a dependency:**
1. Edit `requirements.in`.
2. Regenerate with the command in `requirements.txt`'s header, using a new `--exclude-newer` UTC cutoff.
3. Review the lock's diff, and let the proof run on the PR.

**To move the base image:**
1. Resolve the new `python:3.11-slim` index digest from the registry. It is read-only, and needs no
   credential.
2. Replace the digest in the `Dockerfile`.
3. The Dockerfile is a guarded file: the guard test's `CURRENT_DELTA_PATHS` carries it until the next release
   is deployed and re-pinned.

**Limit of the claim:** the Hugging Face Space builds the same `Dockerfile` with its own builder. It installs
the identical pinned bytes, but its image metadata is not bit-for-bit the proof's image. The proof governs
the inputs, not HF's builder.
