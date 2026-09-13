# Post-one-look dependency map

Written 2026-09-12, read-only. No holdout row, no database, no §5A statistic was inspected to
produce it, and no lane it describes was modified. Every claim is derived from Git, the
committed contracts, and the workflow/guard configuration.

Its question: **after the one look is taken, what is actually blocked by the result, and what
was never blocked at all?**

## 0. The headline

Most of the backlog does **not** depend on the §5A result. Three of the four areas surveyed are
independent of it in content; only the methodology lane genuinely waits. Two things that look
like blockers are not:

- **The `T_close` freeze on `R202-01`, `A203-01` and `integration/b11-combined` has already
  lapsed by its own terms.** `STATE.md` froze them "until after `T_close`". That instant passed
  at 2026-09-12T04:00:00Z. They are unblocked **now**, not after the one look.
- **The Hugging Face release is blocked by policy, not by content.** Nothing in the evaluator or
  the frozen lanes touches a deployed-bundle path. It waits only because the owner chose to hold
  `DEPLOY_PROHIBITED` until the result is captured — a ruling that can be lifted independently
  of what the result says.

One suspected coupling was checked and **does not exist**: the source-integrity guard watches a
fixed set of eleven critical files, and none of the four open or frozen lanes touches any of
them, so merging any of them leaves the deploy delta set unchanged and the guard undisturbed.

## 1. Lane inventory and conflict surface

| Lane | Branch | Files changed | Pushed |
|---|---|---|---|
| §5A evaluator | `feat/5a-evaluator` | evaluation package, `calibration/metrics.py`, `persistence/repository.py`, CLI, pin, workflow, tests | no |
| Collector stop | `ops/stop-post-tclose-collector` | `oos-pair-evidence.yml` + 2 tests | no |
| R202-01 | `fix/r202-01` | `adapters/http_client.py` + test | no |
| A203-01 | `fix/a203-01` | `validation/market_data.py` + test | no |

**All six pairs are file-disjoint.** No lane touches a guarded deploy path, and no lane touches
any of the eight `distributional-v1` freeze-closure files — verified, so none of them can
disturb the candidate freeze or the evidence already collected.

The one latent conflict worth recording: `feat/5a-evaluator` is the only lane touching
`persistence/repository.py`. Any future migration-0008 *code* work would collide there. The
0008 *application* is a database action and collides with nothing.

## 2. Classification

### Class A — independent of the result, and unblocked NOW

| Item | Why independent |
|---|---|
| `R202-01` provider HTTP byte cap and wall-clock deadline | Touches no closure file, no watched file, no deploy path. The holdout is closed and at rest, so it cannot reach the evidence. |
| `A203-01` candle ordering and future-boundary fail-closed | Same. |
| `integration/b11-combined` | Integration evidence for the two above; no independent content. |
| Collector stop | Prepared. Changes when the collector runs, never what it writes. |
| Candle-fetch width `> 205` bars (R2 §7.2c) | A capability change. Unlocks Track B on 15m; nothing about it turns on the v1 result. |

**One sequencing rule binds this whole class: land it BEFORE any new `T_freeze`.** These change
what a future holdout would observe. Merged before a new candidate freeze, the hardened
behaviour is inside the new baseline's provenance. Merged after, the new holdout runs on
un-hardened ingestion and a later merge sits outside the frozen baseline — a provenance mess
that is free to avoid and expensive to unwind.

### Class B — independent in content, gated by owner policy

**Hugging Face release / clean-room backport.** Production is at `hf/main = a89b45e`
(PROD-SAFE-2), 166 commits behind main. The deploy delta is five guarded paths, of which
`analysis_service.py` is the standing structural clean-room delta that never clears.

Independent because the evaluator touches **zero** deployed-bundle paths and the frozen lanes
touch **zero** watched files. Blocked only by the held `DEPLOY_PROHIBITED`.

The real decision here is **ordering, not permission**: a release taken *before* any promotion
carries only the accumulated safe UI work and is a clean-room backport of already-reviewed
content. A release taken *after* a promotion carries the methodology change with it and needs
its own review. Releasing first is the simpler, more reviewable path, and it is available the
moment the result is checkpointed.

### Class C — independent in content, sequence-constrained

**Migration 0008 (`analysis_run_details`), T4.** Zero coupling to §5A: the evaluator makes no
reference to it, and it touches neither `predictions` nor `prediction_outcomes`. The
prerequisite N+1 blocker was closed by PR #63, so nothing else stands against it.

The constraint is operational, not logical: **it is a production database write and the one look
is a production database read, so do not overlap them.** Additive DDL should not lock the
prediction tables, but "one irreversible action at a time" is the cheaper rule than reasoning
about lock scope, and both are T4 one-shot actions where a rerun is prohibited.

### Class D — genuinely depends on the result

| Item | Nature of the dependency |
|---|---|
| Promotion of `AUTHORIZED(s,t)` cells | Exists only on PASS. §5A.7 authorizes per cell; nothing promotes otherwise. |
| Calibration cohort handling | Promotion assigns a new `methodology_version`, which resets calibration to `NO_SAMPLES`. Only reachable through promotion. |
| `distributional-v2` freeze decision (R2 §7.2d) | The R2 report conditions it explicitly on the `T_close` result, and §7.1 requires the one look to run first. |
| A new candidate freeze, `T_freeze`, `T0`, holdout | §5A.9: the only acceptance path for any new candidate, and its baseline depends on whether v1 promoted. |

**The methodology-version reset is the coupling that makes this class serial.** The doctrine is
explicit that a new `methodology_version` resets the evidence base and the prior cohort must
survive as the control. A v1 promotion and a v2 freeze are two resets; overlapping them destroys
the control cohort twice and the sequencing is a safety property, not bureaucracy.

### Class E — decidable now, actionable later

R2 §7.2 batches four owner decisions. Two of them — **(a)** a skill gate for zero-drift models
and **(b)** what the directional display should show under one — are prerequisites *for* v2
rather than consequences *of* the v1 result. They can be decided while the result is still
unknown, which removes them from the critical path without committing to anything.

## 3. The maximum safe parallel batch after the one look

Concurrency is limited by three real constraints, not by appetite: never two T4 actions at once;
never two `methodology_version` resets overlapping; and owner interactions are batched.

    ── BEFORE the one look (available now) ─────────────────────────────
    Class A merges: R202-01, A203-01, integration evidence.  ONE T3 batch.
    Independent of the result, unblocked since T_close, and best landed
    before any new T_freeze.

    ── THE ONE LOOK ────────────────────────────────────────────────────
    Codex verification -> consolidated review -> owner authorization ->
    readiness (repeatable) -> consumption (once) -> result CHECKPOINTED.
    Nothing else runs concurrently with the consumption read.

    ── WAVE 1, fully parallel, 3 lanes, ONE owner batch ────────────────
    L1  HF clean-room release of accumulated safe work        T3/T4
    L2  Migration 0008 apply                                  T4   (after
        the consumption read completes, never during it)
    L3  Candle-fetch width > 205 bars                         T2
    Disjoint systems: a Space, a database, and source. No shared file.

    ── WAVE 2, only if PASS, strictly serial ───────────────────────────
    Promotion of AUTHORIZED(s,t) cells, then calibration cohort handling.
    One reset. Nothing else touching methodology runs alongside it.

    ── WAVE 3, gated on Wave 2 and the Class E decisions ───────────────
    distributional-v2 module (R2 §7.4), then a NEW candidate freeze,
    new T_freeze, new T0, new holdout. Class A must already be merged.

If the result is **NOT PASS**, Wave 2 disappears entirely and Wave 3 becomes the live question
immediately — so a NOT PASS *accelerates* the backlog rather than blocking it. That is worth
stating plainly in advance, because it removes any incentive to hope for a particular result.

## 4. What could go wrong, and the rule that prevents it

| Hazard | Rule |
|---|---|
| Two T4 actions overlapping | Serialize. 0008 waits for the consumption read to finish. |
| A deploy silently carrying an unreviewed promotion | Release before promotion, or re-review the bundle after. |
| A new holdout running on un-hardened ingestion | Land Class A before any new `T_freeze`. |
| Two `methodology_version` resets overlapping | One reset at a time; the prior cohort must survive as control. |
| A future 0008 code lane colliding with the evaluator | Both touch `persistence/repository.py`; land the evaluator first. |
| The collector resuming under a retired pre-registration | Already prevented: the inverted cadence assertion fails the build. |

## 5. Standing limits on this map

It classifies **dependency**, not desirability: nothing here recommends doing any of it, and
every T3 and T4 remains the owner's call. It was produced without inspecting the holdout, the
database, or any §5A statistic, so it cannot and does not anticipate the result. And it assumes
the four lanes stay as they are today — a review finding that changes the evaluator's file set
could reintroduce a conflict that is disjoint right now.
