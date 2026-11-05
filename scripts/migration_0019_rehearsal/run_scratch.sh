#!/usr/bin/env bash
# One scratch PostgreSQL cluster for the migration 0019 rehearsal (NG4, Route S). A local run and the CI workflow
# run this same script:
#   run_scratch.sh <postgres bin dir> <fresh work dir> <report path> <on|off>
# It starts a private server listening on a socket only (no TCP) with track_commit_timestamp set as asked, applies
# the Supabase-like role fixtures and every root migration (production's applied state) as a CREATEROLE
# non-superuser owner, runs rehearse.py, which applies migrations/authored/0019_lattice_evidence.sql and probes it,
# and stops the server. It never reads a database URL from the environment and never contacts a remote.
set -euo pipefail
BIN="$1"
WORK="$2"
REPORT="$3"
COMMIT_TS="$4"
case "$COMMIT_TS" in on|off) ;; *) echo "REFUSED: the fourth argument must be on or off" >&2; exit 2 ;; esac
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OWNER="$(id -un)"
DB=migration_0019_rehearsal
if [ -e "$WORK" ]; then
  echo "REFUSED: $WORK exists; give a fresh work directory" >&2
  exit 2
fi
mkdir -p "$WORK"
SOCKET="$(mktemp -d /tmp/u19.XXXXXX)"  # a socket path must stay under about 100 bytes
cleanup() {
  "$BIN/pg_ctl" -D "$WORK/data" -m fast -w stop >/dev/null 2>&1 || true
  rm -rf "$SOCKET"
}
trap cleanup EXIT
"$BIN/initdb" -D "$WORK/data" -U postgres --auth=trust --encoding=UTF8 --locale=C >"$WORK/initdb.log"
"$BIN/pg_ctl" -D "$WORK/data" -l "$WORK/server.log" -w start \
  -o "-c listen_addresses='' -c unix_socket_directories='$SOCKET' -c fsync=off -c track_commit_timestamp=$COMMIT_TS" \
  >/dev/null
export PGOPTIONS="-c client_min_messages=warning"  # keep the existing migrations' notices out of the log
as_super() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -h "$SOCKET" -U postgres "$@"; }
as_owner() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -h "$SOCKET" -U "$OWNER" "$@"; }
as_super -d postgres -c "CREATE ROLE \"$OWNER\" LOGIN"
as_super -d postgres -f "$ROOT/scripts/migration_0013_rehearsal/00_supabase_like_roles.sql"
as_super -d postgres -v owner="$OWNER" \
  -f "$ROOT/scripts/migration_0016_rehearsal/00_supabase_like_authenticator.sql"
as_super -d postgres -c "CREATE DATABASE $DB OWNER \"$OWNER\""
as_super -d "$DB" -v owner="$OWNER" \
  -f "$ROOT/scripts/migration_0013_rehearsal/01_supabase_like_grants.sql"
as_super -d "$DB" -v owner="$OWNER" \
  -f "$ROOT/scripts/migration_0015_rehearsal/00_supabase_like_function_grants.sql"
for migration in "$ROOT"/migrations/[0-9][0-9][0-9][0-9]_*.sql; do
  as_owner -d "$DB" -f "$migration" >>"$WORK/migrations.log" 2>&1
done
"${PYTHON:-python}" "$ROOT/scripts/migration_0019_rehearsal/rehearse.py" \
  --url "postgresql:///$DB?host=$SOCKET&user=$OWNER" \
  --super-url "postgresql:///$DB?host=$SOCKET&user=postgres" \
  --commit-ts "$COMMIT_TS" --report "$REPORT"
