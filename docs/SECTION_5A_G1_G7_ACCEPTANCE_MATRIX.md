# G1–G7 acceptance matrix

Written 2026-09-12 against the frozen implementation `feat/5a-evaluator@2b31832`.

Two repair rounds on the seal-and-capture causal class have each been defeated by siblings of
the defect they fixed. The loop being inverted here is the cause: the same model authored the
defects and then the repairs, and imagined the same cases twice. **So the failing tests are
authored first, by the verifier, against a frozen implementation, before any repair exists.**

## Rules for the test-authoring pass

1. **No production-code change.** Not one line. The implementation is frozen at `2b31832`.
2. **Every test must FAIL (RED) against the frozen tree**, or the finding is reported
   **REFUTED** with the evidence that it does not reproduce. A finding that cannot be made to
   fail is as valuable a result as one that can.
3. **Tests assert the CORRECT behaviour, never the defective behaviour.** Run 2's probes were
   written as `test_..._documents_...`, passing by asserting what the code wrongly does. Those
   go red on their own repair and fight the fix. Every test here must go **RED now and GREEN
   when repaired**.
4. **No live database, no network, no push, no readiness, no consumption against real data.**
5. Where a property needs a type or ordering the real driver produces, **simulate the driver**,
   do not connect to it.

## The matrix

Each row states an **observable property**. It does not prescribe an implementation — choosing
that is the repair's job, and prescribing it here would re-import the blind spot this pass
exists to remove.

### G1 — CRITICAL — a database value type must not be able to spend the look

The digest is computed after the probability read and before the seal claim, and
`_canonical_json` handles only `datetime`. Postgres `NUMERIC` arrives through psycopg as
`Decimal`, so on real data the **first** consumption reads the holdout and raises with no seal.

| # | Property |
|---|---|
| G1.1 | With every probability delivered as `Decimal`, a consumption either completes or leaves a durable seal. It must never read probabilities and leave none. |
| G1.2 | The same holds for **every** type the driver can return for the projected columns — enumerate them (`NUMERIC`→`Decimal`, `TIMESTAMPTZ`→`datetime`, `TEXT`→`str`, `JSONB`→`dict`/`list`, `NULL`→`None`) and cover each. |
| G1.3 | Canonicalization is deterministic: the same driver output hashes identically across runs and processes. |
| G1.4 | Canonicalization does not silently alter a scored value. If the canonical form of `Decimal("0.6")` differs from that of `0.6`, that is a **driver-dependent digest** — report it as a finding rather than assuming it is acceptable. |

### G2 — CRITICAL — absence must be treated as tampering, not permission

`recompute_from_snapshot` guards with `if recorded_pin is not None`, so deleting the field
skips the check entirely.

| # | Property |
|---|---|
| G2.1 | A snapshot with `evaluator_pin_digest` **removed** is refused. |
| G2.2 | A snapshot with `result_inputs_digest` **altered** is refused; it is recomputed and compared, never copied into the result. |
| G2.3 | Enumerate every field the recompute path trusts, and show each is integrity-checked. A field that is read but unchecked is a finding in its own right. |

### G3 — HIGH — at most one process may read the probabilities

Two concurrent consumptions both read before one loses the singleton `INSERT`, so the look is
spent twice though only one seals.

| # | Property |
|---|---|
| G3.1 | Under two concurrent consumptions, the probability read happens **at most once** across both. |
| G3.2 | The loser is refused with the one-look error and produces no result. |
| G3.3 | The winner's durable seal contains the captured evidence. |
| G3.4 | Whatever satisfies G3.1 must still satisfy F2 (durable and cross-run) and F3 (no read without a seal). A repair that trades one for another is not a repair. |

### G4 — HIGH — nothing that can disable the pin check may itself be unpinned

`scripts/evaluate_section_5a.py` can pass `verify_pin=False` and is not in the pinned set.

| # | Property |
|---|---|
| G4.1 | Every production entrypoint able to influence pin verification is itself pinned; editing it breaks the pin. |
| G4.2 | No production code path reaches `verify_pin=False`. Tests may; the CLI may not. |
| G4.3 | Sweep for any **other** input that can change the answer and is outside the pin. This is the finding class that has recurred most. |

### G5 — MEDIUM — identity must be stable for identical database state

The feature-diagnostics query has no `ORDER BY`, so row order — and therefore the digest — is
whatever the server returns.

| # | Property |
|---|---|
| G5.1 | Two reads of identical database state yield byte-identical digests. |
| G5.2 | Every read feeding a digest carries a deterministic `ORDER BY` (assert on the SQL text). |
| G5.3 | The digest is order-independent by construction as well, so a driver returning a different order cannot change it. G5.2 and G5.3 are both required: one is the source, the other the backstop. |

### G6 — MEDIUM — the mandatory diagnostics are still incomplete

| # | Property |
|---|---|
| G6.1 | Enumerate §5A.10's list verbatim from the contract. Every item is present **per timeframe and per cell**, in **both** readiness and consumption output. |
| G6.2 | No quantity is reported as a number that nothing measured. The `UNMEASURED` treatment generalizes: absence is reported as absence. |

### G7 — MEDIUM — the two Tier-1 qualifiers must accept the same population

`_oos_arm` accepts an explicit `arm` field that the Postgres SQL cannot see, so the in-memory
and Postgres qualifiers can disagree.

| # | Property |
|---|---|
| G7.1 | A differential test over crafted rows — including one carrying an explicit `arm` field — shows the in-memory and Postgres qualifiers admitting an identical population. |
| G7.2 | Either the explicit-`arm` path is removed or the SQL can see it. The two behaviours must not coexist, because the divergence is silent and changes which rows are analysed. |

## Sibling sweep, carried forward

Each round has found siblings of the previous round's classes. Sweep for these specifically,
and report anything found as a new finding rather than folding it into an existing row:

- another **local-only assumption** presented as a global guarantee (the F2 class)
- another **unpinned input** that can change the answer (the F6/G4 class)
- another **fabricated default** standing in for something unmeasured (the F7 class)
- another **raw-versus-canonical inconsistency** between two code paths (the F8/G1 class)
- another **guard that treats absence as permission** (the G2 class)

## Output

`.work/g1-g7-red-tests.md`: for each row, the test name, whether it is **RED** against
`2b31832` or the finding is **REFUTED**, and the exact observed failure. Plus any new finding
from the sibling sweep.

Repair may begin only after this pass returns. The subsequent verification is a **completely
fresh full adversarial pass**, not a re-run of these targeted tests.
