from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.quant import candidate_r4_c1 as c1
from crypto_probability_engine.quant_ng import artifact as art


def cell(timeframe: str, **changes) -> dict:
    values = {"coefficients": [-1.0] + [0.15] * (len(c1.HAR_FEATURES[timeframe]) + 1),
              "profile": [0.6 + 0.02 * index for index in range(c1.PROFILE_CELLS)],
              "knots": [float(index) for index in range(-50, 51)], "sample_size": 25_000}
    values.update(changes)
    return values


def asymmetric_knots() -> list[float]:
    values = [float(index) for index in range(-50, 51)]
    values[-1] = 49.0
    return values


def payload(**changes):
    value = {
        "schema_version": art.SCHEMA_VERSION, "artifact_id": "artifact-1",
        "recipe_id": c1.CANDIDATE_NAME, "recipe_sha256": c1.RECIPE_SHA256,
        "symbol": "BTC/USDT", "venue": "BINANCE_PUBLIC", "timeframe": "1H",
        "horizon_bars": c1.HORIZON_BARS, "training_start_utc": "2024-01-01T00:00:00Z",
        "training_end_utc": "2024-06-01T00:00:00Z", "band_low": 0.01,
        "band_high": 0.03, "staleness_cap_days": 30, "fitted_at_utc": "2024-06-02T00:00:00Z",
        "fit_code_sha256": "1" * 64, "corpus_manifest_sha256": "2" * 64,
        "central_quantile": 0.8, "exposures": ["BTC/USDT"], "custody_location": "owner vault",
        "independent_copy": art.IndependentCopy.NONE_PENDING_OWNER_CUSTODY_RULING.value,
        "freeze_anchor_kind": art.AnchorKind.OWNER_APPROVED_ANCHOR.value,
        "freeze_anchor_ref": "owner-ref", "freeze_anchor_utc": "2024-06-03T00:00:00Z",
        "constants": {"candidate": c1.CANDIDATE_NAME, "recipe_sha256": c1.RECIPE_SHA256,
                      "cells": {"BTC/USDT": {"1H": cell("1H")}}},
    }
    value.update(changes)
    return value


def test_valid_manifest_loads() -> None:
    manifest = art.load_manifest(payload())
    assert manifest.artifact_id == "artifact-1"
    assert manifest.freeze_anchor_kind == art.AnchorKind.OWNER_APPROVED_ANCHOR
    with pytest.raises(TypeError):
        manifest.constants["other"] = 1
    payload_value = payload()
    loaded = art.load_manifest(payload_value)
    payload_value["constants"]["cells"]["BTC/USDT"]["1H"]["profile"][0] = -100
    assert loaded.constants["cells"]["BTC/USDT"]["1H"]["profile"][0] == 0.6
    with pytest.raises(TypeError):
        loaded.constants["cells"]["BTC/USDT"]["1H"]["sample_size"] = 1


def test_missing_key_names_field() -> None:
    value = payload()
    del value["artifact_id"]
    with pytest.raises(ValueError, match="artifact_id"):
        art.load_manifest(value)


@pytest.mark.parametrize("changes,field", [
    ({"schema_version": "wrong"}, "schema_version"),
    ({"artifact_id": None}, "artifact_id"),
    ({"extra": 1}, "unknown key"),
    ({"recipe_sha256": "0" * 64}, "recipe_sha256"),
    ({"recipe_id": "unknown"}, "recipe_id"),
    ({"horizon_bars": 5}, "horizon_bars"),
    ({"venue": "OTHER"}, "venue"),
    ({"venue": "OKX_PUBLIC"}, "venue"),
    ({"constants": {"candidate": c1.CANDIDATE_NAME,
                     "recipe_sha256": c1.RECIPE_SHA256,
                     "cells": {"ETH/USDT": {"1H": cell("1H")}}}}, "constants"),
    ({"fit_code_sha256": "A" * 64}, "fit_code_sha256"),
    ({"training_start_utc": "2024-01-01T00:00:00+00:00"}, "training_start_utc"),
    ({"training_start_utc": "2024-01-01T00:00:00"}, "training_start_utc"),
    ({"training_start_utc": "2024-07-01T00:00:00Z"}, "chronology"),
    ({"training_end_utc": "2024-06-03T00:00:00Z"}, "chronology"),
    ({"training_start_utc": "2024-06-01T00:00:00Z"}, "chronology"),
    ({"freeze_anchor_kind": "NONE", "freeze_anchor_ref": "local", "freeze_anchor_utc": None},
     "freeze_anchor_ref"),
    ({"freeze_anchor_kind": "REMOTE_COMMIT", "freeze_anchor_ref": None}, "freeze_anchor_ref"),
    ({"freeze_anchor_kind": "NONE", "freeze_anchor_ref": None,
      "freeze_anchor_utc": "2024-06-03T00:00:00Z"}, "freeze_anchor_utc"),
    ({"freeze_anchor_kind": "REMOTE_COMMIT", "freeze_anchor_utc": None}, "freeze_anchor_utc"),
    ({"freeze_anchor_kind": "LOCAL_SEAL"}, "freeze_anchor_kind"),
    ({"freeze_anchor_utc": "2024-06-01T00:00:00Z"}, "freeze_anchor_utc"),
    ({"band_high": 1}, "band_low/band_high"),
    ({"band_low": 0.04}, "band_low/band_high"),
    ({"band_low": True}, "band_low"),
    ({"band_low": 0.0}, "band_low"),
    ({"central_quantile": 0.5}, "central_quantile"),
    ({"central_quantile": 1}, "central_quantile"),
    ({"staleness_cap_days": True}, "staleness_cap_days"),
    ({"staleness_cap_days": 0}, "staleness_cap_days"),
    ({"staleness_cap_days": -1}, "staleness_cap_days"),
    ({"staleness_cap_days": 10**10}, "staleness_cap_days"),
    ({"exposures": [""]}, "exposures"),
    ({"exposures": ("BTC/USDT",)}, "exposures"),
    ({"exposures": "BTC/USDT"}, "exposures"),
    ({"custody_location": " "}, "custody_location"),
    ({"independent_copy": "UNKNOWN"}, "independent_copy"),
    ({"corpus_manifest_sha256": "bad"}, "corpus_manifest_sha256"),
    ({"constants": {"candidate": c1.CANDIDATE_NAME, "recipe_sha256": c1.RECIPE_SHA256,
                     "cells": {"BTC/USDT": {"1H": cell("1H", knots=asymmetric_knots())}}}},
     "constants"),
])
def test_invalid_manifest_values_are_refused(changes, field) -> None:
    with pytest.raises(ValueError) as exc:
        art.load_manifest(payload(**changes))
    if field:
        assert field in str(exc.value)


def test_artifact_status_order_and_boundaries() -> None:
    manifest = art.load_manifest(payload())
    fitted = datetime(2024, 6, 2, tzinfo=UTC)
    cap_end = manifest.training_end_utc + timedelta(days=30)
    common = dict(symbol="BTC/USDT", venue="BINANCE_PUBLIC", timeframe="1H", band_frac=0.01)
    assert art.artifact_status(manifest, now_utc=cap_end, **common) == art.ArtifactStatus.ELIGIBLE
    assert art.artifact_status(manifest, now_utc=cap_end + timedelta(seconds=1),
                               **common) == art.ArtifactStatus.ARTIFACT_STALE
    for band in (0.01, 0.03):
        assert art.artifact_status(manifest, now_utc=fitted, **{**common, "band_frac": band}) == (
            art.ArtifactStatus.ELIGIBLE)
    for band in (0.009999, 0.030001):
        assert art.artifact_status(manifest, now_utc=fitted, **{**common, "band_frac": band}) == (
            art.ArtifactStatus.BAND_OUT_OF_RANGE)
    assert art.artifact_status(manifest, now_utc=cap_end + timedelta(days=1), venue="OKX_PUBLIC",
                               symbol="BTC/USDT", timeframe="1H", band_frac=2) == (
            art.ArtifactStatus.CELL_MISMATCH)
    assert art.artifact_status(manifest, now_utc=cap_end + timedelta(days=1), band_frac=0.5,
                               symbol="BTC/USDT", venue="BINANCE_PUBLIC", timeframe="1H") == (
            art.ArtifactStatus.ARTIFACT_STALE)
    assert art.artifact_status(manifest, now_utc=fitted, band_frac=0.02,
                               symbol="ETH/USDT", venue="BINANCE_PUBLIC", timeframe="1H") == (
            art.ArtifactStatus.CELL_MISMATCH)
    assert art.artifact_status(manifest, now_utc=fitted, band_frac=0.02,
                               symbol="BTC/USDT", venue="BINANCE_PUBLIC", timeframe="15m") == (
            art.ArtifactStatus.CELL_MISMATCH)
    with pytest.raises(ValueError, match="precede"):
        art.artifact_status(manifest, now_utc=fitted - timedelta(seconds=1), **common)
    with pytest.raises(ValueError, match="UTC"):
        art.artifact_status(manifest, now_utc=datetime(2024, 6, 2), **common)
    for invalid in (True, "0.02", float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="band_frac"):
            art.artifact_status(manifest, now_utc=fitted, **{**common, "band_frac": invalid})
    with pytest.raises(ValueError, match="build manifests with load_manifest"):
        art.artifact_status(replace(manifest, _loaded=False), now_utc=fitted, **common)


def test_anchor_enums_and_boundaries_are_pinned() -> None:
    assert set(art.AnchorKind) == {art.AnchorKind.REMOTE_COMMIT,
                                   art.AnchorKind.OWNER_APPROVED_ANCHOR, art.AnchorKind.NONE}
    assert set(art.IndependentCopy) == {art.IndependentCopy.CONFIRMED,
                                       art.IndependentCopy.NONE_PENDING_OWNER_CUSTODY_RULING}
    value = payload(freeze_anchor_utc="2024-06-02T00:00:00Z")
    assert art.load_manifest(value).freeze_anchor_utc == datetime(2024, 6, 2, tzinfo=UTC)
    assert art.load_manifest(payload(training_end_utc="2024-06-02T00:00:00Z")).training_end_utc == (
        datetime(2024, 6, 2, tzinfo=UTC))
    with pytest.raises(ValueError, match="build manifests with load_manifest"):
        art.claim_ready(replace(art.load_manifest(payload()), _loaded=False))


def test_every_recipe_venue_is_a_known_venue() -> None:
    # The recipe binding makes the general allow-list redundant today (mutant M8 survives by
    # design); this invariant keeps it meaningful if a recipe ever names a venue.
    for _sha, _validator, _horizon, venues in art.RECIPES.values():
        assert set(venues) <= set(art.VENUES)


def test_full_width_digits_are_not_an_instant() -> None:
    with pytest.raises(ValueError, match="training_start_utc"):
        art.load_manifest(payload(training_start_utc="２０２４-01-01T00:00:00Z"))


@pytest.mark.parametrize("kind,ready", [(art.AnchorKind.NONE, False),
                                        (art.AnchorKind.REMOTE_COMMIT, True),
                                        (art.AnchorKind.OWNER_APPROVED_ANCHOR, True)])
def test_claim_ready_tracks_anchor_kind(kind, ready) -> None:
    value = payload(freeze_anchor_kind=kind.value)
    if kind == art.AnchorKind.NONE:
        value.update(freeze_anchor_ref=None, freeze_anchor_utc=None)
    assert art.claim_ready(art.load_manifest(value)) is ready
