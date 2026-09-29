"""Migration 0012's literal values accept exactly what the resolver writes. Normal CI only.

The reason pattern must accept every reason key of the resolver, and the policy pattern every
rq-v<N> label. The resolver's reason maps (scripts.resolve_outcomes SKIP_REASONS and ERROR_REASONS,
merged with N2 in #132) are cross-checked exactly. These imports reach far beyond the hash-locked
runtime, so this file is deliberately NOT one of the dispatch job's in-job tests.

Python's re.fullmatch reads these two patterns exactly as PostgreSQL's ``~`` does: they use only
anchors, alternation, bracket classes and bounded repetition.
"""

from __future__ import annotations

import re

import pytest

from scripts import apply_migration_0012 as apply_0012
from scripts import resolve_outcomes

(REASON,) = apply_0012.EXPECTED_CONSTRAINTS["prs_reason_format"][2]
(POLICY,) = apply_0012.EXPECTED_CONSTRAINTS["prs_policy_version_format"][2]
STATUSES = apply_0012.EXPECTED_CONSTRAINTS["prs_status_valid"][2]
REASON_MAPS = ("SKIP_REASONS", "ERROR_REASONS")
# The resolver's reason keys (N2, #132). The maps must equal them exactly, so that a new key is
# reviewed here against the pattern before the resolver can write it.
RESOLVER_SKIP_REASONS = (
    "skip_ineligible",
    "skip_invalid_target",
    "skip_not_due",
    "skip_terminal_bar_missing",
)
RESOLVER_ERROR_REASONS = (
    "error_row_unreadable",
    "error_provider_rejected",
    "error_provider_unavailable",
    "error_candle_invalid",
    "error_save_not_ok",
    "error_save_exception",
    "error_outcome_conflict",
    "error_other",
)


@pytest.mark.parametrize("key", [*RESOLVER_SKIP_REASONS, *RESOLVER_ERROR_REASONS])
def test_the_reason_pattern_accepts_every_reason_key_of_the_resolver(key: str) -> None:
    assert re.fullmatch(REASON, key), key


def test_the_resolver_s_reason_maps_are_exactly_the_reviewed_keys() -> None:
    """Both maps are on this commit (N2), and each equals its reviewed tuple, in order."""

    assert [name for name in REASON_MAPS if hasattr(resolve_outcomes, name)] == list(REASON_MAPS)
    assert tuple(resolve_outcomes.SKIP_REASONS) == RESOLVER_SKIP_REASONS
    assert tuple(resolve_outcomes.ERROR_REASONS) == RESOLVER_ERROR_REASONS
    skip_keys = list(resolve_outcomes.SKIP_REASONS)
    error_keys = list(resolve_outcomes.ERROR_REASONS)
    assert skip_keys and error_keys
    for key in [*skip_keys, *error_keys]:
        assert isinstance(key, str) and re.fullmatch(REASON, key), key
    assert all(key.startswith("skip_") for key in skip_keys), skip_keys
    assert all(key.startswith("error_") for key in error_keys), error_keys


@pytest.mark.parametrize(
    "key",
    ["failed_x", "skip_", "SKIP_X", "error_x-y", "error_" + "x" * 59, "skip_x\n", ""],
    ids=["other-prefix", "bare-prefix", "uppercase", "hyphen", "65-characters", "newline", "empty"],
)
def test_the_reason_pattern_rejects_what_is_not_a_reason_key(key: str) -> None:
    assert re.fullmatch(REASON, key) is None, key


def test_the_longest_reason_key_is_64_characters() -> None:
    longest = "error_" + "x" * 58
    assert len(longest) == 64 and re.fullmatch(REASON, longest)
    assert re.fullmatch(REASON, "skip_" + "x" * 58)
    assert re.fullmatch(REASON, "skip_" + "x" * 59) is None


@pytest.mark.parametrize("label", ["rq-v1", "rq-v2", "rq-v12", "rq-v100"])
def test_the_policy_pattern_accepts_every_rq_label(label: str) -> None:
    assert re.fullmatch(POLICY, label), label


@pytest.mark.parametrize("label", ["rq-v0", "rq-1", "rq-v01", "rq-v", "RQ-V1", "rq-v1\n"])
def test_the_policy_pattern_rejects_what_is_not_an_rq_label(label: str) -> None:
    assert re.fullmatch(POLICY, label) is None, label


def test_the_statuses_are_exactly_the_three_of_rq_v1() -> None:
    assert STATUSES == {"RETRYABLE", "QUARANTINED", "RESOLVED"}
    assert apply_0012.EXPECTED_CONSTRAINTS["prs_state_shape"][2] == STATUSES
    assert apply_0012.EXPECTED_INDEXES["prediction_resolution_status_retry_idx"][2] == {
        "RETRYABLE"
    }
