# Operating doctrine

Extracted 2026-08-15 from the UABO Autonomous Epoch Mode amendment, which was retired as a
product. The doctrine was the valuable part; the control plane that implemented it was not.
Full rationale: `UABO_UCPE_STRATEGIC_RESET_2026-08-15/OPUS_STRATEGIC_AUDIT_AND_DECISION.md`.

## Actors

Claude Code holds the loop. Codex implements headlessly via `codex exec`. Scripts verify.
Git records. The owner decides only what is irreversible. **There is no orchestrator.**

Use the cheapest actor that is not inferior: **script > Codex > Opus > owner.**
Escalate on evidence, never on preference.

## The ten rules

1. **Raw before parsed.** For any consequential action, capture exact argv, exit code, and
   raw stdout/stderr *before* anything interprets them. A parser failure must never be a
   reason to repeat a consequential action.
2. **Preserve the first causal failure.** Never overwrite it, never let a later symptom
   replace it. Diagnose before repairing.
3. **Never blind-retry.** An identical command with no intervening change is prohibited.
   On a repeat of the same causal class: root cause → sibling scan → downstream-consumer
   scan → regression test → one consolidated repair. Bound at two attempts, then escalate.
4. **Preflight wide, not just deep.** Before delegating, assert that every path, import,
   environment variable, config key, and external dependency the task needs actually
   exists. Verifying each step's binding rigorously while never asking "does everything
   this run needs exist?" is what produced UABO's five-failure chain.
5. **Fail closed on scope.** A change touching a path outside the task's allowed set is
   rejected, not negotiated.
6. **One-shot authorization for irreversible actions only.** Consumable, no-rerun
   authorization is correct and nearly free at T4, where such events are rare. Applying it
   to reversible local work converts ordinary bugs into owner-gated incidents.
7. **Owner interruptions are rendered, never narrated.** `ACTION_ID · WHY · WHERE ·
   EXACT_STEPS · DO_NOT_DO · EXPECTED_RESULT · HOW_VERIFIED · RESUME`. One screen.
   Executable without inference. Short human resume phrases. Batch them.
8. **Review by risk tier.** No model review of T0/T1. Actual diff review at T2+. No model
   micro-review after every step, ever.
9. **Stable context lives in files.** `CLAUDE.md` + `AGENTS.md` + `STATE.md` are the whole
   canonical core. Everything else is retrieved on demand. Agents exchange task files and
   result files, never transcripts. Pass paths, never contents.
10. **Deterministic tooling owns everything deterministic.** Hashes, status, tests, lint,
    scans, packaging, progress math. Zero model calls for any of it.

## Why external anchors, not internal chains

Hash-chained internal evidence detects accident and drift but not a local actor able to
rewrite every record. A Git commit pushed to a remote is a stronger guarantee at a fraction
of the cost. Git already provides checkpointing, identity, history, and reversibility —
do not reimplement them.

## The economics that make delegation safe

- A delegation returns ~30 bytes into the loop-holder's context, not a transcript.
- The full test suite runs in ~4 seconds, so any change can be accepted or rejected
  without a model call. **Protect this. Keep `verify.sh` under 30 seconds.**
- Work happens on a branch, so the blast radius of any mistake is `git checkout .`.

## Anti-regrowth

Six process artifacts maximum. Nothing enters the reusable template until it has been
genuinely needed in **two** real projects. UABO's failure mode was generalizing from zero
completed projects: it produced 115 MB of control evidence and zero lines of product code
before terminating on a missing directory. If process files exceed ten, or coordination
artifacts exceed 20% of source-plus-test bytes for two consecutive weeks, delete the
excess — do not refactor it.

---

# Owner-facing doctrine (adopted 2026-08-19)

Canonical home. `CLAUDE.md` points here and does not restate it.

## Quant North Star

**Honesty about uncertainty is the product.** UCPE's value is a calibrated, gated statement of
what is and is not known — not a forecast that sounds confident.

- **Evidence outranks argument.** A gate closes on a citation a sceptic could re-check, never on
  a persuasive case. "Release requires evidence."
- **Never convert NOT_RUN into PASS.** If it did not happen, it is not done.
- **Pre-register before measuring.** Fix inference sets, margins, and decision rules before
  seeing data, and record them where they cannot be quietly edited. Never fit a method to a
  result.
- **Measure rather than assume.** If a parameter is obtainable read-only, obtain it. Assumed
  values get sensitivity ranges and an explicit route to replacing them.
- **State the estimand.** Every number answers a specific question about a specific population.
  Carrying a control size or margin from one population into another silently changes the
  question.
- **Distinguish proven from reconstructed** from inferred. Say which, every time.
- **Aggregate evidence is never a per-timeframe guarantee.**

## Free-resource discipline

Paid API cost target is **zero**. Deterministic tools are free and authoritative; use them first
and let them decide. Reserve model reasoning for judgment that tools cannot render. Never
silently substitute a model — record any substitution. The GPT sidecar is exceptional, reached
only through the owner's own logged-in session, never an API key.

## Safe learning

The system must be able to learn without endangering what it already knows.

- **The control cohort is sacred.** `USER_REQUESTED` is the evidence base; `CONTROLLED_SMOKE` and
  `SCHEDULED_SHADOW_EVIDENCE` exist so deliberate activity can never masquerade as it.
- **Predictions are immutable.** Nothing is updated, deleted, or relabelled — so a
  misclassification is permanent, and classification must be proven *before* the write.
- **Canary before commitment.** Ahead of any irreversible write, make the smallest possible one
  and verify it. This bounded a real misclassification to a single row.
- **A new `methodology_version` resets the evidence base**, so the prior cohort must survive as
  the control. Sequencing is a safety property, not bureaucracy.
- **Gate on insufficient evidence, never on optimism.** `INSUFFICIENT_EVIDENCE` activates the
  hard gate; a horizon with no data is protected, not guessed at.

## Whole-product thinking

The deliverable is an operator's working system, not a merged diff.

- **The owner is a non-coder.** Never require reading code to answer a question.
- **Minimum owner effort.** Batch decisions; pre-flight every handed-over command against its
  exact failure path; give one command, not a menu; state expected output and the decision rule
  for each outcome *before* it runs.
- **First time right.** A command that cannot run costs more than the work it saved.
- **Verify the whole chain, not the merge.** Deployed ≠ merged; configured ≠ saved; returned 200
  ≠ took effect. Confirm with two independent signals.
- **Correct in place, loudly.** Retract in the same file; never silently edit a claim.
- **Leave it resumable.** Any pause must be recoverable from `STATE.md` + Git + `.work/` alone.

## Response UI for owner-facing replies

`WHAT THIS MEANS` · `WHERE` · `DO NOW` · `INPUT NEEDED` · `SEND THIS` · `THEN` · `DO NOT` ·
`RETURN WHEN`. Omit only genuinely empty headings. Never bury an owner action in prose.
