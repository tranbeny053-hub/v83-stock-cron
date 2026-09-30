# UCPE → UOR handoff manifest for F1 (`radar_evidence.v1`)

**What this is.** UCPE hands UOR these files, per UOR handoff file 05 §13.
- UOR pins the schemas by the sha256 values below. Any change to a pinned schema means a new version.
- **Status:** authored locally on UCPE branch `feat/f1-governed-automation`. Nothing is deployed, enabled or issued.
- **Owner-gated steps:** the handoff itself (T3/G2) and every enablement step (see the contract, section 13).

| File | Role | sha256 |
|---|---|---|
| `schemas/radar_evidence.schema.json` | pinned success schema | `460458ade4f65e6850e024d3d3a6cc042c40219b802b8ddd89c93ae35a4be5c7` |
| `schemas/radar_evidence_error.schema.json` | pinned error schema | `983001a75249ed5b5b0f5df5fae1910ab4a511418eaac81172a6362cfb1d6315` |
| `docs/automation/RADAR_EVIDENCE_V1.md` | the UCPE canon contract | `12560196a48adcc370c157457b7caf4f070defb050ba105076a2d44361ecac77` |
| `docs/automation/F1_NODE_CLASSIFICATION.md` | proposal nodes under UCPE canon | `aeb69179ab0d715b91d8bf0f1c1ddb083d5d67b29855fe8e825235a731695885` |
| `docs/automation/COHORT_READER_AUDIT.md` | why the origin is isolated | `ad8b0b9c770a82063106c24f5db6f071657efdfada2913d9e84d7a505fd1b19f` |
| `docs/automation/CREDENTIAL_ROTATION.md` | credential issue, rotation and revocation | `961659b39c34ac6ea9043cbcd877f0e9c95a124ea0134433fde3cf759aed0c52` |
| `docs/automation/RETENTION_AND_IDEMPOTENCY.md` | retention and idempotency audit | `dd9e923cd85c00e8550f8a84b9e1bb48ecdc44fd4221250503e166359285a6e7` |
| `docs/automation/F1_RELEASE_PLAN.md` | the owner-gated release plan | `44d09b1cc4cdf1ec1dd70aaac99d09e0441d50394221a173aed5894b5ca5120c` |
| `docs/automation/examples/MANIFEST.json` | example provenance and digests | `484c03ec6252277a7b3acba5015778f725c5977e724ba1164c8c1fcad5d0b466` |
| `docs/automation/examples/radar_evidence.v1.synthetic-btc-4h-gate-blocked.json` | synthetic example: gate blocked | `c47e0e5ef6f30725d488c56e6b3b73849b445ef19f7079aac1bc98cbd872620f` |
| `docs/automation/examples/radar_evidence.v1.synthetic-eth-1h-h2-hold.json` | synthetic example: H2 hold | `2c33037891d5d44f9f625f47681bba1f281e0de7c37bb025aea11f84048b5c65` |
| `docs/automation/examples/radar_evidence_error.v1.synthetic-quota-exceeded.json` | synthetic error example | `55907162860e60316fd39bb4fdf07cc627fba452074123779158ff23a3a56c60` |

**Verifying a received body.**
1. Parse the JSON body.
2. Remove `evidence_hash`.
3. Serialize the rest with RFC 8785 JCS.
4. Compare `"sha256:" + hex(sha256(bytes))` with the removed `evidence_hash`.

The raw response bytes are themselves the JCS form of the full body.

**The examples.** They are SYNTHETIC_FIXTURE: the real pipeline on deterministic fixture candles, with no live data, no holdout and no section 5A evidence.
- Their release identity `UCPE-SYNTHETIC-EXAMPLE-V1` is served by no release, and must never be allowlisted.
- To regenerate them: `PYTHONPATH=src:. python -m tests.automation.examples_builder --write`.
