#!/usr/bin/env bash
# Deterministic verification gate. Prints exactly one line.
#   ./verify.sh              lint + tests + safety scanners
#   ./verify.sh --preflight  assert everything a task needs EXISTS, before delegating
# Never calls a model. Never touches a remote. Never writes outside .work/.
set -uo pipefail
cd "$(dirname "$0")"

PY=./.venv/bin/python
RUFF=./.venv/bin/ruff
LOG=.work/verify.log
mkdir -p .work

fail() { echo "VERIFY=FAIL $1"; exit 1; }

# ---------- preflight ----------
if [ "${1:-}" = "--preflight" ]; then
  shift
  [ -x "$PY" ] || fail "PREFLIGHT missing .venv (run: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt)"
  "$PY" - <<'EOF' >/dev/null 2>&1 || { echo "VERIFY=FAIL PREFLIGHT dependency import failed"; exit 1; }
import fastapi, numpy, pydantic, jsonschema, httpx, orjson, psycopg, pytest  # noqa
EOF
  PYTHONPATH=src "$PY" -c "import crypto_probability_engine.api.app" >/dev/null 2>&1 \
    || fail "PREFLIGHT app import failed"
  for p in pyproject.toml requirements.txt src tests schemas migrations scripts .github/workflows; do
    [ -e "$p" ] || fail "PREFLIGHT missing required path: $p"
  done
  for s in check_no_forbidden_scope check_no_secrets check_no_full_article_body; do
    [ -f "scripts/$s.py" ] || fail "PREFLIGHT missing scanner: scripts/$s.py"
  done
  git rev-parse --git-dir >/dev/null 2>&1 || fail "PREFLIGHT not a git repository"
  # extra paths asserted by the caller: ./verify.sh --preflight <path>...
  for p in "$@"; do
    [ -e "$p" ] || fail "PREFLIGHT task-required path absent: $p"
  done
  echo "VERIFY=PASS preflight ok ($(git rev-parse --short HEAD))"
  exit 0
fi

# ---------- full gate ----------
[ -x "$PY" ]   || fail "missing .venv"
[ -x "$RUFF" ] || fail "missing ruff in .venv"

"$RUFF" check . >"$LOG" 2>&1 || fail "ruff: $(grep -m1 -E '^[^ ]+:[0-9]+' "$LOG" | cut -c1-120)"

"$PY" -m pytest -q >"$LOG" 2>&1 || {
  first=$(grep -m1 -E '^(FAILED|ERROR)' "$LOG" | cut -c1-120)
  [ -n "$first" ] || first=$(tail -3 "$LOG" | head -1 | cut -c1-120)
  fail "pytest: ${first:-unknown} (see $LOG)"
}
SUMMARY=$(grep -m1 -E '[0-9]+ (passed|failed)' "$LOG" | cut -c1-60)

PYTHONPATH=src "$PY" scripts/validate_schemas.py >"$LOG" 2>&1 || {
  first=$(awk 'NF { line=$0 } END { print line }' "$LOG" | cut -c1-120)
  fail "schemas: ${first:-unknown} (see $LOG)"
}

PYTHONPATH=src "$PY" scripts/manual_smoke.py >"$LOG" 2>&1 || {
  first=$(awk 'NF { line=$0 } END { print line }' "$LOG" | cut -c1-120)
  fail "smoke: ${first:-unknown} (see $LOG)"
}

for s in check_no_forbidden_scope check_no_secrets check_no_full_article_body; do
  "$PY" "scripts/$s.py" >>"$LOG" 2>&1 || fail "scanner $s (see $LOG)"
done

echo "VERIFY=PASS ruff ok | $SUMMARY | schemas+smoke ok | scanners 3/3 | $(git rev-parse --short HEAD)"
