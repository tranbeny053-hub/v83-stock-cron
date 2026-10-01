# UCPE → UOR handoff manifest for F1 (`radar_evidence.v1`)

**What this is.** UCPE hands UOR these files, per UOR handoff file 05 §13.
- UOR pins the schemas by the sha256 values below. Any change to a pinned schema means a new version.
- **Status:** authored locally on UCPE branch `feat/f1-governed-automation`. Nothing is deployed, enabled or issued.
- **Owner-gated steps:** the handoff itself (T3/G2) and every enablement step (see the contract, section 13).

| File | Role | sha256 |
|---|---|---|
| `schemas/radar_evidence.schema.json` | pinned success schema | `460458ade4f65e6850e024d3d3a6cc042c40219b802b8ddd89c93ae35a4be5c7` |
| `schemas/radar_evidence_error.schema.json` | pinned error schema | `983001a75249ed5b5b0f5df5fae1910ab4a511418eaac81172a6362cfb1d6315` |
| `docs/automation/RADAR_EVIDENCE_V1.md` | the UCPE canon contract | `601d0fb589c1827962b00e218cc80f3116af8ded1246056ed967dd5b3f23674c` |
| `docs/automation/F1_NODE_CLASSIFICATION.md` | proposal nodes under UCPE canon | `5e122299106ad1f26f81a3185b3a486b1d2490e234a022f4753b81844ccd0bd4` |
| `docs/automation/COHORT_READER_AUDIT.md` | why the origin is isolated | `ad8b0b9c770a82063106c24f5db6f071657efdfada2913d9e84d7a505fd1b19f` |
| `docs/automation/CREDENTIAL_ROTATION.md` | credential issue, rotation and revocation | `961659b39c34ac6ea9043cbcd877f0e9c95a124ea0134433fde3cf759aed0c52` |
| `docs/automation/RETENTION_AND_IDEMPOTENCY.md` | retention and idempotency audit | `6ffcbd7460286202dac1ca1c3c9eaf11ffdb46fb3b1233cf358e98bcededb2ad` |
| `docs/automation/F1_RELEASE_PLAN.md` | the owner-gated release plan | `9125efc72793d4ead68ea64ae327cae8bc98ebcb49f27fb3b92dd68170b96c1e` |
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
