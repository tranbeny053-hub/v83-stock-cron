"""The section 5A evaluation CLI. Parsing only; nothing is executed."""

from __future__ import annotations

import pytest

from crypto_probability_engine.oos.evaluation import runner
from scripts import evaluate_section_5a as cli


def test_default_mode_is_readiness_not_consume() -> None:
    """The safe mode is the one you get by forgetting to choose."""

    args = cli.build_parser().parse_args([])
    assert args.mode == runner.MODE_READINESS
    assert args.confirm == ""


def test_consume_requires_an_explicit_mode_and_token() -> None:
    args = cli.build_parser().parse_args(
        ["--mode", "consume", "--confirm", runner.CONFIRMATION_TOKEN]
    )
    assert args.mode == runner.MODE_CONSUME
    assert args.confirm == runner.CONFIRMATION_TOKEN


def test_recompute_mode_is_available_for_the_sealed_no_result_state() -> None:
    assert cli.build_parser().parse_args(["--mode", "recompute"]).mode == "recompute"


def test_cli_rejects_an_unknown_mode() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--mode", "definitely-not-a-mode"])


def test_recovery_modes_are_available() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["--mode", "recompute"]).mode == "recompute"
    assert parser.parse_args(["--mode", "recompute-artifact"]).mode == "recompute-artifact"


def test_the_cli_requires_a_positive_durable_postgres_declaration() -> None:
    """G8. build_operator_repository silently falls back to in-memory without a database URL;
    a missing secret must refuse rather than seal process-locally."""

    from crypto_probability_engine.persistence import repository as module

    with pytest.raises(runner.ConsumptionRefused, match="not a durable Postgres authority"):
        cli.require_durable_authority(module.InMemoryPersistenceRepository())
    rest = module.SupabaseRestRepository.__new__(module.SupabaseRestRepository)
    with pytest.raises(runner.ConsumptionRefused, match="SUPABASE_DB_URL"):
        cli.require_durable_authority(rest)
    cli.require_durable_authority(
        module.SupabasePersistenceRepository("postgresql://never-connected")
    )


def test_consume_without_a_database_refuses_before_any_read(monkeypatch) -> None:
    """End to end through main(): no SUPABASE_DB_URL means in-memory, which must refuse."""

    for name in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(runner.ConsumptionRefused, match="not a durable Postgres authority"):
        cli.main(["--mode", "consume", "--confirm", runner.CONFIRMATION_TOKEN])
