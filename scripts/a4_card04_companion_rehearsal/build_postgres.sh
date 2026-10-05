#!/usr/bin/env bash
# Build PostgreSQL 17.6, the governed version (production runs 17.6), from the PostgreSQL project's
# source tarball, verified against the pinned sha256 below, into <fresh prefix>. A local run and the
# CI workflow run this same script:
#   build_postgres.sh <fresh prefix>
# It downloads only that tarball, over https, and installs nothing outside the prefix.
set -euo pipefail
PREFIX="$1"
VERSION=17.6
SHA256=e0630a3600aea27511715563259ec2111cd5f4353a4b040e0be827f94cd7a8b0
URL="https://ftp.postgresql.org/pub/source/v$VERSION/postgresql-$VERSION.tar.bz2"
if [ -e "$PREFIX" ]; then
  echo "REFUSED: $PREFIX exists; give a fresh prefix" >&2
  exit 2
fi
SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT
curl --fail --silent --show-error --location --retry 3 --proto '=https' --tlsv1.2 \
  -o "$SRC/postgresql.tar.bz2" "$URL"
python3 - "$SRC/postgresql.tar.bz2" "$SHA256" <<'PY'
import hashlib
import sys

with open(sys.argv[1], "rb") as source:
    digest = hashlib.sha256(source.read()).hexdigest()
if digest != sys.argv[2]:
    sys.exit(f"REFUSED: the PostgreSQL source's sha256 {digest} is not the pinned one")
PY
tar -xjf "$SRC/postgresql.tar.bz2" -C "$SRC"
cd "$SRC/postgresql-$VERSION"
step() {
  local log="$SRC/$1.log"
  shift
  "$@" >"$log" 2>&1 || { tail -60 "$log"; exit 1; }
}
step configure ./configure --prefix="$PREFIX" --without-readline --without-icu --without-zlib
step make make -j"$(python3 -c 'import os; print(os.cpu_count() or 2)')"
step install make install
"$PREFIX/bin/postgres" --version
