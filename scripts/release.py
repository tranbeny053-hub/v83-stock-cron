"""UCPE release tooling: the proven W26/F1 release chain, tracked and tested (plan §11.2-§11.3).

Every step captures its raw inputs and outputs before it judges them. Read-only steps run freely.
The two consequential steps refuse unless the operator passes the exact authorization inputs, and
default to a dry run:
  - `deploy`: one plain fast-forward push of the release commit to the Space;
  - `rollback`: one force-with-lease push back to a registered, H2-safe release.
Nothing here deploys, re-pins or rolls back on its own, retries a consequential command, reads a
secret, or touches the database.

  identity        set the release identity in a worktree: build_info.py, its test, the delta mirror
  preflight       preconditions before a deploy (read-only; --dry-push: an authenticated dry run)
  deploy          the single fast-forward push of D (a dry run unless --authorize D --release-id ID)
  settle          after the push: RUNNING at D, health, build-info, served frontend bytes, probes
  repin           build the post-deploy re-pin commit (baseline, guard test, release registry)
  guard-verify    strict check of one guard run: explicit HEALTHY in every round, not just success
  rollback-check  validate a rollback target: registered, carries the H2 hold, migration-compatible
  rollback        the authorized force-with-lease push back to a validated target (dry run default)

Usage: python scripts/release.py <command> --help.
Runbooks: docs/runbooks/RELEASE.md and docs/runbooks/ROLLBACK.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = "ops/release/config.json"
REGISTRY_PATH = "ops/release/releases.json"
BASELINE_PATH = "ops/hf_runtime_baseline.json"
BUILD_INFO_PATH = "src/crypto_probability_engine/config/build_info.py"
BUILD_INFO_TEST_PATH = "tests/api/test_build_info.py"
GUARD_TEST_PATH = "tests/scripts/test_source_integrity_guard.py"
H2_HOLD_PATH = "src/crypto_probability_engine/calibration/skill.py"
H2_HOLD_MARKER = "LEGACY_PASS_LIFTS_HARD_BLOCK: bool = False"
RUNTIME_PATHS = ("src", "frontend", "schemas", "Dockerfile", "requirements.txt")
FRONTEND_FILES = {
    "root": "frontend/index.html",
    "app_js": "frontend/app.js",
    "styles_css": "frontend/styles.css",
}
ERROR_STAGES = frozenset({"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"})
REPIN_AUTHOR = ("UCPE release", "release@ucpe.invalid")
SHA_RE = re.compile(r"[0-9a-f]{40}")
# A probe stays on base_url: plain path characters and an optional query, never a scheme, an
# authority ("//host" or "user@host") or a fragment.
PROBE_PATH_RE = re.compile(r"/(?!/)[A-Za-z0-9._~/-]*(?:\?[A-Za-z0-9._~=&-]*)?")
RELEASE_ID_RE = re.compile(
    r"UCPE-(?P<name>PROD-[A-Z0-9]+(?:-[A-Z0-9]+)*)-(?P<date>\d{8})-(?P<suffix>[A-Z])"
)
FINGERPRINT_PREFIX = "UCPE LIVE BUILD · "
IDENTITY_CONSTANTS = (
    ("release_id", "RELEASE_ID"),
    ("release_label", "RELEASE_LABEL"),
    ("environment", "ENVIRONMENT"),
    ("source_milestone", "SOURCE_MILESTONE"),
)
FINGERPRINT_DERIVATION = (
    'SHORT_RELEASE_ID = RELEASE_ID.removeprefix("UCPE-")',
    'FINGERPRINT = f"UCPE LIVE BUILD · {SHORT_RELEASE_ID}"',
)
DELTA_HEADER = (
    "# Guarded source files that currently differ between the deployed pin and this tree.\n"
    "# It goes non-empty whenever a guarded change is merged but not yet deployed, and empties\n"
    "# again once the deploy lands and ops/hf_runtime_baseline.json is re-pinned.\n"
)
DELTA_BLOCK_RE = re.compile(
    r"^# Guarded source files that currently differ between the deployed pin and this tree\.\n"
    r"(?:#.*\n)*"
    r"CURRENT_DELTA_PATHS: list\[str\] = (?:\[\]|\[\n(?:    \"[^\"\n]+\",\n)*\])\n",
    re.M,
)
PIN_LINE_RE = re.compile(r'^PIN_SHA = "(?P<sha>[0-9a-f]{40})"$', re.M)
URL_USERINFO_RE = re.compile(rb"(https?://)[^/\s@]+@")


def redact(data: bytes) -> bytes:
    """Strip any userinfo from URLs: evidence keeps everything except credentials."""

    return URL_USERINFO_RE.sub(rb"\1***@", data)


class Stop(Exception):
    """A precondition or check failed: report it and change nothing further."""


@dataclass
class Env:
    """Everything that touches the outside world, injectable for tests."""

    root: Path
    config: dict[str, Any]
    run: Callable[..., tuple[int, bytes, bytes]]  # (argv, extra_env=None) -> (rc, out, err)
    http: Callable[[str, str, bytes | None], tuple[int, bytes]]
    now: Callable[[], datetime]
    sleep: Callable[[float], None]


def _run(argv: Sequence[str], extra_env: dict[str, str] | None = None) -> tuple[int, bytes, bytes]:
    environment = {**os.environ, **extra_env} if extra_env else None
    result = subprocess.run(list(argv), capture_output=True, check=False, env=environment)
    return result.returncode, result.stdout, result.stderr


def _http(method: str, url: str, body: bytes | None) -> tuple[int, bytes]:
    headers = {"User-Agent": "ucpe-release/1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, f"transport error: {type(error).__name__}".encode()


def real_env(root: Path = ROOT) -> Env:
    config = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    return Env(root=root, config=config, run=_run, http=_http, now=lambda: datetime.now(UTC),
               sleep=time.sleep)


# ------------------------------------------------------------------------------------- evidence


class Evidence:
    """Raw captures and verdicts for one step, written before anything interprets them."""

    def __init__(self, directory: Path) -> None:
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise Stop(f"evidence directory {directory} already exists; evidence is never "
                       "overwritten") from None
        self.directory = directory
        self.lines: list[str] = []

    def raw(self, name: str, rc: int, out: bytes, err: bytes) -> None:
        (self.directory / f"{name}.out").write_bytes(redact(out))
        (self.directory / f"{name}.err").write_bytes(redact(err))
        (self.directory / f"{name}.rc").write_text(f"{rc}\n", encoding="utf-8")

    def http(self, name: str, status: int, body: bytes) -> None:
        (self.directory / f"{name}.raw").write_bytes(body)
        (self.directory / f"{name}.http").write_text(f"{status}\n", encoding="utf-8")

    def note(self, name: str, text: str) -> None:
        (self.directory / name).write_text(text, encoding="utf-8")

    def check(self, ok: bool, text: str) -> bool:
        line = f"{'PASS' if ok else 'STOP'}  {text}"
        self.lines.append(line)
        print(line)
        return ok

    def finish(self, label: str, ok: bool, detail: str = "") -> bool:
        suffix = f" {detail}" if detail else ""
        verdict = f"{label}={'PASS' if ok else 'STOP'}{suffix} ({self.directory})"
        (self.directory / "VERDICTS").write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        (self.directory / "VERDICT").write_text(verdict + "\n", encoding="utf-8")
        manifest = [
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(self.directory)}"
            for path in sorted(self.directory.rglob("*"))
            if path.is_file() and path.name != "MANIFEST.sha256"
        ]
        (self.directory / "MANIFEST.sha256").write_text(
            "\n".join(manifest) + "\n", encoding="utf-8"
        )
        print(verdict)
        return ok


def evidence_dir(env: Env, step: str, sha: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    stamp = env.now().strftime("%Y%m%dT%H%M%SZ")
    base = env.root / ".work" / "release" / f"{step}_{stamp}_{sha[:12]}"
    candidate, index = base, 1
    while candidate.exists():
        index += 1
        candidate = base.with_name(f"{base.name}_{index}")
    return candidate


# ------------------------------------------------------------------------------------------ git


def git(env: Env, *args: str, root: Path | None = None) -> bytes:
    rc, out, err = env.run(["git", "-C", str(root or env.root), *args])
    if rc != 0:
        raise Stop(f"git {' '.join(args[:3])} failed: {err.decode(errors='replace').strip()}")
    return out


def git_text(env: Env, *args: str, root: Path | None = None) -> str:
    return git(env, *args, root=root).decode("utf-8").strip()


def blob(env: Env, rev: str, path: str) -> bytes:
    return git(env, "cat-file", "blob", f"{rev}:{path}")


def is_ancestor(env: Env, older: str, newer: str) -> bool:
    rc, _, _ = env.run(["git", "-C", str(env.root), "merge-base", "--is-ancestor", older, newer])
    return rc == 0


def require_sha(value: str, what: str) -> str:
    if not SHA_RE.fullmatch(value or ""):
        raise Stop(f"{what} must be exactly 40 lowercase hex characters")
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------------------------- identity


def default_label_and_milestone(release_id: str) -> tuple[str, str]:
    match = RELEASE_ID_RE.fullmatch(release_id)
    if match is None:
        raise Stop(f"release id {release_id!r} must look like UCPE-PROD-<NAME>-<YYYYMMDD>-<A-Z>")
    name = match["name"]
    return f"{name} release of main", name.lower()


def parse_identity(build_info_text: str) -> dict[str, str]:
    """The identity a build serves, read the way build_info.py derives it."""

    identity: dict[str, str] = {}
    for key, constant in IDENTITY_CONSTANTS:
        found = re.findall(rf'^{constant} = "([^"\n]*)"$', build_info_text, flags=re.M)
        if len(found) != 1:
            raise Stop(f"build_info.py does not assign {constant} exactly once")
        identity[key] = found[0]
    for line in FINGERPRINT_DERIVATION:
        if build_info_text.count(line) != 1:
            raise Stop("build_info.py no longer derives the fingerprint the way this tool assumes")
    identity["fingerprint"] = FINGERPRINT_PREFIX + identity["release_id"].removeprefix("UCPE-")
    return identity


def identity_at(env: Env, rev: str) -> dict[str, str]:
    return parse_identity(blob(env, rev, BUILD_INFO_PATH).decode("utf-8"))


def baseline_at(env: Env, rev: str) -> dict[str, Any]:
    raw = blob(env, rev, BASELINE_PATH).decode("utf-8")
    baseline = json.loads(raw)
    if canonical_json(baseline) != raw:
        raise Stop(f"{BASELINE_PATH} at {rev[:12]} is not in canonical form")
    if baseline.get("schema_version") != "hf-runtime-baseline.v1":
        raise Stop(f"{BASELINE_PATH} at {rev[:12]} has an unknown schema_version")
    return baseline


def guarded_delta(digests: dict[str, str], read: Callable[[str], bytes | None]) -> list[str]:
    """Guarded paths whose bytes differ from the pinned digests: the guard's own definition."""

    delta = []
    for path, digest in digests.items():
        data = read(path)
        if data is None or sha256(data) != digest:
            delta.append(path)
    return sorted(delta)


def delta_at(env: Env, rev: str, baseline: dict[str, Any]) -> list[str]:
    def read(path: str) -> bytes | None:
        rc, out, _ = env.run(["git", "-C", str(env.root), "cat-file", "blob", f"{rev}:{path}"])
        return out if rc == 0 else None

    return guarded_delta(baseline["critical_source_digests"], read)


def delta_in_tree(tree: Path, baseline: dict[str, Any]) -> list[str]:
    def read(path: str) -> bytes | None:
        target = tree / path
        return target.read_bytes() if target.is_file() else None

    return guarded_delta(baseline["critical_source_digests"], read)


def asset_tokens(index_html: str) -> dict[str, str]:
    tokens = {}
    for key, name in (("app_js", "app.js"), ("styles_css", "styles.css")):
        found = sorted(set(re.findall(rf'/{re.escape(name)}\?v=([A-Za-z0-9._-]+)"', index_html)))
        if len(found) != 1:
            raise Stop(f"index.html does not reference exactly one {name}?v= token")
        tokens[key] = found[0]
    return tokens


def has_h2_hold(env: Env, rev: str) -> bool:
    rc, out, _ = env.run(["git", "-C", str(env.root), "cat-file", "blob", f"{rev}:{H2_HOLD_PATH}"])
    if rc != 0:
        return False
    text = out.decode("utf-8", errors="replace")
    return (
        text.count(H2_HOLD_MARKER + "\n") == 1
        and "LEGACY_PASS_LIFTS_HARD_BLOCK: bool = True" not in text
    )


# ----------------------------------------------------------------------------------- text edits


def replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise Stop(f"{what}: expected exactly one match, found {count}")
    return text.replace(old, new)


def set_build_info(text: str, identity: dict[str, str]) -> str:
    current = parse_identity(text)
    for key, constant in IDENTITY_CONSTANTS:
        if key == "environment":
            continue
        text = replace_once(
            text, f'{constant} = "{current[key]}"\n', f'{constant} = "{identity[key]}"\n', constant
        )
    return text


def set_build_info_test(text: str, old: dict[str, str], new: dict[str, str]) -> str:
    for key in ("release_id", "fingerprint", "source_milestone"):
        text = replace_once(
            text,
            f'    assert payload["{key}"] == "{old[key]}"\n',
            f'    assert payload["{key}"] == "{new[key]}"\n',
            f"the build-info test's {key} expectation",
        )
    return text


def delta_block(paths: Iterable[str], note: Sequence[str]) -> str:
    lines = [DELTA_HEADER]
    lines.extend(f"# {line}\n" for line in note)
    ordered = sorted(paths)
    if ordered:
        body = "".join(f'    "{path}",\n' for path in ordered)
        lines.append(f"CURRENT_DELTA_PATHS: list[str] = [\n{body}]\n")
    else:
        lines.append("CURRENT_DELTA_PATHS: list[str] = []\n")
    return "".join(lines)


def set_guard_delta(text: str, paths: Iterable[str], note: Sequence[str]) -> str:
    matches = DELTA_BLOCK_RE.findall(text)
    if len(matches) != 1:
        raise Stop(
            f"{GUARD_TEST_PATH}: the CURRENT_DELTA_PATHS block was found {len(matches)} times"
        )
    return DELTA_BLOCK_RE.sub(lambda _m: delta_block(paths, note), text)


def set_guard_pin(text: str, pin: str) -> str:
    matches = PIN_LINE_RE.findall(text)
    if len(matches) != 1:
        raise Stop(f"{GUARD_TEST_PATH}: PIN_SHA was found {len(matches)} times")
    return PIN_LINE_RE.sub(f'PIN_SHA = "{pin}"', text)


def set_guard_identity(text: str, old: dict[str, str], new: dict[str, str]) -> str:
    for key in ("release_id", "release_label", "environment", "source_milestone", "fingerprint"):
        if old[key] == new[key]:
            continue
        text = replace_once(
            text,
            f'    assert intended.{key} == "{old[key]}"\n',
            f'    assert intended.{key} == "{new[key]}"\n',
            f"the guard test's pinned {key} assertion",
        )
    return text


# -------------------------------------------------------------------------------- identity step


def cmd_identity(env: Env, args: argparse.Namespace) -> int:
    tree = Path(args.worktree).resolve()
    if git_text(env, "status", "--porcelain", "--untracked-files=all", root=tree):
        raise Stop("the worktree is not clean")
    head = git_text(env, "rev-parse", "HEAD", root=tree)
    label, milestone = default_label_and_milestone(args.release_id)
    build_info = (tree / BUILD_INFO_PATH).read_text(encoding="utf-8")
    old = parse_identity(build_info)
    new = dict(old)
    new.update(
        release_id=args.release_id,
        release_label=args.label or label,
        source_milestone=args.milestone or milestone,
        fingerprint=FINGERPRINT_PREFIX + args.release_id.removeprefix("UCPE-"),
    )
    if new["release_id"] == old["release_id"]:
        raise Stop("the release id is unchanged: every deploy names a new release")
    (tree / BUILD_INFO_PATH).write_text(set_build_info(build_info, new), encoding="utf-8")
    test_path = tree / BUILD_INFO_TEST_PATH
    test_path.write_text(set_build_info_test(test_path.read_text(encoding="utf-8"), old, new),
                         encoding="utf-8")
    baseline = json.loads((tree / BASELINE_PATH).read_text(encoding="utf-8"))
    delta = delta_in_tree(tree, baseline)
    note = [
        f"Now standing in it: {', '.join(Path(path).name for path in delta)}, merged but not yet",
        f"deployed. {new['release_id']} names the next deploy; all of them clear",
        "when it lands and the baseline is re-pinned.",
    ]
    guard_path = tree / GUARD_TEST_PATH
    guard_path.write_text(set_guard_delta(guard_path.read_text(encoding="utf-8"), delta, note),
                          encoding="utf-8")
    print(f"IDENTITY=OK on {head[:12]}: {old['release_id']} -> {new['release_id']}")
    print(f"  label {new['release_label']!r}, milestone {new['source_milestone']!r}")
    print(f"  fingerprint {new['fingerprint']!r}")
    print(f"  guard delta mirror: {delta}")
    print("Next: ./verify.sh in this worktree, commit, then push and merge (a T3).")
    return 0


# ------------------------------------------------------------------------------------ preflight


def runtime_delta(env: Env, older: str, newer: str) -> list[str]:
    out = git_text(env, "diff", "--name-only", older, newer, "--", *RUNTIME_PATHS)
    return sorted(line for line in out.splitlines() if line)


def delta_digest(paths: Sequence[str]) -> str:
    return sha256(("\n".join(sorted(paths)) + "\n").encode("utf-8"))


def parse_guard_summaries(log: str) -> list[dict[str, Any]]:
    summaries = []
    for line in log.splitlines():
        start = line.find('{"')
        if start < 0:
            continue
        try:
            value = json.loads(line[start:])
        except ValueError:
            continue
        if isinstance(value, dict) and "final_classification" in value:
            summaries.append(value)
    return summaries


def guard_checks(
    summary: dict[str, Any], *, pin: str, release: str, delta: Sequence[str]
) -> list[tuple[bool, str]]:
    return [
        (summary.get("final_classification") == "HEALTHY",
         f"final_classification HEALTHY (got {summary.get('final_classification')})"),
        (summary.get("per_round_classifications") == ["HEALTHY"] * 3,
         f"every round HEALTHY (got {summary.get('per_round_classifications')})"),
        (summary.get("exit_code") == 0, f"exit_code 0 (got {summary.get('exit_code')})"),
        (summary.get("hf_main_sha") == pin and summary.get("pinned_hf_main_sha") == pin,
         f"hf_main_sha == pinned == {pin[:12]} (got {str(summary.get('hf_main_sha'))[:12]} / "
         f"{str(summary.get('pinned_hf_main_sha'))[:12]})"),
        (summary.get("live_release_id") == release
         and summary.get("intended_release_id") == release,
         f"live == intended == {release}"),
        (sorted(summary.get("deployment_delta_paths") or []) == sorted(delta),
         f"deployment delta {sorted(delta)} (got {summary.get('deployment_delta_paths')})"),
    ]


def gh_json(env: Env, ev: Evidence, name: str, *args: str) -> Any:
    rc, out, err = env.run(["gh", *args, "--repo", env.config["github_repo"]])
    ev.raw(name, rc, out, err)
    if rc != 0:
        raise Stop(f"gh {' '.join(args[:2])} failed (rc {rc})")
    return json.loads(out or b"null")


def fetch(env: Env, ev: Evidence, name: str, url: str, method: str = "GET",
          body: bytes | None = None) -> tuple[int, bytes]:
    status, data = env.http(method, url, body)
    ev.http(name, status, data)
    return status, data


def space_runtime(env: Env, ev: Evidence, name: str) -> tuple[str | None, str | None]:
    status, data = fetch(env, ev, name, env.config["space_api"])
    try:
        runtime = json.loads(data).get("runtime", {}) if status == 200 else {}
    except ValueError:
        runtime = {}
    return runtime.get("stage"), runtime.get("sha")


def json_field(data: bytes, key: str) -> Any:
    try:
        value = json.loads(data)
    except ValueError:
        return None
    return value.get(key) if isinstance(value, dict) else None


def cmd_preflight(env: Env, args: argparse.Namespace) -> int:
    d = require_sha(args.d, "D")
    ev = Evidence(evidence_dir(env, "preflight", d, args.evidence_dir))
    ev.note("INPUT", f"D={d}\ndry_push={bool(args.dry_push)}\n")
    ok = True

    rc, out, err = env.run(["git", "-C", str(env.root), "fetch", "-q", "origin", "main"])
    ev.raw("fetch_origin", rc, out, err)
    origin_main = git_text(env, "rev-parse", "origin/main")
    runs = gh_json(env, ev, "ci_on_d", "run", "list", "--commit", d, "--json",
                   "workflowName,event,status,conclusion,headBranch,databaseId")
    push_ci = [
        r for r in runs if r["workflowName"] == env.config["ci_workflow"] and r["event"] == "push"
    ]
    ok &= ev.check(
        rc == 0 and origin_main == d and bool(push_ci)
        and all(r["status"] == "completed" and r["conclusion"] == "success"
                and r["headBranch"] == "main" for r in push_ci),
        "1 D is origin/main, and the push CI on D completed with success",
    )

    baseline = baseline_at(env, d)
    pin = baseline["hf_main_sha"]
    rc, out, err = env.run(["git", "-C", str(env.root), "ls-remote", env.config["hf_remote"],
                            "refs/heads/main"])
    ev.raw("ls_hf", rc, out, err)
    hf_main = out.decode().split("\t")[0] if rc == 0 and out else ""
    ok &= ev.check(hf_main == pin, f"2 hf refs/heads/main is the baseline pin {pin[:12]}")

    stage, running = space_runtime(env, ev, "space")
    info_status, info = fetch(env, ev, "build_info", env.config["base_url"] + "/v1/build-info")
    health_status, _ = fetch(env, ev, "health", env.config["base_url"] + "/healthcheck")
    ok &= ev.check(
        stage == "RUNNING" and running == pin and info_status == 200
        and json_field(info, "release_id") == baseline["release_id"] and health_status == 200,
        f"3 the Space is RUNNING at the pin, serving {baseline['release_id']}, healthcheck 200",
    )

    ok &= ev.check(is_ancestor(env, pin, d),
                   f"4 the pin {pin[:12]} is an ancestor of D (fast-forward)")

    delta = runtime_delta(env, pin, d)
    ev.note("runtime_delta.txt", "\n".join(delta) + "\n")
    digest = delta_digest(delta)
    if args.expect_runtime_delta:
        expected = sorted(
            line.strip()
            for line in Path(args.expect_runtime_delta).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        delta_ok = delta == expected
    else:
        delta_ok = args.accept_runtime_delta == digest
    ok &= ev.check(
        delta_ok,
        f"5 the runtime delta ({len(delta)} files, digest {digest[:16]}) is the reviewed one",
    )
    if not delta_ok:
        print(f"  review runtime_delta.txt, then rerun with --accept-runtime-delta {digest}")

    guard = env.config["guard_workflow"]
    latest = gh_json(env, ev, "guard_latest", "run", "list", "--workflow", guard, "--limit", "1",
                     "--json", "databaseId,event,status,conclusion,headBranch,headSha")
    queued = gh_json(env, ev, "guard_queued", "run", "list", "--workflow", guard, "--status",
                     "queued", "--json", "databaseId")
    running_runs = gh_json(env, ev, "guard_running", "run", "list", "--workflow", guard, "--status",
                           "in_progress", "--json", "databaseId")
    guard_ok = bool(latest) and queued == [] and running_runs == []
    if guard_ok:
        run = latest[0]
        rc, out, err = env.run(["gh", "run", "view", str(run["databaseId"]), "--repo",
                                env.config["github_repo"], "--log"])
        ev.raw("guard_log", rc, out, err)
        summaries = parse_guard_summaries(out.decode("utf-8", errors="replace"))
        guard_ok = (
            rc == 0 and len(summaries) == 1 and run["status"] == "completed"
            and run["conclusion"] == "success" and run["headBranch"] == "main"
            and run["headSha"] == d
            and all(passed for passed, _ in guard_checks(
                summaries[0], pin=pin, release=baseline["release_id"],
                delta=delta_at(env, d, baseline)))
        )
    ok &= ev.check(guard_ok, "6 the latest guard run is on D, explicitly HEALTHY with the expected "
                             "delta; none is queued or running")

    if args.dry_push:
        rc, out, err = env.run(["git", "-C", str(env.root), "push", "--dry-run",
                                env.config["hf_remote"], f"{d}:refs/heads/main"])
        ev.raw("dry_push", rc, out, err)
        ok &= ev.check(rc == 0 and push_is_fast_forward(err.decode(errors="replace"), pin, d),
                       f"7 the dry run authenticates and shows {pin[:7]}..{d[:7]} -> main")
    ev.note("PREFLIGHT.json", canonical_json({
        "d": d, "pin": pin, "dry_push": bool(args.dry_push), "runtime_delta_digest": digest,
        "verdict": "PASS" if ok else "STOP", "utc": env.now().isoformat(),
    }))
    return 0 if ev.finish("PREFLIGHT", ok) else 1


def push_is_fast_forward(stderr: str, older: str, newer: str) -> bool:
    pattern = rf"^ +{older[:7]}[0-9a-f]*\.\.{newer[:7]}[0-9a-f]* +\S+ -> main$"
    return re.search(pattern, stderr, flags=re.M) is not None and "forced update" not in stderr


# --------------------------------------------------------------------------------------- deploy


def fresh_preflight(env: Env, directory: str | None, d: str, max_age_minutes: float) -> Path:
    base = env.root / ".work" / "release"
    candidates = [Path(directory)] if directory else sorted(base.glob(f"preflight_*_{d[:12]}"))
    for path in reversed(candidates):
        record_path = path / "PREFLIGHT.json"
        if not record_path.is_file():
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        age = (env.now() - datetime.fromisoformat(record["utc"])).total_seconds() / 60
        fresh = 0 <= age <= max_age_minutes
        if record["d"] == d and record["verdict"] == "PASS" and record["dry_push"] and fresh:
            return path
    raise Stop(f"no PASS preflight with --dry-push for {d[:12]} within {max_age_minutes:g} minutes")


def cmd_deploy(env: Env, args: argparse.Namespace) -> int:
    d = require_sha(args.d, "D")
    remote = env.config["hf_remote"]
    command = ["git", "-C", str(env.root), "push", remote, f"{d}:refs/heads/main"]
    if args.authorize is None and args.release_id is None:
        print("DEPLOY=DRY_RUN nothing was pushed. The exact command, for an authorized run:")
        print("  " + " ".join(command))
        print(f"Authorize it with: --authorize {d} --release-id <the release id at D>")
        return 0
    if args.authorize != d:
        raise Stop("--authorize must repeat D exactly")
    if args.release_id != identity_at(env, d)["release_id"]:
        raise Stop("--release-id is not the release identity at D")
    marker = env.root / ".work" / "release" / f"CONSUMED_deploy_{d}"
    if marker.exists():
        raise Stop(f"the deploy of {d[:12]} is already consumed ({marker}); never rerun it")
    preflight = fresh_preflight(env, args.preflight_dir, d, args.max_preflight_age)
    ev = Evidence(evidence_dir(env, "deploy", d, args.evidence_dir))
    pin = json.loads((preflight / "PREFLIGHT.json").read_text(encoding="utf-8"))["pin"]
    ev.note("INPUT", f"D={d}\nrelease_id={args.release_id}\npreflight={preflight}\n")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{ev.directory}\n", encoding="utf-8")
    ev.note("STARTED_UTC", env.now().isoformat() + "\n")
    rc, out, err = env.run(command)
    ev.raw("push", rc, out, err)
    ev.note("ENDED_UTC", env.now().isoformat() + "\n")
    ok = ev.check(rc == 0 and push_is_fast_forward(err.decode(errors="replace"), pin, d),
                  f"the push fast-forwarded {pin[:7]}..{d[:7]} -> main, with no force")
    return 0 if ev.finish("DEPLOY", ok, "CONSUMED; never rerun") else 1


# --------------------------------------------------------------------------------------- settle


def cmd_settle(env: Env, args: argparse.Namespace) -> int:
    d = require_sha(args.d, "D")
    probes = [parse_probe(env, spec) for spec in args.probe or []]
    ev = Evidence(evidence_dir(env, "settle", d, args.evidence_dir))
    identity = identity_at(env, d)
    deadline = time.monotonic() + args.timeout_minutes * 60
    poll = 0
    while True:
        poll += 1
        stage, running = space_runtime(env, ev, f"poll_{poll:03d}")
        print(f"{env.now().strftime('%H:%M:%SZ')} poll {poll}: {stage} {running}")
        if stage == "RUNNING" and running == d:
            break
        if stage in ERROR_STAGES:
            ev.check(False, f"the Space reported {stage}")
            ev.finish("SETTLE", False)
            return 1
        if time.monotonic() >= deadline:
            ev.check(False, f"not RUNNING at D within {args.timeout_minutes:g} minutes")
            ev.finish("SETTLE", False)
            return 1
        env.sleep(args.spacing_seconds)
    ok = ev.check(True, f"RUNNING at D after {poll} poll(s)")
    base = env.config["base_url"]
    health_status, _ = fetch(env, ev, "health", base + "/healthcheck")
    ok &= ev.check(health_status == 200, "healthcheck 200")
    info_status, info = fetch(env, ev, "build_info", base + "/v1/build-info")
    ok &= ev.check(
        info_status == 200 and json_field(info, "release_id") == identity["release_id"]
        and json_field(info, "fingerprint") == identity["fingerprint"],
        f"build-info is {identity['release_id']} with its fingerprint",
    )
    tokens = asset_tokens(blob(env, d, FRONTEND_FILES["root"]).decode("utf-8"))
    for key, path in FRONTEND_FILES.items():
        url = base + ("/" if key == "root" else f"/{Path(path).name}?v={tokens[key]}")
        status, data = fetch(env, ev, key, url)
        ok &= ev.check(status == 200 and sha256(data) == sha256(blob(env, d, path)),
                       f"GET {url.removeprefix(base)} serves D's {path} bytes")
    for index, probe in enumerate(probes, start=1):
        ok &= run_probe(env, ev, index, probe)
    return 0 if ev.finish("SETTLE", ok) else 1


@dataclass(frozen=True)
class Probe:
    spec: str
    method: str
    path: str
    expected: int
    assertions: tuple[str, ...]


def parse_probe(env: Env, spec: str) -> Probe:
    """METHOD PATH STATUS [dotted.key=value ...], refused before anything is fetched or recorded."""

    parts = spec.split()
    if len(parts) < 3 or parts[0] not in {"GET", "POST"} or not parts[2].isdigit():
        raise Stop(f"bad --probe {spec!r}: use 'GET|POST /path STATUS [key.path=value ...]'")
    method, path = parts[0], parts[1]
    if not PROBE_PATH_RE.fullmatch(path):
        raise Stop(f"bad --probe path {path!r}: only a plain absolute path on base_url")
    if method == "POST" and path not in env.config.get("post_probe_paths", []):
        raise Stop(f"POST --probe {path!r} is not in post_probe_paths ({CONFIG_PATH})")
    return Probe(spec, method, path, int(parts[2]), tuple(parts[3:]))


def run_probe(env: Env, ev: Evidence, index: int, probe: Probe) -> bool:
    """One extra read-only check of the release."""

    status, data = fetch(env, ev, f"probe_{index}", env.config["base_url"] + probe.path,
                         probe.method, b"{}" if probe.method == "POST" else None)
    ok = status == probe.expected
    for assertion in probe.assertions:
        key, _, value = assertion.partition("=")
        current: Any
        try:
            current = json.loads(data)
        except ValueError:
            current = None
        for part in key.split("."):
            current = current.get(part) if isinstance(current, dict) else None
        ok &= str(current) == value
    return ev.check(ok, f"probe {probe.spec}")


# ---------------------------------------------------------------------------------------- repin


def load_registry(text: str) -> dict[str, Any]:
    registry = json.loads(text)
    if registry.get("schema_version") != "ucpe-release-registry.v1":
        raise Stop(f"{REGISTRY_PATH} has an unknown schema_version")
    return registry


def cmd_repin(env: Env, args: argparse.Namespace) -> int:
    d = require_sha(args.d, "D")
    tree = Path(args.worktree).resolve()
    if git_text(env, "rev-parse", "HEAD", root=tree) != d:
        raise Stop("the worktree HEAD is not D")
    if git_text(env, "status", "--porcelain", "--untracked-files=all", root=tree):
        raise Stop("the worktree is not clean")
    baseline = baseline_at(env, d)
    previous = baseline["hf_main_sha"]
    if previous == d:
        raise Stop("the baseline at D already pins D")
    if not is_ancestor(env, previous, d):
        raise Stop(f"the previous pin {previous[:12]} is not an ancestor of D")
    old = {key: baseline[key] for key in ("release_id", "release_label", "environment",
                                          "source_milestone", "fingerprint")}
    new = identity_at(env, d)
    if new["release_id"] == old["release_id"]:
        raise Stop("D carries the same release id as the pin: a deploy must name a new release")
    delta = delta_at(env, d, baseline)
    if BUILD_INFO_PATH not in delta:
        raise Stop("build_info.py is not in the guarded delta at D")

    repinned = json.loads(canonical_json(baseline))
    repinned["hf_main_sha"] = d
    repinned.update(new)
    for path in delta:
        repinned["critical_source_digests"][path] = sha256(blob(env, d, path))
    repinned["frontend_asset_tokens"] = asset_tokens(blob(env, d, FRONTEND_FILES["root"]).decode())
    if delta_at(env, d, repinned):
        raise Stop("the re-pinned digests do not equal D's bytes")
    (tree / BASELINE_PATH).write_text(canonical_json(repinned), encoding="utf-8")

    guard_path = tree / GUARD_TEST_PATH
    text = set_guard_pin(guard_path.read_text(encoding="utf-8"), d)
    text = set_guard_identity(text, old, new)
    text = set_guard_delta(text, [], [
        f"{new['release_id']} deployed main's own tree, so nothing stands in it:",
        f"{', '.join(Path(path).name for path in delta)} cleared with that release.",
    ])
    guard_path.write_text(text, encoding="utf-8")

    registry_path = tree / REGISTRY_PATH
    registry = load_registry(registry_path.read_text(encoding="utf-8"))
    if any(entry["commit"] == d for entry in registry["releases"]):
        raise Stop(f"{d[:12]} is already registered")
    registry["releases"].append({
        "commit": d,
        "deployed_over": previous,
        "h2_hold": has_h2_hold(env, d),
        "release_id": new["release_id"],
    })
    registry_path.write_text(canonical_json(registry), encoding="utf-8")

    changed = sorted(git_text(env, "diff", "--name-only", root=tree).splitlines())
    if changed != sorted([BASELINE_PATH, GUARD_TEST_PATH, REGISTRY_PATH]):
        raise Stop(f"the re-pin changed {changed}, not exactly the baseline, guard test, registry")
    date = git_text(env, "show", "-s", "--format=%cI", d)
    name, email = REPIN_AUTHOR
    identity_env = {
        "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": date,
    }
    git(env, "add", "--", BASELINE_PATH, GUARD_TEST_PATH, REGISTRY_PATH, root=tree)
    message = (
        f"chore(pin): production is {new['release_id'].removeprefix('UCPE-')} ({d[:12]}); "
        "the guard re-pinned from its bytes\n\nThe deployment delta is empty: production serves "
        "main's own tree "
        f"({new['release_id']}).\nBuilt by scripts/release.py repin.\n"
    )
    rc, out, err = env.run(
        ["git", "-C", str(tree), "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify",
         "-m", message],
        identity_env,
    )
    if rc != 0:
        raise Stop(f"the re-pin commit failed: {err.decode(errors='replace').strip()}")
    p = git_text(env, "rev-parse", "HEAD", root=tree)
    print(f"REPIN=OK P={p} parent={d} delta_cleared={delta}")
    return 0


# --------------------------------------------------------------------------------- guard verify


def cmd_guard_verify(env: Env, args: argparse.Namespace) -> int:
    for value, what in ((args.expect_head, "--expect-head"), (args.expect_pin, "--expect-pin")):
        require_sha(value, what)
    ev = Evidence(evidence_dir(env, "guard_verify", args.expect_head, args.evidence_dir))
    meta = gh_json(env, ev, "run_meta", "run", "view", args.run_id, "--json",
                   "event,status,conclusion,headBranch,headSha,workflowName")
    rc, out, err = env.run(["gh", "run", "view", args.run_id, "--repo", env.config["github_repo"],
                            "--log"])
    ev.raw("run_log", rc, out, err)
    summaries = parse_guard_summaries(out.decode("utf-8", errors="replace"))
    ok = ev.check(len(summaries) == 1,
                  f"exactly one guard summary in the log (found {len(summaries)})")
    ok &= ev.check(
        meta.get("headBranch") == "main" and meta.get("headSha") == args.expect_head
        and meta.get("status") == "completed" and meta.get("conclusion") == "success",
        f"the run is on main at {args.expect_head[:12]}, completed with success",
    )
    if len(summaries) == 1:
        ev.note("guard_summary.json", canonical_json(summaries[0]))
        for passed, text in guard_checks(summaries[0], pin=args.expect_pin,
                                         release=args.expect_release,
                                         delta=json.loads(args.expect_delta)):
            ok &= ev.check(passed, text)
    return 0 if ev.finish("GUARD_VERIFY", ok) else 1


# ------------------------------------------------------------------------------------- rollback


def rollback_findings(
    env: Env, target: str, current: str, registry: dict[str, Any]
) -> list[tuple[bool, str]]:
    entry = next((item for item in registry["releases"] if item["commit"] == target), None)
    target_migrations = {
        Path(name).name[:4]
        for name in git_text(env, "ls-tree", "--name-only", target, "migrations/").splitlines()
        if re.fullmatch(r"\d{4}_.*\.sql", Path(name).name)
    }
    newer = [m for m in registry["migrations_applied"] if m["id"] not in target_migrations]
    return [
        (entry is not None, f"{target[:12]} is a registered release"),
        (entry is not None and entry.get("h2_hold") is True and has_h2_hold(env, target),
         "the target carries the H2 fail-closed hold (registry and code agree)"),
        (entry is not None and identity_at(env, target)["release_id"] == entry["release_id"],
         "the target's build identity matches its registry entry"),
        (target != current and is_ancestor(env, target, current),
         f"the target is an older ancestor of the current production {current[:12]}"),
        (all(m.get("additive") is True for m in newer),
         "every migration applied after the target is additive: "
         + (", ".join(f"{m['id']}" for m in newer) or "none")),
    ]


def cmd_rollback_check(env: Env, args: argparse.Namespace, *, quiet_command: bool = False) -> int:
    target = require_sha(args.target, "the target")
    ev = Evidence(evidence_dir(env, "rollback_check", target, args.evidence_dir))
    registry = load_registry((env.root / REGISTRY_PATH).read_text(encoding="utf-8"))
    rc, out, err = env.run(["git", "-C", str(env.root), "ls-remote", env.config["hf_remote"],
                            "refs/heads/main"])
    ev.raw("ls_hf", rc, out, err)
    current = out.decode().split("\t")[0] if rc == 0 and out else ""
    ok = ev.check(bool(SHA_RE.fullmatch(current)),
                  f"current production read from the hf remote: {current[:12]}")
    if args.expected_current:
        ok &= ev.check(current == args.expected_current, "it equals --expected-current")
    if ok:
        for passed, text in rollback_findings(env, target, current, registry):
            ok &= ev.check(passed, text)
    if ok and not quiet_command:
        print("The owner's rollback command (a T4; `scripts/release.py rollback` runs it when "
              "authorized):")
        print(f"  git push --force-with-lease=refs/heads/main:{current} {env.config['hf_remote']} "
              f"{target}:refs/heads/main")
    return 0 if ev.finish("ROLLBACK_CHECK", ok) else 1


def cmd_rollback(env: Env, args: argparse.Namespace) -> int:
    target = require_sha(args.target, "the target")
    if args.authorize is None:
        result = cmd_rollback_check(env, args)
        print("ROLLBACK=DRY_RUN nothing was pushed. Authorize with --authorize <target> "
              "--expected-current <production sha> --release-id <the target's release id>.")
        return result
    if args.authorize != target or not args.expected_current:
        raise Stop("--authorize must repeat the target, and --expected-current is required")
    if args.release_id != identity_at(env, target)["release_id"]:
        raise Stop("--release-id is not the release identity at the target")
    marker = env.root / ".work" / "release" / f"CONSUMED_rollback_{target}_{args.expected_current}"
    if marker.exists():
        raise Stop("this rollback is already consumed; never rerun it")
    check_args = argparse.Namespace(**{**vars(args), "evidence_dir": None})
    if cmd_rollback_check(env, check_args, quiet_command=True) != 0:
        raise Stop("the rollback check did not pass")
    ev = Evidence(evidence_dir(env, "rollback", target, args.evidence_dir))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{ev.directory}\n", encoding="utf-8")
    rc, out, err = env.run([
        "git", "-C", str(env.root), "push",
        f"--force-with-lease=refs/heads/main:{args.expected_current}",
        env.config["hf_remote"], f"{target}:refs/heads/main",
    ])
    ev.raw("push", rc, out, err)
    ok = ev.check(rc == 0 and "forced update" in err.decode(errors="replace"),
                  f"the Space main moved back to {target[:12]} under the lease")
    print("Next: settle at the target; the owner decides the follow-up "
          "(docs/runbooks/ROLLBACK.md).")
    return 0 if ev.finish("ROLLBACK", ok, "CONSUMED; never rerun") else 1


# ------------------------------------------------------------------------------------------ cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("identity", help="set the next release identity in a clean worktree")
    p.add_argument("--worktree", required=True)
    p.add_argument("--release-id", required=True)
    p.add_argument("--label")
    p.add_argument("--milestone")

    p = sub.add_parser("preflight", help="read-only preconditions before a deploy")
    p.add_argument("d")
    p.add_argument("--dry-push", action="store_true")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--expect-runtime-delta", help="file listing the reviewed runtime paths")
    group.add_argument("--accept-runtime-delta", help="the sha256 printed for the reviewed delta")
    p.add_argument("--evidence-dir")

    p = sub.add_parser("deploy", help="the single fast-forward push (a dry run unless authorized)")
    p.add_argument("d")
    p.add_argument("--authorize")
    p.add_argument("--release-id")
    p.add_argument("--preflight-dir")
    p.add_argument("--max-preflight-age", type=float, default=30.0, help="minutes")
    p.add_argument("--evidence-dir")

    p = sub.add_parser("settle", help="post-push checks")
    p.add_argument("d")
    p.add_argument("--timeout-minutes", type=float, default=30.0)
    p.add_argument("--spacing-seconds", type=float, default=30.0)
    p.add_argument("--probe", action="append", help="'GET|POST /path STATUS [key.path=value ...]'")
    p.add_argument("--evidence-dir")

    p = sub.add_parser("repin", help="build the post-deploy re-pin commit in a worktree at D")
    p.add_argument("d")
    p.add_argument("--worktree", required=True)

    p = sub.add_parser("guard-verify", help="strict check of one guard run")
    p.add_argument("run_id")
    p.add_argument("--expect-head", required=True)
    p.add_argument("--expect-pin", required=True)
    p.add_argument("--expect-release", required=True)
    p.add_argument("--expect-delta", default="[]", help="JSON list of guarded paths")
    p.add_argument("--evidence-dir")

    for name, help_text in (
        ("rollback-check", "validate a rollback target"),
        ("rollback", "the authorized force-with-lease push (a dry run by default)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("target")
        p.add_argument("--expected-current")
        p.add_argument("--evidence-dir")
        if name == "rollback":
            p.add_argument("--authorize")
            p.add_argument("--release-id")
    return parser


COMMANDS: dict[str, Callable[[Env, argparse.Namespace], int]] = {
    "identity": cmd_identity,
    "preflight": cmd_preflight,
    "deploy": cmd_deploy,
    "settle": cmd_settle,
    "repin": cmd_repin,
    "guard-verify": cmd_guard_verify,
    "rollback-check": cmd_rollback_check,
    "rollback": cmd_rollback,
}


def main(argv: Sequence[str] | None = None, env: Env | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](env or real_env(), args)
    except Stop as stop:
        print(f"{args.command.upper().replace('-', '_')}=STOP {stop}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.environ.setdefault("LC_ALL", "C")
    raise SystemExit(main())
