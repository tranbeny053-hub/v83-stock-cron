"""P3-PRIV-R: the draft least-privilege roles, their rollback, the rehearsal and its workflow.

What a database is not needed for, checked here:
- the draft and its rollback are parsed and held to the rehearsal's own expected matrix, so the
  SQL, the harness and the design cannot drift apart;
- the harness's verdict logic, its JWT and its refusal to run anywhere but a scratch runner;
- the workflow's contract.
The database half runs in .github/workflows/privilege-rehearsal.yml, on scratch PostgreSQL behind a
real PostgREST.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path

import pytest

from scripts.privilege_rehearsal import rehearse

ROOT = Path(__file__).resolve().parents[2]
# Migration 0016 itself (owner ruling E1 = YES, W2), which the harness applies, and its rollback.
DRAFT = (ROOT / "migrations/0016_least_privilege_roles.sql").read_text()
ROLLBACK = (ROOT / "scripts/privilege_rehearsal/rollback_0016.sql").read_text()
FIXTURE = (ROOT / "scripts/privilege_rehearsal/00_supabase_like_authenticator.sql").read_text()
# Migration 0017 itself (owner ruling WB1 = YES, after 0016), which the harness applies after 0016,
# and its rollback.
DRAFT_0017 = (ROOT / "migrations/0017_forecast_bundle_rpc.sql").read_text()
ROLLBACK_0017 = (ROOT / "scripts/privilege_rehearsal/rollback_0017.sql").read_text()
WORKFLOW = (ROOT / ".github/workflows/privilege-rehearsal.yml").read_text(encoding="utf-8")


def statements(sql: str) -> list[str]:
    """The SQL's statements, comments dropped and whitespace collapsed (no DO body has a ';')."""

    body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    parts = re.split(r";\s*(?=\n|$)", re.sub(r"\$(\w*)\$.*?\$\1\$", "$$ $$", body, flags=re.S))
    return [" ".join(part.split()) for part in parts if part.strip()]


def table_grants(sql: str) -> dict[str, dict[str, set[str]]]:
    grants: dict[str, dict[str, set[str]]] = {}
    for statement in statements(sql):
        match = re.fullmatch(r"GRANT ([A-Z, ]+) ON TABLE (.+) TO (\w+)", statement)
        if match:
            privileges = {p.strip() for p in match.group(1).split(",")}
            for table in match.group(2).split(","):
                name = table.strip().removeprefix("public.")
                grants.setdefault(match.group(3), {}).setdefault(name, set()).update(privileges)
    return grants


def policies(sql: str, verb: str = "CREATE") -> set[tuple[str, str, str]]:
    found = set()
    for statement in statements(sql):
        if verb == "CREATE":
            match = re.fullmatch(
                r"CREATE POLICY (\w+) ON public\.(\w+) FOR (\w+) TO (\w+) (.+)", statement
            )
            if match:
                name, table, command, role, _ = match.groups()
                assert name == f"{role}_{command.lower()}", statement
                found.add((table, role, command))
        else:
            match = re.fullmatch(
                r"DROP POLICY (\w+)_(select|insert|update|delete) ON public\.(\w+)", statement
            )
            if match:
                found.add((match.group(3), match.group(1), match.group(2).upper()))
    return found


# ------------------------------------------------------------------------ the draft


def test_migration_0016_is_authored_with_its_route_and_is_what_the_harness_applies() -> None:
    """The rehearsed bytes are the migration's: the harness applies migrations/0016 itself."""

    assert "AUTHORED, NOT APPLIED" in DRAFT and "scripts/apply_migration_0016.py" in DRAFT
    assert "NOT A MIGRATION" not in DRAFT
    assert rehearse.DRAFT == ROOT / "migrations" / "0016_least_privilege_roles.sql"
    assert not (ROOT / "scripts/privilege_rehearsal/draft_0016_least_privilege_roles.sql").exists()


def test_a_second_application_is_refused_before_any_change() -> None:
    every = statements(DRAFT)
    assert every[0].startswith("DO $$"), "the refusal must come first"
    refusal = re.compile(
        r"IF EXISTS \(\s*SELECT 1 FROM pg_catalog\.pg_roles\s+WHERE rolname IN \("
        r"'ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver'\)\s*\) THEN\s+"
        r"RAISE EXCEPTION '[^']*a second application is refused'\s+USING ERRCODE = 'UP016';"
    )
    head = DRAFT.split("CREATE ROLE ucpe_api_writer", 1)[0]
    assert refusal.search(head), "the role-exists refusal must raise UP016, which P7 expects"
    for needed in ("authenticator", "CREATEROLE", "prosecdef"):
        assert needed in head, needed


def test_exactly_four_roles_none_with_any_power() -> None:
    created = re.findall(r"^CREATE ROLE (\w+) (.+);$", DRAFT, flags=re.M)
    assert [name for name, _ in created] == list(rehearse.NEW_ROLES)
    for _, attributes in created:
        assert attributes.split() == [
            "NOLOGIN",
            "NOINHERIT",
            "NOSUPERUSER",
            "NOCREATEDB",
            "NOCREATEROLE",
            "NOREPLICATION",
            "NOBYPASSRLS",
        ]


def test_every_table_grant_is_the_rehearsals_expected_matrix() -> None:
    expected = {
        role: {t: set(p) for t, p in tables.items()}
        for role, tables in rehearse.EXPECTED_TABLES.items()
    }
    assert table_grants(DRAFT) == expected


def test_every_grant_has_exactly_its_policies() -> None:
    assert policies(DRAFT) == rehearse.expected_policies()
    assert len(rehearse.expected_policies()) == 40


def test_nothing_existing_is_revoked_and_no_api_role_gains_anything() -> None:
    revokes = [s for s in statements(DRAFT) if s.startswith("REVOKE")]
    assert revokes == [
        "REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner",
        "REVOKE ucpe_bundle_owner FROM CURRENT_USER",
    ]
    for statement in statements(DRAFT):
        if statement.startswith("GRANT"):
            assert not re.search(r"\bTO (PUBLIC|anon|authenticated|service_role)\b", statement), (
                statement
            )


def test_the_only_powers_beyond_rows_are_the_writers_watchlist_delete() -> None:
    for role, tables in table_grants(DRAFT).items():
        for table, privileges in tables.items():
            assert not privileges & {"TRUNCATE", "TRIGGER", "REFERENCES", "MAINTAIN", "ALL"}
            if "DELETE" in privileges:
                assert (role, table) == ("ucpe_api_writer", "watchlist")


def test_the_writer_has_no_direct_write_to_core_evidence() -> None:
    writer = table_grants(DRAFT)["ucpe_api_writer"]
    for core in (
        "predictions",
        "prediction_feature_snapshots",
        "prediction_derivatives_snapshots",
        "prediction_outcomes",
    ):
        assert writer.get(core, set()) <= {"SELECT"}, core


def test_the_bundle_rpc_becomes_definer_owned_by_its_narrow_owner_with_temporary_powers() -> None:
    every = statements(DRAFT)
    function = "public.save_prediction_bundle(jsonb, jsonb, jsonb)"
    order = [
        f"GRANT EXECUTE ON FUNCTION {function} TO ucpe_api_writer",
        f"ALTER FUNCTION {function} SECURITY DEFINER",
        "GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE",
        "GRANT CREATE ON SCHEMA public TO ucpe_bundle_owner",
        f"ALTER FUNCTION {function} OWNER TO ucpe_bundle_owner",
        "REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner",
        "REVOKE ucpe_bundle_owner FROM CURRENT_USER",
    ]
    positions = [every.index(statement) for statement in order]
    assert positions == sorted(positions) and positions[-1] - positions[0] == len(order) - 1
    assert [s for s in every if "SECURITY DEFINER" in s] == [order[1]]
    assert "CREATE OR REPLACE FUNCTION" not in DRAFT, "the body is unchanged"


def test_authenticator_may_switch_to_the_writer_only() -> None:
    memberships = [s for s in statements(DRAFT) if re.fullmatch(r"GRANT ucpe_\w+ TO \w+.*", s)]
    assert memberships == [
        "GRANT ucpe_api_writer TO authenticator WITH INHERIT FALSE, SET TRUE",
        "GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE",
    ]


def test_every_table_is_schema_qualified() -> None:
    for statement in statements(DRAFT) + statements(ROLLBACK):
        for match in re.finditer(r"\bON (?:TABLE |SEQUENCE )?(\w+(?:\.\w+)?)", statement):
            if match.group(1) not in ("SCHEMA", "FUNCTION"):
                assert match.group(1).startswith("public."), statement


# ------------------------------------------------------------------------ the rollback


def test_the_rollback_drops_exactly_the_drafts_policies_and_roles() -> None:
    assert policies(ROLLBACK, "DROP") == policies(DRAFT)
    assert "DROP ROLE ucpe_api_writer, ucpe_bundle_owner, ucpe_space_db, ucpe_resolver;" in ROLLBACK
    assert "REVOKE ucpe_api_writer FROM authenticator;" in ROLLBACK


def test_the_rollback_returns_the_rpc_before_revoking_the_writers_execute() -> None:
    every = statements(ROLLBACK)
    function = "public.save_prediction_bundle(jsonb, jsonb, jsonb)"
    owner = every.index(f"ALTER FUNCTION {function} OWNER TO CURRENT_USER")
    invoker = every.index(f"ALTER FUNCTION {function} SECURITY INVOKER")
    execute = every.index(f"REVOKE EXECUTE ON FUNCTION {function} FROM ucpe_api_writer")
    assert owner < invoker < execute
    assert "DELETE FROM" not in ROLLBACK and "TRUNCATE" not in ROLLBACK, "evidence is never deleted"


# ------------------------------------------------------------------------ the fixture


def test_the_fixture_mirrors_supabases_authenticator_with_no_password_on_a_command_line() -> None:
    assert "\\getenv authenticator_password PRIVILEGE_REHEARSAL_AUTHENTICATOR_PASSWORD" in FIXTURE
    assert "CREATE ROLE authenticator LOGIN NOINHERIT;" in FIXTURE
    assert (
        "GRANT anon, authenticated, service_role TO authenticator WITH INHERIT FALSE, SET TRUE;"
        in FIXTURE
    )
    assert 'ALTER ROLE :"owner" CREATEROLE;' in FIXTURE and "SUPERUSER" not in FIXTURE


# ------------------------------------------------------------------------ the harness


def test_matrix_differences_name_missing_and_extra_privileges() -> None:
    observed = {"r": {"a": {"SELECT", "DELETE"}}}
    expected = {"r": {"a": frozenset({"SELECT", "INSERT"})}}
    assert rehearse.matrix_differences(observed, expected, ("r",), ("a", "b")) == [
        "r on a: missing ['INSERT'], extra ['DELETE']"
    ]
    assert rehearse.matrix_differences(expected, expected, ("r",), ("a",)) == []


def test_only_an_insufficient_privilege_counts_as_a_refusal() -> None:
    assert rehearse.refused({"refused": "42501", "served": None, "typo": "42601"}) == [
        "served",
        "typo",
    ]


def test_maintain_is_checked_from_postgresql_17() -> None:
    assert "MAINTAIN" not in rehearse.table_privileges(160015)
    assert rehearse.table_privileges(170006)[-1] == "MAINTAIN"


def test_the_jwt_is_hs256_names_its_role_and_expires() -> None:
    key = "k" * 40
    header, claims, signature = rehearse.mint_jwt("ucpe_api_writer", key, now=1000).split(".")

    def decode(part: str) -> dict:
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

    assert decode(header) == {"alg": "HS256", "typ": "JWT"}
    assert decode(claims) == {"role": "ucpe_api_writer", "iat": 1000, "exp": 1900}
    digest = hmac.new(key.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == signature


def test_every_criterion_must_pass() -> None:
    passing = {name: {"verdict": "PASS"} for name in rehearse.CRITERIA}
    assert rehearse.unmet(passing) == []
    assert rehearse.unmet({**passing, "P4": {"verdict": "FAIL"}}) == ["P4"]
    assert rehearse.unmet({}) == list(rehearse.CRITERIA)


@pytest.mark.parametrize(
    ("variable", "owner_url", "postgrest_url"),
    [
        (
            "SUPABASE_DB_URL",
            "postgresql:///privilege_rehearsal?host=/var/run/postgresql",
            "http://127.0.0.1:3000",
        ),
        (None, "postgresql://user@db.example.invalid:5432/postgres", "http://127.0.0.1:3000"),
        (
            None,
            "postgresql:///privilege_rehearsal?host=/var/run/postgresql",
            "https://project.example.invalid",
        ),
    ],
)
def test_it_refuses_anything_but_a_scratch_runner(
    monkeypatch, variable, owner_url, postgrest_url
) -> None:
    for name in rehearse.FORBIDDEN_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    if variable:
        monkeypatch.setenv(variable, "present")
    with pytest.raises(SystemExit, match="REFUSED"):
        rehearse._require_scratch(owner_url, postgrest_url)


def test_it_accepts_the_scratch_runner(monkeypatch) -> None:
    for name in rehearse.FORBIDDEN_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    rehearse._require_scratch(
        "postgresql:///privilege_rehearsal?host=/var/run/postgresql", "http://127.0.0.1:3000"
    )


# ------------------------------------------------------------------------ the workflow


def test_the_workflow_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in WORKFLOW
    for forbidden in (
        "push:",
        "schedule",
        "workflow_dispatch",
        "secrets.",
        "SUPABASE",
        "environment:",
        "set -x",
    ):
        assert forbidden not in WORKFLOW, forbidden
    assert "permissions:\n  contents: read\n" in WORKFLOW
    for path in (
        "scripts/privilege_rehearsal/**",
        "scripts/core_write_inventory.py",  # D1-D4 run the inventory
        "migrations/**",
        "src/crypto_probability_engine/persistence/**",
        "src/crypto_probability_engine/automation/**",
        "src/crypto_probability_engine/resolution/**",
        "src/crypto_probability_engine/api/analysis_service.py",
        ".github/workflows/privilege-rehearsal.yml",
    ):
        assert f"      - {path}\n" in WORKFLOW, path


def test_postgrest_is_two_pinned_release_binaries_checked_by_sha256() -> None:
    pins = re.findall(r"- postgrest: (v[0-9.]+)\n\s+sha256: ([0-9a-f]{64})\n", WORKFLOW)
    assert [version for version, _ in pins] == ["v14.18", "v16.4"]
    assert 'echo "${POSTGREST_SHA256}  $RUNNER_TEMP/$archive" | sha256sum -c -' in WORKFLOW
    assert (
        "https://github.com/PostgREST/postgrest/releases/download/${POSTGREST_VERSION}/" in WORKFLOW
    )


def test_the_database_is_every_migration_before_0016_and_no_scratch_value_on_a_command_line() -> (
    None
):
    # The harness applies migration 0016 itself, then migration 0017.
    earlier = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0016"
    )
    assert len(earlier) == 15
    assert f'cat {" ".join(earlier)} > "$RUNNER_TEMP/migrations_0001_0015.sql"' in WORKFLOW
    assert 'PRIVILEGE_REHEARSAL_AUTHENTICATOR_PASSWORD="$(openssl rand -hex 24)"' in WORKFLOW
    assert 'PGRST_JWT_SECRET="$(openssl rand -hex 32)"' in WORKFLOW
    assert "--preserve-env=PRIVILEGE_REHEARSAL_AUTHENTICATOR_PASSWORD -u postgres psql" in WORKFLOW
    assert "-v authenticator_password" not in WORKFLOW


def test_every_criterion_is_a_gate_and_the_report_is_uploaded_always() -> None:
    assert (
        "PYTHONPATH=src python scripts/privilege_rehearsal/rehearse.py "
        '--report="privilege-rehearsal-report-${POSTGREST_VERSION}.json" --require-all'
    ) in WORKFLOW
    upload = WORKFLOW.split("      - name: Upload the rehearsal report\n", 1)[1]
    assert "        if: always()\n" in upload
    assert "          path: privilege-rehearsal-report-${{ matrix.postgrest }}.json\n" in upload


# ------------------------------------------------------------------------ W-A: migration 0017


WIDE = "public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)"


def test_migration_0017_is_authored_with_its_route_and_refuses_a_second_application() -> None:
    """The rehearsed bytes are the migration's: the harness applies migrations/0017 itself."""

    assert "AUTHORED, NOT APPLIED" in DRAFT_0017 and "scripts/apply_migration_0017.py" in DRAFT_0017
    assert "WB1 = YES, after 0016" in DRAFT_0017 and "NOT A MIGRATION" not in DRAFT_0017
    assert rehearse.DRAFT_0017 == ROOT / "migrations" / "0017_forecast_bundle_rpc.sql"
    assert rehearse.ROLLBACK_0017 == ROOT / "scripts/privilege_rehearsal/rollback_0017.sql"
    for retired in ("draft_0017_forecast_bundle_rpc.sql", "rollback_draft_0017.sql"):
        assert not (ROOT / "scripts/privilege_rehearsal" / retired).exists(), retired
    every = statements(DRAFT_0017)
    assert every[0].startswith("DO $$"), "the refusal must come first"
    head = DRAFT_0017.split("CREATE FUNCTION", 1)[0]
    assert re.search(
        r"RAISE EXCEPTION '[^']*already exists; a second application is refused'\s+"
        r"USING ERRCODE = 'UP017';",
        head,
    ), "the already-exists refusal must raise UP017, which W9 expects"
    assert "o.rolname = 'ucpe_bundle_owner'" in head, "it needs 0016 with W2"


def test_one_definer_function_with_a_fixed_search_path_and_only_two_callers() -> None:
    every = statements(DRAFT_0017)
    created = [s for s in every if s.startswith("CREATE FUNCTION")]
    assert len(created) == 1
    assert "SECURITY DEFINER SET search_path = pg_catalog, pg_temp" in created[0]
    assert "CREATE OR REPLACE" not in DRAFT_0017, "0015's function is reused, never redefined"
    assert f"REVOKE ALL ON FUNCTION {WIDE} FROM PUBLIC, anon, authenticated" in every
    grants = [s for s in every if s.startswith("GRANT EXECUTE")]
    assert grants == [f"GRANT EXECUTE ON FUNCTION {WIDE} TO ucpe_api_writer, service_role"]


def test_it_reuses_0015_and_rolls_back_its_own_writes_on_any_refusal() -> None:
    body = DRAFT_0017.split("$function$")[1]
    assert "bundle := public.save_prediction_bundle(p_prediction, p_feature_snapshot," in body
    assert (
        body.count("RAISE EXCEPTION 'save_forecast_bundle: refused' USING ERRCODE = 'UB9C1'") == 3
    )
    assert "WHEN SQLSTATE 'UB9C1' THEN" in body and "'refused', true" in body
    for verb in ("UPDATE public.", "DELETE FROM", "TRUNCATE"):
        assert verb not in body, verb


def test_the_run_keys_are_productions_run_summary_and_only_persistence_status_is_not_compared() -> (
    None
):
    from crypto_probability_engine.api.analysis_service import _run_summary

    keys = re.search(r"run_keys CONSTANT text\[\] := ARRAY\[(.*?)\];", DRAFT_0017, flags=re.S)
    run_keys = set(re.findall(r"'(\w+)'", keys.group(1)))
    assert run_keys == set(_run_summary({}))
    compared = re.search(
        r"IF ROW\((\s*stored_run\..*?)\) IS NOT DISTINCT FROM", DRAFT_0017, flags=re.S
    ).group(1)
    stored = set(re.findall(r"stored_run\.(\w+)", compared))
    assert stored == run_keys - {"run_id", "persistence_status"}
    detail = re.search(r"detail_keys CONSTANT text\[\] := ARRAY\[(.*?)\];", DRAFT_0017).group(1)
    assert set(re.findall(r"'(\w+)'", detail)) == {"run_id", "analysis_hash", "detail_payload"}


def test_its_narrow_owner_only_inserts_and_reads_the_run_and_detail_with_policies() -> None:
    assert table_grants(DRAFT_0017) == {
        "ucpe_bundle_owner": {
            "analysis_runs": {"SELECT", "INSERT"},
            "analysis_run_details": {"SELECT", "INSERT"},
        }
    }
    assert policies(DRAFT_0017) == rehearse.wide_expected_policies() - rehearse.expected_policies()
    assert {table: set(privileges) for table, privileges in rehearse.WIDE_OWNER_TABLES.items()} == {
        **{t: set(p) for t, p in rehearse.EXPECTED_TABLES["ucpe_bundle_owner"].items()},
        **table_grants(DRAFT_0017)["ucpe_bundle_owner"],
    }
    assert "UPDATE" not in " ".join(s for s in statements(DRAFT_0017) if s.startswith("GRANT"))


def test_the_owner_change_uses_the_same_temporary_powers_as_0016() -> None:
    every = statements(DRAFT_0017)
    order = [
        "GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE",
        "GRANT CREATE ON SCHEMA public TO ucpe_bundle_owner",
        f"ALTER FUNCTION {WIDE} OWNER TO ucpe_bundle_owner",
        "REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner",
        "REVOKE ucpe_bundle_owner FROM CURRENT_USER",
    ]
    positions = [every.index(statement) for statement in order]
    assert positions == sorted(positions) and positions[-1] - positions[0] == len(order) - 1


def test_the_wider_rollback_removes_exactly_what_migration_0017_added() -> None:
    every = statements(ROLLBACK_0017)
    assert f"DROP FUNCTION {WIDE}" in every
    assert policies(ROLLBACK_0017, "DROP") == policies(DRAFT_0017)
    assert (
        "REVOKE SELECT, INSERT ON TABLE public.analysis_runs, public.analysis_run_details "
        "FROM ucpe_bundle_owner"
    ) in every
    assert "DELETE FROM" not in ROLLBACK_0017 and "TRUNCATE" not in ROLLBACK_0017


def test_the_harness_gates_every_wider_criterion() -> None:
    assert rehearse.WIDE_CRITERIA == (
        "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10"
    )
    assert set(rehearse.WIDE_CRITERIA) <= set(rehearse.CRITERIA)


# ------------------------------------------------------------------------ E3: J1, the signing key


def test_j1_is_a_gate_run_on_the_applied_0017_before_its_rollback() -> None:
    assert rehearse.CRITERIA[rehearse.CRITERIA.index("J1") + 1:] == rehearse.D6_CRITERIA
    source = Path(rehearse.__file__).read_text(encoding="utf-8")
    run = source.split("\ndef run(", 1)[1]
    assert run.index('criteria["W10"]') < run.index('criteria["J1"] = _guarded(') < run.index(
        "rolled_0017 = db.apply(ROLLBACK_0017)")
    assert 'criteria["J1"] = verdict(["the ES256 PostgREST of E3 is not configured"])' in run
    assert 'for name in (*WIDE_CRITERIA, "J1", *D6_CRITERIA):' in run, "0017 not applying fails J1"


def test_d6_runs_on_the_applied_0017_and_is_rolled_back_before_it() -> None:
    """D1-D4 (the owner's D6 ruling): the draft of migration 0018 on top of 0017, then its rollback,
    and only then 0017's own one-shot and rollback."""

    assert rehearse.D6_CRITERIA == ("D1", "D2", "D3", "D4")
    source = Path(rehearse.__file__).read_text(encoding="utf-8")
    run = source.split("\ndef run(", 1)[1]
    assert run.index('criteria["J1"] = _guarded(') < run.index("criteria.update(criteria_d6(") < (
        run.index("second_0017 = db.apply(DRAFT_0017)"))
    assert rehearse.DRAFT_0018.parent == rehearse.HERE, "a draft, never in migrations/"
    d6 = source.split("def criteria_d6(", 1)[1].split("\ndef ", 1)[0]
    for step in ("d6_inventory(db, version)", "db.apply(DRAFT_0018)", "db.apply(ROLLBACK_0018)",
                 'second == "UP018"', "inventory.every_surface(after)", 'answer[1] != "42501"',
                 "persist_through_forecast(writer()[0], work)"):
        assert step in d6, step
    assert set(rehearse.D6_PROBES) == {"F", "V", "R", "G", "K", "C"}
    assert '"draft_0018_sha256"' in source and '"rollback_0018_sha256"' in source


def test_j1_expects_the_documented_acceptances_and_refusals() -> None:
    source = Path(rehearse.__file__).read_text(encoding="utf-8")
    j1 = source.split("def criterion_signing_key(", 1)[1].split("\ndef ", 1)[0]
    assert '!= (200, 403)' in j1, "the writer reads runs and is refused outcomes"
    for refusal in ("unknown_kid", "tampered_signature", "another_key_same_kid", "expired",
                    "hs256_secret"):
        assert f'"{refusal}":' in j1, refusal
    assert "if code != 401" in j1
    assert 'es256.mint(key_file, "service_role"), "prediction_outcomes"' in j1
    assert "persist_through_forecast(writer(token), work)" in j1
    assert "token = writer_signing_key.writer_token(key_file, kid=es256.KID)" in j1, (
        "J1 proves the token the owner mints (scripts/writer_signing_key.py)"
    )


@pytest.mark.parametrize("name", rehearse.ES256_ENVIRONMENT[:2])
def test_the_es256_postgrest_must_be_the_local_scratch_one(monkeypatch, name: str) -> None:
    for forbidden in rehearse.FORBIDDEN_ENVIRONMENT:
        monkeypatch.delenv(forbidden, raising=False)
    monkeypatch.setenv(name, "https://project.supabase.co")
    with pytest.raises(SystemExit, match="must be the local scratch PostgREST"):
        rehearse._require_scratch(
            "postgresql:///privilege_rehearsal?host=/var/run/postgresql", "http://127.0.0.1:3000"
        )


def test_the_workflow_runs_a_second_postgrest_that_trusts_only_the_scratch_es256_key() -> None:
    key = '"$RUNNER_TEMP/scratch-es256.pem"'
    assert f"openssl ecparam -name prime256v1 -genkey -noout -out {key}" in WORKFLOW
    assert (f'PGRST_JWT_SECRET="$(python scripts/privilege_rehearsal/es256.py {key})"'
            in WORKFLOW)
    assert "PGRST_SERVER_PORT=3002" in WORKFLOW and "PGRST_ADMIN_SERVER_PORT=3003" in WORKFLOW
    assert 'PRIVILEGE_REHEARSAL_ES256_POSTGREST_URL="http://127.0.0.1:3002"' in WORKFLOW
    assert 'PRIVILEGE_REHEARSAL_ES256_POSTGREST_ADMIN_URL="http://127.0.0.1:3003"' in WORKFLOW
    assert f"PRIVILEGE_REHEARSAL_ES256_KEY_FILE={key}" in WORKFLOW
    for leak in ("cat \"$RUNNER_TEMP/scratch-es256.pem\"", "scratch-es256.pem\" |"):
        assert leak not in WORKFLOW, "the private key is never printed or piped"


def test_w10_runs_the_released_writer_on_the_applied_0017_before_its_rollback() -> None:
    source = Path(rehearse.__file__).read_text(encoding="utf-8")
    run = source.split("\ndef run(", 1)[1]
    wired = 'criteria["W10"] = _guarded(lambda: criterion_production_writer(db, writer, rest))'
    assert run.index("criteria_wide_bundle(") < run.index(wired) < run.index(
        "rolled_0017 = db.apply(ROLLBACK_0017)")
    # E4: the API key and the writer's JWT apart, and only booleans about them in the report.
    assert "publishable_key=publishable, writer_jwt=jwt" in run
    assert 'request.headers.get("apikey") == publishable' in run


def test_p2_p6_and_p8_keep_the_w_b_writer_and_w10_the_released_one() -> None:
    class Released:
        def save_forecast_bundle(self) -> str:
            return "W-A"

        def circuit_state(self) -> str:
            return "CLOSED"

    view = rehearse.B9Writer(Released())
    assert not hasattr(view, "save_forecast_bundle"), "the W-B path, as the live app persists"
    assert view.circuit_state() == "CLOSED", "everything else goes straight through"
    source = Path(rehearse.__file__).read_text(encoding="utf-8")
    p2 = source.split("def criterion_writer(", 1)[1].split("\ndef ", 1)[0]
    w10 = source.split("def criterion_production_writer(", 1)[1].split("\ndef ", 1)[0]
    assert "persist_through_rest(" in p2 and "persist_through_forecast(" not in p2
    assert "persist_through_forecast(" in w10 and "persist_through_rest(" not in w10


def test_r1_proves_the_resolver_login_the_owner_s_helper_makes() -> None:
    """G1: every rehearsed login stores the helper's SCRAM secret, never the password, and R1 logs
    in through the helper's own URL builder and is refused with a wrong password."""

    source = Path(rehearse.__file__).read_text(encoding="utf-8")
    assert rehearse.CRITERIA.index("R1") == rehearse.CRITERIA.index("P8") + 1
    grant = source.split("    def grant_login(", 1)[1].split("\n    def ", 1)[0]
    assert "from scripts.resolver_credential import scram_verifier" in grant
    assert "sql.Literal(scram_verifier(value))" in grant and "sql.Literal(value)" not in grant
    r1 = source.split("def criterion_resolver_login(", 1)[1].split("\ndef ", 1)[0]
    assert "resolver_credential.build_url(" in r1
    assert '"wrong_password": login("not-" + db.logins["ucpe_resolver"])' in r1
    assert 'steps["wrong_password"] == "REFUSED"' in r1
    assert 'criteria["R1"] = _guarded(lambda: criterion_resolver_login(db))' in source
