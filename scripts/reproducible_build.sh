#!/usr/bin/env bash
# B3 (governing plan §11.1): the governed reproducibility proof for the production image.
#   build <dir>      one clean, cache-free build of HEAD for linux/amd64 with a digest-pinned BuildKit, the
#                    commit's own time as SOURCE_DATE_EPOCH, rewritten layer timestamps and no provenance or
#                    SBOM attestation; writes <dir>/image.tar (a docker archive, which also carries the OCI
#                    index.json) and prints its manifest digest
#   compare <a> <b>  PASS only when two independent builds produced the same manifest digest
#   smoke <dir>      load <dir>/image.tar, run it in fixture mode, and require /healthcheck 200 and the
#                    commit's own release id from /v1/build-info
# It holds no secret, pushes nothing and never deploys. CI runs it: .github/workflows/reproducible-build.yml.
set -euo pipefail
export LC_ALL=C

BUILDKIT_IMAGE="moby/buildkit:v0.33.1@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea"
PLATFORM="linux/amd64"
IMAGE_NAME="ucpe-repro:local"
BUILD_INFO="src/crypto_probability_engine/config/build_info.py"

usage() {
  echo "usage: $0 build <dir> | compare <digest-a> <digest-b> | smoke <dir>" >&2
  exit 2
}

manifest_digest() {
  tar -xOf "$1" index.json | python3 -c '
import json, sys
manifests = json.load(sys.stdin)["manifests"]
if len(manifests) != 1:
    raise SystemExit(f"expected exactly one manifest, found {len(manifests)}")
print(manifests[0]["digest"])
'
}

case "${1:-}" in
  build)
    out="${2:-}"
    [[ -n "$out" ]] || usage
    mkdir -p "$out"
    epoch="$(git log -1 --format=%ct HEAD)"
    builder="ucpe-repro-$$-$RANDOM"
    docker buildx create --name "$builder" --driver docker-container \
      --driver-opt "image=$BUILDKIT_IMAGE" >/dev/null
    trap 'docker buildx rm -f "$builder" >/dev/null 2>&1 || true' EXIT
    docker buildx build --builder "$builder" --platform "$PLATFORM" --no-cache --pull \
      --provenance=false --sbom=false \
      --build-arg "SOURCE_DATE_EPOCH=$epoch" \
      --output "type=docker,dest=$out/image.tar,name=$IMAGE_NAME,rewrite-timestamp=true" .
    digest="$(manifest_digest "$out/image.tar")"
    echo "commit=$(git rev-parse HEAD) SOURCE_DATE_EPOCH=$epoch"
    echo "image.tar sha256=$(sha256sum "$out/image.tar" | cut -d' ' -f1)"
    echo "MANIFEST_DIGEST=$digest"
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
      echo "digest=$digest" >> "$GITHUB_OUTPUT"
    fi
    ;;
  compare)
    a="${2:-}"
    b="${3:-}"
    [[ -n "$a" && -n "$b" ]] || usage
    if [[ ! "$a" =~ ^sha256:[0-9a-f]{64}$ || ! "$b" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "REPRODUCIBLE=STOP malformed digest(s): '$a' '$b'"
      exit 1
    fi
    if [[ "$a" == "$b" ]]; then
      echo "REPRODUCIBLE=PASS both independent builds produced $a"
    else
      echo "REPRODUCIBLE=STOP build A $a differs from build B $b"
      exit 1
    fi
    ;;
  smoke)
    dir="${2:-}"
    [[ -n "$dir" ]] || usage
    expected="$(sed -n 's/^RELEASE_ID = "\(.*\)"$/\1/p' "$BUILD_INFO")"
    docker load -i "$dir/image.tar"
    docker image inspect --format "loaded $IMAGE_NAME as {{.Id}}" "$IMAGE_NAME"
    cid="$(docker run -d -p 127.0.0.1:7860:7860 -e UCPE_DATA_MODE=fixture "$IMAGE_NAME")"
    trap 'docker logs "$cid" >&2 || true; docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT
    for _ in $(seq 1 90); do
      curl -fsS -o /dev/null http://127.0.0.1:7860/healthcheck 2>/dev/null && break
      sleep 1
    done
    health="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/healthcheck || true)"
    served="$(curl -sS http://127.0.0.1:7860/v1/build-info \
      | python3 -c 'import json, sys; print(json.load(sys.stdin).get("release_id"))' || true)"
    if [[ "$health" == "200" && -n "$expected" && "$served" == "$expected" ]]; then
      echo "SMOKE=PASS healthcheck 200; build-info $served"
    else
      echo "SMOKE=STOP healthcheck $health; build-info '$served' (expected '$expected')"
      exit 1
    fi
    ;;
  *)
    usage
    ;;
esac
