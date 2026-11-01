"""Versioned experiment campaign manifest for CHI development runs.

The manifest freezes candidate identity, task/resource identity, mechanism
toggles, limits and checks before any run. It contains no expected answers and
is independent of the agent under test.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "chi-experiment-campaign-v1"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MECHANISMS = {"F1", "F2", "F3", "F4", "F5", "F6"}
MODES = {"off", "on", "na"}
ROLES = {"provider", "payer", "cm"}
CANDIDATE_KEYS = {"source_sha256", "bundle_sha256", "model", "endpoint", "simulator", "capabilities"}
RESOURCE_KEYS = {"manifest_sha256", "world_image_id"}
TASK_KEYS = {"task_id", "role", "resources", "attempt", "checks"}
LIMIT_KEYS = {"provider_requests", "output_tokens"}
CELL_COMMON = {"cell_id", "mechanism", "mode", "tasks", "limits"}
CAMPAIGN_KEYS = {"schema", "campaign_id", "candidate", "cells", "stop_conditions", "created_at"}


class ManifestError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _text(value, code: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise ManifestError(code)
    return value


def _hash(value, code: str) -> str:
    if type(value) is not str or not SHA256.fullmatch(value):
        raise ManifestError(code)
    return value


def _positive(value, code: str) -> int:
    if type(value) is not int or value < 1:
        raise ManifestError(code)
    return value


def _candidate(value) -> dict:
    if type(value) is not dict or set(value) != CANDIDATE_KEYS:
        raise ManifestError("manifest_candidate_invalid")
    candidate = {
        "source_sha256": _hash(value["source_sha256"], "manifest_candidate_invalid"),
        "bundle_sha256": _hash(value["bundle_sha256"], "manifest_candidate_invalid"),
        "model": _text(value["model"], "manifest_candidate_invalid"),
        "endpoint": _text(value["endpoint"], "manifest_candidate_invalid"),
        "simulator": _text(value["simulator"], "manifest_candidate_invalid"),
        "capabilities": _text(value["capabilities"], "manifest_candidate_invalid"),
    }
    return candidate


def _task(value) -> dict:
    if type(value) is not dict or set(value) != TASK_KEYS:
        raise ManifestError("manifest_task_invalid")
    if type(value["task_id"]) is not str or not ID.fullmatch(value["task_id"]):
        raise ManifestError("manifest_task_invalid")
    if value["role"] not in ROLES:
        raise ManifestError("manifest_task_invalid")
    resources = value["resources"]
    if type(resources) is not dict or set(resources) != RESOURCE_KEYS:
        raise ManifestError("manifest_task_invalid")
    resources = {
        "manifest_sha256": _hash(resources["manifest_sha256"], "manifest_task_invalid"),
        "world_image_id": _text(resources["world_image_id"], "manifest_task_invalid"),
    }
    attempt = _positive(value["attempt"], "manifest_task_invalid")
    checks = value["checks"]
    if (type(checks) is not list or not checks or len(set(checks)) != len(checks)
            or any(type(item) is not str or not item.strip() or len(item) > 64 for item in checks)):
        raise ManifestError("manifest_task_invalid")
    return {"task_id": value["task_id"], "role": value["role"], "resources": resources,
            "attempt": attempt, "checks": list(checks)}


def _cell(value) -> dict:
    if type(value) is not dict or value.get("mode") not in MODES:
        raise ManifestError("manifest_cell_invalid")
    mode = value["mode"]
    expected = CELL_COMMON | ({"toggle", "hypothesis"} if mode in {"off", "on"} else {"reason"})
    if set(value) != expected:
        raise ManifestError("manifest_cell_invalid")
    if type(value["cell_id"]) is not str or not ID.fullmatch(value["cell_id"]):
        raise ManifestError("manifest_cell_invalid")
    if value["mechanism"] not in MECHANISMS:
        raise ManifestError("manifest_cell_invalid")
    limits = value["limits"]
    if type(limits) is not dict or set(limits) != LIMIT_KEYS:
        raise ManifestError("manifest_cell_invalid")
    limits = {"provider_requests": _positive(limits["provider_requests"], "manifest_cell_invalid"),
              "output_tokens": _positive(limits["output_tokens"], "manifest_cell_invalid")}
    tasks = value["tasks"]
    if type(tasks) is not list or not tasks:
        raise ManifestError("manifest_cell_invalid")
    normalized_tasks = [_task(task) for task in tasks]
    seen = set()
    for task in normalized_tasks:
        key = (task["task_id"], task["role"], task["attempt"])
        if key in seen:
            raise ManifestError("manifest_task_duplicate")
        seen.add(key)
    cell = {"cell_id": value["cell_id"], "mechanism": value["mechanism"], "mode": mode,
            "tasks": normalized_tasks, "limits": limits}
    if mode in {"off", "on"}:
        cell["toggle"] = _text(value["toggle"], "manifest_cell_invalid")
        cell["hypothesis"] = _text(value["hypothesis"], "manifest_cell_invalid")
    else:
        cell["reason"] = _text(value["reason"], "manifest_cell_invalid")
    return cell


def validate_manifest(value) -> dict:
    if type(value) is not dict or set(value) != CAMPAIGN_KEYS:
        raise ManifestError("manifest_invalid")
    if value["schema"] != SCHEMA:
        raise ManifestError("manifest_schema_invalid")
    if type(value["campaign_id"]) is not str or not ID.fullmatch(value["campaign_id"]):
        raise ManifestError("manifest_invalid")
    created_at = _text(value["created_at"], "manifest_invalid")
    stop = value["stop_conditions"]
    if (type(stop) is not list or not stop or len(set(stop)) != len(stop)
            or any(type(item) is not str or not item.strip() or len(item) > 128 for item in stop)):
        raise ManifestError("manifest_stop_conditions_invalid")
    cells = value["cells"]
    if type(cells) is not list or not cells:
        raise ManifestError("manifest_cells_invalid")
    normalized = [_cell(cell) for cell in cells]
    ids = set()
    by_mechanism = {}
    for cell in normalized:
        if cell["cell_id"] in ids:
            raise ManifestError("manifest_cell_duplicate")
        ids.add(cell["cell_id"])
        by_mechanism.setdefault(cell["mechanism"], {})[cell["mode"]] = cell
    for mechanism, modes in by_mechanism.items():
        if set(modes) == {"off", "on"}:
            off, on = modes["off"], modes["on"]
            def shape(cell):
                return (tuple((task["task_id"], task["role"], task["attempt"])
                              for task in cell["tasks"]), tuple(sorted(cell["limits"].items())))
            if shape(off) != shape(on):
                raise ManifestError("manifest_comparison_mismatch")
        elif set(modes) != {"na"}:
            raise ManifestError("manifest_mechanism_incomplete")
    return {"schema": SCHEMA, "campaign_id": value["campaign_id"],
            "candidate": _candidate(value["candidate"]), "cells": normalized,
            "stop_conditions": list(stop), "created_at": created_at}


def freeze_manifest(value) -> tuple[bytes, str]:
    normalized = validate_manifest(value)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


def main(argv=None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Validate or freeze a CHI experiment manifest")
    parser.add_argument("command", choices=("validate", "freeze"))
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        value = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        normalized = validate_manifest(value)
        _, digest = freeze_manifest(normalized)
        output = {"status": "valid", "manifest_sha256": digest,
                  "campaign_id": normalized["campaign_id"]}
        if args.command == "freeze":
            output["manifest"] = normalized
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except (ManifestError, OSError, ValueError) as exc:
        code = getattr(exc, "code", "manifest_file_invalid")
        print(json.dumps({"status": "invalid", "code": code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
