from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "PHASE_2D3B_READINESS_PROOF.md"
SQL_PATH = ROOT / "sql/phase_2d3b_readiness_proof.sql"
TEST_PATH = ROOT / "tests/docs/test_phase_2d3b_readiness_proof.py"
WORKFLOW_PATH = ROOT / ".github/workflows/derivatives-evidence-cadence.yml"
NORMALIZER_PATH = ROOT / "src/crypto_probability_engine/normalizers/symbols.py"
ANALYSIS_PATH = ROOT / "src/crypto_probability_engine/api/analysis_service.py"
PERSISTENCE_TEST_PATH = ROOT / "tests/persistence/test_derivatives_snapshots.py"


def _code_only(sql: str) -> str:
    """Replace comments and quoted values while retaining executable structure."""

    output: list[str] = []
    index = 0
    state = "code"
    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "code":
            if char == "-" and following == "-":
                output.extend("  ")
                index += 2
                state = "line_comment"
                continue
            if char == "/" and following == "*":
                output.extend("  ")
                index += 2
                state = "block_comment"
                continue
            if char == "'":
                output.append(" ")
                index += 1
                state = "single_quote"
                continue
            if char == '"':
                output.append(" ")
                index += 1
                state = "double_quote"
                continue
            output.append(char)
            index += 1
            continue
        if state == "line_comment":
            output.append("\n" if char == "\n" else " ")
            index += 1
            if char == "\n":
                state = "code"
            continue
        if state == "block_comment":
            if char == "*" and following == "/":
                output.extend("  ")
                index += 2
                state = "code"
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue
        quote = "'" if state == "single_quote" else '"'
        if char == quote and following == quote:
            output.extend("  ")
            index += 2
        elif char == quote:
            output.append(" ")
            index += 1
            state = "code"
        else:
            output.append("\n" if char == "\n" else " ")
            index += 1
    assert state == "code", "SQL contains an unterminated comment or quoted value"
    return "".join(output)


def _statements(sql: str) -> list[str]:
    return [statement.strip() for statement in _code_only(sql).split(";") if statement.strip()]


def _top_level_select_count(statement: str) -> int:
    depth = 0
    count = 0
    for token in re.findall(r"[A-Za-z_]+|[()]", statement):
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            assert depth >= 0
        elif token.upper() == "SELECT" and depth == 0:
            count += 1
    assert depth == 0
    return count


def test_governed_packet_files_exist() -> None:
    assert DOC_PATH.is_file()
    assert SQL_PATH.is_file()
    assert TEST_PATH.is_file()


def test_sql_transaction_is_explicitly_repeatable_read_and_read_only() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert sql.startswith("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;\n")
    assert sql.rstrip().endswith("ROLLBACK;")
    assert "txn_read_only" in sql
    assert "txn_isolation" in sql


def test_sql_has_one_result_producing_top_level_select() -> None:
    statements = _statements(SQL_PATH.read_text(encoding="utf-8"))

    assert [statement.split(maxsplit=1)[0].upper() for statement in statements] == [
        "BEGIN",
        "WITH",
        "ROLLBACK",
    ]
    assert _top_level_select_count(statements[1]) == 1


def test_sql_contains_no_executable_mutation_or_ddl() -> None:
    code = _code_only(SQL_PATH.read_text(encoding="utf-8"))
    forbidden = (
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "COPY",
        "CALL",
        "DO",
        "LOCK",
    )

    assert re.search(rf"(?im)^\s*(?:{'|'.join(forbidden)})\b", code) is None
    assert re.search(r"(?im)^\s*SET\s+ROLE\b", code) is None


def test_sql_contains_no_credentials_urls_or_secret_patterns() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    patterns = (
        r"postgres(?:ql)?://",
        r"https?://",
        r"password\s*=",
        r"api[_-]?key",
        r"secret\s*=",
        r"supabase_db_url",
    )

    for pattern in patterns:
        assert re.search(pattern, sql, flags=re.IGNORECASE) is None


def test_sql_reports_and_gates_both_tables_authoritatively() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    required = {
        "current_role_is_superuser",
        "current_role_bypasses_rls",
        "predictions_owner",
        "predictions_current_role_is_owner",
        "predictions_rls_enabled",
        "predictions_rls_forced",
        "predictions_policy_count",
        "pds_owner",
        "pds_current_role_is_owner",
        "pds_rls_enabled",
        "pds_rls_forced",
        "pds_policy_count",
        "authoritative_visibility",
    }

    assert required <= set(re.findall(r"'([a-z0-9_]+)'\s*,", sql))
    assert "rs.predictions_owner = cr.current_user_name" in sql
    assert "rs.pds_owner = cr.current_user_name" in sql
    assert "NOT rs.predictions_rls_forced" in sql
    assert "NOT rs.pds_rls_forced" in sql


def test_sql_includes_required_json_and_baseline_keys() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    root_keys = {
        "schema_version",
        "captured_at_utc",
        "authority",
        "transaction",
        "rls",
        "migration_contract",
        "append_only_contract",
        "role_privileges",
        "candidate_contract",
        "baseline_counts",
        "clause_results",
        "database_proof_result",
    }
    baseline_keys = {
        "v1_snapshots",
        "v1_distinct_predictions",
        "v1_scheduled_shadow_snapshots",
        "v1_orphans",
        "candidate_identity_occupied",
        "v0_snapshots",
        "v0_scheduled_shadow_snapshots",
        "v0v1_semantic_overlap",
        "v0_non_shadow_influence",
        "v0_nonzero_or_unparseable_influence",
        "v0_duplicate_prediction_groups",
    }
    json_keys = set(re.findall(r"'([a-z0-9_]+)'\s*,", sql))

    assert root_keys <= json_keys
    assert all(key in sql for key in baseline_keys)
    assert "THEN 'PASS'" in sql
    assert "ELSE 'BLOCK'" in sql


def test_sql_includes_exact_candidate_close() -> None:
    assert "2026-07-17T04:00:00Z" in SQL_PATH.read_text(encoding="utf-8")


def test_sql_uses_proven_persisted_normalized_symbol_contract() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    normalizer = NORMALIZER_PATH.read_text(encoding="utf-8")
    analysis = ANALYSIS_PATH.read_text(encoding="utf-8")
    persistence_test = PERSISTENCE_TEST_PATH.read_text(encoding="utf-8")

    assert 'display = f"{base}/{quote}"' in normalizer
    assert "normalized_symbol=symbol.display" in analysis
    assert 'normalized_symbol="BTC/USDT"' in persistence_test
    assert "'BTC/USDT'::text AS candidate_normalized_symbol" in sql
    assert "'BTCUSDT'" not in sql


def test_markdown_contains_required_proof_contracts() -> None:
    document = DOC_PATH.read_text(encoding="utf-8")
    required = (
        "## 3. Identity-proof Terminal block",
        "PASS_IDENTITY=PASS",
        "2026-07-17T04:00:00Z",
        "## 4. Database proof instructions",
        "## 5. Live OKX proof design",
        "## 7. Combined evidence contract",
        "readiness = PASS",
        "readiness = BLOCK",
        "## 9. Authorization matrix",
        "## 10. Next gate",
    )

    for value in required:
        assert value in document


def test_markdown_omits_locked_confirmation_value() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    document = DOC_PATH.read_text(encoding="utf-8")
    match = re.search(r"inputs\.confirm_write\s*(?:==|!=)\s*'([^']+)'", workflow)

    assert match is not None
    locked_value = match.group(1)
    assert locked_value
    assert locked_value not in document, "locked confirmation value must remain omitted"


def test_markdown_does_not_authorize_execution_or_mutation() -> None:
    document = DOC_PATH.read_text(encoding="utf-8")
    required_denials = (
        "proof execution = NO",
        "SQL execution = NO",
        "live OKX request = NO",
        "diagnostic workflow dispatch/rerun = NO",
        "local merge = NO",
        "push/deploy = NO",
        "production write = NO",
    )
    forbidden_approvals = tuple(value.replace("= NO", "= YES") for value in required_denials)

    for value in required_denials:
        assert value in document
    for value in forbidden_approvals:
        assert value not in document


def test_packet_tests_use_no_network_sql_or_mutating_subprocess_api() -> None:
    source = TEST_PATH.read_text(encoding="utf-8")
    forbidden_imports = ("subprocess", "socket", "httpx", "requests", "psycopg")

    for name in forbidden_imports:
        assert f"import {name}" not in source
        assert f"from {name}" not in source
