from pathlib import Path

import pytest

from scripts.migration_0019_rehearsal.run_authored_steps import extract

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "marker", ["secrets.X", "inputs.x", "--mode=run", "--mode=apply", "SUPABASE_DB_URL"]
)
def test_refuses_unsafe_steps(tmp_path, marker):
    p = tmp_path / "x.yml"
    p.write_text(f"jobs:\n  x:\n    steps:\n      - name: target\n        run: echo {marker}\n")
    with pytest.raises(ValueError):
        extract(p, "target")


def test_real_authored_scratch_blocks_are_extracted_byte_exactly():
    for wf, name in (
        ("ng4-pilot-preflight.yml", "Rehearse preflight on scratch PostgreSQL (no secret)"),
        (
            "apply-migration-0019.yml",
            "Rehearse the apply on a scratch local PostgreSQL database (no secret)",
        ),
    ):
        run, env = extract(ROOT / "ops/ng4_pilot/workflows" / wf, name)
        assert run.startswith("sudo systemctl start postgresql.service")
        assert "postgresql:///" in next(iter(env.values()))
