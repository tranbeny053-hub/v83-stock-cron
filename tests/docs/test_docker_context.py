from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def dockerignore_entries() -> set[str]:
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    return {
        line.strip().rstrip("/")
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_whole_context_copy_excludes_sensitive_non_runtime_paths() -> None:
    dockerfile_lines = (ROOT / "Dockerfile").read_text().splitlines()
    assert "COPY . ." in (line.strip() for line in dockerfile_lines), (
        "Dockerfile no longer uses a whole-context copy; update this load-bearing "
        ".dockerignore test to match the new copy strategy"
    )

    ignored = dockerignore_entries()
    assert ".work" in ignored, (
        "COPY . . makes .dockerignore the only protection against raw captures in .work/"
    )
    assert ".venv" in ignored, (
        "COPY . . makes .dockerignore the only protection against copying .venv/"
    )


def test_runtime_paths_remain_in_the_build_context() -> None:
    ignored = dockerignore_entries()
    runtime_paths = {
        "src",
        "frontend",
        "schemas",
        "ops",
        "requirements.txt",
    }

    assert ignored.isdisjoint(runtime_paths), (
        f"runtime paths must not be excluded: {sorted(ignored & runtime_paths)}"
    )
