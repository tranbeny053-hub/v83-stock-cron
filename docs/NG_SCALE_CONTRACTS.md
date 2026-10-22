# NGA scale contracts

Status: **PROPOSAL, UNWIRED**. The NGA plan is not adopted. These pure contracts decide nothing;
they change no served number, gate, row, or response. Every tolerance, cap, and threshold is
supplied by the caller and remains PROPOSED-REQUIRES-OWNER-APPROVAL.

The carried safeguards are documented in
`.work/nga/addendum5/NGA_ADDENDUM_5_CARRIED_SAFEGUARDS.md` (sealed; local). Governing plan
sections: §5.1, §5.3, §7.1, §12.2, §12.3, and §21 OD-FINAL-6.

## Contracts

- `check_row_classes` and `Population` implement the S-E1/S-E2 population/timing matrix. S-E4
  requires the full population names, keeping E2/E3 distinct from release or Phase-3 proof.
- `claim_admissible` checks E1 exclusion, E2/E3 population separation, and only the S-E3
  window-after-anchor condition for the anchor instant supplied by its caller. The artifact's
  anchor kind is represented by `claim_ready`; §5.3 freeze completeness is not checked by code.
- `check_reclassification` refuses any change to population or timing class, stricter than
  "never upgraded" by design.
- `E3Clocks` and `classify_e3` enforce S-C1 and S-C2: app-clock chronology is checked, the source
  snapshot must not predate the lattice instant, and DB commit time is evaluated separately. An
  unknown or late commit cannot be upgraded; late rows remain reportable.
- `vector_sha256`, `ReplayRecord`, and `replay_parity_claimable` implement the S-R1 claim rule:
  the claimant states that bytes are retained and storage is non-lossy. Code cannot verify that
  retained bytes exist; a digest proves identity only while the bytes exist.
- `AnchorKind`, `IndependentCopy`, `ArtifactManifest`, and `claim_ready` enforce S-R3: only remote
  commits or owner-approved anchors count as anchors, and custody and independent-copy status are
  explicit statements. File times, local seals, and git dates do not count as anchors.
- `load_manifest` and `artifact_status` validate the v1 manifest shape, recipe/cell identity,
  recipe venue binding (C1 is Binance spot), fit chronology, per-cell status, training-end
  staleness, and caller-supplied band bounds.
- `windows` validates one window: snapshot first, else one bounded history fetch proven to
  extend the snapshot; never shorter; fail closed.
- `reference` pins spec v1 to R4's generation-2 day-type base rate in
  `ops/quant_ng/REFERENCE_SPEC_v1.json` and a test; spec v1 values are R4's frozen research
  spec, pinned by the loader and a test; pi0 is caller-supplied; synthetic deployments
  are bit-identical to R4's research code.
- `reference_v1d` pins 1D to one type and 365-day memory; n0 = 1 row follows v1's rule.
  This is development only; 1W awaits its alignment and lattice phase definitions.
- `availability` marks 1M and H_extended UNAVAILABLE; the 24-bar extension is deferred,
  not cancelled.
- `candidate` delegates C1's triplet to `candidate_r4_c1` behind an ELIGIBLE manifest, the σ guard,
  and the central range; no model constants exist in the repository.

## Deliberately absent

There is no registry, pipeline, wiring, lattice, model constant, prior value, decision tolerance,
F3 or look. The reference tier's priors and the candidate's constants are always the caller's;
none exists here. OD-NG-6 (2026-10-22): spec v1d approved for development only; 1D is
implemented; 1W waits on two definitions. EXP-01 and EXP-02 on real
data are the owner's to scope; the parity shown here is synthetic. S-R2 revision evidence and
S-R4 retention (including never deleting claim evidence and capacity stop rules) are process
rules with no code here. S-E3 freeze content and S-C1's maximum commit delay are protocol and
owner matters; this code sets neither. These safeguards are executable proposals only; they do
not select or serve a model.
