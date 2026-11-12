"""Deterministic experiment result aggregation with full denominators."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

from scripts.experiments.validate_experiment_manifest import (MECHANISMS, MODES, ROLES, ManifestError,
                                 freeze_manifest, validate_manifest)

SCHEMA = "chi-experiment-summary-v1"
RECORD_SCHEMA = "chi-experiment-record-v1"
CODE = re.compile(r"^[a-z0-9_]{1,64}$")
RECORD_KEYS = {"schema", "campaign_id", "cell_id", "task_id", "role", "attempt",
               "candidate", "run", "logs", "checks", "business", "content",
               "official_reward", "usage", "failure"}
STATUSES = {"completed", "failed", "skipped", "blocked"}
CHECK_STATUS = {"pass", "fail", "na"}


class SummaryError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _number(value, code: str, *, nullable=True):
    if value is None and nullable:
        return None
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise SummaryError(code)
    return value


def _text(value, code: str, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise SummaryError(code)
    return value


def _validate_record(record, manifest, planned):
    if type(record) is not dict or set(record) != RECORD_KEYS or record.get("schema") != RECORD_SCHEMA:
        raise SummaryError("record_invalid")
    if record["campaign_id"] != manifest["campaign_id"]:
        raise SummaryError("record_campaign_mismatch")
    key = (record["cell_id"], record["task_id"], record["role"], record["attempt"])
    if key not in planned:
        raise SummaryError("record_unplanned")
    cell = planned[key]
    if record["candidate"] != manifest["candidate"]:
        raise SummaryError("record_candidate_mismatch")
    run = record["run"]
    if type(run) is not dict or set(run) != {"status", "safe_error_code"} or run["status"] not in STATUSES:
        raise SummaryError("record_run_invalid")
    if run["safe_error_code"] is not None and (type(run["safe_error_code"]) is not str
                                              or not CODE.fullmatch(run["safe_error_code"])):
        raise SummaryError("record_run_invalid")
    logs = record["logs"]
    if type(logs) is not dict or set(logs) != {"present", "reason"} or type(logs["present"]) is not bool:
        raise SummaryError("record_logs_invalid")
    if logs["present"] is False and (type(logs["reason"]) is not str or not logs["reason"].strip()):
        raise SummaryError("record_logs_invalid")
    checks = record["checks"]
    if type(checks) is not list:
        raise SummaryError("record_checks_invalid")
    seen = set()
    normalized_checks = []
    for check in checks:
        if (type(check) is not dict or set(check) != {"id", "status"}
                or type(check["id"]) is not str or check["id"] not in cell["checks"]
                or check["status"] not in CHECK_STATUS or check["id"] in seen):
            raise SummaryError("record_checks_invalid")
        seen.add(check["id"])
        normalized_checks.append({"id": check["id"], "status": check["status"]})
    business = record["business"]
    if type(business) is not dict or set(business) != {"state", "evidence"} \
            or business["state"] not in {"observed", "not_observed", "unknown"}:
        raise SummaryError("record_business_invalid")
    if business["evidence"] is not None and (type(business["evidence"]) is not str
                                             or not business["evidence"].strip()):
        raise SummaryError("record_business_invalid")
    if business["state"] == "observed" and business["evidence"] is None:
        raise SummaryError("record_business_evidence_missing")
    content = record["content"]
    if type(content) is not dict or set(content) != {"status", "result"} \
            or content["status"] not in {"not_performed", "performed"}:
        raise SummaryError("record_content_invalid")
    if content["status"] == "performed" and (type(content["result"]) is not str
                                             or not content["result"].strip()):
        raise SummaryError("record_content_invalid")
    official = _number(record["official_reward"], "record_official_invalid")
    usage = record["usage"]
    if type(usage) is not dict or set(usage) != {"input_tokens", "output_tokens", "cost_usd"}:
        raise SummaryError("record_usage_invalid")
    usage = {"input_tokens": _number(usage["input_tokens"], "record_usage_invalid"),
             "output_tokens": _number(usage["output_tokens"], "record_usage_invalid"),
             "cost_usd": _number(usage["cost_usd"], "record_usage_invalid")}
    failure = record["failure"]
    if failure is not None:
        if (type(failure) is not dict or set(failure) != {"code", "phase"}
                or type(failure["code"]) is not str or not CODE.fullmatch(failure["code"])
                or type(failure["phase"]) is not str or not failure["phase"].strip()):
            raise SummaryError("record_failure_invalid")
    if run["status"] in {"failed", "blocked"} and failure is None:
        raise SummaryError("record_failure_missing")
    if run["status"] == "completed" and failure is not None:
        raise SummaryError("record_failure_unexpected")
    return {"cell": cell, "run": run, "logs": logs, "checks": normalized_checks,
            "business": business, "content": content, "official_reward": official,
            "usage": usage, "failure": failure}


def summarize(manifest_value, records) -> dict:
    manifest = validate_manifest(manifest_value)
    _, digest = freeze_manifest(manifest)
    planned = {}
    for cell in manifest["cells"]:
        for task in cell["tasks"]:
            planned[(cell["cell_id"], task["task_id"], task["role"], task["attempt"])] = {
                "cell_id": cell["cell_id"], "mechanism": cell["mechanism"], "mode": cell["mode"],
                "checks": list(task["checks"]), "role": task["role"]}
    if type(records) is not list:
        raise SummaryError("records_invalid")
    by_cell = {}
    for cell in manifest["cells"]:
        by_cell[cell["cell_id"]] = {
            "cell_id": cell["cell_id"], "mechanism": cell["mechanism"], "mode": cell["mode"],
            "planned": sum(1 for task in cell["tasks"]),
            "attempted": 0, "completed": 0, "failed": 0, "skipped": 0, "blocked": 0,
            "not_run": 0, "missing_evidence": 0,
            "checks": Counter({"pass": 0, "fail": 0, "na": 0, "not_run": 0}),
            "business": Counter(observed=0, not_observed=0, unknown=0),
            "content": Counter(not_performed=0, performed=0),
            "official_reward": Counter(present=0, absent=0),
            "usage": {"input_tokens_known_sum": 0, "input_tokens_missing": 0,
                      "output_tokens_known_sum": 0, "output_tokens_missing": 0,
                      "cost_usd_known_sum": 0, "cost_usd_missing": 0},
            "failure_codes": Counter(),
            "by_role": {},
        }
        for task in cell["tasks"]:
            role = by_cell[cell["cell_id"]]["by_role"].setdefault(
                task["role"], Counter(planned=0, attempted=0, completed=0, failed=0,
                                      skipped=0, blocked=0, not_run=0))
            role["planned"] += 1
    seen = set()
    for record in records:
        validated = _validate_record(record, manifest, planned)
        key = (record["cell_id"], record["task_id"], record["role"], record["attempt"])
        if key in seen:
            raise SummaryError("record_duplicate")
        seen.add(key)
        cell = by_cell[record["cell_id"]]
        role = cell["by_role"].setdefault(record["role"], Counter(
            planned=0, attempted=0, completed=0, failed=0, skipped=0, blocked=0, not_run=0))
        cell["attempted"] += 1
        role["attempted"] += 1
        status = validated["run"]["status"]
        cell[status] += 1
        role[status] += 1
        if not validated["logs"]["present"]:
            cell["missing_evidence"] += 1
        if status in {"failed", "blocked"}:
            cell["failure_codes"][validated["failure"]["code"]] += 1
        business_state = validated["business"]["state"]
        cell["business"][business_state] += 1
        content_status = validated["content"]["status"]
        cell["content"][content_status] += 1
        if validated["official_reward"] is None:
            cell["official_reward"]["absent"] += 1
        else:
            cell["official_reward"]["present"] += 1
        for field in ("input_tokens", "output_tokens", "cost_usd"):
            value = validated["usage"][field]
            if value is None:
                cell["usage"][field + "_missing"] += 1
            else:
                cell["usage"][field + "_known_sum"] += value
        planned_checks = set(planned[key]["checks"])
        received = {check["id"]: check["status"] for check in validated["checks"]}
        if status in {"skipped", "blocked"}:
            cell["checks"]["not_run"] += len(planned_checks)
        else:
            for check_id in planned_checks:
                cell["checks"][received.get(check_id, "not_run")] += 1
    total = {"planned": 0, "attempted": 0, "completed": 0, "failed": 0, "skipped": 0,
             "blocked": 0, "not_run": 0, "missing_evidence": 0}
    for cell in by_cell.values():
        cell["not_run"] = cell["planned"] - cell["attempted"]
        cell["checks"] = dict(cell["checks"])
        cell["business"] = dict(cell["business"])
        cell["content"] = dict(cell["content"])
        cell["official_reward"] = dict(cell["official_reward"])
        cell["failure_codes"] = dict(sorted(cell["failure_codes"].items()))
        cell["by_role"] = {role: dict(values) for role, values in sorted(cell["by_role"].items())}
        for role in cell["by_role"].values():
            role["not_run"] = role["planned"] - role["attempted"]
        for name in total:
            total[name] += cell[name]
    mechanisms = []
    for mechanism in sorted(MECHANISMS):
        cells = [cell for cell in by_cell.values() if cell["mechanism"] == mechanism]
        if not cells:
            continue
        modes = {cell["mode"] for cell in cells}
        mechanisms.append({
            "mechanism": mechanism,
            "comparison": "off_on" if modes == {"off", "on"} else "not_applicable",
            "cells": [cell["cell_id"] for cell in cells],
        })
    return {
        "schema": SCHEMA,
        "campaign_id": manifest["campaign_id"],
        "manifest_sha256": digest,
        "candidate": manifest["candidate"],
        "planned_tasks": total["planned"],
        "records": len(records),
        "totals": total,
        "cells": list(by_cell.values()),
        "mechanisms": mechanisms,
        "note": "counts/denominators only; no success rate, clinical verdict or official reward is synthesized",
    }


def main(argv=None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Summarize CHI experiment records")
    parser.add_argument("command", choices=("summarize",))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--records", required=True)
    args = parser.parse_args(argv)
    try:
        manifest_value = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        path = Path(args.records)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".jsonl":
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            records = json.loads(text)
        summary = summarize(manifest_value, records)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except (SummaryError, ManifestError, OSError, ValueError) as exc:
        code = getattr(exc, "code", "records_file_invalid")
        print(json.dumps({"status": "invalid", "code": code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
