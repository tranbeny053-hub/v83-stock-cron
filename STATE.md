# STATE

Updated: 2026-08-16

## Recovery block — read this first on resume
```
LOOP_STATE=IDLE_AWAITING_OWNER
CURRENT_MILESTONE=operating-model: GPT sidecar amendment (Change A closed; Change B NOT started)
CURRENT_BRANCH=chore/gpt-sidecar
LAST_GREEN_SHA=b52f7ca
LAST_VERIFY=PASS 776 passed · 2026-08-16
CODEX_PENDING=NONE
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=none open; no T3/T4 pending
NEXT_ACTION=owner picks the next milestone; nothing is half-applied
```
Update this block on every pause, every milestone change, and every GPT consultation.
`GPT_REQUEST_STATE` ∈ `NONE` · `DRAFTED` · `SENT_WAITING_RESULT` · `COMPLETED_RESULT_SAVED` ·
`SKIPPED_UNAVAILABLE`.

**Goal** — Complete UCPE v1: a production-quality, analysis-only crypto probability engine.

**v1 scope** — resolver + calibration activation · deploy the GitHub↔HF gap · full
hard-gating · horizon-specific probability modelling · live smokes · release-gate closure.
**Out of v1 (owner decision 2026-08-15):** Phase 2D.3B derivatives first-write. Preserved
in Git on `preserve/2d3b-readiness-packet`; must not block v1.

**Repo** — canonical working copy is this directory, `/Users/kha/Documents/Kha-app/UCPE`.
`origin` = `github.com/tranbeny053-hub/v83-stock-cron` (CI + cron).
`hf` = the Hugging Face Space — **pushing to `hf` is a deployment (T3)**.
Pre-Git copy preserved read-only at `/Users/kha/Documents/Kha-app/v8-crypto-api-clean`;
proven byte-identical to `676fafb` except the four files now committed. Retire it after v1.

**Last green** — `main` @ `1b06aab` · `VERIFY=PASS` 776 passed, ruff clean, 3/3 scanners.
Deployed production build is `e6ee23c`; `main` is one pin commit ahead of it by design.

**Change A is merged to GitHub (2026-08-16).** PR #2 `feat/calibration-truth` → `main`,
head `44ca1d9`, CI green on that exact head, merged as merge commit
`e6ee23cc81274c2ad68e247293738bc8e81f082a` = `origin/main`. 20 files, +1252 −28. The
merged tree is byte-identical to the PR head. **Nothing was deployed** — `hf` was verified
unchanged at `30d4982` before and after, and no workflow references Hugging Face or
triggers on push to `main`, so merging cannot deploy.

**Branches** — `main` = `origin/main` = `e6ee23c` (also the exact deploy source, now live) ·
`chore/deploy-pin-change-a` (deploy packet, pushed for the pin PR) ·
`feat/calibration-truth` (merged) · `preserve/2d3b-readiness-packet` ·
`chore/operating-model`.

**Production — Change A IS DEPLOYED (2026-08-16).** HF Space live at `e6ee23c`,
`stage=RUNNING`, `cpu-basic`, healthy. The prior build `30d4982` was a strict ancestor,
24 commits behind, so the deploy was the expected fast-forward.

**Live operations (verified 2026-08-15, read-only)** — all 7 GitHub workflows active.
Outcome resolver: 670 runs, last 100 all successful. Source-integrity guard green.
**Database: all 7 migrations (0001–0007) APPLIED. No migration work is required.**
965 predictions, 813 resolved outcomes (DOWN 376 / UP 327 / TIMEOUT 110).

**Prediction generation is traffic-driven, not scheduled.** A prediction row is written
only as a best-effort background side-effect of a session-gated `/v1/analyze` or
`/v1/analyze_batch` call (`app.py:164,185` → `analysis_service.py:510`). No scheduled
workflow calls it: keepalive GETs `/` only; the other two schedules resolve outcomes and
check source integrity. So `predictions_last_7d = 0` means **no operator used the app
since 2026-08-05 04:25:18Z** — the month spent on UABO. It is not a fault.

**CI has now run.** `ci.yml` triggers on `push` to `codex/**` and on `pull_request`; PR #2
supplied the first real trigger. Check run `test` completed `success` on head `44ca1d9`.
Clean-room verification of this repository has now actually executed.

**Calibration — MEASURED (verified 2026-08-15, read-only production query)**
Default cohort **806 samples → `MEASURED`** (threshold ≥500). Nothing is lost to data
quality: `excluded_prediction_not_live = 0`, `excluded_outcome_not_live = 0`,
`excluded_bad_label = 0`. The only exclusions are 7 correctly-cohorted rows
(5 `CONTROLLED_SMOKE` + 2 `SCHEDULED_SHADOW_EVIDENCE`), so the derivatives smoke rows are
**already reclassified** — the contamination query returned no rows.
Single `model_version=phase1a-wave4b0` and `methodology_version=heuristic-v1-wave4b0`
across all 806 → **no `VERSION_MIX_WARNING`**. A clean single-version sample.

Per-timeframe, all `WARMING_UP` (100–299): 15m 172 · 4H 172 · 1H 165 · 1D 163 · 1W 134.
**1M has zero resolved outcomes** (its horizons sit among the 152 still-unresolved).
So unscoped reports are MEASURED; per-timeframe reports warn; per-symbol will warn more.

*This is the second time live evidence beat the documentation: the strategic audit
assumed calibration was stuck at `INSUFFICIENT_SAMPLE`. It is at `MEASURED`.*

**Gate** — `./verify.sh` is now materially equivalent to GitHub CI: ruff, full pytest,
`validate_schemas.py`, `manual_smoke.py`, and all 3 safety scanners. **3.84 s**, one-line
output, first-causal-failure preserved. A local PASS is now as strong as a green CI run.

**HF production (read-only, 2026-08-15)** — Space `RUNNING`, `cpu-basic`, sha `30d4982`
(= baseline), uptime ~2.5 days. `/healthcheck` 200; `/v1/build-info` 200 with fingerprint
`UCPE-W4D3-OPS-2A0-20260622-A`. `/v1/system_status` and `/v1/calibration` both return
**401 with a well-formed UNAUTHORIZED body — the route is registered and its auth gate
works** (not 404, not 500).

**Production CAN serve calibration — configuration proven end to end (2026-08-16).**
Owner confirmed the HF Space secret key `SUPABASE_DB_URL` is PRESENT. Every file in the
calibration path is **byte-identical** between the deployed build `30d4982` and `main`:
`calibration/service.py`, `calibration/metrics.py`, `persistence/repository.py`,
`persistence/prediction_origin.py`, `config/settings.py`, `api/app.py`,
`api/calibration_endpoint.py`. So `build_operator_repository` selects
`SupabasePersistenceRepository`, the endpoint's `_EXPECTED_REPOSITORY` guard
(`SUPABASE_POSTGRES`) passes, and it reads the same database the resolver writes to.
Only the live HTTP invocation is unverified (session-gated; not circumvented).

**But `/v1/calibration` will NOT report MEASURED.** The endpoint never issues an unscoped
query: `calibration_endpoint.py:118` iterates `SUPPORTED_TIMEFRAMES` =
`("15m","1H","4H","1D","1W","1M")` and builds one scoped report per timeframe. So
production will report **WARMING_UP ×5 and NO_SAMPLES for 1M** — not MEASURED. The
806/MEASURED figure is the unscoped aggregate, which no endpoint requests. Reaching
MEASURED per timeframe needs ≥500 resolved outcomes in a single timeframe (currently
134–172), i.e. roughly 3× more operator traffic per timeframe.

**Deploy packet for Change A — prepared, verified, unpushed (2026-08-16)**
Branch `chore/deploy-pin-change-a`, **local only, never pushed**, `VERIFY=PASS` 776.
The pin commit is `1712469`; `a4bd2ac` and this checkpoint are `STATE.md`-only commits on top.
The source-integrity guard (`.github/workflows/source-integrity-guard.yml`, cron `27 */2 * * *`
→ `scripts/source_integrity_guard.py`) is a **composite pin** held as tracked literals in
`ops/hf_runtime_baseline.json`: the HF `refs/heads/main` commit SHA, SHA-256 of eleven
guarded source blobs read from that HF commit, plus build identity and frontend asset
tokens. It runs in GitHub Actions and reads the manifest from the **GitHub** checkout; it
queries HF only for its ref SHA and blobs. So the pin update belongs on GitHub `main`
only — never in the HF repo. No secret supplies any expected value.

The packet changes exactly five literals: `hf_main_sha` `30d4982` → `e6ee23c`, and the four
guarded digests Change A alters (`schemas/response.schema.json`, `api/analysis_service.py`,
`api/app.py`, `derivatives_intel/runtime.py`). `config/build_info.py` is byte-identical
across both builds, so the **fingerprint does not move** — drift would come from the SHA
and blob layers, not identity. The test's `PIN_SHA`/`CURRENT_DELTA_PATHS` mirror follows;
non-empty-delta coverage is retained by `test_shallow_checkout_advisory_is_non_failing`.

**Order held: deploy first, pin second — all four steps executed 2026-08-16.**
(1) `e6ee23c` pushed to `hf` (fast-forward); (2) health confirmed; (3)
`chore/deploy-pin-change-a` landed on GitHub `main` by PR #3; (4) guard dispatched.
The `PIN_DRIFT` window between (1) and (3) opened and closed as designed and was never
observed as a failure, because the guard was only dispatched after the pin landed.

**PIN CLOSED — PR #3 merged.** `chore/deploy-pin-change-a` @ `7290a0e` → `main`, CI check
run `test` = `success` on that exact head, merged as merge commit
`1b06aab32ed560cf890609ef9c722862c71ebf6c` = `origin/main`. The PR contained exactly three
files — `ops/hf_runtime_baseline.json`, `tests/scripts/test_source_integrity_guard.py`,
`STATE.md` — no source, schema, gate, or quant change. `mergeable_state` was `clean`.

**SOURCE-INTEGRITY GUARD — HEALTHY, exit 0** (`workflow_dispatch` run `31941852536`,
head `1b06aab`). `pinned_hf_main_sha` == `hf_main_sha` == `e6ee23c`, so **no `PIN_DRIFT`
remains**. Three probe rounds all `HEALTHY`; `critical_source_match: true`;
`mismatched_path_names: []`; `frontend_asset_match: true`; live fingerprint == intended.

*Correction to the earlier prediction:* the advisory came back
**`SCHEDULER_DIVERGENT_FROM_PIN`, not `SCHEDULER_AHEAD_OF_PIN`.** This is benign and
contract-defined. The guard workflow uses `actions/checkout@v4` with no `fetch-depth`, so
the runner has a depth-1 shallow clone and the ancestry walk in `evaluate_deployment_delta`
raises; `_safe_deployment_advisory` catches it and returns the fallback
(`scheduler_ahead_count: null`, `deployment_delta_paths: []`) — exactly what was observed.
`test_shallow_checkout_advisory_is_non_failing` covers this path, and the advisory
structurally cannot affect Q1: the summary validator raises
`"Integrity summary advisory affected Q1."` if it ever did, and
`test_advisory_internal_failure_cannot_fail_healthy_q1` pins that. So the advisory is
non-failing by contract, not by interpretation. **Expect this advisory on every run until
the workflow sets `fetch-depth: 0`** — not a fault, and not worth a change on its own.

Rollback was pre-authorized but **not used and not needed**. For reference, restoring the
previous build would need
`git push --force-with-lease=refs/heads/main:e6ee23cc81274c2ad68e247293738bc8e81f082a hf 30d4982903e6f44e063616bc3f03f334bd2544e2:refs/heads/main`
plus reverting the five pin literals on GitHub — a force is required because the restore
moves the remote backwards.

**CHANGE A DEPLOYED TO PRODUCTION — 2026-08-16.**
`e6ee23c` is live on the HF Space. Pre-deploy fail-closed checks all passed first:
`origin/main` = `e6ee23c` exactly, `hf refs/heads/main` = `30d4982` exactly, ancestry
confirmed fast-forward, packet diff exactly the five pin literals + test mirror +
`STATE.md`, `./verify.sh` = `PASS` 776.

*First attempt was blocked at the credential boundary and mutated nothing.* `git push hf`
hung ten minutes and transferred zero bytes: `credential.helper` is `osxkeychain` with no
`huggingface.co` entry, so git fell back to an interactive username prompt the harness
askpass never answers. Confirmed with `GIT_TERMINAL_PROMPT=0` →
`fatal: could not read Username for 'https://huggingface.co'`; reproduced with the sandbox
disabled, so not a sandbox effect. **Anonymous read of `hf` works — only write needs
credentials**, which is why every `git ls-remote hf` succeeded throughout.
Resolution: the owner ran `hf auth login`, which installs the CLI and writes
`~/.cache/huggingface/token` but **does not configure git over HTTPS**. The push was
completed by bridging that owner-provisioned token to git for the single push via an
inline `credential.helper`. **No token was printed, stored in the repo, or modified.**
If `osxkeychain` still lacks a `huggingface.co` entry, a future push needs the same bridge
or a one-time `hf auth login --add-to-git-credential`.

**Deploy evidence — restart proven independently of the fingerprint.** `hf refs/heads/main`
= `e6ee23c`; HF Spaces API reports `sha=e6ee23c`, `stage=RUNNING`, `cpu-basic`;
`uptime_seconds` collapsed **278648 → 28** and resumed climbing, so the runtime genuinely
rebuilt and restarted. The build fingerprint stayed
`UCPE LIVE BUILD · W4D3-OPS-2A0-20260622-A` exactly as predicted — `config/build_info.py`
is byte-identical across both builds — which is why it was never used as deploy proof.
Health after deploy: `/healthcheck` 200 `status=OK` · `/v1/build-info` 200 · `/` 200 ·
`/v1/calibration` and `/v1/system_status` both **401 `UNAUTHORIZED` with a well-formed
body — routes registered, auth gates intact, not 404 and not 500**.
No rollback was used and none was needed. No DB write, no migration, no secret change.

**CANONICAL HANDOFF CHECKPOINT — CHANGE A DEPLOYMENT CLOSURE COMPLETE (2026-08-16).**
Production `e6ee23c` · GitHub `main` `1b06aab` · guard `HEALTHY` exit 0 · no `PIN_DRIFT`.
Closure boundaries held exactly: **no production DB write, no migration applied, no secret
created or modified, no rollback used, and Change B not started.** The one secret-adjacent
act was *using* the owner's already-provisioned HF token for a single push without printing,
storing, or altering it. Nothing in this closure is pending or half-applied.

**GPT SIDECAR AMENDED INTO THE OPERATING MODEL — 2026-08-16 (T0, docs only).**
`CLAUDE.md` gains two sections — *GPT sidecar* and *Pause and resume* — and `STATE.md`
gains the recovery block above. **No new process file**: still exactly six
(`CLAUDE.md` `AGENTS.md` `STATE.md` `verify.sh` `delegate.sh` `docs/OPERATING_DOCTRINE.md`).
`.work/gpt-request.md` and `.work/gpt-result.md` are gitignored ephemera, not artifacts.
Routing is unchanged — deterministic tool > Codex > Opus > owner — and GPT sits outside the
loop at ≤1 consultation per milestone.

*Smoke test executed once, end to end, and discarded.* A temporary ChatGPT thread was
opened in the owner's logged-in Plus session via Claude Code Chrome; the Advanced menu read
**Model `GPT-5.6 Sol`, Effort High** before anything was sent; a 566-byte non-sensitive
handshake went out and a 450-byte reply came back (`UCPE-SIDECAR-OK` · self-reported
`GPT-5.6 Sol` · one clause on why advice carries no authority). Both limits held (≤2 KB
request, ≤1 KB result). **No OpenAI API and no API key**: no `OPENAI*` environment variable
exists, no key file on disk, the `openai` package is not installed in `.venv`, and the
repository contains no `openai` or `api.openai.com` reference — the only transport was the
browser UI. The smoke thread is **not** project history and is referenced nowhere.

**Open decisions** — none blocking.

**NEXT ACTION** — owner's call on what ships next; Change A needs nothing further.
Worth knowing before choosing: production now serves Change A's gating, but
`/v1/calibration` still reports **`WARMING_UP` ×5 and `NO_SAMPLES` for 1M**, because the
endpoint only issues per-timeframe scoped queries and no timeframe has ≥500 resolved
outcomes (134–172 each). The 806/`MEASURED` figure remains an unscoped aggregate no
endpoint requests. Since predictions are traffic-driven, that gap closes only with roughly
3× more operator traffic per timeframe — not with time alone.
Change B (horizon-specific probability modelling) stays deferred and **has not started**:
it needs a new `methodology_version`, which resets calibration to `NO_SAMPLES`, so the
806-sample cohort must survive as the control until Change A has re-accumulated evidence
under gating.
