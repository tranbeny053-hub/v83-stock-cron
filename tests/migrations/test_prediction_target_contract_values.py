"""Migration 0011's literal values are the application's own. Normal CI only.

The venue labels its constraint accepts must be exactly the venues the resolver resolves on and the
writer records. Its target version, venue labels and column order must also be target contract
v1's (crypto_probability_engine.targets.contract_v1, merged with N1 in #131). These imports reach
far beyond the hash-locked runtime, so this file is deliberately NOT one of the dispatch job's
in-job tests.
"""

from __future__ import annotations

from crypto_probability_engine.adapters.provider_selection import DATA_SOURCE_BY_PROVIDER
from crypto_probability_engine.targets import contract_v1
from scripts import apply_migration_0011 as apply_0011
from scripts.resolve_outcomes import EXACT_SOURCE_PROVIDERS

VENUES = apply_0011.NEW_CONSTRAINTS["predictions_reference_venue_chk"][1]
TARGET_VERSIONS = apply_0011.NEW_CONSTRAINTS["predictions_target_version_chk"][1]


def test_the_venue_literals_are_the_resolver_s_and_the_writer_s_venues() -> None:
    assert VENUES == {"BINANCE_PUBLIC", "OKX_PUBLIC"}
    assert VENUES == set(EXACT_SOURCE_PROVIDERS)
    # The writer's mapping holds exactly the two public venues today, so nothing is filtered out.
    assert VENUES == set(DATA_SOURCE_BY_PROVIDER.values())
    assert dict(EXACT_SOURCE_PROVIDERS) == {
        venue: provider for provider, venue in DATA_SOURCE_BY_PROVIDER.items()
    }
    assert "CROSS_PROVIDER" not in VENUES, "a cross-provider row names no single venue"


def test_the_target_version_literal_is_the_only_version() -> None:
    assert TARGET_VERSIONS == {"tc-v1"}


def test_target_contract_v1_agrees_with_the_migration() -> None:
    assert contract_v1.TARGET_VERSION_V1 == "tc-v1"
    assert {contract_v1.TARGET_VERSION_V1} == TARGET_VERSIONS
    assert set(contract_v1.VENUE_LABELS.values()) == VENUES
    assert dict(contract_v1.VENUE_LABELS) == DATA_SOURCE_BY_PROVIDER
    assert tuple(contract_v1.STAMP_FIELDS) == apply_0011.NEW_COLUMN_NAMES
