"""The UOR handoff examples: reproducible byte for byte, schema-valid and provenance-declared."""

from __future__ import annotations

import hashlib
import json

from crypto_probability_engine.automation.contract import (
    error_body_valid,
    evidence_hash,
    radar_evidence_valid,
)
from crypto_probability_engine.config.build_info import build_info_payload
from tests.automation import examples_builder

WITHHELD = (
    "observed_directional_rate",
    "legacy_verdict",
    "skill_evidence",
    "quant_v2",
    "derivatives_intelligence",
    "USER_REQUESTED",
    "CONTROLLED_SMOKE",
    "SCHEDULED_SHADOW_EVIDENCE",
)


def _committed() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in examples_builder.EXAMPLES_DIR.iterdir()}


def test_the_committed_examples_are_exactly_what_the_builder_produces() -> None:
    assert _committed() == examples_builder.build_examples()


def test_every_example_validates_and_every_evidence_hash_verifies() -> None:
    manifest = json.loads(_committed()["MANIFEST.json"])
    assert len([f for f in manifest["files"] if f["validates_against"] == "radar_evidence.v1"]) >= 2
    for entry in manifest["files"]:
        body = json.loads(_committed()[entry["file"]])
        if entry["validates_against"] == "radar_evidence.v1":
            assert radar_evidence_valid(body), entry["file"]
            assert evidence_hash(body) == body["evidence_hash"], entry["file"]
        else:
            assert entry["validates_against"] == "radar_evidence_error.v1"
            assert error_body_valid(body), entry["file"]


def test_the_manifest_declares_synthetic_provenance_and_exact_digests() -> None:
    committed = _committed()
    manifest = json.loads(committed["MANIFEST.json"])
    assert manifest["provenance"].startswith("SYNTHETIC_FIXTURE:")
    assert "no holdout" in manifest["provenance"] and "no live data" in manifest["provenance"]
    for entry in manifest["files"]:
        assert hashlib.sha256(committed[entry["file"]]).hexdigest() == entry["sha256"]
    assert sorted(committed) == sorted([*(f["file"] for f in manifest["files"]), "MANIFEST.json"])


def test_the_examples_carry_a_release_no_one_serves_and_nothing_withheld() -> None:
    real_release = build_info_payload()["release_id"]
    for name, content in _committed().items():
        text = content.decode("utf-8")
        for withheld in WITHHELD:
            assert withheld not in text, (name, withheld)
        body = json.loads(text)
        if "build_info" in body:
            assert body["build_info"]["release_id"] == "UCPE-SYNTHETIC-EXAMPLE-V1" != real_release
