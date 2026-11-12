#!/usr/bin/env bash
# Run the repository tests and verify both exports in isolated Docker containers.
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT=$(pwd)
COMMIT=$(git rev-parse HEAD)
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--allow-dirty" ]; }; then
  echo "usage: $0 [--allow-dirty]" >&2
  exit 2
fi
if [ "$#" -eq 0 ] && [ -n "$(git status --porcelain)" ]; then
  echo "Commit tracked changes before verifying, or pass --allow-dirty." >&2
  exit 2
fi

VENDOR=$(cd "${CHI_VENDOR_DIR:-$ROOT/vendor/chi-bench}" && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/chi-verify.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
MODEL_DEPS=${CHI_MODEL_DEPS_VOLUME:-chi-h-root-model-deps-20261027-v1}
PDF_DEPS=${CHI_PDF_DEPS_VOLUME:-chi-k-pdf-deps-20261027-v1}
DEV_IMAGE=${CHI_DEV_IMAGE:-chi-agent-dev:latest}
CONTROLLER_IMAGE=${CHI_CONTROLLER_IMAGE:-chi-agent-py312-review:controller}

mkdir -p "$ROOT/vendor/chi-bench" "$ROOT/runs"
docker_options=(
  --rm --pull=never --network none --read-only --tmpfs /tmp
  -v "$MODEL_DEPS:/model-deps:ro" -v "$PDF_DEPS:/pdf-deps:ro"
  -e PYTHONDONTWRITEBYTECODE=1
)
source_options=(
  -v "$ROOT:/workspace:ro" -v "$VENDOR:/workspace/vendor/chi-bench:ro"
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/src:/workspace:/workspace/tests
  -w /workspace
)

echo "commit $COMMIT"
docker run "${docker_options[@]}" "${source_options[@]}" --tmpfs /workspace/runs \
  "$DEV_IMAGE" /opt/venv/bin/python -m pytest -q -p no:cacheprovider tests
docker run "${docker_options[@]}" "${source_options[@]}" \
  "$CONTROLLER_IMAGE" /opt/a-venv/bin/python -m unittest tests.test_role_payer_projection

docker run "${docker_options[@]}" "${source_options[@]}" -v "$TMP:/out:rw" "$DEV_IMAGE" sh -ec '
  python -m scripts.tools.inspect_imports --allow-unknown
  python -m scripts.tools.release_bundle build --target /out/go --source-root /workspace --source-commit "$1"
  python -m scripts.tools.release_bundle verify --root /out/go
  python -m chi_agent.evaluation_bundle build --target /out/evaluation
  python -m chi_agent.evaluation_bundle verify --root /out/evaluation
' sh "$COMMIT"

check_export() {
  docker run "${docker_options[@]}" -v "$1:/package:ro" -v "$VENDOR:/package/vendor/chi-bench:ro" \
    -e PYTHONPATH=/model-deps:/pdf-deps:/package/vendor/chi-bench/src \
    -w /tmp "$DEV_IMAGE" sh -ec "$2"
}

check_export "$TMP/go/package" '
  digest=$(python -c '"'"'import json; print(json.load(open("/package/bundle-manifest.json"))["manifest_sha256"])'"'"')
  /usr/local/bin/python -S /package/scripts/go_chi_entry.py preflight --bundle-sha256 "$digest" > /tmp/go.json
  python -c '"'"'
import json
from pathlib import Path
report = json.loads(Path("/tmp/go.json").read_bytes())
assert report["status"] == "identity_verified" and report["official_reward"] is None
print("Go preflight", report["status"], report["identity_sha256"])
'"'"'
'

check_export "$TMP/evaluation" '
  /usr/local/bin/python -S /package/scripts/evaluation_entry.py preflight > /tmp/evaluation.json
  code=0
  /usr/local/bin/python -S /package/scripts/evaluation_entry.py live > /tmp/paused.json || code=$?
  test "$code" -eq 2
  python -c '"'"'
import json
from pathlib import Path
report = json.loads(Path("/tmp/evaluation.json").read_bytes())
paused = json.loads(Path("/tmp/paused.json").read_bytes())
assert report["technical_ready"] and report["accounting"]["official_reward"] is None
assert paused["safe_error_code"] == "real_execution_paused" and not paused["credentials_read"]
print("Evaluation preflight", report["readiness"], report["entry"]["bundle_manifest_sha256"])
'"'"'
'
