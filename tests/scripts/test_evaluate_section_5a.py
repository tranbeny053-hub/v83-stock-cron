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
