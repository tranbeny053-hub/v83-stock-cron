from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from scripts import quant_ng_object_name as names

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/quant_ng_object_name.py"
ROOT = Path(__file__).resolve().parents[2]


def test_known_answers() -> None:
    assert (
        names.encode_digest("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        == "ujrgskkipovshshkpqvrvksoppmvrpikinqukhukmkprpjksqkplpphrnoliroll"
    )
    assert names.encode_digest("0" * 64) == "g" * 64
    assert names.encode_digest("f" * 64) == "v" * 64
    encoded = names.encode_digest("5a" + "f3" + "0" * 60)
    assert "5a" not in encoded and "f3" not in encoded


def test_full_table() -> None:
    for digit, letter in zip("0123456789abcdef", names.ALPHABET, strict=True):
        assert names.encode_digest(digit * 64) == letter * 64
        assert names.decode_name(letter * 64) == digit * 64


def test_deterministic_round_trips_and_single_position_mutations() -> None:
    digests = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(32)]
    assert all(names.decode_name(names.encode_digest(value)) == value for value in digests)
    digest = "0123456789abcdef" * 4
    base_name = names.encode_digest(digest)
    variants = {
        names.encode_digest(digest[:index] + digit + digest[index + 1 :])
        for index in range(64)
        for digit in "0123456789abcdef"
        if digit != digest[index]
    }
    all_names = {base_name, *variants}
    assert len(variants) == 960
    assert len(all_names) == 961
    assert all(
        names.decode_name(value)
        in {digest[:i] + c + digest[i + 1 :] for i in range(64) for c in "0123456789abcdef"}
        for value in all_names
    )


@pytest.mark.parametrize(
    "value",
    [
        "G" * 64,
        "W" * 64,
        "w" * 64,
        "f" * 64,
        "a" * 64,
        "0" * 64,
        "g" * 63,
        "g" * 65,
        "g" * 31 + "/" + "g" * 32,
        "g" * 31 + "." + "g" * 32,
        "g" * 31 + " " + "g" * 32,
        None,
    ],
    ids=[
        "uppercase",
        "outside-uppercase",
        "outside-w",
        "outside-f",
        "outside-a",
        "outside-zero",
        "short",
        "long",
        "slash",
        "dot",
        "whitespace",
        "non-string",
    ],
)
def test_strict_decode_refusals(value: object) -> None:
    with pytest.raises(names.Refusal, match="^not a canonical object name$"):
        names.decode_name(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    ["A" * 64, "0" * 63, "0" * 65, "0" * 63 + "g", None],
    ids=["uppercase", "short", "long", "non-hex", "non-string"],
)
def test_strict_encode_refusals(value: object) -> None:
    with pytest.raises(names.Refusal, match="^digest must be 64 lowercase hex characters$"):
        names.encode_digest(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "root",
    ["relative/root", "/tmp/F3root", "/tmp/HOLDOUT"],
    ids=["relative", "uppercase-token-one", "uppercase-token-two"],
)
def test_root_refusals(root: str) -> None:
    message = (
        "root must be an absolute path" if not root.startswith("/") else "protected root component"
    )
    with pytest.raises(names.Refusal, match=f"^{message}$"):
        names.object_path(root, "0" * 64)


def test_object_path_is_contained_without_filesystem_access() -> None:
    result = names.object_path("/tmp/objects-root", "0" * 64)
    assert result == Path("/tmp/objects-root") / ("g" * 64)
    assert result.parent == Path("/tmp/objects-root")


def test_protected_token_safety_proof() -> None:
    assert all(
        any(char.lower() not in names.ALPHABET for char in token) for token in names.PROTECTED
    )
    assert all(names.is_token_safe(char * 64) for char in names.ALPHABET)


def test_static_module_constraints() -> None:
    source = SCRIPT.read_text()
    imports = re.findall(
        r"^import ([A-Za-z_][A-Za-z0-9_.]*)|^from ([A-Za-z_][A-Za-z0-9_.]*) import", source, re.M
    )
    modules = {a or b for a, b in imports}
    assert modules <= {"__future__", "importlib.util", "os", "sys", "pathlib"}
    assert "quant_ng_fit" in source
    for forbidden in (
        "open(",
        "os.listdir",
        "Path.exists",
        "resolve(",
        "stat(",
        "rename",
        "unlink",
        "mkdir",
    ):
        assert forbidden not in source
    blocked = ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
    script_paths = (path for path in (ROOT / "scripts").glob("*.py") if not _blocked(path, blocked))
    for path in script_paths:
        if path != SCRIPT:
            assert "quant_ng_object_name" not in path.read_text()
    test_paths = (path for path in (ROOT / "tests").rglob("*.py") if not _blocked(path, blocked))
    src_paths = (path for path in (ROOT / "src").rglob("*.py") if not _blocked(path, blocked))
    for path in test_paths:
        if path != Path(__file__):
            assert "quant_ng_object_name" not in path.read_text()
    for path in src_paths:
        assert "quant_ng_object_name" not in path.read_text()


def _blocked(path: Path, tokens: tuple[str, ...]) -> bool:
    return any(token in part.lower() for part in path.parts for token in tokens)


class _RaisingPath:
    def __fspath__(self):
        raise OSError("refused fspath")


@pytest.mark.parametrize(
    "root, reason",
    [
        ("/", "root must not be a filesystem root"),
        ("/tmp/objects\x00root", "root must be an absolute path"),
        (_RaisingPath(), "root must be an absolute path"),
    ],
    ids=["filesystem-root", "nul-byte", "raising-pathlike"],
)
def test_obj1_object_path_refuses_odd_roots(root, reason):
    with pytest.raises(names.Refusal, match="^" + reason + "$"):
        names.object_path(root, "0" * 64)


def test_obj1_a_bare_name_is_safe_only_as_a_whole_component():
    # The documented scope: concatenation can form a token, so object_path is the only API.
    name = names.encode_digest("0" * 60 + "5884")
    assert names.is_token_safe(name)
    assert not names.is_token_safe(name + "_run.json")
    assert "WHOLE path component" in names.__doc__
