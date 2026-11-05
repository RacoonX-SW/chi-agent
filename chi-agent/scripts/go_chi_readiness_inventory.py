"""Read-only inventory of selected, already-recorded run metadata (D/P5).

v2 binds each output row to the exact file bytes read in one snapshot. If a
source changes during the read, the row is marked unstable and derived metrics
are not emitted. Missing/invalid/truncated sources remain null with an explicit
status; only complete evidence can produce 0/false. No model, world, Trial or
judge is started.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path("/workspace")
RUNS = [
    {"candidate": "W-actual", "role": "provider", "task": "public output CASE-ACT-001",
     "simulator": "none", "root": "runs/unified-role-cm-lifecycle-root/actual/w-go-c-provider-20261031-001"},
    {"candidate": "W-actual", "role": "payer", "task": "public output CASE-6B9F238D",
     "simulator": "none", "root": "runs/unified-role-cm-lifecycle-root/actual/w-go-c-payer-20261031-001"},
    {"candidate": "W-actual", "role": "cm", "task": "cm_afib_moderate_anxious_001",
     "simulator": "dev-go", "root": "runs/unified-role-cm-lifecycle-root/actual/w-go-c-cm-20261031-001"},
    {"candidate": "real-external-v2", "role": "provider", "task": "pa_t032_t032_o002_p01_new_referral_provider",
     "simulator": "none", "root": "runs/real-external/provider-001"},
    {"candidate": "real-external-v5", "role": "cm", "task": "cm_afib_moderate_anxious_001",
     "simulator": "dev-go", "root": "runs/real-external/cm-004"},
    {"candidate": "real-external-v7", "role": "payer", "task": "pa_t027_t027_o002_p01_nurse_review_payer",
     "simulator": "none", "root": "runs/real-external/payer-014"},
]

FILES = ("run_log.txt", "run_result.json", "context.jsonl", "trace.jsonl", "orchestration.json")
LIMITS = {"run_log.txt": 1024 * 1024, "run_result.json": 16 * 1024 * 1024,
          "context.jsonl": 64 * 1024 * 1024, "trace.jsonl": 64 * 1024 * 1024,
          "orchestration.json": 1024 * 1024}
MAX_LINES = 200000

WINDOWS = {
    "connect_seconds": 10,
    "main_read_seconds": 240,
    "main_io_seconds": 300,
    "confirmation_read_seconds": 360,
    "confirmation_io_seconds": 420,
    "chi_admission_seconds": 900,
    "b_admission_seconds": 180,
    "auxiliary_read_seconds": 450,
    "chi_operator_seconds": 1380,
    "role_runner_timeout_seconds": 1500,
    "role_operator_timeout_seconds": 2040,
}
_SAFE_INT = re.compile(r"^-?[0-9]+$")


def _read_raw(path, limit):
    if path.is_symlink():
        return {"status": "symlink", "bytes": None, "sha256": None, "data": None}
    if not path.is_file():
        return {"status": "missing", "bytes": None, "sha256": None, "data": None}
    try:
        data = path.read_bytes()
    except OSError:
        return {"status": "unreadable", "bytes": None, "sha256": None, "data": None}
    if len(data) > limit:
        return {"status": "oversized", "bytes": len(data), "sha256": None, "data": None}
    return {"status": "present", "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "data": data}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _json(entry):
    if entry["status"] != "present":
        return None, entry["status"]
    try:
        value = json.loads(entry["data"].decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except Exception:
        return None, "invalid"
    if type(value) is not dict:
        return None, "invalid"
    return value, "present"


def _jsonl(entry):
    if entry["status"] != "present":
        return None, entry["status"]
    try:
        lines = entry["data"].decode("utf-8").splitlines()
    except UnicodeError:
        return None, "invalid"
    if len(lines) > MAX_LINES:
        return None, "truncated"
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line, object_pairs_hook=_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except Exception:
            return None, "invalid"
        if type(row) is not dict:
            return None, "invalid"
        rows.append(row)
    if not rows:
        return [], "empty"
    return rows, "present"


def _int(value):
    return type(value) is int and not isinstance(value, bool) and value >= 0


def _snapshot(root):
    first = {name: _read_raw(root / "runner-logs" / "result" / name, LIMITS[name])
             if name != "orchestration.json" else _read_raw(root / name, LIMITS[name])
             for name in FILES}
    second = {name: _read_raw(root / "runner-logs" / "result" / name, LIMITS[name])
              if name != "orchestration.json" else _read_raw(root / name, LIMITS[name])
              for name in FILES}
    stable = all(first[name]["status"] == second[name]["status"]
                 and first[name]["sha256"] == second[name]["sha256"]
                 for name in FILES)
    return first, stable


_COMPLETION_V1 = {"schema", "verification", "business_effect", "reason", "target",
                   "claim", "last_mutation_call_id", "latest_business_status",
                   "open_unknowns", "claim_violation", "stagnation", "note"}
_COMPLETION_V2 = _COMPLETION_V1 | {"claim_policy", "last_business_mutation",
                                   "last_file_mutation", "required_readback",
                                   "remaining_limitations"}
_COMPLETION_V3 = _COMPLETION_V2 | {"unresolved_file_deliveries"}
_COMPLETION_KEYS = {"chi-completion-v1": _COMPLETION_V1,
                    "chi-completion-v2": _COMPLETION_V2,
                    "chi-completion-v3": _COMPLETION_V3}
_CLAIM_KEYS = {"version", "target", "verified_status_call_id", "at_utc_ms", "kind"}
_TRACE_ROLES = {"system", "user", "assistant", "tool", "reasoning"}
_EVENTS = {"returned", "returned_error", "refused", "failed"}
_SOURCE_KINDS = {"business_status", "business_mutation", "business_evidence",
                 "policy_evidence", "file_evidence", "file_deliverable",
                 "patient_evidence", "neutral", "unknown_mutation", "other_evidence"}


def _text(value):
    return type(value) is str and bool(value)


def _reference(value):
    return value is None or (type(value) is dict
        and set(value) == {"call_id", "tool", "seq", "event"}
        and _text(value["call_id"]) and _text(value["tool"])
        and _int(value["seq"]) and value["seq"] > 0
        and type(value["event"]) is str and value["event"] in _EVENTS)


def _status_view(value, schema):
    if value is None:
        return True
    keys = {"text", "source_call_id", "source_seq"}
    if schema != "chi-completion-v1":
        keys |= {"source_tool", "source_kind", "source_scope", "source_event"}
    if (type(value) is not dict or set(value) != keys
            or not _text(value["text"]) or not _text(value["source_call_id"])
            or not _int(value["source_seq"]) or value["source_seq"] <= 0):
        return False
    return schema == "chi-completion-v1" or (
        _text(value["source_tool"]) and _text(value["source_scope"])
        and type(value["source_kind"]) is str and value["source_kind"] in _SOURCE_KINDS
        and type(value["source_event"]) is str and value["source_event"] in _EVENTS)


def _stagnation(value):
    return value is None or (type(value) is dict
        and set(value) == {"tool", "count", "call_id", "effect"}
        and _text(value["tool"]) and _int(value["count"]) and value["count"] > 0
        and (value["call_id"] is None or _text(value["call_id"]))
        and _text(value["effect"]))


def _unresolved(value):
    return (type(value) is list and len(value) <= 256 and all(
        type(item) is dict and set(item) == {"call_id", "tool", "resource", "event"}
        and all(_text(item[key]) for key in ("call_id", "tool"))
        and (item["resource"] is None or _text(item["resource"]))
        and type(item["event"]) is str and item["event"] in {"failed", "returned_error"}
        for item in value))


def _completion_state(value):
    """Return (status, verification, reason, claim_present); incomplete is not false."""
    if value is None:
        return "missing", None, None, None
    if type(value) is not dict:
        return "invalid", None, None, None
    schema = value.get("schema")
    if type(schema) is not str:
        return "invalid", None, None, None
    keys = _COMPLETION_KEYS.get(schema)
    if keys is None:
        return "invalid", None, None, None
    if not keys <= set(value):
        return "incomplete", None, None, None
    if set(value) - keys:
        return "invalid", None, None, None
    if type(value["verification"]) is not str or value["verification"] not in {
            "mechanical_pass", "not_applicable", "blocked"}:
        return "invalid", None, None, None
    if type(value["business_effect"]) is not str or value["business_effect"] not in {
            "observed", "not_observed", "not_verified", "unknown", "violation"}:
        return "invalid", None, None, None
    if value["reason"] is not None and type(value["reason"]) is not str:
        return "invalid", None, None, None
    target = value["target"]
    if (type(target) is not dict or set(target) != {"case_id", "patient_id"}
            or any(item is not None and type(item) is not str for item in target.values())):
        return "invalid", None, None, None
    claim = value["claim"]
    if claim is not None:
        if (type(claim) is not dict or set(claim) != _CLAIM_KEYS
                or type(claim["version"]) is not int or isinstance(claim["version"], bool)
                or claim["version"] < 0
                or type(claim["target"]) is not dict
                or set(claim["target"]) != {"case_id", "patient_id"}
                or any(item is not None and type(item) is not str
                       for item in claim["target"].values())
                or (claim["verified_status_call_id"] is not None
                    and type(claim["verified_status_call_id"]) is not str)
                or type(claim["at_utc_ms"]) is not int or isinstance(claim["at_utc_ms"], bool)
                or claim["at_utc_ms"] <= 0 or claim["kind"] != "model_claim"):
            return "invalid", None, None, None
    if type(value["claim_violation"]) is not bool:
        return "invalid", None, None, None
    if type(value["open_unknowns"]) is not list or any(
            type(item) is not str for item in value["open_unknowns"]):
        return "invalid", None, None, None
    if not _status_view(value["latest_business_status"], schema):
        return "invalid", None, None, None
    if not _stagnation(value["stagnation"]):
        return "invalid", None, None, None
    if value["last_mutation_call_id"] is not None and not _text(value["last_mutation_call_id"]):
        return "invalid", None, None, None
    if type(value["note"]) is not str:
        return "invalid", None, None, None
    if schema in {"chi-completion-v2", "chi-completion-v3"}:
        if type(value["claim_policy"]) is not str:
            return "invalid", None, None, None
        if any(not _reference(value[key])
               for key in ("last_business_mutation", "last_file_mutation")):
            return "invalid", None, None, None
        if (value["required_readback"] is not None
                and type(value["required_readback"]) is not str):
            return "invalid", None, None, None
        if value["required_readback"] not in {None, "business_status", "file_delivery"}:
            return "invalid", None, None, None
        if (type(value["remaining_limitations"]) is not list
                or any(type(item) is not str for item in value["remaining_limitations"])):
            return "invalid", None, None, None
    if schema == "chi-completion-v3":
        if not _unresolved(value["unresolved_file_deliveries"]):
            return "invalid", None, None, None
    return "present", value["verification"], value["reason"], claim is not None


def _trace_counts(rows, status):
    """Only a complete, structurally valid trace may produce 0/false-like counts."""
    if status != "present":
        return None, None, None, status
    for row in rows:
        if (type(row) is not dict or type(row.get("role")) is not str
                or row.get("role") not in _TRACE_ROLES
                or type(row.get("content")) is not str):
            return None, None, None, "invalid"
    refusals = errors = unknown_writes = 0
    for row in rows:
        if row["role"] != "tool":
            continue
        content = row["content"]
        if content.startswith("REFUSED:"):
            refusals += 1
        elif content.startswith("UNKNOWN_WRITE_EFFECT:"):
            unknown_writes += 1
        elif content.startswith("ERROR:"):
            errors += 1
    return refusals, errors, unknown_writes, "present"


def inventory(item):
    root = ROOT / item["root"]
    snapshot, stable = _snapshot(root)
    hashes = {name: {key: snapshot[name][key] for key in ("status", "bytes", "sha256")}
              for name in FILES}
    base = {"candidate": item["candidate"], "role": item["role"], "task": item["task"],
            "simulator": item["simulator"], "run": root.name,
            "source_hashes": hashes, "snapshot_stable": stable}
    if not stable:
        base.update({"snapshot_status": "changed_during_read", "status": None,
                     "provider_requests": None, "input_tokens": None,
                     "output_tokens": None, "completion_verification": None,
                     "completion_reason": None, "claim_present": None,
                     "trace_refusals": None, "trace_errors": None,
                     "trace_unknown_write_effects": None})
        return base

    run_log, run_log_status = _json(snapshot["run_log.txt"])
    result, result_status = _json(snapshot["run_result.json"])
    orchestration, orchestration_status = _json(snapshot["orchestration.json"])
    context, context_status = _jsonl(snapshot["context.jsonl"])
    trace, trace_status = _jsonl(snapshot["trace.jsonl"])

    status = run_log.get("status") if run_log_status == "present" else None
    provider_requests = run_log.get("provider_requests") if run_log_status == "present" else None
    if not _int(provider_requests):
        provider_requests = None
    sdk_turns = result.get("turns") if result_status == "present" else None
    if not _int(sdk_turns):
        sdk_turns = None
    input_tokens = result.get("input_tokens") if result_status == "present" else None
    output_tokens = result.get("output_tokens") if result_status == "present" else None
    if not _int(input_tokens):
        input_tokens = None
    if not _int(output_tokens):
        output_tokens = None

    context_complete = context_status == "present" and all(
        _int(row.get("total_chars")) and _int(row.get("estimated_tokens")) for row in context)
    context_chars = max(row["total_chars"] for row in context) if context_complete else None
    context_tokens = max(row["estimated_tokens"] for row in context) if context_complete else None
    purposes = {}
    if context_status == "present":
        for row in context:
            purpose = row.get("purpose")
            if type(purpose) is str:
                purposes[purpose] = purposes.get(purpose, 0) + 1

    refusals, errors, unknown_writes, trace_status = _trace_counts(trace, trace_status)

    completion = run_log.get("completion") if run_log_status == "present" else None
    if run_log_status != "present":
        completion_status = "run_log_" + run_log_status
        completion_verification = completion_reason = claim_present = None
    else:
        completion_status, completion_verification, completion_reason, claim_present =             _completion_state(completion)

    elapsed_ms = run_log.get("elapsed_ms") if run_log_status == "present" else None
    elapsed_source = "run_log" if _int(elapsed_ms) else None
    if not _int(elapsed_ms) and orchestration_status == "present":
        elapsed_ms = orchestration.get("elapsed_ms")
        elapsed_source = "orchestration" if _int(elapsed_ms) else None
    if not _int(elapsed_ms):
        elapsed_ms = None
        elapsed_source = None
    admission_margin = (max(0, WINDOWS["chi_admission_seconds"] * 1000 - elapsed_ms)
                        if _int(elapsed_ms) else None)

    official_reward = None
    official_reward_source = None
    reward_values = []
    if run_log_status == "present" and "official_reward" in run_log:
        reward_values.append(("run_log", run_log["official_reward"]))
    if orchestration_status == "present" and "official_reward" in orchestration:
        reward_values.append(("orchestration", orchestration["official_reward"]))
    if reward_values and all(value is None for _, value in reward_values):
        official_reward_source = "+".join(name for name, _ in reward_values)
    elif reward_values and all(type(value) in (int, float) and value in (0, 1)
                               for _, value in reward_values) and all(
                                   value == reward_values[0][1] for _, value in reward_values):
        official_reward = reward_values[0][1]
        official_reward_source = reward_values[0][0]
    elif reward_values:
        official_reward_source = "conflict"

    base.update({
        "snapshot_status": "stable",
        "run_log_status": run_log_status,
        "run_result_status": result_status,
        "context_status": context_status,
        "trace_status": trace_status,
        "orchestration_status": orchestration_status,
        "status": status if type(status) is str else None,
        "safe_error_code": run_log.get("safe_error_code") if run_log_status == "present" else None,
        "runner_exit_code": orchestration.get("runner_exit_code") if orchestration_status == "present" else None,
        "provider_requests": provider_requests,
        "sdk_turns": sdk_turns,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": result.get("cached_tokens") if result_status == "present" else None,
        "cost_usd": result.get("cost_usd") if result_status == "present" else None,
        "context_requests": len(context) if context_status == "present" else None,
        "context_max_chars": context_chars,
        "context_max_estimated_tokens": context_tokens,
        "context_fields_complete": context_complete if context_status == "present" else None,
        "estimated_token_ratio": None,
        "estimated_token_ratio_status": "not_measured_no_same_request_usage",
        "context_purposes": purposes,
        "elapsed_ms": elapsed_ms,
        "elapsed_source": elapsed_source,
        "chi_admission_margin_ms_coarse": admission_margin,
        "tool_events": run_log.get("tool_events") if run_log_status == "present" else None,
        "trace_refusals": refusals,
        "trace_unknown_write_effects": unknown_writes,
        "trace_errors": errors,
        "completion_status": completion_status,
        "completion_verification": completion_verification,
        "completion_reason": completion_reason,
        "claim_present": claim_present,
        "patient_simulator_requests": run_log.get("patient_simulator_requests")
        if run_log_status == "present" else None,
        "patient_simulator_input_tokens_known": run_log.get("patient_simulator_input_tokens_known")
        if run_log_status == "present" else None,
        "patient_simulator_output_tokens_known": run_log.get("patient_simulator_output_tokens_known")
        if run_log_status == "present" else None,
        "official_reward": official_reward,
        "official_reward_source": official_reward_source,
    })
    for key in ("tool_events", "patient_simulator_requests",
                "patient_simulator_input_tokens_known",
                "patient_simulator_output_tokens_known"):
        if not _int(base[key]):
            base[key] = None
    return base


def main():
    rows = [inventory(item) for item in RUNS]
    payload = {
        "schema": "chi-score-readiness-inventory-v2",
        "read_only": True,
        "runs": rows,
        "windows": WINDOWS,
        "notes": [
            "each row is bound to the SHA-256 of the exact bytes read; snapshot_stable=false means no mixed metrics were emitted.",
            "missing/invalid/truncated sources stay null with explicit status; only complete trace/context evidence can produce 0.",
            "estimated_token_ratio is not measured because context.jsonl has no same-request actual token count.",
            "elapsed_ms is a coarse runner/orchestration value; admission margin is an upper bound, not a request timestamp.",
            "this inventory does not claim stable p95, score improvement or causal effects.",
        ],
    }
    print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
