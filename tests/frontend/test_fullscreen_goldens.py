"""The whole-screen regression pins (fullscreen_goldens.py): every screen, line by line and in
order, is exactly its committed golden.

The other frontend tests assert phrases and membership. These pins catch what those cannot: a line
that moved, a line that was added, a line that changed anywhere on a screen. They are regression
detectors, not acceptance: a golden records a screen as it is.

When a screen is meant to change, regenerate the goldens and review the diff:

    PYTHONPATH=src:. .venv/bin/python -m tests.frontend.fullscreen_goldens --write
"""

from __future__ import annotations

import copy
import difflib
import itertools
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import fullscreen_goldens as goldens
import pytest

from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.features import volatility
from crypto_probability_engine.quant import probability_three_state, tail_cvar
from tests.fixtures.market_data import FIXED_NOW

ROOT = Path(__file__).resolve().parents[2]
harness = goldens.harness

# scenario -> (gate action, hard blocks, decision-view state, storage at request time)
_EVIDENCE = "SKILL_NOT_DEMONSTRATED"
SCENARIOS = {
    "evidence_only": ("NO_TRADE", [_EVIDENCE], "NO_ACCEPTED_CLAIM", "STATELESS"),
    "risk_and_evidence": (
        "NO_TRADE",
        ["TAIL_RISK_BREACH", _EVIDENCE],
        "NO_ACCEPTED_CLAIM",
        "STATELESS",
    ),
    "wide_spread_and_evidence": (
        "NO_TRADE",
        ["EXECUTION_COST_TOO_HIGH", "LIQUIDITY_NOT_VIABLE", _EVIDENCE],
        "NO_ACCEPTED_CLAIM",
        "STATELESS",
    ),
    "missing_order_book_and_evidence": (
        "NO_TRADE",
        ["LIQUIDITY_NOT_VIABLE", _EVIDENCE],
        "NO_ACCEPTED_CLAIM",
        "STATELESS",
    ),
    "kill_switch_and_evidence": (
        "ABORT",
        ["KILL_SWITCH", _EVIDENCE],
        "NO_ACCEPTED_CLAIM",
        "STATELESS",
    ),
    "storage_OK": ("NO_TRADE", [_EVIDENCE], "NO_ACCEPTED_CLAIM", "OK"),
    "storage_UNAVAILABLE": ("NO_TRADE", [_EVIDENCE], "NO_ACCEPTED_CLAIM", "UNAVAILABLE"),
    "storage_STATELESS": ("NO_TRADE", [_EVIDENCE], "NO_ACCEPTED_CLAIM", "STATELESS"),
    "risk_only_SYNTHETIC": ("NO_TRADE", ["TAIL_RISK_BREACH"], "NO_ACCEPTED_CLAIM", "STATELESS"),
    "missing_order_book_only_SYNTHETIC": (
        "NO_TRADE",
        ["LIQUIDITY_NOT_VIABLE"],
        "NO_ACCEPTED_CLAIM",
        "STATELESS",
    ),
    "system_only_SYNTHETIC": ("ABORT", ["KILL_SWITCH"], "NO_ACCEPTED_CLAIM", "STATELESS"),
    "first_check_blocks_SYNTHETIC": ("NO_TRADE", [_EVIDENCE], "NO_ACCEPTED_CLAIM", "STATELESS"),
    "accepted_claim_SYNTHETIC": (
        "NO_TRADE",
        [_EVIDENCE],
        "ACCEPTED_FORECAST_CLAIM",
        "STATELESS",
    ),
    "permission_SYNTHETIC": ("WATCH", [], "DIRECTIONAL_PERMISSION", "STATELESS"),
}
HISTORY = (
    "evidence_only",
    "risk_and_evidence",
    "wide_spread_and_evidence",
    "missing_order_book_and_evidence",
    "kill_switch_and_evidence",
    "storage_OK",
    "risk_only_SYNTHETIC",
    "missing_order_book_only_SYNTHETIC",
    "system_only_SYNTHETIC",
)
# Pinned as a saved run only (the evidence-only analysis as an older run stores it).
SAVED_BEFORE = "saved_before_this_change"
FILES = len(SCENARIOS) * 3 + len(HISTORY) + 1


def _explain(found: list[str]) -> str:
    return "\n".join(
        [
            "the committed whole-screen goldens are not what the screens render now:",
            *found,
            "If the change is intended, regenerate them and review the diff:",
            f"    {goldens.REGENERATE}",
        ]
    )


def _first_difference(name: str, committed: str, built: str) -> str:
    diff = difflib.unified_diff(
        committed.split("\n"),
        built.split("\n"),
        f"committed/{name}",
        f"rendered/{name}",
        lineterm="",
        n=1,
    )
    return "\n".join(list(diff)[:40])


def _assert_pinned(built: dict[str, str], directory: Path = goldens.GOLDENS) -> None:
    """The pin itself: a directory holds exactly the files the screens render, byte for byte."""

    committed = goldens.committed(directory)
    found = goldens.differences(built, directory)
    shown = [
        _first_difference(name, committed[name], built[name])
        for name in sorted(built.keys() & committed.keys())
        if built[name] != committed[name]
    ][:3]
    assert found == [], _explain([*found, *shown])
    assert committed == built


@pytest.fixture(scope="module")
def cases() -> dict[str, dict]:
    return goldens.build_cases()


@pytest.fixture(scope="module")
def reopened(cases: dict[str, dict]) -> dict[str, dict]:
    return goldens.build_reopened(cases)


@pytest.fixture(scope="module")
def rendered(cases: dict[str, dict], reopened: dict[str, dict]) -> dict[str, dict]:
    return goldens.render(cases, reopened)


@pytest.fixture(scope="module")
def raw(rendered: dict[str, dict]) -> dict[str, dict[str, list[str]]]:
    """One build: every screen, nothing normalized."""

    return rendered["screens"]


@pytest.fixture(scope="module")
def built(raw: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    return goldens.golden_files(raw)


def test_the_committed_goldens_are_exactly_what_the_builder_produces(built: dict) -> None:
    _assert_pinned(built)


def test_every_scenario_and_surface_has_a_golden_and_no_file_is_stray(raw: dict) -> None:
    # The builder's tables are the ones listed here: a scenario cannot be dropped in one place.
    assert list(goldens.SCENARIOS) == list(SCENARIOS)
    assert goldens.HISTORY == HISTORY
    assert goldens.SURFACES == ("single", "batch", "detail")
    assert goldens.SAVED_BEFORE == SAVED_BEFORE
    expected = goldens.expected_names()
    # 14 scenarios on 3 surfaces, 9 of them as a saved run read back, and one older saved run.
    assert len(expected) == len(set(expected)) == 14 * 3 + 9 + 1 == FILES == 52
    for scenario in SCENARIOS:
        surfaces = (*goldens.SURFACES, *(("history",) if scenario in HISTORY else ()))
        assert list(raw[scenario]) == list(surfaces), scenario
        for surface in surfaces:
            assert f"{scenario}.{surface}.txt" in expected, (scenario, surface)
            assert raw[scenario][surface], f"{scenario}.{surface}: an empty screen"
    assert list(raw[SAVED_BEFORE]) == ["history"] and raw[SAVED_BEFORE]["history"]
    assert sorted(raw) == sorted([*SCENARIOS, SAVED_BEFORE]), "exactly these scenarios"
    present = sorted(path.name for path in goldens.GOLDENS.iterdir())
    missing, stray = sorted(set(expected) - set(present)), sorted(set(present) - set(expected))
    assert not missing and not stray, _explain(
        [*(f"missing: {name}" for name in missing), *(f"stray: {name}" for name in stray)]
    )


def test_the_scenarios_are_what_their_names_say(cases: dict[str, dict]) -> None:
    assert list(cases) == list(SCENARIOS)
    for name, (action, blocks, state, storage) in SCENARIOS.items():
        payload = cases[name]
        assert payload["gate_result"]["action"] == action, name
        assert payload["gate_result"]["hard_blocks"] == blocks, name
        assert payload["frontend_display"]["disposition"] == action, name
        assert payload["decision_view"]["state"] == state, name
        assert payload["debug"]["persistence_status"] == storage, name
        timeframe = "1W" if name == "permission_SYNTHETIC" else "1H"
        assert payload["timeframes"]["primary"] == timeframe, name
        assert payload["normalized_symbol"] == "BTC/USDT", name
    # The order book each scenario names: none at all, or one whose spread is measured.
    for name in SCENARIOS:
        liquidity = cases[name]["liquidity_state"]
        if name.startswith("missing_order_book"):
            assert liquidity["status"] == "DEGRADED" and liquidity["spread_frac"] is None, name
            assert liquidity["warning"] == "Order book unavailable.", name
        else:
            assert liquidity["status"] == "OK", name
            wide = liquidity["spread_frac"] > 0.01
            assert wide is (name == "wide_spread_and_evidence"), name
    # SYNTHETIC means what it says: the registries the harness patched are empty again, and the
    # evidence gate blocks every analysis that is not named SYNTHETIC.
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()
    assert len(decision_view.ACCEPTANCE_BLOCKERS) == 4
    for name, (_, blocks, _, _) in SCENARIOS.items():
        assert name.endswith("_SYNTHETIC") or _EVIDENCE in blocks, name


def test_two_builds_in_a_row_are_identical(raw: dict, built: dict) -> None:
    """New analyses, and app.js told another time (a year on) in another time zone: the same
    goldens, byte for byte."""

    again = goldens.render_screens(clock=FIXED_NOW + timedelta(days=366), zone="Pacific/Kiritimati")
    assert again != raw, "every build draws new run ids: without normalizing, no two are equal"
    assert goldens.golden_files(again) == built


def _case(cases: dict[str, dict], scenario: str) -> dict:
    """The analysis a scenario's screens show: the older saved run is the evidence-only one."""

    return cases["evidence_only" if scenario == SAVED_BEFORE else scenario]


def _run_ids(payloads: dict[str, dict]) -> set[str]:
    return {payload["run_id"] for payload in payloads.values()}


def _wording(text: str, run_ids: set[str]) -> str:
    """A text without its run ids and without its digits: what normalizing must never touch."""

    for run_id in run_ids:
        text = text.replace(run_id, "")
    text = text.replace(goldens.RUN_ID_PLACEHOLDER, "")
    return re.sub(rf"[\d{goldens.ROUNDED_MARK}]", "", text)


def _has_long_decimal(text: str) -> bool:
    return any(
        len(number.replace(".", "").lstrip("0")) > goldens.SIGNIFICANT_DIGITS
        for number in re.findall(r"\d+\.\d+", text)
    )


def test_only_run_ids_and_long_decimals_are_normalized(cases: dict, raw: dict) -> None:
    """No wording is normalized away. Beside the run ids the backend gave these very analyses,
    a normalized text differs from the rendered one in digits only, and only where a decimal has
    more than twelve significant digits."""

    run_ids = _run_ids(cases)
    assert len(run_ids) == len(cases), "every analysis has a run id of its own"
    changed = long_decimals = 0
    for scenario, surfaces in raw.items():
        for surface, texts in surfaces.items():
            for text in texts:
                stable = goldens.normalize(text)
                assert _wording(stable, run_ids) == _wording(text, run_ids), (scenario, surface)
                assert not any(run_id in stable for run_id in run_ids), (scenario, surface)
                if stable == text:
                    continue
                changed += 1
                has_run_id = any(run_id in text for run_id in run_ids)
                assert has_run_id or _has_long_decimal(text), (scenario, surface, text)
                long_decimals += _has_long_decimal(text)
    assert changed and long_decimals
    # Every panel prints its run id once, and the golden prints the placeholder in its place.
    for scenario, surfaces in raw.items():
        for surface in set(surfaces) & {"detail", "history"}:
            texts = [goldens.normalize(text) for text in surfaces[surface]]
            assert texts.count(goldens.RUN_ID_PLACEHOLDER) == 1, (scenario, surface)
            assert _case(cases, scenario)["run_id"] in surfaces[surface], (scenario, surface)


def test_normalizing_is_exactly_these_two_rules() -> None:
    run_id = "run_" + "0123456789abcdef" * 2
    assert goldens.normalize(run_id) == "run_<RUN_ID>"
    assert goldens.normalize(f'"run_id": "{run_id}",') == '"run_id": "run_<RUN_ID>",'
    assert goldens.normalize("run_" + "g" * 32) == "run_" + "g" * 32, "not a run id"
    assert goldens.normalize("run_0123") == "run_0123", "not a run id"
    # More than twelve significant digits: rounded to twelve, and marked.
    assert goldens.normalize("0.00004973774149870241") == "0.0000497377414987…"
    assert goldens.normalize('"arbiter_value": -0.0033261537715641495') == (
        '"arbiter_value": -0.00332615377156…'
    )
    assert goldens.normalize("1.0087609511889863,") == "1.00876095119…,"
    assert goldens.normalize("4.973774149870241e-05") == "4.97377414987…e-05"
    # Twelve or fewer: untouched, whatever is around them.
    for text in (
        "22.12% (band ±0.41%)",
        "Directional edge is 0.008824 from existing probability values.",
        "0.123456789012",
        "99999999999.5",
        "2026-06-06T12:00:00Z",
        "1234567890123456789",
        "sha256:" + "0123456789abcdef" * 4,
        "v1.2.3",
    ):
        assert goldens.normalize(text) == text, text
    # Wording is never touched.
    sentence = "No forecast-quality claim has been accepted for this model and timeframe."
    assert goldens.normalize(sentence) == sentence


def _another_platform(function: Callable[[float], float], calls: list[int]) -> Callable:
    """`function` as another platform's maths library may compute it: each result moved by up to
    two units in the last place, in a fixed pattern (-2, -1, 0, 1, 2, ...)."""

    steps = itertools.cycle((-2, -1, 0, 1, 2))

    def moved(value: float) -> float:
        calls[0] += 1
        result, step = function(value), next(steps)
        for _ in range(abs(step)):
            result = math.nextafter(result, math.copysign(math.inf, step))
        return result

    return moved


def test_a_last_digit_of_the_platforms_maths_does_not_change_a_golden(
    cases: dict, raw: dict, built: dict
) -> None:
    """CI and a developer's machine do not share a maths library, and a library's log and tanh
    are not rounded the same everywhere. Every such call of the analysis is moved here by a unit
    or two in the last place: the screens then print other last digits (realized volatility
    does), and the goldens are the same, byte for byte. So the percentages do not sit on a
    rounding boundary, and twelve significant digits are enough."""

    logs, tanhs = [0], [0]
    with pytest.MonkeyPatch.context() as patch:
        # The three calls of the platform's library on the path of an analysis.
        patch.setattr(volatility, "log", _another_platform(math.log, logs))
        patch.setattr(tail_cvar, "log", _another_platform(math.log, logs))
        patch.setattr(probability_three_state, "tanh", _another_platform(math.tanh, tanhs))
        moved_cases = goldens.build_cases()
        moved = goldens.render(moved_cases, goldens.build_reopened(moved_cases))["screens"]
    assert logs[0] > 200 * len(cases) and tanhs[0] >= len(cases), "the analysis calls them"

    differing = []
    for scenario, surfaces in raw.items():
        for surface, texts in surfaces.items():
            pairs = list(zip(texts, moved[scenario][surface], strict=True))
            differing += [
                (was, now)
                for was, now in pairs
                if goldens.RUN_ID.sub("", was) != goldens.RUN_ID.sub("", now)
            ]
    assert differing, "a moved last digit reaches a screen: this is why decimals are normalized"
    assert all(_has_long_decimal(was) and _has_long_decimal(now) for was, now in differing)
    assert any("realized_vol" in was for was, _ in differing)
    assert goldens.golden_files(moved) == built, (
        "a golden depends on the last digits of the platform's maths library: it would differ "
        "between machines"
    )


_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[0-9T:.Z+-]*")
_HASH = re.compile(r"[0-9a-f]{32,}")


def test_every_time_on_a_screen_is_the_fixtures_and_no_screen_prints_a_hash(
    cases: dict, raw: dict
) -> None:
    fixed = FIXED_NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    for scenario, surfaces in raw.items():
        case = _case(cases, scenario)
        time = case["decision_view"]["time"]
        assert time["as_of_utc"] == time["reference_close_utc"] == fixed, scenario
        assert case["as_of_utc"] == fixed, scenario
        allowed = {fixed, time["horizon_end_utc"]}
        for surface, texts in surfaces.items():
            shown = {found for text in texts for found in _TIME.findall(text)}
            assert shown and shown <= allowed, (scenario, surface, shown - allowed)
            for text in texts:
                assert not _HASH.search(goldens.RUN_ID.sub("", text)), (scenario, surface, text)
                assert case["analysis_hash"] not in text, (scenario, surface)


def test_app_js_is_told_the_time_and_locale_text_cannot_reach_a_golden(cases: dict) -> None:
    """The clock app.js reads is the fixture's, and text formatted for the machine's locale (its
    wording differs between machines and versions of node) is marked, then refused."""

    probe = """
    const formatters = typeof Intl === "object" ? [Intl.NumberFormat, Intl.DateTimeFormat] : [];
    process.stdout.write(JSON.stringify([
      Date.now(), new Date().toISOString(), new Date(0).toISOString(),
      new Date("2026-06-06T12:00:00Z").getTime() === Date.now(),
      new Date().toLocaleString(), new Date().toLocaleDateString(),
      new Date().toLocaleTimeString(), (1234.5).toLocaleString(),
      ...formatters.map((Formatter) => new Formatter().format(1234.5)),
    ]));
    """
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [harness.NODE, "-"],
        input=goldens.frozen_clock(FIXED_NOW) + probe,
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    now, iso, epoch, parsed, *formatted = json.loads(done.stdout)
    assert now == int(FIXED_NOW.timestamp() * 1000)
    assert iso == "2026-06-06T12:00:00.000Z" and epoch == "1970-01-01T00:00:00.000Z"
    assert parsed is True, "a given time is still that time"
    assert len(formatted) >= 4 and set(formatted) == {goldens.LOCALE_MARK}

    # A screen that carries the mark is refused, never written to a golden.
    marked = copy.deepcopy(cases["evidence_only"])
    marked["normalized_symbol"] = f"BTC {goldens.LOCALE_MARK}"
    with pytest.raises(RuntimeError, match="formatted for the machine's locale"):
        goldens.render({"evidence_only": marked}, {})


def test_the_storage_rows_are_what_storage_said_at_request_time(raw: dict, built: dict) -> None:
    """No save receipt is answered in a golden. The three storage scenarios differ from each
    other in the storage rows only, and a panel whose requests have settled reads as the cards
    do, which are read the moment they are made: the row was never replaced."""

    said: dict[str, set[str]] = {status: set() for status in goldens.STORAGE_STATUSES}
    for surface, rows in (("single", 1), ("batch", 1), ("detail", 2)):
        screens = [raw[f"storage_{status}"][surface] for status in goldens.STORAGE_STATUSES]
        assert len({len(screen) for screen in screens}) == 1, surface
        differing = [
            index
            for index, texts in enumerate(zip(*screens, strict=True))
            if len({goldens.RUN_ID.sub("", text) for text in texts}) > 1
        ]
        assert len(differing) == rows, f"{surface}: only the storage rows differ"
        for status, screen in zip(goldens.STORAGE_STATUSES, screens, strict=True):
            said[status] |= {screen[index] for index in differing}
    # One text per status, the same on every surface, and no two statuses read alike.
    assert all(len(texts) == 1 for texts in said.values()), said
    assert len(set().union(*said.values())) == len(goldens.STORAGE_STATUSES)
    # The analysis function's own default is STATELESS: the first scenario is that analysis.
    for surface in goldens.SURFACES:
        assert built[f"storage_STATELESS.{surface}.txt"] == built[f"evidence_only.{surface}.txt"]
    # A saved run read back states the same thing storage said when it was asked.
    (available,) = said["OK"]
    assert raw["storage_OK"]["history"].count(available) == 1


def test_the_one_block_the_goldens_leave_out_is_the_payload_verbatim(
    cases: dict, reopened: dict, rendered: dict
) -> None:
    """The Raw JSON block prints run ids, hashes and every float in full, so it is not pinned.
    It is exactly its heading and the payload the panel was given: nothing else is left out.
    The detail the panel renders beside the payload carries the read-time view of a saved run,
    with its gate view, and none of that is copied into the block (review finding D4): a live
    analysis prints the backend's own response, and a saved run prints its history row."""

    details = goldens.live_details(cases)
    for scenario, payload in cases.items():
        read = details[scenario]["saved_run_view"]
        assert read["schema_version"] == "saved_run_view.v1", scenario
        # The same gate authority; only an accepted state (SYNTHETIC) frames its gates in words
        # of its own, and a saved run has no state.
        gates = payload["decision_view"]["gates"]
        accepted = payload["decision_view"]["accepted_claim"]
        assert {**read["gates"], "framing": ""} == {**gates, "framing": ""}, scenario
        assert (read["gates"]["framing"] == gates["framing"]) is not accepted, scenario
        for key in ("saved_run_view", "gate_view"):
            assert key not in payload and key not in payload["detail_view"], (scenario, key)
    blocks = 0
    for scenario, surfaces in rendered["raw_json"].items():
        for surface, found in surfaces.items():
            given = cases[scenario] if surface == "detail" else reopened[scenario]["row"]
            ((heading, body),) = found
            assert heading == rendered["screens"][scenario][surface][-1], (scenario, surface)
            assert json.loads(body) == given, (scenario, surface)
            assert list(json.loads(body)) == list(given), "the payload's own keys, in order"
            assert '"gate_view"' not in body and '"saved_run_view"' not in body, scenario
            assert body not in rendered["screens"][scenario][surface], (scenario, surface)
            blocks += 1
    assert blocks == len(SCENARIOS) + len(HISTORY) + 1


def test_a_golden_file_reads_back_as_the_screen(raw: dict) -> None:
    several_lines = 0
    for surfaces in raw.values():
        for texts in surfaces.values():
            assert goldens.decode(goldens.encode(texts)) == texts
            several_lines += sum("\n" in text for text in texts)
    assert several_lines, "a View block prints JSON on several lines"
    assert goldens.encode(["one", '{\n  "a": 1\n}', "two"]) == 'one\n{\n  |   "a": 1\n  | }\ntwo\n'
    assert goldens.decode('one\n{\n  |   "a": 1\n  | }\ntwo\n') == ["one", '{\n  "a": 1\n}', "two"]
    assert goldens.encode([]) == "" and goldens.decode("") == []
    # A text is trimmed by the renderer, so none starts with the mark; one that did is refused.
    with pytest.raises(ValueError, match="continuation"):
        goldens.encode(["first", goldens.CONTINUATION + "not a continuation"])


def test_the_builder_reports_missing_stray_and_stale_files(tmp_path: Path, built: dict) -> None:
    directory = tmp_path / "fullscreen"
    assert len(goldens.differences(built, directory)) == len(built), "nothing is written yet"
    goldens.write(built, directory)
    assert goldens.differences(built, directory) == []
    assert goldens.committed(directory) == built
    (directory / "evidence_only.single.txt").write_text("BLOCK\n", encoding="utf-8")
    (directory / "evidence_only.batch.txt").unlink()
    (directory / "left_over.detail.txt").write_text("x\n", encoding="utf-8")
    assert goldens.differences(built, directory) == [
        "missing: evidence_only.batch.txt",
        "stray: left_over.detail.txt",
        "stale: evidence_only.single.txt",
    ]
    goldens.write(built, directory)
    assert goldens.differences(built, directory) == []
    assert not (directory / "left_over.detail.txt").exists()


@pytest.mark.parametrize("name", ["evidence_only.single.txt", "risk_and_evidence.history.txt"])
def test_a_reordered_line_and_an_added_line_each_fail_the_pin(
    tmp_path: Path, built: dict, name: str
) -> None:
    """What a test of phrases and membership lets through, and the pin does not: the comparison
    is of the whole screen, in order. The failure names the command that regenerates."""

    goldens.write(built, tmp_path)
    _assert_pinned(built, tmp_path)
    lines = goldens.decode(built[name])
    middle = len(lines) // 2
    assert lines[middle] != lines[middle + 1]
    changes = {
        "reordered": [*lines[:middle], lines[middle + 1], lines[middle], *lines[middle + 2 :]],
        "added": [*lines[:middle], "One more line.", *lines[middle:]],
        "added last": [*lines, "One more line."],
        "removed": [*lines[:middle], *lines[middle + 1 :]],
        "reworded": [*lines[:middle], lines[middle] + "!", *lines[middle + 1 :]],
    }
    assert sorted(changes["reordered"]) == sorted(lines), "membership cannot tell them apart"
    assert set(lines) <= set(changes["added"]), "every phrase is still there"
    for change, screen in changes.items():
        now = {**built, name: goldens.encode(screen)}
        assert goldens.differences(now, tmp_path) == [f"stale: {name}"], change
        with pytest.raises(AssertionError) as failure:
            _assert_pinned(now, tmp_path)
        message = str(failure.value)
        assert goldens.REGENERATE in message and f"stale: {name}" in message, change
        assert f"committed/{name}" in message, f"{change}: the difference is shown"


def test_the_check_command_fails_on_a_stale_golden_and_names_the_regenerate_command(
    tmp_path: Path, built: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "fullscreen"
    goldens.write(
        {**built, "evidence_only.single.txt": built["evidence_only.batch.txt"]}, directory
    )
    (directory / "left_over.detail.txt").write_text("x\n", encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(goldens, "build", lambda: built)  # the screens of this very build
        assert goldens.main(["--check"], directory=directory) == 1
        failed = capsys.readouterr()
        assert "stale: evidence_only.single.txt" in failed.err
        assert "stray: left_over.detail.txt" in failed.err
        assert goldens.REGENERATE in failed.err
        assert goldens.main(["--write"], directory=directory) == 0
        assert goldens.main(["--check"], directory=directory) == 0
        assert f"is current ({FILES} files)" in capsys.readouterr().out
    assert goldens.committed(directory) == built
    with pytest.raises(SystemExit):
        goldens.main([])  # neither --write nor --check: nothing is built, nothing is written
    assert "--write" in capsys.readouterr().err


def test_the_documented_check_command_passes_on_this_tree() -> None:
    done = subprocess.run(  # noqa: S603 - this interpreter on this repository's own module
        [sys.executable, "-m", "tests.frontend.fullscreen_goldens", "--check"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(["src", "."])},
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, _explain([done.stdout, done.stderr])
    assert f"is current ({FILES} files)" in done.stdout
