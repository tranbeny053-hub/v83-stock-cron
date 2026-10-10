"""Linux's per-argument limit, applied on every platform.

Linux refuses any single command-line argument of 128 KiB or more with "Argument list too long";
macOS accepts it. CI runs on Linux, so a harness that hands node a large script in argv (`node -e`)
passes on a Mac and fails only in CI: #246's first CI run, where one script held the whole of app.js
and every case. A large script goes to node on stdin.

The same limit holds for each environment string and for a `shell=True` command, which the shell
receives as one argument.
"""

from __future__ import annotations

import errno
import os
import subprocess
from collections.abc import Iterator

import pytest

# MAX_ARG_STRLEN: 32 pages of 4 KiB. The terminating NUL counts, so the longest argument is one
# byte less.
LINUX_MAX_ARG_BYTES = 131072


@pytest.fixture(autouse=True, scope="module")
def linux_argument_limit() -> Iterator[None]:
    """Module-scoped, so it is in force before a module's own fixtures start a process."""

    real_init = subprocess.Popen.__init__

    def init(self, args, *rest, **kwargs) -> None:
        if isinstance(args, (str, bytes, os.PathLike)):
            strings = [os.fsencode(args)]
        else:
            if not isinstance(args, (list, tuple)):
                # Popen takes any iterable: read a one-shot one once, and hand the list on.
                args = list(args)
            strings = [os.fsencode(arg) for arg in args]
        if kwargs.get("shell"):
            program = "/bin/sh"
        else:
            program = os.fsdecode(strings[0]) if strings else ""
        # A child inherits this process's environment unless it is given its own.
        environment = os.environ if kwargs.get("env") is None else kwargs["env"]
        for key, value in environment.items():
            strings.append(os.fsencode(key) + b"=" + os.fsencode(value))
        if any(len(string) >= LINUX_MAX_ARG_BYTES for string in strings):
            raise OSError(errno.E2BIG, "Argument list too long", program)
        real_init(self, args, *rest, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess.Popen, "__init__", init)
        yield
