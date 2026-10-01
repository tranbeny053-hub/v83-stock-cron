"""scripts/release.py: the tracked release chain (plan §11.2-§11.3, bundle B4).

Two layers:
- fidelity: the text editors and parsers run against the repository's real files, so a format drift
  in build_info.py, its test, the guard test, index.html or the baseline fails here first;
- rehearsal: a full identity -> preflight -> deploy -> settle -> repin -> guard-verify -> rollback
  sequence in temporary git repositories with bare `origin` and `hf` remotes. GitHub and HTTP are
  fakes; git is real. Nothing touches the network, the Space or GitHub.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import release as rel

ROOT = Path(__file__).resolve().parents[2]
ALPHA = "UCPE-PROD-ALPHA-20261001-A"
BETA = "UCPE-PROD-BETA-20261002-A"
APP = "src/crypto_probability_engine/api/app.py"
CRITICAL = (
    "Dockerfile",
    "frontend/app.js",
    "frontend/index.html",
    "frontend/styles.css",
    "schemas/build_info.schema.json",
    "schemas/response.schema.json",
    "src/crypto_probability_engine/api/analysis_service.py",
    APP,
    rel.BUILD_INFO_PATH,
    "src/crypto_probability_engine/derivatives_intel/runtime.py",
    "src/crypto_probability_engine/quant_v2/contract.py",
)


def _real(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ------------------------------------------------------------------------- fidelity: real files


def test_identity_parses_the_real_build_info_the_way_it_derives_the_fingerprint() -> None:
    identity = rel.parse_identity(_real(rel.BUILD_INFO_PATH))
    baseline = json.loads(_real(rel.BASELINE_PATH))
    assert identity["fingerprint"] == rel.FINGERPRINT_PREFIX + identity["release_id"][len("UCPE-"):]
    assert identity["environment"] == baseline["environment"]
    assert rel.RELEASE_ID_RE.fullmatch(identity["release_id"])


def test_default_label_and_milestone_follow_the_recorded_releases() -> None:
    assert rel.default_label_and_milestone("UCPE-PROD-F1-AUTOMATION-20261001-A") == (
        "PROD-F1-AUTOMATION release of main",
        "prod-f1-automation",
    )
    assert rel.default_label_and_milestone("UCPE-PROD-TC-V1-STAMP-20260930-A") == (
        "PROD-TC-V1-STAMP release of main",
        "prod-tc-v1-stamp",
    )
    for bad in ("UCPE-PROD-F1-20261001", "PROD-F1-20261001-A", "UCPE-PROD-f1-20261001-A", ""):
        with pytest.raises(rel.Stop):
            rel.default_label_and_milestone(bad)


def test_build_info_and_its_test_round_trip_on_the_real_files() -> None:
    old = rel.parse_identity(_real(rel.BUILD_INFO_PATH))
    new = dict(old, release_id=BETA, release_label="PROD-BETA release of main",
               source_milestone="prod-beta", fingerprint="UCPE LIVE BUILD · PROD-BETA-20261002-A")
    edited = rel.set_build_info(_real(rel.BUILD_INFO_PATH), new)
    assert rel.parse_identity(edited) == new
    test_text = rel.set_build_info_test(_real(rel.BUILD_INFO_TEST_PATH), old, new)
    assert f'assert payload["release_id"] == "{BETA}"' in test_text
    assert old["release_id"] not in test_text


def test_the_guard_test_editors_match_the_real_guard_test_exactly_once() -> None:
    text = _real(rel.GUARD_TEST_PATH)
    assert len(rel.DELTA_BLOCK_RE.findall(text)) == 1
    assert len(rel.PIN_LINE_RE.findall(text)) == 1
    with_delta = rel.set_guard_delta(text, [APP, rel.BUILD_INFO_PATH], ["note one", "note two"])
    assert f'CURRENT_DELTA_PATHS: list[str] = [\n    "{APP}",\n' in with_delta
    assert "# note two\nCURRENT_DELTA_PATHS" in with_delta
    cleared = rel.set_guard_delta(with_delta, [], ["cleared"])
    assert "# cleared\nCURRENT_DELTA_PATHS: list[str] = []\n" in cleared
    repinned = rel.set_guard_pin(cleared, "e" * 40)
    assert rel.PIN_LINE_RE.findall(repinned) == ["e" * 40]
    baseline = json.loads(_real(rel.BASELINE_PATH))
    old = {key: baseline[key] for key in ("release_id", "release_label", "environment",
                                          "source_milestone", "fingerprint")}
    new = dict(old, release_id=BETA, release_label="PROD-BETA release of main",
               source_milestone="prod-beta", fingerprint="UCPE LIVE BUILD · PROD-BETA-20261002-A")
    edited = rel.set_guard_identity(repinned, old, new)
    assert f'    assert intended.release_id == "{BETA}"\n' in edited
    assert f'    assert intended.release_id == "{old["release_id"]}"\n' not in edited


def test_the_delta_definition_equals_the_guard_tests_own_mirror() -> None:
    from tests.scripts import test_source_integrity_guard as guard_test

    baseline = json.loads(_real(rel.BASELINE_PATH))
    assert rel.delta_in_tree(ROOT, baseline) == sorted(guard_test.CURRENT_DELTA_PATHS)


def test_asset_tokens_read_from_the_real_index_match_the_baseline() -> None:
    baseline = json.loads(_real(rel.BASELINE_PATH))
    assert rel.asset_tokens(_real("frontend/index.html")) == baseline["frontend_asset_tokens"]
    with pytest.raises(rel.Stop):
        rel.asset_tokens('<script src="/app.js?v=a"></script><script src="/app.js?v=b"></script>')


def test_the_committed_registry_is_consistent_and_ends_at_the_pin() -> None:
    registry = rel.load_registry(_real(rel.REGISTRY_PATH))
    baseline = json.loads(_real(rel.BASELINE_PATH))
    assert rel.canonical_json(registry) == _real(rel.REGISTRY_PATH)
    releases = registry["releases"]
    assert all(rel.SHA_RE.fullmatch(entry["commit"]) for entry in releases)
    assert all(rel.RELEASE_ID_RE.fullmatch(entry["release_id"]) for entry in releases)
    for previous, entry in zip(releases, releases[1:], strict=False):
        assert entry["deployed_over"] == previous["commit"], "each release follows the last"
    assert releases[-1]["commit"] == baseline["hf_main_sha"]
    assert releases[-1]["release_id"] == baseline["release_id"]
    assert releases[0]["h2_hold"] is False, "the pre-hold release is never safe"
    ids = [migration["id"] for migration in registry["migrations_applied"]]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    on_main = sorted(
        path.name[:4] for path in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")
    )
    assert ids == on_main, (
        "every migration on main is registered; the rollback check conservatively treats each as "
        "applied, so a new migration must say whether it is additive"
    )
    # An explicit "applied_run": null marks a migration authored on main but not yet applied
    # (0001-0007 predate apply tracking and carry no applied_run key at all). The 0014 apply
    # records its run and so empties this list; update it then.
    unapplied = [m for m in registry["migrations_applied"]
                 if "applied_run" in m and m["applied_run"] is None]
    assert [m["id"] for m in unapplied] == ["0014"]
    assert all(m["additive"] is True for m in unapplied), (
        "an authored, unapplied migration must be vouched additive, or merging it would block "
        "every H2-safe rollback"
    )


def test_the_config_names_no_local_path_secret_or_release_id() -> None:
    text = _real(rel.CONFIG_PATH)
    config = json.loads(text)
    assert set(config) == {"schema_version", "github_repo", "hf_remote", "base_url", "space_api",
                           "ci_workflow", "guard_workflow", "post_probe_paths"}
    # The only POST a settle may send is the automation route, which refuses without a credential.
    assert config["post_probe_paths"] == ["/v1/automation/radar-evidence"]
    assert "/Users/" not in text and "UCPE-PROD" not in text


def test_push_output_parsing_accepts_only_a_plain_fast_forward() -> None:
    older, newer = "a" * 40, "b" * 40
    good = f"To https://example.invalid/space\n   aaaaaaa..bbbbbbb  {newer} -> main\n"
    assert rel.push_is_fast_forward(good, older, newer)
    forced = good.replace("main\n", "main (forced update)\n")
    assert not rel.push_is_fast_forward(forced, older, newer)
    # A plain fast-forward line next to a forced update elsewhere is still refused.
    mixed = good + " + ccccccc...ddddddd  other -> other (forced update)\n"
    assert not rel.push_is_fast_forward(mixed, older, newer)
    assert not rel.push_is_fast_forward(good.replace("aaaaaaa", "ccccccc"), older, newer)
    assert not rel.push_is_fast_forward("Everything up-to-date\n", older, newer)


def test_evidence_never_keeps_url_credentials(tmp_path: Path) -> None:
    ev = rel.Evidence(tmp_path / "ev")
    ev.raw("push", 0, b"", b"To https://user:abc123@huggingface.co/spaces/x\n"
                          b"To https://tok@example.invalid/y\n")
    kept = (tmp_path / "ev" / "push.err").read_bytes()
    assert b"abc123" not in kept and b"tok@" not in kept
    assert b"https://***@huggingface.co/spaces/x" in kept
    with pytest.raises(rel.Stop):
        rel.Evidence(tmp_path / "ev")


def test_guard_checks_require_explicit_healthy_in_every_round() -> None:
    summary = {
        "final_classification": "HEALTHY", "per_round_classifications": ["HEALTHY"] * 3,
        "exit_code": 0, "hf_main_sha": "a" * 40, "pinned_hf_main_sha": "a" * 40,
        "live_release_id": ALPHA, "intended_release_id": ALPHA, "deployment_delta_paths": [],
    }
    checks = rel.guard_checks(summary, pin="a" * 40, release=ALPHA, delta=[])
    assert all(passed for passed, _ in checks)
    drifted = dict(summary, per_round_classifications=["HEALTHY", "PIN_DRIFT", "HEALTHY"])
    assert not all(passed for passed, _ in rel.guard_checks(drifted, pin="a" * 40, release=ALPHA,
                                                             delta=[]))


def test_the_h2_marker_check_rejects_the_rollback_switch() -> None:
    assert "LEGACY_PASS_LIFTS_HARD_BLOCK: bool = True" not in _real(rel.H2_HOLD_PATH)
    assert _real(rel.H2_HOLD_PATH).count(rel.H2_HOLD_MARKER + "\n") == 1


# --------------------------------------------------------------------------- rehearsal fixtures


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(cwd), "-c", "commit.gpgsign=false", *args],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _build_info(release_id: str) -> str:
    text = _real(rel.BUILD_INFO_PATH)
    current = rel.parse_identity(text)
    label, milestone = rel.default_label_and_milestone(release_id)
    for constant, old, new in (("RELEASE_ID", current["release_id"], release_id),
                               ("RELEASE_LABEL", current["release_label"], label),
                               ("SOURCE_MILESTONE", current["source_milestone"], milestone)):
        text = text.replace(f'{constant} = "{old}"', f'{constant} = "{new}"')
    return text


def _identity(release_id: str) -> dict[str, str]:
    return rel.parse_identity(_build_info(release_id))


def _guard_test(pin: str, identity: dict[str, str]) -> str:
    asserts = "".join(
        f'    assert intended.{key} == "{identity[key]}"\n'
        for key in ("release_id", "release_label", "environment", "source_milestone", "fingerprint")
    )
    return (
        f'PIN_SHA = "{pin}"\n'
        + rel.delta_block([], ["fixture"])
        + "\n\ndef test_identity(intended):\n"
        + asserts
    )


def _build_info_test(identity: dict[str, str]) -> str:
    return "".join(
        f'    assert payload["{key}"] == "{identity[key]}"\n'
        for key in ("release_id", "fingerprint", "source_milestone")
    )


def _baseline(root: Path, pin: str, identity: dict[str, str]) -> dict:
    return {
        "critical_source_digests": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in CRITICAL
        },
        "environment": identity["environment"],
        "fingerprint": identity["fingerprint"],
        "frontend_asset_tokens": {"app_js": "tok1", "styles_css": "tok1"},
        "hf_main_sha": pin,
        "release_id": identity["release_id"],
        "release_label": identity["release_label"],
        "schema_version": "hf-runtime-baseline.v1",
        "source_milestone": identity["source_milestone"],
    }


CONFIG = {
    "schema_version": "ucpe-release-config.v1",
    "github_repo": "owner/repo",
    "hf_remote": "hf",
    "base_url": "http://ucpe.test",
    "space_api": "http://hf.test/api/spaces/x",
    "ci_workflow": "CI",
    "guard_workflow": "guard.yml",
    "post_probe_paths": ["/v1/automation/radar-evidence"],
}


class World:
    """A deployed ALPHA release, its re-pin on main, and bare `origin` and `hf` remotes."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.work = tmp / "work"
        self.work.mkdir()
        _git(self.work, "init", "-q", "-b", "main")
        _git(self.work, "config", "user.name", "Fixture")
        _git(self.work, "config", "user.email", "fixture@example.invalid")
        alpha = _identity(ALPHA)
        for path in CRITICAL:
            if path not in (rel.BUILD_INFO_PATH, "frontend/index.html"):
                _write(self.work, path, f"stand-in for {path}\n")
        _write(self.work, "frontend/index.html",
               '<link href="/styles.css?v=tok1" />\n<script src="/app.js?v=tok1"></script>\n')
        _write(self.work, rel.BUILD_INFO_PATH, _build_info(ALPHA))
        _write(self.work, rel.BUILD_INFO_TEST_PATH, _build_info_test(alpha))
        _write(self.work, rel.H2_HOLD_PATH, f"# hold\n{rel.H2_HOLD_MARKER}\n")
        _write(self.work, "migrations/0001_init.sql", "-- init\n")
        _write(self.work, rel.CONFIG_PATH, _canonical(CONFIG))
        _write(self.work, rel.REGISTRY_PATH, _canonical({
            "schema_version": "ucpe-release-registry.v1",
            "releases": [],
            "migrations_applied": [
                {"id": "0001", "additive": None},
                {"id": "0011", "additive": True},
            ],
        }))
        _write(self.work, rel.GUARD_TEST_PATH, _guard_test("1" * 40, alpha))
        _write(self.work, rel.BASELINE_PATH, _canonical(_baseline(self.work, "1" * 40, alpha)))
        _git(self.work, "add", "-A")
        _git(self.work, "commit", "-q", "-m", "release alpha")
        self.c0 = _git(self.work, "rev-parse", "HEAD")
        # The alpha re-pin on main: baseline, guard test and registry name C0.
        _write(self.work, rel.BASELINE_PATH, _canonical(_baseline(self.work, self.c0, alpha)))
        _write(self.work, rel.GUARD_TEST_PATH, _guard_test(self.c0, alpha))
        registry = json.loads((self.work / rel.REGISTRY_PATH).read_text())
        registry["releases"].append({"commit": self.c0, "deployed_over": None, "h2_hold": True,
                                     "release_id": ALPHA})
        _write(self.work, rel.REGISTRY_PATH, _canonical(registry))
        _git(self.work, "commit", "-qam", "re-pin alpha")
        for name in ("origin", "hf"):
            bare = tmp / f"{name}.git"
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
            _git(self.work, "remote", "add", name, str(bare))
        _git(self.work, "push", "-q", "origin", "main")
        _git(self.work, "push", "-q", "hf", f"{self.c0}:refs/heads/main")
        self.clock = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
        self.http_map: dict[tuple[str, str], tuple[int, bytes]] = {}
        self.gh_ci: list[dict] = []
        self.gh_guard_latest: list[dict] = []
        self.gh_guard_log = ""
        self.gh_meta: dict = {}

    def env(self) -> rel.Env:
        return rel.Env(root=self.work, config=dict(CONFIG), run=self._run, http=self._http,
                       now=lambda: self.clock, sleep=lambda _seconds: None)

    def _http(self, method: str, url: str, body: bytes | None) -> tuple[int, bytes]:
        return self.http_map.get((method, url), (404, b"not found"))

    def _run(self, argv, extra_env=None):
        if argv[0] != "gh":
            return rel._run(argv, extra_env)
        if "--commit" in argv:
            return 0, json.dumps(self.gh_ci).encode(), b""
        if "--status" in argv:
            return 0, b"[]", b""
        if "--limit" in argv:
            return 0, json.dumps(self.gh_guard_latest).encode(), b""
        if "--log" in argv:
            return 0, self.gh_guard_log.encode(), b""
        if "--json" in argv:
            return 0, json.dumps(self.gh_meta).encode(), b""
        return 1, b"", b"unexpected gh call"

    def worktree(self, name: str, rev: str) -> Path:
        path = self.tmp / name
        _git(self.work, "worktree", "add", "-q", "--detach", str(path), rev)
        return path

    def hf_main(self) -> str:
        return _git(self.work, "ls-remote", "hf", "refs/heads/main").split("\t")[0]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return World(tmp_path)


def _summary_line(**fields: object) -> str:
    return "2026-10-02T09:00:00Z " + json.dumps(fields)


def _prepare_beta(world: World) -> str:
    """A guarded change, then the identity step and its commit: returns D."""

    _write(world.work, APP, "changed app\n")
    _write(world.work, "migrations/0011_new.sql", "-- additive\n")
    _git(world.work, "add", "-A")
    _git(world.work, "commit", "-q", "-m", "guarded change")
    tree = world.worktree("wt_identity", "HEAD")
    assert rel.main(["identity", "--worktree", str(tree), "--release-id", BETA], world.env()) == 0
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "release identity beta")
    d = _git(tree, "rev-parse", "HEAD")
    _git(world.work, "merge", "-q", "--ff-only", d)
    _git(world.work, "push", "-q", "origin", "main")
    return d


def _arm_preflight(world: World, d: str) -> None:
    alpha = _identity(ALPHA)
    world.gh_ci = [{"workflowName": "CI", "event": "push", "status": "completed",
                    "conclusion": "success", "headBranch": "main", "databaseId": 1}]
    world.gh_guard_latest = [{"databaseId": 9, "event": "workflow_dispatch", "status": "completed",
                              "conclusion": "success", "headBranch": "main", "headSha": d}]
    world.gh_guard_log = _summary_line(
        final_classification="HEALTHY", per_round_classifications=["HEALTHY"] * 3, exit_code=0,
        hf_main_sha=world.c0, pinned_hf_main_sha=world.c0, live_release_id=ALPHA,
        intended_release_id=ALPHA, deployment_delta_paths=[APP, rel.BUILD_INFO_PATH])
    world.http_map = {
        ("GET", CONFIG["space_api"]): (200, json.dumps({"runtime": {"stage": "RUNNING",
                                                                    "sha": world.c0}}).encode()),
        ("GET", CONFIG["base_url"] + "/v1/build-info"): (200, json.dumps(alpha).encode()),
        ("GET", CONFIG["base_url"] + "/healthcheck"): (200, b'{"status":"OK"}'),
    }


def _arm_settle(world: World, d: str, release_id: str = BETA) -> None:
    def blob(path: str) -> bytes:
        return subprocess.run(["git", "-C", str(world.work), "cat-file", "blob", f"{d}:{path}"],
                              capture_output=True, check=True).stdout

    base = CONFIG["base_url"]
    world.http_map = {
        ("GET", CONFIG["space_api"]): (200, json.dumps({"runtime": {"stage": "RUNNING",
                                                                    "sha": d}}).encode()),
        ("GET", base + "/healthcheck"): (200, b'{"status":"OK"}'),
        ("GET", base + "/v1/build-info"): (200, json.dumps(_identity(release_id)).encode()),
        ("GET", base + "/"): (200, blob("frontend/index.html")),
        ("GET", base + "/app.js?v=tok1"): (200, blob("frontend/app.js")),
        ("GET", base + "/styles.css?v=tok1"): (200, blob("frontend/styles.css")),
        ("POST", base + "/v1/automation/radar-evidence"): (
            503,
            b'{"error":{"code":"AUTOMATION_DISABLED"},"schema_version":"radar_evidence_error.v1"}',
        ),
    }


# ------------------------------------------------------------------------------------ rehearsal


def test_identity_sets_the_three_files_and_mirrors_the_guarded_delta(world: World) -> None:
    d = _prepare_beta(world)
    shown = subprocess.run(["git", "-C", str(world.work), "show", "--stat", "--format=", d],
                           capture_output=True, text=True, check=True).stdout
    assert rel.BUILD_INFO_PATH in shown and rel.BUILD_INFO_TEST_PATH in shown
    assert rel.GUARD_TEST_PATH in shown
    guard_text = (world.work / rel.GUARD_TEST_PATH).read_text()
    assert f'    "{APP}",\n    "{rel.BUILD_INFO_PATH}",\n]' in guard_text
    assert rel.parse_identity((world.work / rel.BUILD_INFO_PATH).read_text())["release_id"] == BETA


def test_identity_refuses_a_dirty_worktree_or_an_unchanged_release(world: World) -> None:
    tree = world.worktree("wt_dirty", "HEAD")
    _write(tree, "stray.txt", "x\n")
    assert rel.main(["identity", "--worktree", str(tree), "--release-id", BETA], world.env()) == 1
    clean = world.worktree("wt_same", "HEAD")
    assert rel.main(["identity", "--worktree", str(clean), "--release-id", ALPHA], world.env()) == 1


def test_the_full_release_chain_then_an_h2_safe_rollback(
    world: World, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d = _prepare_beta(world)
    _arm_preflight(world, d)

    # Preflight: an unreviewed runtime delta stops; the reviewed digest passes with the dry push.
    assert rel.main(["preflight", d, "--evidence-dir", str(tmp_path / "pf0")], world.env()) == 1
    digest = rel.delta_digest([APP, rel.BUILD_INFO_PATH])
    pf = tmp_path / "pf1"
    assert rel.main(["preflight", d, "--dry-push", "--accept-runtime-delta", digest,
                     "--evidence-dir", str(pf)], world.env()) == 0
    assert "PREFLIGHT=PASS" in (pf / "VERDICT").read_text()
    assert world.hf_main() == world.c0, "a preflight never moves the Space"

    # Deploy: a dry run by default; wrong authorization refuses; the exact one pushes once.
    assert rel.main(["deploy", d], world.env()) == 0
    assert world.hf_main() == world.c0
    capsys.readouterr()
    assert rel.main(["deploy", d, "--authorize", world.c0, "--release-id", BETA, "--preflight-dir",
                     str(pf)], world.env()) == 1
    assert "--authorize must repeat D exactly" in capsys.readouterr().err
    assert rel.main(["deploy", d, "--authorize", d, "--release-id", ALPHA, "--preflight-dir",
                     str(pf)], world.env()) == 1
    assert "--release-id is not the release identity at D" in capsys.readouterr().err
    assert world.hf_main() == world.c0, "a refused deploy pushes nothing"
    world.clock += timedelta(minutes=31)
    assert rel.main(["deploy", d, "--authorize", d, "--release-id", BETA, "--preflight-dir",
                     str(pf)], world.env()) == 1, "a stale preflight refuses"
    world.clock -= timedelta(minutes=31)
    assert rel.main(["deploy", d, "--authorize", d, "--release-id", BETA, "--preflight-dir",
                     str(pf), "--evidence-dir", str(tmp_path / "dep")], world.env()) == 0
    assert world.hf_main() == d
    capsys.readouterr()
    assert rel.main(["deploy", d, "--authorize", d, "--release-id", BETA, "--preflight-dir",
                     str(pf)], world.env()) == 1, "a consumed deploy never reruns"
    assert "already consumed" in capsys.readouterr().err

    # Settle: identity, bytes and the probe pass; the old identity or an error stage stops.
    _arm_settle(world, d)
    probe = "POST /v1/automation/radar-evidence 503 error.code=AUTOMATION_DISABLED"
    assert rel.main(["settle", d, "--probe", probe, "--evidence-dir", str(tmp_path / "s1")],
                    world.env()) == 0
    _arm_settle(world, d)
    world.http_map[("GET", CONFIG["base_url"] + "/app.js?v=tok1")] = (200, b"stale bytes")
    assert rel.main(["settle", d, "--evidence-dir", str(tmp_path / "s1b")], world.env()) == 1
    _arm_settle(world, d, release_id=ALPHA)
    assert rel.main(["settle", d, "--evidence-dir", str(tmp_path / "s2")], world.env()) == 1
    world.http_map[("GET", CONFIG["space_api"])] = (
        200, json.dumps({"runtime": {"stage": "BUILD_ERROR", "sha": d}}).encode())
    assert rel.main(["settle", d, "--evidence-dir", str(tmp_path / "s3")], world.env()) == 1

    # Re-pin: deterministic, exactly three files, the guard test and registry follow D.
    first, second = world.worktree("wt_repin1", d), world.worktree("wt_repin2", d)
    assert rel.main(["repin", d, "--worktree", str(first)], world.env()) == 0
    assert rel.main(["repin", d, "--worktree", str(second)], world.env()) == 0
    p = _git(first, "rev-parse", "HEAD")
    assert p == _git(second, "rev-parse", "HEAD"), "the re-pin commit is deterministic"
    files = _git(first, "show", "--name-only", "--format=", p).splitlines()
    assert sorted(files) == sorted([rel.BASELINE_PATH, rel.GUARD_TEST_PATH, rel.REGISTRY_PATH])
    baseline = json.loads((first / rel.BASELINE_PATH).read_text())
    assert baseline["hf_main_sha"] == d and baseline["release_id"] == BETA
    assert rel.delta_in_tree(first, baseline) == []
    guard_text = (first / rel.GUARD_TEST_PATH).read_text()
    assert f'PIN_SHA = "{d}"' in guard_text and "CURRENT_DELTA_PATHS: list[str] = []" in guard_text
    assert f'assert intended.release_id == "{BETA}"' in guard_text
    registry = json.loads((first / rel.REGISTRY_PATH).read_text())
    assert registry["releases"][-1] == {"commit": d, "deployed_over": world.c0, "h2_hold": True,
                                        "release_id": BETA}
    _git(world.work, "merge", "-q", "--ff-only", p)

    # Guard verify: explicit HEALTHY with delta [] passes; one drifted round stops.
    world.gh_meta = {"event": "workflow_dispatch", "status": "completed", "conclusion": "success",
                     "headBranch": "main", "headSha": p, "workflowName": "guard"}
    healthy = dict(final_classification="HEALTHY", per_round_classifications=["HEALTHY"] * 3,
                   exit_code=0, hf_main_sha=d, pinned_hf_main_sha=d, live_release_id=BETA,
                   intended_release_id=BETA, deployment_delta_paths=[])
    world.gh_guard_log = _summary_line(**healthy)
    verify = ["guard-verify", "7", "--expect-head", p, "--expect-pin", d, "--expect-release", BETA]
    assert rel.main(verify + ["--evidence-dir", str(tmp_path / "g1")], world.env()) == 0
    world.gh_guard_log = _summary_line(**dict(
        healthy, per_round_classifications=["HEALTHY", "PIN_DRIFT", "HEALTHY"]))
    assert rel.main(verify + ["--evidence-dir", str(tmp_path / "g2")], world.env()) == 1

    # Rollback: the registered, H2-safe ALPHA validates; a dry run moves nothing; the authorized
    # run moves the Space back under the lease, once.
    assert rel.main(["rollback-check", world.c0, "--evidence-dir", str(tmp_path / "r1")],
                    world.env()) == 0
    assert rel.main(["rollback", world.c0, "--evidence-dir", str(tmp_path / "r2")],
                    world.env()) == 0
    assert world.hf_main() == d
    authorized = ["rollback", world.c0, "--authorize", world.c0, "--expected-current", d,
                  "--release-id", ALPHA]
    assert rel.main(authorized + ["--evidence-dir", str(tmp_path / "r3")], world.env()) == 0
    assert world.hf_main() == world.c0
    assert rel.main(authorized, world.env()) == 1, "a consumed rollback never reruns"


def test_rollback_check_refuses_unsafe_targets(world: World, tmp_path: Path) -> None:
    d = _prepare_beta(world)
    _git(world.work, "push", "-q", "hf", f"{d}:refs/heads/main")
    env = world.env()
    # A commit that is not registered.
    assert rel.main(["rollback-check", d + "", "--evidence-dir", str(tmp_path / "a")], env) == 1
    # A registered release whose code lacks the hold.
    _write(world.work, rel.H2_HOLD_PATH, "# no hold here\n")
    _git(world.work, "commit", "-qam", "pre-hold stand-in")
    unsafe = _git(world.work, "rev-parse", "HEAD")
    registry = json.loads((world.work / rel.REGISTRY_PATH).read_text())
    registry["releases"].append({"commit": unsafe, "deployed_over": None, "h2_hold": True,
                                 "release_id": BETA})
    _write(world.work, rel.REGISTRY_PATH, _canonical(registry))
    findings = dict((text, ok) for ok, text in rel.rollback_findings(env, unsafe, d, registry))
    assert findings["the target carries the H2 fail-closed hold (registry and code agree)"] is False
    # A migration newer than the target that is not additive.
    registry = json.loads((world.work / rel.REGISTRY_PATH).read_text())
    registry["releases"] = registry["releases"][:1]
    registry["migrations_applied"][1]["additive"] = False
    results = rel.rollback_findings(env, world.c0, d, registry)
    assert [ok for ok, _ in results] == [True, True, True, True, False]
    # The target must be older than production.
    results = rel.rollback_findings(env, world.c0, world.c0, registry)
    assert results[3][0] is False


def test_repin_refuses_a_relabel_that_keeps_the_release_id(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (world.work / rel.BUILD_INFO_PATH).read_text()
    _write(world.work, rel.BUILD_INFO_PATH,
           text.replace('RELEASE_LABEL = "PROD-ALPHA release of main"',
                        'RELEASE_LABEL = "PROD-ALPHA relabelled"'))
    _git(world.work, "commit", "-qam", "relabel without a new release id")
    d = _git(world.work, "rev-parse", "HEAD")
    tree = world.worktree("wt_relabel", d)
    capsys.readouterr()
    assert rel.main(["repin", d, "--worktree", str(tree)], world.env()) == 1
    assert "same release id" in capsys.readouterr().err
    assert _git(tree, "rev-parse", "HEAD") == d, "nothing was committed"


def test_repin_refuses_when_the_release_id_did_not_change(world: World) -> None:
    _write(world.work, APP, "changed app only\n")
    _git(world.work, "commit", "-qam", "guarded change without identity")
    d = _git(world.work, "rev-parse", "HEAD")
    tree = world.worktree("wt_noid", d)
    assert rel.main(["repin", d, "--worktree", str(tree)], world.env()) == 1
    assert _git(tree, "rev-parse", "HEAD") == d, "nothing was committed"


@pytest.mark.parametrize(
    ("probe", "reason"),
    [
        ("POST /v1/auth/logout 401", "is not in post_probe_paths"),
        ("POST /v1/automation/radar-evidence/ 503", "is not in post_probe_paths"),
        ("GET @evil.example/x 200", "only a plain absolute path on base_url"),
        ("GET //evil.example/x 200", "only a plain absolute path on base_url"),
        ("GET https://evil.example/ 200", "only a plain absolute path on base_url"),
        ("GET /healthcheck#x 200", "only a plain absolute path on base_url"),
        ("DELETE /healthcheck 200", "use 'GET|POST /path STATUS"),
    ],
)
def test_settle_refuses_an_unsafe_probe_before_any_request_or_evidence(
    world: World, tmp_path: Path, capsys: pytest.CaptureFixture[str], probe: str, reason: str
) -> None:
    requests: list[tuple[str, str]] = []
    env = world.env()
    env.http = lambda method, url, body: requests.append((method, url)) or (404, b"")
    evidence = tmp_path / "settle"
    argv = ["settle", "a" * 40, "--probe", probe, "--evidence-dir", str(evidence)]
    assert rel.main(argv, env) == 1
    assert reason in capsys.readouterr().err
    assert requests == [] and not evidence.exists()


def test_a_listed_post_probe_and_a_plain_get_probe_parse() -> None:
    env = rel.Env(root=ROOT, config=dict(CONFIG), run=rel._run, http=lambda *a: (0, b""),
                  now=lambda: datetime.now(UTC), sleep=lambda _s: None)
    post = rel.parse_probe(env, "POST /v1/automation/radar-evidence 503 error.code=X")
    assert (post.method, post.path, post.expected, post.assertions) == (
        "POST", "/v1/automation/radar-evidence", 503, ("error.code=X",))
    assert rel.parse_probe(env, "GET /v1/build-info?x=1 200").path == "/v1/build-info?x=1"
    # Fail closed: a config without the list allows no POST probe at all.
    del env.config["post_probe_paths"]
    with pytest.raises(rel.Stop, match="is not in post_probe_paths"):
        rel.parse_probe(env, "POST /v1/automation/radar-evidence 503")
