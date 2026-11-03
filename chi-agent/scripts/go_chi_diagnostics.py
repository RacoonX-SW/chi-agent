"""Finite, safe diagnostic causes for Go CHI evidence (stdlib only).

The module defines the only allowed stage/reason pairs and validates both
diagnostic versions. It never imports runtime, SDK or ledger modules and never
accepts free text: producers pass a stage/reason pair, never an exception
message.
"""
from __future__ import annotations

import json
import re

SCHEMA_V1 = "chi-go-diagnostic-v1"
SCHEMA_V2 = "chi-go-diagnostic-v2"
CAUSE_SCHEMA = "chi-safe-cause-v1"
CODE = re.compile(r"[a-z0-9_]{1,64}")
MAX_CAUSE_BYTES = 256

STAGES = {
    "tool_batch": frozenset({"assistant_shape", "unfinished_batch", "call_shape",
                             "call_id_invalid", "call_id_reused", "function_shape",
                             "tool_unknown", "arguments_json", "arguments_schema"}),
    "request": frozenset({"route_invalid", "body_invalid", "history_invalid",
                          "budget_exceeded", "time_limit"}),
    "response": frozenset({"invalid_json", "shape_invalid", "output_truncated",
                           "too_large", "http_error", "secret_detected"}),
    "usage": frozenset({"unknown", "over_limit"}),
    "transport": frozenset({"cancelled", "timeout", "request_error", "unknown"}),
    "persistence": frozenset({"evidence_write", "state_write", "log_write"}),
    "summary": frozenset({"rejected"}),
    "recovery": frozenset({"rejected"}),
    "other": frozenset({"unspecified"}),
}

_CODE_CAUSES = {
    "chi_route_invalid": ("request", "route_invalid"),
    "chi_headers_invalid": ("request", "body_invalid"),
    "chi_request_invalid": ("request", "body_invalid"),
    "chi_request_limit": ("request", "budget_exceeded"),
    "chi_run_time_limit": ("request", "time_limit"),
    "chi_response_invalid": ("response", "shape_invalid"),
    "chi_response_json_invalid": ("response", "invalid_json"),
    "chi_output_truncated": ("response", "output_truncated"),
    "chi_response_too_large": ("response", "too_large"),
    "chi_http_error": ("response", "http_error"),
    "chi_secret_in_body": ("response", "secret_detected"),
    "chi_usage_unknown": ("usage", "unknown"),
    "chi_usage_over_limit": ("usage", "over_limit"),
    "chi_cancelled": ("transport", "cancelled"),
    "chi_timeout": ("transport", "timeout"),
    "chi_transport_error": ("transport", "request_error"),
    "chi_transport_unknown": ("transport", "unknown"),
    "chi_evidence_persistence_failed": ("persistence", "evidence_write"),
    "chi_persistence_failed": ("persistence", "state_write"),
    "chi_log_persistence_failed": ("persistence", "log_write"),
    "chi_b_receipt_persistence_failed": ("persistence", "state_write"),
    "chi_aux_response_invalid": ("response", "shape_invalid"),
    "chi_aux_transport_error": ("transport", "request_error"),
    "chi_aux_cancelled": ("transport", "cancelled"),
    "chi_summary_invalid": ("summary", "rejected"),
    "chi_summary_unavailable": ("summary", "rejected"),
    "chi_summary_source_changed": ("summary", "rejected"),
    "chi_summary_limit": ("summary", "rejected"),
    "chi_summary_configuration_invalid": ("summary", "rejected"),
    "chi_recovery_invalid": ("recovery", "rejected"),
    "chi_recovery_history_changed": ("recovery", "rejected"),
    "chi_recovery_limit": ("recovery", "rejected"),
    "chi_recovery_persistence_failed": ("recovery", "rejected"),
}


def build_cause(stage: str, reason: str) -> dict:
    if stage not in STAGES or reason not in STAGES[stage]:
        raise ValueError("diagnostic_cause_invalid")
    cause = {"schema": CAUSE_SCHEMA, "stage": stage, "reason": reason}
    if len(json.dumps(cause, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_CAUSE_BYTES:
        raise ValueError("diagnostic_cause_invalid")
    return cause


def validate_cause(value) -> bool:
    if type(value) is not dict or set(value) != {"schema", "stage", "reason"}:
        return False
    if value.get("schema") != CAUSE_SCHEMA:
        return False
    stage, reason = value.get("stage"), value.get("reason")
    if type(stage) is not str or type(reason) is not str:
        return False
    if stage not in STAGES or reason not in STAGES[stage]:
        return False
    try:
        return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= MAX_CAUSE_BYTES
    except (TypeError, ValueError):
        return False


def cause_for_code(code: str) -> dict | None:
    pair = _CODE_CAUSES.get(code)
    if pair is None:
        return None if code == "ok" else build_cause("other", "unspecified")
    return build_cause(*pair)


def validate_v1(doc: dict) -> bool:
    return (type(doc) is dict and doc.get("schema") == SCHEMA_V1
            and doc.get("kind") == "diagnostic" and type(doc.get("code")) is str
            and CODE.fullmatch(doc["code"]) is not None
            and type(doc.get("elapsed_ms")) is int and not isinstance(doc.get("elapsed_ms"), bool)
            and doc["elapsed_ms"] >= 0)


def validate_v2(doc: dict) -> bool:
    if type(doc) is not dict or set(doc) != {"schema", "kind", "code", "elapsed_ms", "cause"}:
        return False
    if doc.get("schema") != SCHEMA_V2 or doc.get("kind") != "diagnostic":
        return False
    if type(doc.get("code")) is not str or CODE.fullmatch(doc["code"]) is None:
        return False
    elapsed = doc.get("elapsed_ms")
    if type(elapsed) is not int or isinstance(elapsed, bool) or elapsed < 0:
        return False
    cause = doc.get("cause")
    if doc["code"] == "ok":
        return cause is None
    return validate_cause(cause)
