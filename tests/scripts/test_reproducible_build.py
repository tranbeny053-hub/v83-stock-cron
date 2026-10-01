"""B3 (governing plan §11.1): the reproducible build's inputs are pinned; its proof is well formed.

The proof itself (two independent clean builds with identical manifest digests, then a fixture
smoke) runs in CI: .github/workflows/reproducible-build.yml. These tests pin what makes it possible
and keep the script's decision logic honest without Docker.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reproducible_build.sh"
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _name(requirement: str) -> str:
    return re.split(r"[\[<>=;\s]", requirement.strip(), maxsplit=1)[0].lower().replace("_", "-")


def test_the_base_image_is_pinned_by_digest_and_the_install_enforces_hashes() -> None:
    dockerfile = _text("Dockerfile")
    froms = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
    assert len(froms) == 1
    assert re.fullmatch(r"FROM python:3\.11-slim@sha256:[0-9a-f]{64}", froms[0])
    assert "ARG SOURCE_DATE_EPOCH" in dockerfile.splitlines()
    install = next(line for line in dockerfile.splitlines() if "pip install" in line)
    assert "--require-hashes" in install and "--no-cache-dir" in install
    # The hash seed is fixed for the install step only; the running app keeps hash randomization.
    assert install.startswith("RUN PYTHONHASHSEED=0 pip install ")
    code = [line for line in dockerfile.splitlines() if not line.startswith("#")]
    assert sum("PYTHONHASHSEED" in line for line in code) == 1
    assert "-r requirements.txt" in install


def test_the_image_takes_no_mutable_or_date_stamped_step() -> None:
    dockerfile = _text("Dockerfile")
    for forbidden in ("apt-get", "apk add", "adduser", "useradd", "curl ", "wget ", "ADD "):
        assert forbidden not in dockerfile, f"{forbidden!r} makes the build time-dependent"
    assert "USER 1000" in dockerfile.splitlines()
    assert "COPY . ." in (line.strip() for line in dockerfile.splitlines())


def test_the_lock_pins_every_package_by_version_and_hash() -> None:
    lock = _text("requirements.txt")
    header = lock.splitlines()[:2]
    assert "--generate-hashes" in header[1] and "--exclude-newer" in header[1]
    assert "--python-version 3.11" in header[1]
    blocks = re.split(r"\n(?=[A-Za-z0-9])", lock.split("\n", 2)[2])
    assert blocks, "the lock lists no package"
    for block in blocks:
        first = block.splitlines()[0]
        assert re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[^\s\\]+", first), first
        assert re.search(r"--hash=sha256:[0-9a-f]{64}", block), f"{first} has no sha256"


def test_every_top_level_dependency_is_in_the_lock() -> None:
    wanted = {_name(line) for line in _text("requirements.in").splitlines()
              if line.strip() and not line.lstrip().startswith("#")}
    locked = {_name(line) for line in _text("requirements.txt").splitlines()
              if re.match(r"^[A-Za-z0-9]", line)}
    assert wanted and wanted <= locked, sorted(wanted - locked)
    assert {"psycopg-binary", "psycopg-pool"} <= locked, "psycopg's extras are locked too"


def test_the_build_script_pins_buildkit_and_strips_every_time_dependent_output() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'moby/buildkit:v[\d.]+@sha256:[0-9a-f]{64}"', script)
    for required in ("--no-cache", "--pull", "--provenance=false", "--sbom=false",
                     "rewrite-timestamp=true", "--platform \"$PLATFORM\"", 'PLATFORM="linux/amd64"',
                     "git log -1 --format=%ct HEAD", "SOURCE_DATE_EPOCH=$epoch",
                     # a docker archive loads on either Docker image store and keeps index.json
                     "type=docker,dest=$out/image.tar"):
        assert required in script, required
    for push in ("docker push", "--push", "git push", "type=registry", "push=true"):
        assert push not in script, f"the proof never pushes anything ({push!r})"
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def _compare(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), "compare", *args], capture_output=True, text=True,
                          check=False)


def test_compare_passes_only_identical_well_formed_digests() -> None:
    same = _compare(DIGEST, DIGEST)
    assert same.returncode == 0 and "REPRODUCIBLE=PASS" in same.stdout
    different = _compare(DIGEST, OTHER)
    assert different.returncode == 1 and "REPRODUCIBLE=STOP" in different.stdout
    for bad in (("", ""), ("sha256:abc", "sha256:abc"), (DIGEST.upper(), DIGEST.upper())):
        assert _compare(*bad).returncode != 0, bad


def test_the_script_refuses_an_unknown_command() -> None:
    result = subprocess.run(["bash", str(SCRIPT), "deploy"], capture_output=True, text=True,
                            check=False)
    assert result.returncode == 2 and "usage" in result.stderr
