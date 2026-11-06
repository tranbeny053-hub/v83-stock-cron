import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops/ng4_pilot/workflows"


def test_workflows_are_dormant_and_have_pinned_trust_boundary():
    paths = [OPS / "ng4-pilot-preflight.yml", OPS / "apply-migration-0019.yml"]
    assert all(".github/workflows" not in p.parts for p in paths)
    refs = set()
    for path in paths:
        text = path.read_text()
        assert "AUTHORED BUT DISABLED" in text
        assert '"on":\n  workflow_dispatch:' in text
        assert not re.search(r"^\s*(schedule|push|pull_request|workflow_call):", text, re.M)
        assert "permissions:\n  contents: read" in text
        assert "group: section-5a-evaluation" in text
        assert "environment: production-db-owner" in text
        assert all(
            "shell: bash" in line for line in text.splitlines() if line.strip().startswith("shell:")
        )
        refs.update(re.findall(r"uses:\s*([^\s]+)", text))
        assert "${{ secrets.SUPABASE_DB_URL }}" in text
        assert text.count("${{ secrets.SUPABASE_DB_URL }}") == 1
        assert "expected_sha:" in text
        assert ("confirm:" in text) == (path.name == "apply-migration-0019.yml")
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in refs)
    assert len(refs) == 3


def test_route_headers_describe_ng4_checks_not_0018_checks():
    preflight = (OPS / "ng4-pilot-preflight.yml").read_text().split('"on":', 1)[0]
    apply = (OPS / "apply-migration-0019.yml").read_text().split('"on":', 1)[0]
    forbidden = r"\b(?:service_role|bundle|D6|0016 and 0017|0001-0004)\b"
    assert not re.search(forbidden, preflight, re.I)
    assert not re.search(forbidden, apply, re.I)
    assert "ucpe_lattice" in preflight and "READ ONLY" in preflight
    assert "ucpe_lattice" in apply and "migration_0019_capacity.sql" in apply
    for header in (preflight, apply):
        assert "AUTHORED BUT DISABLED" in header
        assert "renames this file into .github/workflows unchanged" in header
        assert "production-db-owner" in header
        assert "section-5a-evaluation" in header
        assert "Only the" in header and "database secret" in header
