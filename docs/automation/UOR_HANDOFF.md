# UCPE → UOR handoff manifest for F1 (`radar_evidence.v1`)

**What this is.** UCPE hands UOR these files, per UOR handoff file 05 §13.
- UOR pins the schemas by the sha256 values below. Any change to a pinned schema means a new version.
- **Status:** merged into UCPE main (M `5da10ef3`) and deployed OFF in release `UCPE-PROD-F1-AUTOMATION-20261001-A` (`5a3ef022`). Nothing is enabled or issued.
- **Owner-gated steps:** the handoff itself (T3/G2) and every enablement step (see the contract, section 13).

| File | Role | sha256 |
|---|---|---|
| `schemas/radar_evidence.schema.json` | pinned success schema | `460458ade4f65e6850e024d3d3a6cc042c40219b802b8ddd89c93ae35a4be5c7` |
| `schemas/radar_evidence_error.schema.json` | pinned error schema | `983001a75249ed5b5b0f5df5fae1910ab4a511418eaac81172a6362cfb1d6315` |
| `docs/automation/RADAR_EVIDENCE_V1.md` | the UCPE canon contract | `37d3857e64eb29cd26b6f4bf744c542e1a18c2e1049c44f6bafafae6643e27c3` |
| `docs/automation/F1_NODE_CLASSIFICATION.md` | proposal nodes under UCPE canon | `70fb0bad6431830498f06699d57eca5cf4f56ce4de7eb2863ac4772163d27178` |
| `docs/automation/COHORT_READER_AUDIT.md` | why the origin is isolated | `ad8b0b9c770a82063106c24f5db6f071657efdfada2913d9e84d7a505fd1b19f` |
| `docs/automation/CREDENTIAL_ROTATION.md` | credential issue, rotation and revocation | `4cb6de4d7adc4d7b208d3e738cbbcc2f25b115ca48615c363d65e1c9282c5cce` |
| `docs/automation/RETENTION_AND_IDEMPOTENCY.md` | retention and idempotency audit | `e97d93670a3dfb1c2e489e0bbfd59f87947da89be6e5274d430f1875d5b0787f` |
| `docs/automation/F1_RELEASE_PLAN.md` | the owner-gated release plan | `4a79195c515f834532ae5fae3d8fe475f0a8fe132f76ca47b831cdf881267432` |
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
