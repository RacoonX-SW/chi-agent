#!/usr/bin/env bash
# Repeatable offline verification: full tests, controller-only tests, bundle
# build, bundle validation and preflight. Runs everything in Docker; the host
# only orchestrates Docker and Git.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
COMMIT=$(git rev-parse HEAD)
ALLOW_DIRTY=0
if [ "${1:-}" = "--allow-dirty" ]; then
  ALLOW_DIRTY=1
elif [ $# -gt 0 ]; then
  echo "usage: $0 [--allow-dirty]" >&2
  exit 2
fi
if [ "$ALLOW_DIRTY" -eq 0 ] && [ -n "$(git status --porcelain)" ]; then
  echo "working tree is dirty; commit first or pass --allow-dirty" >&2
  exit 2
fi

TMP=$(mktemp -d "${TMPDIR:-/tmp}/chi-verify.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
MODEL_DEPS=${CHI_MODEL_DEPS_VOLUME:-chi-h-root-model-deps-20261027-v1}
PDF_DEPS=${CHI_PDF_DEPS_VOLUME:-chi-k-pdf-deps-20261027-v1}
DEV_IMAGE=${CHI_DEV_IMAGE:-chi-agent-dev:latest}
CONTROLLER_IMAGE=${CHI_CONTROLLER_IMAGE:-chi-agent-py312-review:controller}

run_tests() {
  local log="$TMP/tests.log"
  echo "== full unittest (dev image) =="
  docker run --rm --network none \
    -v "$ROOT:/workspace:rw" \
    -v "$MODEL_DEPS:/model-deps:ro" \
    -v "$PDF_DEPS:/pdf-deps:ro" \
    -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts:/workspace/tests \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -w /workspace "$DEV_IMAGE" \
    /opt/venv/bin/python -m unittest discover -s tests >"$log" 2>&1 || {
      tail -60 "$log" >&2
      exit 1
    }
  tail -4 "$log"
  grep -E '^Ran [0-9]+ tests|^OK' "$log" || true
}

run_controller_tests() {
  local log="$TMP/controller-tests.log"
  echo "== controller-only tests =="
  docker run --rm --network none --read-only --tmpfs /tmp \
    -v "$ROOT:/workspace:ro" \
    -v "$MODEL_DEPS:/model-deps:ro" \
    -v "$PDF_DEPS:/pdf-deps:ro" \
    -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts:/workspace/tests \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -w /workspace "$CONTROLLER_IMAGE" \
    /opt/a-venv/bin/python -m unittest tests.test_role_payer_projection >"$log" 2>&1 || {
      tail -60 "$log" >&2
      exit 1
    }
  tail -4 "$log"
}

build_and_preflight() {
  local target="$TMP/bundle"
  local build_log="$TMP/build.log"
  echo "== bundle build =="
  docker run --rm --network none \
    -v "$ROOT:/workspace:ro" \
    -v "$TMP:/out:rw" \
    -v "$MODEL_DEPS:/model-deps:ro" \
    -v "$PDF_DEPS:/pdf-deps:ro" \
    -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -w /workspace "$DEV_IMAGE" \
    /opt/venv/bin/python scripts/go_chi_release.py build \
      --target /out/bundle --source-root /workspace --source-commit "$COMMIT" \
      >"$build_log" 2>&1 || {
        tail -40 "$build_log" >&2
        exit 1
      }
  tail -1 "$build_log"
  local bundle_sha
  bundle_sha=$(python3 - "$target/release-manifest.json" <<'PY'
import json
import sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
print(data["bundle_manifest_sha256"])
PY
)

  echo "== bundle validate =="
  docker run --rm --network none --read-only --tmpfs /tmp \
    -v "$ROOT:/workspace:ro" \
    -v "$TMP:/out:ro" \
    -v "$MODEL_DEPS:/model-deps:ro" \
    -e PYTHONPATH=/model-deps:/workspace/scripts \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -w /workspace "$DEV_IMAGE" \
    /opt/venv/bin/python -c "
from pathlib import Path
from go_chi_bundle import validate_bundle
i = validate_bundle(Path('/out/bundle/package'))
print('bundle_id', i.bundle_id)
print('manifest_sha256', i.manifest_sha256)
print('files', len(i.files))
"

  echo "== preflight =="
  local preflight="$TMP/preflight.json"
  docker run --rm --network none --read-only --tmpfs /tmp \
    -v "$target/package:/package:ro" \
    -v "$ROOT/vendor/chi-bench:/package/vendor/chi-bench:ro" \
    -v "$MODEL_DEPS:/model-deps:ro" \
    -v "$PDF_DEPS:/pdf-deps:ro" \
    -e PYTHONPATH=/model-deps:/pdf-deps:/package/vendor/chi-bench/src \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -w /tmp "$DEV_IMAGE" \
    /usr/local/bin/python -S /package/scripts/go_chi_entry.py preflight \
      --bundle-sha256 "$bundle_sha" >"$preflight" 2>&1 || {
        tail -40 "$preflight" >&2
        exit 1
      }
  python3 - "$preflight" <<'PY'
import json
import sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
print("status", data.get("status"))
print("identity", data.get("identity_sha256"))
print("official_reward", data.get("official_reward"))
if data.get("status") != "identity_verified":
    raise SystemExit("preflight did not verify the identity")
PY
}

echo "commit $COMMIT"
run_tests
run_controller_tests
build_and_preflight
echo "OK: tests, controller tests, bundle and preflight passed"
