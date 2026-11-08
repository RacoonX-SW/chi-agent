#!/usr/bin/env python3
"""Identified Go CHI runner; all task resources and persistent state are external."""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).absolute().parent.parent
sys.dont_write_bytecode = True

from evaluation_bundle import BundleFailure, _check_components, _read_regular_bounded
from go_chi_bundle import validate_bundle
from go_chi_context import (DEFAULT_BUDGET, DEFAULT_BUDGET_V3, budget_from_bytes,
                            budget_from_input_tokens)
from go_chi_diagnostics import is_safe_error_code, validate_cause
from go_chi_journal import ChiJournal, publish_b_receipt
from go_chi_local import acquire_existing_history
from go_chi_policy import TIME_POLICY, FEE_POLICY, RECOVERY_POLICY, SUMMARY_POLICY, SUMMARY_VERSIONS, summary_policy
from opencode_go_provider import GoFailure, INSTRUCTION, SYSTEM, load_profile

CONFIG = {"schema": "chi-go-evaluation-entry-v1", "provider_profile_id": "opencode-go-deepseek-v4.1-flash-v1",
          "policy_mode": "record_only", "hard_cap_usd": None, "chi_max_requests": 50,
          "chi_max_output_tokens": 8192, "confirmation_max_requests": 2,
          "confirmation_max_output_tokens": 32768, "coding_b_max_requests": 6,
          "coding_b_max_output_tokens": 1024, "automatic_retries": 0, "time_policy": TIME_POLICY, "fee_policy": FEE_POLICY,
          "output_recovery_policy": RECOVERY_POLICY, "input_summary_policy": SUMMARY_POLICY,
          "input_summary_policy_v2": summary_policy('chi-input-summary-v2')}
DIGEST = re.compile(r"^[0-9a-f]{64}$")
REQUIREMENTS_POLICY = "chi-requirements-v1"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _same(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict): return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


RUN_LOG_SCHEMA = "chi-go-run-log-v2"
MAX_RUN_LOG_BYTES = 1024 * 1024
_RUN_LOG_KEYS = frozenset({
    "schema", "status", "safe_error_code", "safe_cause", "provider_requests",
    "physical_requests", "logical_model_steps", "recovery_policy",
    "recovery_permits_consumed", "recovery_limits", "journal_usage",
    "journal_usage_scope", "current_run_agent_usage", "tool_events",
    "final_output_claimed", "elapsed_ms", "official_reward",
    "input_summary_policy", "summary_events", "capabilities", "guidance_version",
    "guidance_sha256", "task_state_version", "task_state_target",
    "task_state_claim", "task_state_claim_violation", "task_state_open_unknowns",
    "completion", "task_state_sha256", "context_budget", "context_requests",
    "context_max_chars", "context_max_estimated_tokens", "context_prompt_tokens",
    "context_max_estimated_tokens_upper", "context_max_estimated_tokens_calibrated",
    "context_prompt_tokens_observed", "context_bytes_per_token_actual",
    "patient_simulator_requests", "patient_simulator_input_tokens_known",
    "patient_simulator_output_tokens_known", "first_error_code",
    "outer_error_code", "cleanup_error_code", "journal_error_code",
    "log_fallback", "log_fallback_reason", "requirements_policy",
})
_RUN_LOG_INTS = frozenset({
    "provider_requests", "logical_model_steps", "recovery_permits_consumed",
    "tool_events", "elapsed_ms", "summary_events", "task_state_version",
    "context_requests", "context_max_chars", "context_max_estimated_tokens",
    "context_prompt_tokens", "context_max_estimated_tokens_upper",
    "context_max_estimated_tokens_calibrated", "context_prompt_tokens_observed",
    "patient_simulator_requests",
    "patient_simulator_input_tokens_known", "patient_simulator_output_tokens_known",
})
_RUN_LOG_STRINGS = frozenset({
    "status", "safe_error_code", "recovery_policy", "journal_usage_scope",
    "input_summary_policy", "capabilities", "guidance_version", "guidance_sha256",
    "task_state_sha256", "context_budget", "first_error_code", "outer_error_code",
    "cleanup_error_code", "journal_error_code", "log_fallback_reason",
    "requirements_policy",
})
_RUN_LOG_FLOATS = frozenset({"context_bytes_per_token_actual"})
_RUN_LOG_JSON = frozenset({
    "safe_cause", "physical_requests", "recovery_limits", "journal_usage",
    "current_run_agent_usage", "task_state_target", "task_state_claim",
    "task_state_open_unknowns", "completion",
})
_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,64}$")


_COMPLETION_REASON = re.compile(
    r"^completion_(blocked_claim_violation|blocked_unknown|file_write_failed|readback_required|"
    r"requirements_undeclared|requirements_empty|requirements_open|requirements_evidence_invalid|"
    r"missing_step|terminal_object_missing|business_write_failed)"
    r"(:[A-Za-z0-9_.-]{1,128})?$")
_TARGET_KEYS = {"case_id", "patient_id"}
_CLAIM_KEYS = {"version", "target", "verified_status_call_id", "at_utc_ms", "kind"}
_REFERENCE_KEYS = {"call_id", "tool", "seq", "event"}
_STATUS_KEYS = {"text", "source_call_id", "source_seq", "source_tool",
                "source_kind", "source_scope", "source_event"}
_COMPLETION_V2_KEYS = {
    "schema", "verification", "business_effect", "reason", "target", "claim",
    "claim_policy", "latest_business_status", "last_business_mutation",
    "last_file_mutation", "last_mutation_call_id", "required_readback",
    "open_unknowns", "claim_violation", "stagnation", "remaining_limitations", "note",
}
_COMPLETION_V3_KEYS = _COMPLETION_V2_KEYS | {"unresolved_file_deliveries"}
_COMPLETION_V4_KEYS = _COMPLETION_V3_KEYS | {"requirements"}
_COMPLETION_V5_KEYS = _COMPLETION_V3_KEYS | {"completion_evidence"}
_REQUIREMENTS_KEYS = {"policy", "instruction_sha256", "declared", "status", "count",
                      "done", "waived", "open", "open_ids", "verification",
                      "semantic_completion_verified"}
_REQUIREMENTS_STATUSES = {"undeclared", "empty_unverified", "open",
                          "closed_reported", "closed_with_waivers"}
_SOURCE_KINDS = {"business_status", "business_mutation", "business_evidence",
                 "policy_evidence", "file_evidence", "file_deliverable",
                 "patient_evidence", "neutral", "unknown_mutation", "other_evidence"}
_EVENTS = {"returned", "returned_error", "refused", "failed"}
_PHYSICAL_KEYS = {"main", "confirmation", "continuation", "patient_simulator", "summary"}


def _is_int(value, minimum=0):
    return type(value) is int and not isinstance(value, bool) and value >= minimum


def _is_text(value, limit=256, *, allow_newlines=False, allow_empty=False):
    if type(value) is not str or len(value) > limit or (not value and not allow_empty):
        return False
    for ch in value:
        if allow_newlines and ch in "\n\t":
            continue
        if ord(ch) < 32 or ord(ch) == 127:
            return False
    return True


def _is_code(value, *, allow_none=True):
    if value is None:
        return allow_none
    return is_safe_error_code(value)


def _is_target(value):
    return (type(value) is dict and set(value) == _TARGET_KEYS
            and all(item is None or _is_text(item, 96) for item in value.values()))


def _is_claim(value):
    if value is None:
        return True
    return (type(value) is dict and set(value) == _CLAIM_KEYS
            and _is_int(value["version"])
            and _is_target(value["target"])
            and (value["verified_status_call_id"] is None
                 or _is_text(value["verified_status_call_id"], 128))
            and _is_int(value["at_utc_ms"], 1)
            and value["kind"] == "model_claim")


def _is_reference(value):
    if value is None:
        return True
    return (type(value) is dict and set(value) == _REFERENCE_KEYS
            and _is_text(value["call_id"], 128) and _is_text(value["tool"], 128)
            and _is_int(value["seq"], 1) and type(value["event"]) is str
            and value["event"] in _EVENTS)


def _is_status_view(value):
    if value is None:
        return True
    return (type(value) is dict and set(value) == _STATUS_KEYS
            and _is_text(value["text"], 800, allow_newlines=True)
            and _is_text(value["source_call_id"], 128)
            and _is_int(value["source_seq"], 1)
            and _is_text(value["source_tool"], 128)
            and type(value["source_kind"]) is str
            and value["source_kind"] in _SOURCE_KINDS
            and _is_text(value["source_scope"], 128)
            and type(value["source_event"]) is str
            and value["source_event"] in _EVENTS)


def _is_open_unknowns(value):
    return (type(value) is list and len(value) <= 16
            and all(type(item) is str and re.fullmatch(r"u[0-9]{1,3}", item)
                    for item in value))


def _is_requirements(value):
    if type(value) is not dict or set(value) != _REQUIREMENTS_KEYS:
        return False
    if value["policy"] != REQUIREMENTS_POLICY:
        return False
    if (type(value["instruction_sha256"]) is not str
            or not DIGEST.fullmatch(value["instruction_sha256"])):
        return False
    if type(value["declared"]) is not bool:
        return False
    if type(value["status"]) is not str or value["status"] not in _REQUIREMENTS_STATUSES:
        return False
    for key in ("count", "done", "waived", "open"):
        if not _is_int(value[key]):
            return False
    if value["count"] != value["done"] + value["waived"] + value["open"]:
        return False
    open_ids = value["open_ids"]
    if (type(open_ids) is not list or len(open_ids) > 8
            or len(open_ids) != value["open"]
            or any(type(item) is not str or not re.fullmatch(r"r[0-9]{1,2}", item)
                   for item in open_ids)
            or len(set(open_ids)) != len(open_ids)):
        return False
    if value["verification"] != "provenance_only":
        return False
    if value["semantic_completion_verified"] is not False:
        return False
    return True


def _is_completion(value):
    if type(value) is not dict:
        return False
    schema = value.get("schema")
    if schema == "chi-completion-v2":
        keys = _COMPLETION_V2_KEYS
    elif schema == "chi-completion-v3":
        keys = _COMPLETION_V3_KEYS
    elif schema == "chi-completion-v4":
        keys = _COMPLETION_V4_KEYS
    elif schema == "chi-completion-v5":
        keys = _COMPLETION_V5_KEYS
        if "requirements" in value:
            keys = keys | {"requirements"}
    else:
        return False
    if set(value) != keys:
        return False
    if type(value["verification"]) is not str \
            or value["verification"] not in {"mechanical_pass", "not_applicable", "blocked"}:
        return False
    if type(value["business_effect"]) is not str \
            or value["business_effect"] not in {"observed", "not_observed", "not_verified",
                                                "unknown", "violation"}:
        return False
    reason = value["reason"]
    if reason is not None and (type(reason) is not str
                               or not _COMPLETION_REASON.fullmatch(reason)):
        return False
    if not _is_target(value["target"]) or not _is_claim(value["claim"]):
        return False
    if value["claim_policy"] not in {"optional_final_text", "mandatory_claim"}:
        return False
    if schema == "chi-completion-v5" and value["claim_policy"] != "mandatory_claim":
        return False
    if not _is_status_view(value["latest_business_status"]):
        return False
    if not _is_reference(value["last_business_mutation"]) \
            or not _is_reference(value["last_file_mutation"]):
        return False
    if value["last_mutation_call_id"] is not None \
            and not _is_text(value["last_mutation_call_id"], 128):
        return False
    if type(value["required_readback"]) is not str \
            and value["required_readback"] is not None:
        return False
    if value["required_readback"] not in {None, "business_status", "file_delivery"}:
        return False
    if not _is_open_unknowns(value["open_unknowns"]):
        return False
    if type(value["claim_violation"]) is not bool:
        return False
    stagnation = value["stagnation"]
    if stagnation is not None:
        if (type(stagnation) is not dict
                or set(stagnation) != {"tool", "count", "call_id", "effect"}
                or not _is_text(stagnation["tool"], 128)
                or not _is_int(stagnation["count"], 1)
                or (stagnation["call_id"] is not None
                    and not _is_text(stagnation["call_id"], 128))
                or not _is_text(stagnation["effect"], 64)):
            return False
    limitations = value["remaining_limitations"]
    allowed_limitations = {"final_text_without_claim_not_blocked"}
    if schema == "chi-completion-v4":
        allowed_limitations.add("requirements_provenance_only_not_semantic_completion")
    if schema == "chi-completion-v5":
        allowed_limitations.add("requirements_provenance_only_not_semantic_completion")
    if (type(limitations) is not list
            or any(type(item) is not str
                   or item not in allowed_limitations
                   for item in limitations)):
        return False
    if not _is_text(value["note"], 1024, allow_newlines=True):
        return False
    if schema in {"chi-completion-v3", "chi-completion-v4", "chi-completion-v5"}:
        unresolved = value["unresolved_file_deliveries"]
        if type(unresolved) is not list or len(unresolved) > 256:
            return False
        for item in unresolved:
            if (type(item) is not dict
                    or set(item) != {"call_id", "tool", "resource", "event"}
                    or not _is_text(item["call_id"], 128)
                    or not _is_text(item["tool"], 128)
                    or not _is_text(item["resource"], 2048)
                    or type(item["event"]) is not str
                    or item["event"] not in {"failed", "returned_error"}):
                return False
    if schema == "chi-completion-v5":
        evidence = value["completion_evidence"]
        if (type(evidence) is not dict
                or set(evidence) != {"schema", "policy", "missing_steps", "terminal_objects"}
                or evidence.get("schema") != "chi-completion-evidence-v1"
                or evidence.get("policy") != "chi-context-v3"
                or type(evidence.get("missing_steps")) is not list
                or any(type(item) is not list or not item
                       or any(type(name) is not str for name in item)
                       for item in evidence["missing_steps"])
                or type(evidence.get("terminal_objects")) is not list
                or any(type(name) is not str for name in evidence["terminal_objects"])):
            return False
    if schema == "chi-completion-v4" and not _is_requirements(value["requirements"]):
        return False
    return True


def _is_physical_requests(value):
    return (type(value) is dict and set(value) <= _PHYSICAL_KEYS
            and all(_is_int(item) for item in value.values()))


def _is_current_usage(value):
    return (type(value) is dict
            and set(value) == {"input_tokens_known", "output_tokens_known", "complete"}
            and _is_int(value["input_tokens_known"])
            and _is_int(value["output_tokens_known"])
            and type(value["complete"]) is bool)


def _is_recovery_limits(value):
    return (type(value) is dict
            and set(value) == {"per_chain", "per_run", "shared_requests"}
            and all(_is_int(item, 1) for item in value.values()))


def _is_journal_usage(value):
    if type(value) is not dict:
        return False
    if set(value) != {"input_tokens_known", "output_tokens_known", "usd",
                      "account_prior_history", "billing_details_warnings",
                      "billing_complete", "unsettled_requests"}:
        return False
    if not _is_int(value["input_tokens_known"]) or not _is_int(value["output_tokens_known"]):
        return False
    if value["account_prior_history"] != "unknown" or type(value["billing_complete"]) is not bool:
        return False
    if not _is_int(value["billing_details_warnings"]):
        return False
    usd = value["usd"]
    if type(usd) is not dict or set(usd) != {"charged_usd", "list_cost_usd", "allowance_usd"}:
        return False
    for item in usd.values():
        if (type(item) is not dict or set(item) != {"known", "complete"}
                or type(item["complete"]) is not bool
                or type(item["known"]) is not str or len(item["known"]) > 64
                or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?(?:E[+-]?[0-9]+)?", item["known"])):
            return False
    unsettled = value["unsettled_requests"]
    if type(unsettled) is not list or len(unsettled) > 256:
        return False
    for item in unsettled:
        if (type(item) is not dict or set(item) != {"run", "round", "status"}
                or not _is_text(item["run"], 64) or not _is_int(item["round"])
                or not _is_text(item["status"], 64)):
            return False
    return True


def _read_run_log(logs_dir):
    """Read a bounded, whitelisted run log; invalid input becomes None."""
    try:
        return _read_run_log_checked(logs_dir)
    except Exception:
        # A malformed nested value must not escape the error boundary.
        return None


def _read_run_log_checked(logs_dir):
    path = logs_dir / "run_log.txt"
    try:
        if path.is_symlink() or not path.is_file():
            return None
        raw = _read_regular_bounded(path, MAX_RUN_LOG_BYTES, "chi_run_log_invalid")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except Exception:
        return None
    if type(value) is not dict or value.get("schema") != RUN_LOG_SCHEMA:
        return None
    if any(key not in _RUN_LOG_KEYS for key in value):
        return None
    if value.get("log_fallback") is True:
        required = {"schema", "status", "safe_error_code", "official_reward",
                    "log_fallback", "log_fallback_reason"}
        if value.get("log_fallback_reason") != "invalid_or_missing_runtime_log":
            return None
    else:
        required = {"schema", "status", "safe_error_code", "provider_requests",
                    "tool_events", "official_reward"}
        if value.get("capabilities") == "f0-f3-v1":
            required |= {"completion", "task_state_target", "task_state_version",
                         "task_state_claim", "task_state_open_unknowns",
                         "task_state_claim_violation"}
    if not required <= set(value):
        return None
    for key, item in value.items():
        if key in _RUN_LOG_INTS:
            if not _is_int(item):
                return None
        elif key in _RUN_LOG_FLOATS:
            if type(item) is not float or item < 0 or item != item:
                return None
        elif key in _RUN_LOG_STRINGS:
            if item is not None and not _is_text(item, 256):
                return None
            if (key in {"safe_error_code", "first_error_code", "outer_error_code",
                        "cleanup_error_code", "journal_error_code"}
                    and not _is_code(item)):
                return None
            if key in {"guidance_sha256", "task_state_sha256"} and item is not None \
                    and not DIGEST.fullmatch(item):
                return None
            if key == "status" and item not in {"complete", "incomplete"}:
                return None
            if key == "recovery_policy" and item not in {None, "chi-output-recovery-v1"}:
                return None
            if key == "input_summary_policy" and item not in {
                    None, "chi-input-summary-v1", "chi-input-summary-v2"}:
                return None
            if key == "requirements_policy" and item not in {None, REQUIREMENTS_POLICY}:
                return None
            if key == "capabilities" and item not in {None, "f0-f3-v1"}:
                return None
            if key == "guidance_version" and item not in {
                    "chi-role-guidance-v1", "chi-role-guidance-v2", "chi-role-guidance-v3",
                    "chi-role-guidance-v4"}:
                return None
            if key == "context_budget" and item not in {
                    None, "chi-context-budget-v1", "chi-context-budget-v2", "chi-context-budget-v3"}:
                return None
            if key == "journal_usage_scope" and item not in {None, "account_namespace"}:
                return None
            if key == "log_fallback_reason" and item not in {
                    None, "invalid_or_missing_runtime_log"}:
                return None
        elif key in _RUN_LOG_JSON:
            validators = {
                "safe_cause": lambda item: item is None or validate_cause(item),
                "physical_requests": _is_physical_requests,
                "recovery_limits": _is_recovery_limits,
                "journal_usage": _is_journal_usage,
                "current_run_agent_usage": _is_current_usage,
                "task_state_target": _is_target,
                "task_state_claim": _is_claim,
                "task_state_open_unknowns": _is_open_unknowns,
                "completion": _is_completion,
            }
            if not validators[key](item):
                return None
        elif key == "official_reward":
            if item is not None:
                return None
        elif key in {"task_state_claim_violation", "final_output_claimed", "log_fallback"}:
            if type(item) is not bool:
                return None
    return value


def _write_run_log(logs_dir, value):
    path = logs_dir / "run_log.txt"
    try:
        if path.is_symlink():
            return False
        raw = json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_RUN_LOG_BYTES:
            return False
        with path.open("w", encoding="utf-8") as handle:
            handle.write(raw.decode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        return True
    except Exception:
        return False


def _failure_run_log(logs_dir, *, error, journal_error=None):
    """Preserve a valid runtime log and add the outer failure layer."""
    existing = _read_run_log(logs_dir)
    if existing is None:
        value = {"schema": RUN_LOG_SCHEMA, "status": "incomplete",
                 "safe_error_code": error, "first_error_code": error,
                 "outer_error_code": None, "log_fallback": True,
                 "log_fallback_reason": "invalid_or_missing_runtime_log",
                 "official_reward": None}
    else:
        value = dict(existing)
        first = existing.get("safe_error_code")
        if type(first) is not str or not _SAFE_CODE.fullmatch(first):
            first = error
            outer = None
        else:
            outer = error if error != first else None
        value.update({"schema": RUN_LOG_SCHEMA, "status": "incomplete",
                      "safe_error_code": first, "first_error_code": first,
                      "outer_error_code": outer, "log_fallback": False})
    if journal_error is not None:
        value["journal_error_code"] = journal_error
    return _write_run_log(logs_dir, value)


def _cleanup_run_log(logs_dir, code):
    existing = _read_run_log(logs_dir)
    if existing is None:
        value = {"schema": RUN_LOG_SCHEMA, "status": "incomplete",
                 "safe_error_code": code, "first_error_code": None,
                 "outer_error_code": None, "cleanup_error_code": code,
                 "log_fallback": True, "log_fallback_reason": "invalid_or_missing_runtime_log",
                 "official_reward": None}
    else:
        value = dict(existing)
        value.update({"status": "incomplete", "cleanup_error_code": code})
        if not value.get("safe_error_code"):
            value["safe_error_code"] = code
    return _write_run_log(logs_dir, value)


def _identity(expected):
    from model_runner_adapter import _sdk_identity, _upstream_identity
    from pdf_resource_reader import dependency_identity
    if type(expected) is not str or not DIGEST.fullmatch(expected):
        raise GoFailure("chi_manifest_identity_required")
    identity = validate_bundle(ROOT)
    if identity.manifest_sha256 != expected:
        raise GoFailure("chi_manifest_identity_mismatch")
    raw = _read_regular_bounded(ROOT / "profiles/go-chi-entry.json", 16384, "chi_config_invalid")
    try:
        config = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not _same(config, CONFIG): raise ValueError
    except Exception:
        raise GoFailure("chi_config_invalid") from None
    load_profile()
    sdk = _sdk_identity()
    if sdk.get("httpx") != "0.28.1":
        raise GoFailure("chi_sdk_identity_mismatch")
    for name, version in {"mcp": "1.30.0", "jsonschema": "4.26.0", "pydantic": "2.14.1",
                          "pydantic-core": "2.50.1", "httpcore": "1.0.9"}.items():
        try:
            if importlib.metadata.version(name) != version:
                raise ValueError
        except Exception:
            raise GoFailure("chi_sdk_identity_mismatch") from None
        sdk[name] = version
    upstream = _upstream_identity()
    pdf = dependency_identity(ROOT / "requirements-pdf.lock")
    sdk_sources = {}
    for module in ("agents", "openai", "httpx", "httpcore", "mcp", "jsonschema", "pydantic"):
        try:
            spec = importlib.util.find_spec(module)
            if spec is None or spec.origin is None:
                raise ValueError
            directory = Path(spec.origin).parent
            digest = hashlib.sha256()
            entries = list(directory.rglob("*"))
            if any(path.is_symlink() for path in entries):
                raise ValueError
            files = sorted(path for path in entries if path.suffix in {".py", ".pyc", ".so"})
            if not files or len(files) > 10000:
                raise ValueError
            for path in files:
                if path.is_symlink() or not path.is_file():
                    raise ValueError
                relative = path.relative_to(directory).as_posix()
                digest.update(relative.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
            sdk_sources[module] = digest.hexdigest()
        except Exception:
            raise GoFailure("chi_sdk_identity_unavailable") from None
    data = {"bundle_manifest_sha256": identity.manifest_sha256, "sdk": sdk, "sdk_sources_sha256": sdk_sources,
            "upstream": upstream, "pdf": pdf}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest(), data


def _path(value, *, exists=False):
    try:
        return _check_components(Path(value), "chi_path_invalid", final_may_be_missing=not exists)
    except BundleFailure:
        raise GoFailure("chi_path_invalid") from None


def _disjoint(a, b):
    return a != b and a not in b.parents and b not in a.parents


def _url(value):
    try:
        parsed = urlsplit(value)
        if (len(value) > 2048 or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path != "/mcp" or parsed.port is None or not 1 <= parsed.port <= 65535
                or "?" in value or "#" in value or any(ch.isspace() for ch in value)):
            raise ValueError
    except Exception:
        raise GoFailure("chi_mcp_url_invalid") from None
    return value


def _instruction(path):
    path = _path(path, exists=True)
    if (any(part.lower() in {"fixtures", "fixture", "hidden", "private", "verifier"} for part in path.parts)
            or path.name.lower() in {"tasks.jsonl", "task.jsonl", "expected.jsonl", ".env"}
            or path.name.startswith(".")):
        raise GoFailure("chi_instruction_forbidden")
    try:
        raw = _read_regular_bounded(path, 65536, "chi_instruction_invalid")
        text = raw.decode("utf-8")
        if not text.strip() or "\x00" in text: raise ValueError
    except Exception:
        raise GoFailure("chi_instruction_invalid") from None
    return path, text


def _handbook_digest(root: Path) -> str:
    digest = hashlib.sha256()
    try:
        paths = sorted(root.rglob("*"))
        if len(paths) > 10000: raise ValueError
        total = 0
        count = 0
        for path in paths:
            relative = path.relative_to(root)
            if any(part.startswith(".") or part.lower() in {"fixture", "fixtures", "verifier", "judge", "hidden", "private", "expectations"}
                   for part in relative.parts):
                continue
            if path.is_symlink(): raise ValueError
            if path.is_dir(): continue
            raw = _read_regular_bounded(path, 16 * 1024 * 1024, "chi_handbook_invalid")
            count += 1
            total += len(raw)
            if total > 64 * 1024 * 1024: raise ValueError
            digest.update(relative.as_posix().encode() + b"\0" + hashlib.sha256(raw).digest())
        if count == 0: raise ValueError
    except Exception:
        raise GoFailure("chi_handbook_invalid") from None
    return digest.hexdigest()


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "coding-b", "live", "audit-history", "rebind-history", "inspect-history", "acknowledge-unsettled", "reconcile-provider"))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--evaluation-id")
    parser.add_argument("--task-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--history-mode", choices=("local", "external"))
    parser.add_argument("--local-q-root", type=Path)
    parser.add_argument("--expected-old-identity")
    parser.add_argument("--expected-accounting-sha256")
    parser.add_argument("--migration-reason")
    parser.add_argument("--provider-record", type=Path)
    parser.add_argument("--provider-record-sha256")
    parser.add_argument("--target-run")
    parser.add_argument("--target-round", type=int)
    parser.add_argument("--expected-request-sha256")
    parser.add_argument("--acknowledgement-reason")
    parser.add_argument("--output-recovery", choices=(RECOVERY_POLICY["version"],), default=None)
    parser.add_argument("--recovery-view-policy", choices=("canonical-v1",), default=None)
    parser.add_argument("--input-summary", choices=SUMMARY_VERSIONS, default=None)
    parser.add_argument("--requirements", choices=(REQUIREMENTS_POLICY,), default=None)
    parser.add_argument("--context-max-estimated-tokens", type=int, default=None)
    parser.add_argument("--context-max-input-tokens", type=int, default=None)
    parser.add_argument("--main-max-tokens", type=int, default=None)
    parser.add_argument("--role", choices=("provider", "payer", "cm"))
    parser.add_argument("--instruction-file", type=Path)
    parser.add_argument("--mcp-url")
    parser.add_argument("--workspace-root", type=Path, default=Path("/logs/artifacts/workspaces"))
    parser.add_argument("--handbook-root", type=Path, default=Path("/workspace/skills/managed-care-operations-handbook"))
    parser.add_argument("--tool-reference", type=Path, action="append", default=[])
    return parser


async def _run_b(journal, secret):
    import httpx
    from openai import AsyncOpenAI
    from agents.models.openai_chatcompletions import Converter
    from go_chi_guard import ChiGuard
    from go_chi_runtime import coding_tools, run_coding_b
    holder = {}
    tools = coding_tools(lambda: holder["guard"])
    session = "chi-" + uuid.uuid4().hex
    guard = ChiGuard(journal, secret, session, httpx.AsyncHTTPTransport(retries=0, verify=True),
                     tools=[Converter.tool_to_openai(tool) for tool in tools], system=SYSTEM, instruction=INSTRUCTION,
                     claimed=lambda: False, confirmation=lambda: None)
    holder["guard"] = guard
    client = AsyncOpenAI(api_key=secret, base_url="https://opencode.ai/inference/go/openai/v1",
        default_headers={"User-Agent": "chi-agent", "X-OpenCode-Session": session}, max_retries=0,
        http_client=httpx.AsyncClient(transport=guard, trust_env=False, follow_redirects=False,
                                      timeout=httpx.Timeout(float(TIME_POLICY['main_read_seconds']),
                                                            connect=float(TIME_POLICY['connect_seconds']))))
    try:
        return await run_coding_b(client, guard, tools)
    finally:
        await client.close()


def main(argv=None, *, development=None):
    args = _parser().parse_args(argv)
    q = journal = None
    b_receipt = None
    output = {"status": "blocked", "official_reward": None}
    try:
        if args.requirements is not None and (args.mode != "live" or args.input_summary is not None
                                               or args.output_recovery is not None):
            raise GoFailure("chi_requirements_configuration_invalid")
        if args.input_summary is not None and (args.mode != 'live' or args.output_recovery is not None):
            raise GoFailure('chi_summary_configuration_invalid')
        if args.output_recovery is not None and args.mode != "live":
            raise GoFailure("chi_recovery_invalid")
        if args.context_max_estimated_tokens is not None and (
                args.mode != "live" or not 1 <= args.context_max_estimated_tokens <= 3_500_000):
            raise GoFailure("chi_context_budget_invalid")
        if args.context_max_input_tokens is not None and (
                args.mode != "live" or not 1 <= args.context_max_input_tokens <= 1_000_000):
            raise GoFailure("chi_context_budget_invalid")
        if args.context_max_estimated_tokens is not None and args.context_max_input_tokens is not None:
            raise GoFailure("chi_context_budget_invalid")
        if args.main_max_tokens is not None and (
                args.mode != "live" or not 1024 <= args.main_max_tokens <= 32768):
            raise GoFailure("chi_context_budget_invalid")
        if args.mode == "live" and (args.output_recovery is not None or args.input_summary is not None):
            if not (args.recovery_view_policy == "canonical-v1"
                    and args.output_recovery is not None
                    and args.input_summary is None):
                raise GoFailure("chi_context_policy_incompatible")
        identity, identity_detail = _identity(args.bundle_sha256)
        if args.mode == "preflight":
            import importlib
            for module in ("go_chi_diagnostics", "go_chi_context", "go_chi_recovery", "go_chi_summary", "go_chi_guidance", "go_chi_search", "go_chi_state",
                           "go_chi_guard", "go_chi_mcp", "go_chi_tools", "go_chi_runtime"):
                loaded = importlib.import_module(module)
                path = Path(getattr(loaded, "__file__", "")).resolve()
                if ROOT not in path.parents:
                    raise GoFailure("chi_package_module_missing")
            print(json.dumps({"status": "identity_verified", "identity_sha256": identity,
                              "identity": identity_detail, "official_reward": None}, sort_keys=True))
            return 0
        if args.mode == "reconcile-provider":
            from go_chi_journal import reconcile_provider_timeout
            if (args.history_mode != "external" or args.local_q_root is not None
                    or args.output_root is None or args.provider_record is None
                    or args.provider_record_sha256 is None or args.target_run is None
                    or args.target_round is None or args.expected_request_sha256 is None
                    or args.expected_accounting_sha256 is None or args.acknowledgement_reason is None):
                raise GoFailure("chi_reconcile_inputs_required")
            if args.expected_old_identity is not None and args.expected_old_identity != identity:
                raise GoFailure("chi_reconcile_identity_mismatch")
            result = reconcile_provider_timeout(
                _path(args.output_root, exists=True), identity=identity,
                accounting_sha256=args.expected_accounting_sha256, run=args.target_run,
                round_number=args.target_round, request_sha256=args.expected_request_sha256,
                provider_path=args.provider_record, provider_sha256=args.provider_record_sha256,
                reason=args.acknowledgement_reason)
            print(json.dumps({**result, "official_reward": None}, sort_keys=True))
            return 0
        if args.mode in {"audit-history", "rebind-history", "inspect-history", "acknowledge-unsettled"}:
            from go_chi_journal import audit_or_rebind, inspect_history, acknowledge_unsettled
            if args.history_mode != "local" or args.local_q_root is None or args.output_root is None:
                raise GoFailure("chi_local_history_required")
            qroot = _path(args.local_q_root, exists=True)
            root = _path(args.output_root, exists=True)
            if root != qroot / "chi-evaluation": raise GoFailure("chi_local_history_path_invalid")
            q = acquire_existing_history(qroot)
            if args.mode == 'acknowledge-unsettled':
                if args.provider_record is None or args.provider_record_sha256 is None:
                    raise GoFailure('chi_provider_record_invalid')
                result = acknowledge_unsettled(root, identity=args.expected_old_identity,
                    accounting_sha256=args.expected_accounting_sha256, run=args.target_run, round_number=args.target_round,
                    request_sha256=args.expected_request_sha256, provider_path=args.provider_record,
                    provider_sha256=args.provider_record_sha256, reason=args.acknowledgement_reason)
            elif args.mode == 'inspect-history':
                result = inspect_history(root, args.expected_old_identity, args.expected_accounting_sha256)
                if (args.provider_record is None) != (args.provider_record_sha256 is None):
                    raise GoFailure('chi_provider_record_invalid')
                if args.provider_record is not None:
                    from go_chi_inspect import inspect_provider
                    result['provider_record'] = inspect_provider(args.provider_record, args.provider_record_sha256,
                                                                result.get('pending_request'))
            else:
                if args.provider_record is not None or args.provider_record_sha256 is not None:
                    raise GoFailure('chi_provider_record_invalid')
                result = audit_or_rebind(root, args.expected_old_identity, args.expected_accounting_sha256,
                                         identity if args.mode == "rebind-history" else None, args.migration_reason)
            print(json.dumps({**result, "official_reward": None}, sort_keys=True))
            return 0
        if not all((args.evaluation_id, args.task_id, args.attempt_id, args.run_id, args.output_root,
                    args.logs_dir, args.history_mode)):
            raise GoFailure("chi_identity_and_paths_required")
        if args.mode == "coding-b" and (args.task_id != "synthetic-coding-b" or args.role or args.instruction_file or args.mcp_url):
            raise GoFailure("chi_b_contract_invalid")
        if args.mode == "live" and not all((args.role, args.instruction_file, args.mcp_url)):
            raise GoFailure("chi_launch_inputs_required")
        output_root, logs_dir, bundle = _path(args.output_root), _path(args.logs_dir), _path(ROOT, exists=True)
        if (not _disjoint(output_root, bundle) or not _disjoint(logs_dir, bundle)
                or not _disjoint(logs_dir, output_root) or logs_dir.exists() or not logs_dir.parent.is_dir()):
            raise GoFailure("chi_output_path_invalid")
        instruction_path = instruction = None
        launch = {"kind": "coding_b", "instruction_sha256": hashlib.sha256(INSTRUCTION.encode()).hexdigest(), "fee_policy": FEE_POLICY}
        if args.mode == "live":
            instruction_path, instruction = _instruction(args.instruction_file)
            if not _disjoint(instruction_path, output_root) or not _disjoint(instruction_path, logs_dir) or not _disjoint(instruction_path, bundle):
                raise GoFailure("chi_launch_path_overlap")
            _url(args.mcp_url)
            workspace = _path(args.workspace_root, exists=True)
            handbook = _path(args.handbook_root, exists=True)
            if (workspace != Path("/logs/artifacts/workspaces")
                    or handbook != Path("/workspace/skills/managed-care-operations-handbook")
                    or not workspace.is_dir() or not handbook.is_dir()):
                raise GoFailure("chi_resource_root_invalid")
            if any(not _disjoint(target, resource) for target in (output_root, logs_dir)
                   for resource in (workspace, handbook)):
                raise GoFailure("chi_launch_path_overlap")
            allowed_refs = {Path("/input/tool_reference.md"),
                            Path("/opt/healthverse-task-assets/tool_reference.md"),
                            Path("/opt/chi-bench-task-assets/tool_reference.md")}
            if not args.tool_reference:
                raise GoFailure("chi_reference_required")
            for reference in args.tool_reference:
                ref = _path(reference, exists=True)
                if (ref not in allowed_refs or not ref.is_file() or any(part.lower() in {"fixture", "fixtures", "hidden", "private", "verifier"}
                                              for part in ref.parts)
                        or any(not _disjoint(target, ref) for target in (output_root, logs_dir))):
                    raise GoFailure("chi_reference_invalid")
            references = {str(path): hashlib.sha256(_read_regular_bounded(_path(path, exists=True), 16 * 1024 * 1024,
                            "chi_reference_invalid")).hexdigest() for path in args.tool_reference}
            launch = {"kind": "chi", "role": args.role, "fee_policy": FEE_POLICY,
                      "instruction_sha256": hashlib.sha256(instruction.encode()).hexdigest(),
                      "mcp_url_sha256": hashlib.sha256(args.mcp_url.encode()).hexdigest(),
                      "tool_references_sha256": references, "handbook_sha256": _handbook_digest(handbook),
                      "context_policy": "chi-context-v3"}
            if args.output_recovery is not None:
                launch['output_recovery'] = args.output_recovery
            if args.recovery_view_policy is not None:
                launch['recovery_view_policy'] = args.recovery_view_policy
            if args.input_summary is not None:
                launch['input_summary'] = args.input_summary
            if args.requirements is not None:
                launch['requirements'] = args.requirements
            if args.main_max_tokens is not None:
                launch['main_max_tokens'] = args.main_max_tokens
            if development is not None and args.role == 'cm':
                launch['aux_contract'] = 'patient-simulator-v1'
        if args.history_mode == "local":
            if args.local_q_root is None:
                raise GoFailure("chi_local_history_required")
            qroot = _path(args.local_q_root, exists=True)
            # One deterministic CHI namespace beneath the existing Q root:
            # changing an output label cannot bypass a prior CHI pending claim.
            if output_root != qroot / "chi-evaluation" or not _disjoint(qroot, logs_dir):
                raise GoFailure("chi_local_history_path_invalid")
            q = acquire_existing_history(qroot)
        elif args.local_q_root is not None:
            raise GoFailure("chi_external_history_invalid")
        journal = ChiJournal(output_root, identity=identity, evaluation=args.evaluation_id, task=args.task_id,
                             attempt=args.attempt_id, run=args.run_id,
                             kind="coding_b" if args.mode == "coding-b" else "chi", require_b=args.mode == "live",
                             launch=launch)
        secret = os.environ.get("OPENCODE_API_KEY")
        if type(secret) is not str or not secret.strip():
            raise GoFailure("chi_credential_missing")
        if args.mode == "coding-b":
            logs_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
            text = asyncio.run(_run_b(journal, secret))
            (logs_dir / "run_output.txt").write_text(text, encoding="utf-8")
            (logs_dir / "run_result.json").write_text(json.dumps({"status": "complete", "official_reward": None,
                "run_id": args.run_id, "requests": len(journal.run["requests"]),
                "usage": journal.usage_totals()}, sort_keys=True), encoding="utf-8")
            (logs_dir / "run_log.txt").write_text(json.dumps({"schema": RUN_LOG_SCHEMA,
                "status": "complete", "safe_error_code": None,
                "provider_requests": len(journal.run["requests"]), "tool_events": len(journal.run["tool_events"]),
                "final_output_claimed": False, "official_reward": None}, sort_keys=True), encoding="utf-8")
        else:
            import httpx
            from go_chi_runtime import run_chi
            context_budget = dict(DEFAULT_BUDGET_V3)
            if context_budget.get("model") != "deepseek-v4.1-flash":
                raise GoFailure("chi_config_invalid")
            if args.context_max_estimated_tokens is not None:
                context_budget = budget_from_bytes(args.context_max_estimated_tokens, context_budget)
                launch["context_max_bytes"] = args.context_max_estimated_tokens
            if args.context_max_input_tokens is not None:
                context_budget = budget_from_input_tokens(args.context_max_input_tokens, context_budget)
                launch["context_max_input_tokens"] = args.context_max_input_tokens
            async def execute():
                kwargs = dict(role=args.role, instruction=instruction, mcp_url=args.mcp_url,
                    instruction_path=instruction_path, logs_dir=logs_dir, workspace_root=args.workspace_root,
                    handbook_root=args.handbook_root, tool_references=args.tool_reference,
                    lower=httpx.AsyncHTTPTransport(retries=0, verify=True),
                    capabilities="f0-f3-v1", requirements=args.requirements,
                    context_budget=context_budget,
                    main_max_tokens=args.main_max_tokens or 8192)
                if development is None:
                    return await run_chi(journal, secret, **kwargs)
                return await development(journal, secret, run_chi, kwargs)
            text = asyncio.run(execute())
        journal.finish("complete")
        if args.mode == "coding-b":
            journal.prepare_b_receipt()
            b_receipt = copy.deepcopy(journal.run)
        output = {"status": "complete", "run_id": args.run_id, "identity_sha256": identity,
                  "usage": journal.usage_totals(), "official_reward": None}
        code = 0
    except BaseException as exc:
        code = 1
        error = getattr(exc, "code", "chi_entry_failed")
        if type(error) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", error):
            error = "chi_entry_failed"
        output = {"status": "incomplete" if journal is not None else "blocked", "safe_error_code": error, "official_reward": None}
        journal_error = None
        if journal is not None:
            try:
                journal.finish("failed", error)
            except Exception:
                journal_error = "chi_persistence_failed"
                output["safe_error_code"] = journal_error
            logs = locals().get("logs_dir")
            if logs is not None and logs.is_dir():
                try:
                    (logs / "run_error.json").write_text(json.dumps(output, sort_keys=True), encoding="utf-8")
                except Exception:
                    output["safe_error_code"] = "chi_log_persistence_failed"
                if not _failure_run_log(logs, error=error, journal_error=journal_error):
                    output["safe_error_code"] = "chi_log_persistence_failed"
        if isinstance(exc, KeyboardInterrupt): output["safe_error_code"] = "chi_interrupted"
    finally:
        cleanup_error = None
        if journal is not None:
            try: journal.close()
            except Exception: cleanup_error = "chi_cleanup_failed"
        if q is not None:
            try: q.close()
            except Exception: cleanup_error = "chi_cleanup_failed"
        if cleanup_error is not None:
            output, code = {"status": "incomplete", "safe_error_code": cleanup_error, "official_reward": None}, 1
            logs = locals().get("logs_dir")
            if logs is not None and logs.is_dir():
                _cleanup_run_log(logs, cleanup_error)
    if code == 0 and b_receipt is not None:
        try:
            publish_b_receipt(output_root, identity, b_receipt)
        except Exception:
            output, code = {"status": "incomplete", "safe_error_code": "chi_b_receipt_persistence_failed", "official_reward": None}, 1
    print(json.dumps(output, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
