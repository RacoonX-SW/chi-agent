#!/usr/bin/env python3
"""Read-only prepared B plan/preflight and synthetic-only official-runner rehearsal."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from .execution_policy import (ExecutionPolicy, PolicyFailure, is_validated_policy,
                                load_local_policy, make_evaluation_policy)
from .provider_profile import ProfileFailure, load_profile, validate_budget_evidence


class PreparationFailure(Exception):
    def __init__(self, code: str, phase: str = "preflight"):
        super().__init__(code)
        self.code = code
        self.phase = phase


ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_RUNS = ROOT / "runs" / "b-provider-preflight" / "synthetic"
EVALUATION_RUNS = ROOT / "runs" / "evaluation-policy-rehearsal"
APPLICATION_SOURCE_FILES = (
    "src/chi_agent/model_runner_adapter.py", "src/chi_agent/budget_evaluation.py", "src/chi_agent/provider_profile.py", "src/chi_agent/execution_policy.py",
    "src/chi_agent/provider_transport.py", "src/chi_agent/evaluation_preflight.py", "profiles/local-development-policy.json",
)
FIXTURE_SCENARIOS = (
    "success", "http-429", "http-503", "connect-error", "timeout", "missing-usage",
    "invalid-final-usage", "over-output", "over-input", "over-document-context", "over-profile-output",
    "batch-valid-then-invalid", "duplicate-call-id",
    "final-no-reasoning", "final-content-whitespace", "post-tool-503", "evaluation-over-five",
)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _source_and_sdk(application_files: tuple[str, ...] = APPLICATION_SOURCE_FILES) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        from . import model_runner_adapter as adapter
        vendor = adapter._upstream_identity()
        sdk = adapter._sdk_identity()
        if sdk.get("httpx") != "0.28.1":
            raise PreparationFailure("sdk_version_mismatch")
        sources = {}
        for relative in application_files:
            path = ROOT / relative
            sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"vendor": vendor, "application_identity": "sha256_of_explicit_runner_guard_sources",
                "application_sources_sha256": sources}, sdk
    except Exception as exc:
        code = getattr(exc, "code", None)
        if exc.__class__.__name__ == "PackageNotFoundError":
            code = "sdk_package_missing"
        elif isinstance(exc, ModuleNotFoundError):
            code = "optional_sdk_layer_unavailable"
        if code not in {"sdk_version_mismatch", "upstream_identity_unavailable", "upstream_identity_mismatch"}:
            if code not in {"sdk_package_missing", "optional_sdk_layer_unavailable"}:
                code = "source_or_sdk_identity_unavailable"
        raise PreparationFailure(code) from None


def _profile_summary(profile) -> dict[str, Any]:
    raw = profile.raw
    return {
        "profile_id": raw["profile_id"], "profile_sha256": profile.sha256,
        "candidate": raw["candidate"], "model": raw["model"],
        "documented_model_mapping": raw["documented_model_mapping"],
        "model_mapping_status": raw["model_mapping_status"],
        "response_model_policy": raw["response_model_policy"],
        "endpoint": raw["endpoint"], "api": raw["api"], "key_env_name": raw["key_env"],
        "thinking": raw["thinking"], "reasoning_effort": raw["reasoning_effort"],
        "max_rounds": raw["max_rounds"], "max_output_tokens": raw["max_output_tokens"],
        "documented_output_ceiling": raw["documented_output_ceiling"],
        "input_reservation": raw["input_reservation"], "pricing": raw["pricing"],
        "auth_state": "unverified",
        "actual_calls_authorized": False,
    }


def _policy_summary(policy: ExecutionPolicy) -> dict[str, Any]:
    return {"policy_id": policy.policy_id, "policy_sha256": policy.sha256,
            "scope": policy.scope, "mode": policy.mode,
            "hard_cap_cny": str(policy.hard_cap_cny) if policy.hard_cap_cny is not None else None,
            "is_final_frozen_evaluation_policy": False if policy.scope == "evaluation_rehearsal" else None}


def build_plan(policy: ExecutionPolicy | None = None) -> dict[str, Any]:
    policy = policy or load_local_policy()
    if not is_validated_policy(policy):
        raise PreparationFailure("execution_policy_invalid")
    profile = load_profile()
    try:
        upstream, sdk = _source_and_sdk()
        identity = {"status": "verified_for_offline_integration", "sdk": sdk, "source": upstream}
    except PreparationFailure as exc:
        identity = {"status": "unavailable", "safe_error_code": exc.code, "sdk": None, "source": None}
    budget = ({
        "scope": "shared_B_C", "cap_cny": str(policy.hard_cap_cny), "currency": "CNY",
        "prior_spend": "unknown", "status": "unknown", "source": None,
        "real_aggregate_cost_cny": None,
    } if policy.scope == "local_development" else {
        "scope": "per_evaluation_attempt", "mode": policy.mode,
        "cap_cny": _policy_summary(policy)["hard_cap_cny"], "currency": "CNY",
        "prior_spend": "not_applicable", "status": "not_read", "source": "isolated_attempt",
        "real_aggregate_cost_cny": None,
    })
    return {
        "mode": "read_only_plan", "profile": _profile_summary(profile),
        "execution_policy": _policy_summary(policy),
        "identity": identity,
        "budget": budget,
        "authorization": {"execution_paused": True, "real_api_enabled": False,
                           "official_task_world": False, "grading": False},
        "side_effects": {"files_written": False, "client_created": False,
                          "http_transport_created": False, "credentials_read": False,
                          "ledger_or_claim_created": False},
        "limits_and_estimates": {
            "input_bound": "documented context ceiling, not tokenizer measured",
            "price": "official peak/cache-miss upper estimate, not billed cost",
            "estimated_cost_per_max_request_cny": str(
                (Decimal(profile.input_reserve_tokens) * profile.input_price
                 + Decimal(profile.max_output_tokens) * profile.output_price) / Decimal(1_000_000)
            ),
            "request_wire_byte_limit": "resource guard only; not a token estimate",
        },
    }


def build_preflight(budget_path: Path | None = None, *, policy: ExecutionPolicy | None = None) -> dict[str, Any]:
    policy = policy or load_local_policy()
    if not is_validated_policy(policy):
        raise PreparationFailure("execution_policy_invalid")
    if policy.scope == "evaluation_rehearsal":
        if budget_path is not None:
            raise PreparationFailure("development_budget_not_applicable")
        profile = load_profile()
        try:
            upstream, sdk = _source_and_sdk()
            identity = {"status": "verified_for_offline_integration", "sdk": sdk, "source": upstream}
        except PreparationFailure as exc:
            identity = {"status": "unavailable", "safe_error_code": exc.code, "sdk": None, "source": None}
        return {
            "mode": "read_only_evaluation_policy_preflight", "profile": _profile_summary(profile),
            "execution_policy": _policy_summary(policy), "identity": identity,
            "budget": {"scope": "per_evaluation_attempt", "mode": policy.mode,
                       "cap_cny": _policy_summary(policy)["hard_cap_cny"],
                       "prior_spend": "not_applicable", "status": "not_read",
                       "real_aggregate_usage": None, "real_aggregate_cost_cny": None},
            "readiness": "identified_evaluation_policy_rehearsal_not_frozen",
            "authorization": {"execution_paused": True, "actual_calls_authorized": False,
                               "authentication": "unverified", "official_task_world": False, "grading": False},
            "side_effects": {"files_written": False, "client_created": False,
                             "http_transport_created": False, "credentials_read": False,
                             "ledger_or_claim_created": False},
        }
    profile = load_profile()
    budget = validate_budget_evidence(budget_path, cap_cny=policy.hard_cap_cny)
    try:
        upstream, sdk = _source_and_sdk()
        identity = {"status": "verified_for_offline_integration", "sdk": sdk, "source": upstream}
    except PreparationFailure as exc:
        identity = {"status": "unavailable", "safe_error_code": exc.code, "sdk": None, "source": None}
    request_reserve = (
        Decimal(profile.input_reserve_tokens) * profile.input_price
        + Decimal(profile.max_output_tokens) * profile.output_price
    ) / Decimal(1_000_000)
    remaining = policy.hard_cap_cny - Decimal(budget["prior_spend_cny"]) if budget["status"] == "known" else None
    next_reserve_status = (
        "unknown" if remaining is None else
        "within_next_request_upper_bound" if remaining >= request_reserve else
        "insufficient_for_next_max_request_upper_bound"
    )
    ready = (budget["status"] == "known" and next_reserve_status == "within_next_request_upper_bound"
             and identity["status"] == "verified_for_offline_integration")
    return {
        "mode": "read_only_preflight", "profile": _profile_summary(profile),
        "execution_policy": _policy_summary(policy), "identity": identity,
        "budget": {
            "scope": "shared_B_C", "cap_cny": str(policy.hard_cap_cny), "currency": "CNY",
            "prior_spend_cny": budget["prior_spend_cny"], "source": budget["source"],
            "status": budget["status"], "safe_error_code": budget["code"],
            "remaining_cny": (str(policy.hard_cap_cny - Decimal(budget["prior_spend_cny"]))
                              if budget["status"] == "known" else None),
            "next_max_request_reserve_upper_cny": str(request_reserve),
            "next_request_reserve_status": next_reserve_status,
            "max_full_requests_at_profile_ceiling": (
                int(remaining // request_reserve) if remaining is not None else None
            ),
            "real_aggregate_cost_cny": None,
        },
        "readiness": "technical_preflight_only" if ready else "blocked_or_unknown",
        "authorization": {"execution_paused": True, "actual_calls_authorized": False,
                           "authentication": "unverified"},
        "side_effects": {"files_written": False, "client_created": False,
                          "http_transport_created": False, "credentials_read": False,
                          "ledger_or_claim_created": False},
    }


async def _rehearse(scenario: str, run_id: str, *, initial_prior: Decimal = Decimal("0"),
                    synthetic_cap: Decimal | None = None, output_tokens: int | None = None,
                    policy: ExecutionPolicy | None = None, evaluation_id: str | None = None,
                    task_id: str | None = None, attempt_id: str | None = None,
                    output_root: Path | None = None,
                    application_files: tuple[str, ...] = APPLICATION_SOURCE_FILES,
                    execution_identity_sha256: str | None = None,
                    official_launch: dict[str, Any] | None = None) -> tuple[Any, Any, str | None]:
    try:
        from .provider_transport import EvaluationJournal, GuardFailure, SyntheticJournal
    except Exception:
        raise PreparationFailure("optional_sdk_layer_unavailable") from None
    try:
        from .model_runner_adapter import _run_offline
    except Exception:
        raise PreparationFailure("optional_sdk_layer_unavailable") from None

    profile = load_profile()
    policy = policy or load_local_policy()
    if not is_validated_policy(policy):
        raise PreparationFailure("execution_policy_invalid")
    if policy.scope == "evaluation_rehearsal":
        if (any(x is None for x in (evaluation_id, task_id, attempt_id))
                or synthetic_cap is not None or type(initial_prior) is not Decimal
                or not initial_prior.is_finite() or initial_prior != Decimal(0)):
            raise PreparationFailure("evaluation_identity_or_prior_invalid")
    elif (policy.scope != "local_development" or any(x is not None for x in (evaluation_id, task_id, attempt_id))
          or (synthetic_cap is not None and (type(synthetic_cap) is not Decimal
                                            or not synthetic_cap.is_finite()
                                            or synthetic_cap != policy.hard_cap_cny))):
        raise PreparationFailure("execution_policy_scope_invalid")
    upstream, sdk = _source_and_sdk(application_files)
    try:
        if policy.scope == "evaluation_rehearsal":
            journal = EvaluationJournal(output_root or EVALUATION_RUNS, run_id, evaluation_id=evaluation_id,
                                        task_id=task_id, attempt_id=attempt_id, policy=policy, profile=profile,
                                        execution_identity_sha256=execution_identity_sha256)
        else:
            if output_root is not None or execution_identity_sha256 is not None:
                raise PreparationFailure("execution_identity_scope_invalid")
            journal = SyntheticJournal(SYNTHETIC_RUNS, run_id, initial_prior_cny=initial_prior,
                                       prior_source="synthetic-rehearsal-prior-v1",
                                       cap_cny=policy.hard_cap_cny, policy=policy)
    except GuardFailure as exc:
        raise PreparationFailure(exc.code, exc.phase) from None
    ledger = None
    result = None
    try:
        journal.set_metadata({
            "provider_profile": _profile_summary(profile), "sdk": sdk, "source_identity": upstream,
            "execution_policy": _policy_summary(policy),
            "evaluation_identity": ({"evaluation_id": evaluation_id, "task_id": task_id, "attempt_id": attempt_id}
                                    if policy.scope == "evaluation_rehearsal" else None),
            "namespace": policy.scope, "real_budget_status": "unknown",
            "cost_estimate_kind": "synthetic_provider_usage_times_documented_peak_price_not_billed_cost",
            "input_reservation_basis": "full_documented_context_ceiling_per_request_not_measured",
            "price_basis": "official_peak_cache_miss_upper_estimate_not_billed_cost",
            "retry_policy": {"http_client": 0, "agents_model": 0, "outer": 0, "synthetic_tool": 0},
            "real_usage": None, "real_cost_cny": None, "official_reward": None,
            "official_launch": ({
                "instruction_sha256": hashlib.sha256(
                    official_launch["instruction"].encode("utf-8")).hexdigest(),
                "mcp_url": official_launch["mcp_url"],
                "logs_dir": str(official_launch["logs_dir"]),
                "transport": "synthetic_only",
            } if official_launch is not None else None),
        })
        ledger, result = await _run_offline(scenario, prepared={
            "profile": profile, "journal": journal, "policy": policy,
            "cap_cny": policy.hard_cap_cny,
            **({"official_launch": official_launch} if official_launch is not None else {}),
            **({"output_tokens": output_tokens} if output_tokens is not None else {}),
        })
        journal.set_result(send_count=ledger.transport_calls, effects=ledger.effects or [],
                           observed_tool_history=ledger.tool_exchanges or [], final_response=result)
        if ledger.error_code:
            journal.mark_error(ledger.error_code)
        journal.finish(success=ledger.error_code is None and result is not None,
                       cleanup_error_code=ledger.cleanup_error_code)
        return journal, ledger, result
    except GuardFailure as exc:
        try:
            journal.mark_error(exc.code)
            journal.finish(success=False)
        except Exception:
            pass
        raise PreparationFailure(exc.code) from None
    except Exception:
        try:
            journal.mark_error("rehearsal_failed")
            journal.finish(success=False)
        except Exception:
            pass
        raise PreparationFailure("rehearsal_failed", "rehearsal") from None
    finally:
        journal.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "preflight", "rehearse", "live"))
    parser.add_argument("--execution-scope", choices=("local_development", "evaluation"), default="local_development")
    parser.add_argument("--budget-evidence", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--evaluation-id")
    parser.add_argument("--task-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--evaluation-policy", choices=("record_only", "capped"))
    parser.add_argument("--evaluation-cap-cny")
    parser.add_argument("--scenario", choices=FIXTURE_SCENARIOS, default="success")
    args = parser.parse_args(argv)

    # Live is intentionally decided before profile, environment, client, or
    # journal access; no command-line option or profile can authorize it.
    if args.mode == "live":
        print(_json({"mode": "live", "status": "rejected", "safe_error_code": "real_execution_paused",
                     "credentials_read": False, "client_created": False,
                     "transport_created": False, "ledger_or_claim_created": False}))
        return 2
    try:
        if args.execution_scope == "evaluation":
            if args.budget_evidence is not None:
                raise PreparationFailure("development_budget_not_applicable")
            if args.evaluation_policy is None:
                raise PreparationFailure("evaluation_policy_required")
            try:
                policy = make_evaluation_policy(args.evaluation_policy, args.evaluation_cap_cny)
            except PolicyFailure as exc:
                raise PreparationFailure(exc.code) from None
        else:
            if any((args.evaluation_id, args.task_id, args.attempt_id,
                    args.evaluation_policy, args.evaluation_cap_cny)):
                raise PreparationFailure("evaluation_options_require_evaluation_scope")
            policy = load_local_policy()
        if args.mode == "plan":
            print(_json(build_plan(policy)))
            return 0
        if args.mode == "preflight":
            result = build_preflight(args.budget_evidence, policy=policy)
            if policy.scope == "evaluation_rehearsal":
                print(_json(result))
                return 0
            print(_json(result))
            return 0 if result["readiness"] == "technical_preflight_only" else 1
        if not args.run_id:
            raise PreparationFailure("run_id_required")
        if policy.scope == "evaluation_rehearsal" and not all((args.evaluation_id, args.task_id, args.attempt_id)):
            raise PreparationFailure("evaluation_identity_required")
        if policy.scope == "local_development" and any((args.evaluation_id, args.task_id, args.attempt_id)):
            raise PreparationFailure("evaluation_identity_requires_evaluation_scope")
        journal, ledger, result = asyncio.run(_rehearse(
            args.scenario, args.run_id, policy=policy,
            evaluation_id=args.evaluation_id, task_id=args.task_id, attempt_id=args.attempt_id,
        ))
        success = ledger.error_code is None and result is not None
        print(_json({"mode": ("identified_evaluation_policy_rehearsal" if policy.scope == "evaluation_rehearsal"
                               else "synthetic_rehearsal"), "status": "complete" if success else "incomplete",
                     "evidence": str(journal.run_path), "transport_send_count": ledger.transport_calls,
                     "execution_policy": _policy_summary(policy),
                     "evaluation_identity": ({"evaluation_id": args.evaluation_id, "task_id": args.task_id,
                                              "attempt_id": args.attempt_id, "run_id_is_output_label_only": True}
                                             if policy.scope == "evaluation_rehearsal" else None),
                     "safe_error_code": ledger.error_code, "cleanup_error_code": ledger.cleanup_error_code,
                     "real_usage": None, "real_cost_cny": None, "official_reward": None}))
        return 0 if success else 1
    except (ProfileFailure, PreparationFailure, PolicyFailure) as exc:
        code = exc.code
        print(_json({"status": "blocked" if args.mode != "rehearse" else "incomplete",
                     "safe_error_code": code, "credentials_read": False,
                     "real_usage": None, "real_cost_cny": None, "official_reward": None}))
        return 2 if getattr(exc, "phase", "preflight") == "preflight" else 1


if __name__ == "__main__":
    raise SystemExit(main())
