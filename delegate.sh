#!/usr/bin/env bash
# Delegate one bounded task to Codex, file-in / file-out.
#   ./delegate.sh <task-file.md> [read-only|workspace-write] [model-effort]
#
# Contract:
#   in   .work/task-NNN.md      goal, base SHA, allowed/forbidden paths, acceptance
#   out  .work/result-NNN.json  schema-constrained; THIS is all Claude reads
#   log  .work/codex-NNN.log    full transcript; opened only when status != DONE
#
# Codex runs on the ChatGPT subscription (auth_mode=chatgpt). No OpenAI API key
# is set or read here, so no metered API cost is incurred.
set -uo pipefail
cd "$(dirname "$0")"

TASK="${1:?usage: ./delegate.sh <task-file.md> [read-only|workspace-write] [effort]}"
SANDBOX="${2:-workspace-write}"
EFFORT="${3:-medium}"          # medium for mechanical work; xhigh only when justified

[ -f "$TASK" ] || { echo "DELEGATE=FAIL task file not found: $TASK"; exit 1; }
command -v codex >/dev/null || { echo "DELEGATE=FAIL codex CLI not on PATH"; exit 1; }

mkdir -p .work
N="$(basename "$TASK" .md)"; N="${N#task-}"
RESULT=".work/result-${N}.json"
LOG=".work/codex-${N}.log"
SCHEMA=".work/result.schema.json"

cat > "$SCHEMA" <<'EOF'
{
  "type": "object",
  "properties": {
    "status":        {"type": "string", "enum": ["DONE", "BLOCKED", "NEEDS_DECISION"]},
    "summary":       {"type": "string", "maxLength": 400},
    "files_changed": {"type": "array", "items": {"type": "string"}},
    "tests_run":     {"type": "integer"},
    "tests_passed":  {"type": "integer"},
    "blocker":       {"type": "string", "maxLength": 200}
  },
  "required": ["status", "summary", "files_changed", "tests_run", "tests_passed", "blocker"],
  "additionalProperties": false
}
EOF

BASE="$(git rev-parse --short HEAD)"

# A STALE RESULT MUST NEVER SATISFY COMPLETION.
#
# The completion check below is `[ ! -s "$RESULT" ]`, which a leftover file from an
# EARLIER run of the same task satisfies. That happened: a re-run whose model exhausted
# its quota wrote no result, the previous run's verdict was still on disk, and the
# delegation reported OK. The old verdict was very nearly read as the new one.
#
# So: rotate any existing result out of the way first, and afterwards require the result
# to be strictly newer than this invocation.
START_MARKER="$(mktemp)"
trap 'rm -f "$START_MARKER"' EXIT
if [ -e "$RESULT" ]; then
  PREVIOUS="${RESULT%.json}.prev-$(date -u +%Y%m%dT%H%M%SZ).json"
  mv "$RESULT" "$PREVIOUS"
  echo "DELEGATE rotated stale result -> $PREVIOUS" >&2
fi
if [ -e "$LOG" ]; then
  mv "$LOG" "${LOG%.log}.prev-$(date -u +%Y%m%dT%H%M%SZ).log"
fi

echo "DELEGATE start task=$N base=$BASE sandbox=$SANDBOX effort=$EFFORT" >&2

# stdin redirection is MANDATORY: without it codex exec blocks forever on
# "Reading additional input from stdin...".
codex exec \
  -C "$PWD" \
  -s "$SANDBOX" \
  -c model_reasoning_effort="$EFFORT" \
  --output-schema "$SCHEMA" \
  -o "$RESULT" \
  < "$TASK" > "$LOG" 2>&1
RC=$?

if [ $RC -ne 0 ] || [ ! -s "$RESULT" ]; then
  echo "DELEGATE=FAIL rc=$RC (see $LOG)"
  exit 1
fi

# The result must have been written by THIS invocation, not left behind by an earlier one.
# Rotating the old file away already guarantees that; this is defence in depth. Uses
# "not older than" rather than "newer than", because a fast run can share the marker's
# mtime at filesystem granularity and would otherwise be rejected as stale.
if [ "$RESULT" -ot "$START_MARKER" ]; then
  echo "DELEGATE=FAIL result is not newer than this invocation; refusing to report a"
  echo "               possibly stale verdict (see $LOG)"
  exit 1
fi

echo "DELEGATE=OK result=$RESULT log=$LOG base=$BASE"
cat "$RESULT"
