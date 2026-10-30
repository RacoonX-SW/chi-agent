#!/bin/sh
# Build a disposable, local-only rehearsal image and a real synthetic B seed.
# Usage: sh tests/harbor_rehearsal_prepare.sh /absolute/new/output-dir unique-id
set -eu
out=${1:?absolute new output directory required}
id=${2:?unique lowercase image id required}
case "$out" in /*) ;; *) exit 2 ;; esac
case "$id" in *[!a-z0-9-]*|'') exit 2 ;; esac
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base="chi-agent-harbor-synthetic:$id-base"
seed="chi-agent-harbor-synthetic:$id-seed"
container="chi-harbor-b-$id"
docker run --rm --pull=never --network none \
  -v "$root:/work:ro" -v "$out:/out" \
  -v chi-h-root-model-deps-20261027-v1:/model:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf:ro chi-agent-py312-review:dev sh -c '
    set -eu; test ! -e /out/build; mkdir /out/build; cd /work
    python scripts/go_chi_bundle.py build --target /out/build/bundle
    cp -a /work/vendor/chi-bench /out/build/vendor
    mkdir /out/build/model /out/build/pdf
    cp -a /model/. /out/build/model/; cp -a /pdf/. /out/build/pdf/
    cp /work/tests/harbor_synthetic_python.py /out/build/harbor_synthetic_python.py
    cp /work/tests/harbor_synthetic_world.Dockerfile /out/build/Dockerfile'
docker build --pull=false -t "$base" "$out/build"
docker create --pull=never --network none --name "$container" --entrypoint sh "$base" -c '
  digest=$(/usr/local/bin/python3 -c "import json;print(json.load(open(\"/opt/chi-go/bundle-manifest.json\"))[\"manifest_sha256\"])")
  env -i PATH=/workspace/.venv/bin:/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
    python /opt/chi-go/scripts/go_chi_entry.py coding-b --bundle-sha256 "$digest" \
    --evaluation-id harbor-e --task-id synthetic-coding-b --attempt-id b --run-id b \
    --output-root /test/state --logs-dir /test/b-logs --history-mode external'
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT HUP INT TERM
docker start -a "$container"
test "$(docker inspect --format '{{.State.ExitCode}}' "$container")" = 0
docker cp "$container:/test/state" "$out/b-state"
docker cp "$container:/test/b-logs" "$out/b-logs"
docker run --rm --pull=never --network none -v "$out/b-state:/state:ro" -v "$out/b-logs:/logs:ro" \
  chi-agent-py312-review:dev python -c '
import json
from pathlib import Path
receipt = json.loads(Path("/state/b-receipts/b.json").read_text())
seal = json.loads(Path("/state/run-seals/b.json").read_text())
log = json.loads(Path("/logs/run_log.txt").read_text())
assert receipt["schema"] == "chi-go-b-success-v1" and receipt["run"] == "b"
assert seal["schema"] == "chi-go-run-seal-v1" and seal["run"] == "b"
assert receipt["identity"] == seal["identity"] and receipt["run_sha256"] == seal["run_sha256"]
assert log["status"] == "complete" and log["safe_error_code"] is None
'
docker commit --change 'ENTRYPOINT ["/usr/bin/tini","--","/usr/local/bin/entrypoint.sh"]' \
  --change 'CMD ["sleep","infinity"]' "$container" "$seed"
docker rm "$container"
trap - EXIT HUP INT TERM
printf 'seed image: %s\nbundle: %s\n' "$seed" "$out/build/bundle"
