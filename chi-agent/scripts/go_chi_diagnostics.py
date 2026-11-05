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


SAFE_ERROR_CODES = frozenset(_CODE_CAUSES) | frozenset("""
chi_ack_hash_mismatch
chi_ack_inflight
chi_ack_invalid
chi_ack_provider_mismatch
chi_ack_target_invalid
chi_admission_seconds
chi_attempt_or_run_exists
chi_aux_broker_invalid
chi_aux_cancelled
chi_aux_failed
chi_aux_parent_invalid
chi_aux_request_invalid
chi_aux_request_limit
chi_aux_response_invalid
chi_aux_route_invalid
chi_aux_transport_error
chi_b_batch_invalid
chi_b_contract_invalid
chi_b_dispatch_failed
chi_b_dispatch_invalid
chi_b_incomplete
chi_b_order_invalid
chi_b_receipt_invalid
chi_b_receipt_missing
chi_b_receipt_persistence_failed
chi_bench
chi_billing_halted
chi_billing_invalid
chi_cancelled
chi_capabilities_invalid
chi_claim_invalidated
chi_claim_violation
chi_cleanup_failed
chi_config_invalid
chi_confirmation
chi_confirmation_limit
chi_context_budget_exceeded
chi_context_budget_invalid
chi_context_persistence_failed
chi_credential_missing
chi_diagnostic_invalid
chi_entry_failed
chi_evidence_invalid
chi_evidence_path_invalid
chi_evidence_persistence_failed
chi_evidence_shadow_input_invalid
chi_evidence_shadow_invalid
chi_evidence_shadow_role_invalid
chi_external_history_invalid
chi_fatal_unknown
chi_fee_policy_invalid
chi_final_missing
chi_guard_invalid
chi_guidance_role_invalid
chi_handbook_invalid
chi_harness_environment_invalid
chi_harness_exec_failed
chi_harness_history_invalid
chi_harness_identity_invalid
chi_harness_input_invalid
chi_harness_key_missing
chi_harness_log_failed
chi_harness_log_invalid
chi_harness_mcp_invalid
chi_harness_path_invalid
chi_harness_preflight_failed
chi_harness_preflight_log_failed
chi_harness_role_invalid
chi_headers_invalid
chi_history_invalid
chi_history_missing
chi_http_error
chi_identity_and_paths_required
chi_identity_invalid
chi_inspect_hash_mismatch
chi_inspect_invalid
chi_instruction_forbidden
chi_instruction_invalid
chi_interrupted
chi_launch_inputs_required
chi_launch_path_overlap
chi_local_arguments_invalid
chi_local_dispatch_unvalidated
chi_local_edit_invalid
chi_local_guard_missing
chi_local_history_path_invalid
chi_local_history_required
chi_local_path_invalid
chi_local_role_invalid
chi_local_write_failed
chi_log_persistence_failed
chi_manifest_identity_mismatch
chi_manifest_identity_required
chi_max_output_tokens
chi_max_requests
chi_mcp_arguments_invalid
chi_mcp_call_unvalidated
chi_mcp_guard_missing
chi_mcp_name_collision
chi_mcp_result_invalid
chi_mcp_role_ambiguous
chi_mcp_role_invalid
chi_mcp_role_mismatch
chi_mcp_schema_invalid
chi_mcp_transport_error
chi_mcp_url_invalid
chi_migration_hash_mismatch
chi_migration_history_unsettled
chi_migration_invalid
chi_operator_seconds
chi_output_path_invalid
chi_output_truncated
chi_package_module_missing
chi_path_invalid
chi_patient_probe_failed
chi_pending_invalid
chi_persistence_failed
chi_provider_record_invalid
chi_reasoning_invalid
chi_reconcile_hash_mismatch
chi_reconcile_identity_mismatch
chi_reconcile_inflight
chi_reconcile_inputs_required
chi_reconcile_invalid
chi_reconcile_provider_mismatch
chi_reconcile_target_invalid
chi_recovery_history_changed
chi_recovery_invalid
chi_recovery_limit
chi_recovery_persistence_failed
chi_recovery_replay
chi_recovery_tool_unclassified
chi_reference_invalid
chi_reference_required
chi_request_invalid
chi_request_limit
chi_reservation_invalid
chi_resource_root_invalid
chi_response_invalid
chi_response_json_invalid
chi_response_too_large
chi_route_invalid
chi_run_contract_invalid
chi_run_input_invalid
chi_run_log_invalid
chi_run_time_limit
chi_runner_failed
chi_runner_logs_invalid
chi_runner_trajectory_invalid
chi_sdk_identity_mismatch
chi_sdk_identity_unavailable
chi_secret_in_body
chi_state_case_mismatch
chi_state_exists
chi_state_invalid
chi_state_limit
chi_state_missing
chi_state_patient_unbound
chi_state_persistence_failed
chi_state_source_conflict
chi_state_source_not_business
chi_state_source_not_read
chi_state_source_unobserved
chi_state_stale
chi_state_target_invalid
chi_state_target_locked
chi_state_target_required
chi_state_unknown_invalid
chi_state_update_invalid
chi_status_invalid
chi_summary_configuration_invalid
chi_summary_invalid
chi_summary_limit
chi_summary_persistence_failed
chi_summary_replay
chi_summary_source_changed
chi_summary_unavailable
chi_system_prompt_invalid
chi_timeout
chi_tool_batch_invalid
chi_tool_cancelled
chi_tool_event_invalid
chi_tool_execution_failed
chi_tool_name_collision
chi_transport_error
chi_transport_missing
chi_transport_unknown
chi_unknown_write_effect
chi_usage_over_limit
chi_usage_unknown
go_billing_halted
go_chi_context
go_chi_diagnostics
go_chi_guard
go_chi_guidance
go_chi_mcp
go_chi_recovery
go_chi_runtime
go_chi_search
go_chi_state
go_chi_summary
go_chi_tools
go_cleanup_failed
go_client_invalid
go_credential_missing
go_final_invalid
go_headers_invalid
go_history_invalid
go_history_missing
go_http_error
go_identity_unavailable
go_journal_locked_or_invalid
go_pending_invalid
go_persistence_failed
go_preflight_unavailable
go_probe_failed
go_probe_incomplete
go_probe_unavailable
go_profile_invalid
go_rebind_incomplete
go_rebind_not_allowed
go_rebind_reason_invalid
go_request_invalid
go_request_limit_reached
go_response_invalid
go_response_model_mismatch
go_route_invalid
go_secret_in_body
go_state_invalid
go_tool_arguments_invalid
go_tool_batch_invalid
go_tool_not_validated
go_tool_order_invalid
go_transport_unknown
go_usage_over_limit
go_usage_unknown
go_verification_failed
""".split())


def is_safe_error_code(code) -> bool:
    return type(code) is str and code in SAFE_ERROR_CODES


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
