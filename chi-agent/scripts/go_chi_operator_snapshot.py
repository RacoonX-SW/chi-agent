"""Operator-only read-only snapshot of the two fixed world resource tables."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from evaluation_bundle import _fsync_dir, _write_exclusive
from b_provider_transport import _reject_symlink_ancestors
from a_environment import _api_timeout

_PROGRAM = r'''
import json, sqlite3, sys
paths = {"provider": "/tmp/chi-bench-runtime/provider_world.sqlite", "payer": "/tmp/chi-bench-runtime/payer_hidden.sqlite"}
side = sys.argv[1]
db = sqlite3.connect("file:" + paths[side] + "?mode=ro", uri=True)
db.execute("PRAGMA query_only=ON")
rows = []
size = 0
for typ, ident, payload in db.execute("SELECT resource_type, resource_id, payload FROM resources ORDER BY resource_type, resource_id, payload LIMIT 100001"):
    if len(rows) >= 100000 or not all(isinstance(x, str) for x in (typ, ident, payload)):
        raise ValueError("resource_snapshot_invalid")
    row = {"resource_type": typ, "resource_id": ident, "payload": payload}
    size += len(json.dumps(row, ensure_ascii=True).encode())
    if size > 16777216:
        raise ValueError("resource_snapshot_too_large")
    rows.append(row)
sys.stdout.write(json.dumps(rows, ensure_ascii=True, separators=(",", ":")))
'''


def capture_resources(world, output: Path, phase: str) -> dict:
    """Save each side independently; failures are never interpreted as empty."""
    if phase not in {"before", "after"}:
        raise ValueError("invalid_snapshot_phase")
    output = Path(output)
    _reject_symlink_ancestors(output, "resource_snapshot_invalid")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    _reject_symlink_ancestors(output, "resource_snapshot_invalid")
    results = {}
    for side in ("provider", "payer"):
        try:
            deadline = time.monotonic() + 60
            with _api_timeout(world.client, deadline):
                code, raw = world.exec_run(["python", "-c", _PROGRAM, side], demux=False)
            if time.monotonic() > deadline: raise TimeoutError
            if code != 0 or type(raw) is not bytes or len(raw) > 20 * 1024 * 1024:
                raise ValueError
            rows = json.loads(raw)
            if (type(rows) is not list or len(rows) > 100000 or any(type(row) is not dict
                    or set(row) != {"resource_type", "resource_id", "payload"}
                    or any(type(value) is not str for value in row.values()) for row in rows)):
                raise ValueError
            if rows != sorted(rows, key=lambda r: (r["resource_type"], r["resource_id"], r["payload"])):
                raise ValueError
            path = output / f"{phase}-{side}-resources.json"
            _write_exclusive(path, raw)
            _fsync_dir(output)
            results[side] = {"status": "ready", "sha256": hashlib.sha256(raw).hexdigest(), "count": len(rows)}
        except Exception:
            results[side] = {"status": "unavailable", "safe_error_code": "resource_snapshot_failed"}
    return results
