"""conftest.py applies Linux's per-argument limit to every frontend test, on every platform.

Without it a harness that hands node a large script in argv passes on a Mac and fails only in CI.
On Linux the kernel refuses the same calls, so these tests pass there with or without the fixture.
"""

from __future__ import annotations

import errno
import subprocess
import sys

import pytest

LINUX_MAX_ARG_BYTES = 131072
_NOTHING = [sys.executable, "-c", "pass"]


def _run_with_argument_of(size: int) -> None:
    subprocess.run([*_NOTHING, "x" * size], check=True)  # noqa: S603


def _run_with_environment_string_of(size: int) -> None:
    # The shell needs no environment of its own, so the probe is the only string: no real variable
    # can reach a failure's output.
    value = "x" * (size - len("LIMIT_PROBE="))
    subprocess.run(["/bin/sh", "-c", ":"], env={"LIMIT_PROBE": value}, check=True)  # noqa: S603


def _run_with_inherited_environment_string_of(size: int) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIMIT_PROBE", "x" * (size - len("LIMIT_PROBE=")))
        subprocess.run(["/bin/sh", "-c", ":"], check=True)  # noqa: S603


def _run_shell_command_of(size: int) -> None:
    # ":" is the shell's no-op; the rest is its ignored argument.
    subprocess.run(": " + "x" * (size - len(": ")), shell=True, check=True)  # noqa: S602


@pytest.fixture(scope="module")
def refused_inside_a_module_fixture() -> bool:
    """The rendering harnesses start node from a module-scoped fixture; the limit holds there."""

    try:
        _run_with_argument_of(LINUX_MAX_ARG_BYTES)
    except OSError as error:
        return error.errno == errno.E2BIG
    return False


_PROBES = [
    _run_with_argument_of,
    _run_with_environment_string_of,
    _run_with_inherited_environment_string_of,
    _run_shell_command_of,
]


@pytest.mark.parametrize("run", _PROBES)
def test_a_string_at_the_limit_is_refused_as_linux_refuses_it(run) -> None:
    with pytest.raises(OSError) as refused:
        run(LINUX_MAX_ARG_BYTES)
    assert refused.value.errno == errno.E2BIG
    assert len(str(refused.value)) < 1000, "the error names the program, never the string"


@pytest.mark.parametrize("run", _PROBES)
def test_a_string_one_byte_under_the_limit_runs(run) -> None:
    run(LINUX_MAX_ARG_BYTES - 1)


def test_the_limit_holds_inside_a_module_scoped_fixture(
    refused_inside_a_module_fixture: bool,
) -> None:
    assert refused_inside_a_module_fixture


def test_a_multibyte_argument_is_measured_in_bytes() -> None:
    # "§" is two bytes in UTF-8: half the limit in characters is the whole limit in bytes.
    with pytest.raises(OSError) as refused:
        subprocess.run([*_NOTHING, "§" * (LINUX_MAX_ARG_BYTES // 2)], check=True)  # noqa: S603
    assert refused.value.errno == errno.E2BIG


def test_the_caller_sees_its_own_arguments() -> None:
    as_tuple = tuple(_NOTHING)
    assert subprocess.run(as_tuple, check=True).args is as_tuple  # noqa: S603
    # A one-shot iterable is read once and still runs.
    subprocess.run(iter(_NOTHING), check=True)  # noqa: S603
