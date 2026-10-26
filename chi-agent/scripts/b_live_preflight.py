#!/usr/bin/env python3
"""Read-only prepared B plan/preflight and synthetic-only official-runner rehearsal."""

from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from b_provider_profile import ProfileFailure, load_profile, validate_budget_evidence


class PreparationFailure(Exception):
    def __init__(self, code: str, phase: str = "preflight"):
        super().__init__(code)
        self.code = code
        self.phase = phase


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_RUNS = ROOT / "runs" / "b-provider-preflight" / "synthetic"
SYNTHETIC_REHEARSAL_CAP = Decimal("5")
APPLICATION_SOURCE_FILES = (
    "scripts/model_runner_adapter.py", "scripts/b_provider_profile.py",
    "scripts/b_provider_transport.py", "scripts/b_live_preflight.py",
)
FIXTURE_SCENARIOS = (
    "success", "http-429", "http-503", "connect-error", "timeout", "missing-usage",
    "invalid-final-usage", "over-output", "over-input", "over-document-context", "over-profile-output",
    "batch-valid-then-invalid", "duplicate-call-id",
    "final-no-reasoning", "final-content-whitespace", "post-tool-503",
)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _source_and_sdk() -> tuple[dict[str, Any], dict[str, str]]:
    try:
        import model_runner_adapter as adapter
        vendor = adapter._upstream_identity()
        sdk = adapter._sdk_identity()
        if sdk.get("httpx") != "0.28.1":
            raise PreparationFailure("sdk_version_mismatch")
        sources = {}
        for relative in APPLICATION_SOURCE_FILES:
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
        "budget": raw["budget"], "auth_state": "unverified",
        "actual_calls_authorized": False,
    }


def build_plan() -> dict[str, Any]:
    profile = load_profile()
    try:
        upstream, sdk = _source_and_sdk()
        identity = {"status": "verified_for_offline_integration", "sdk": sdk, "source": upstream}
    except PreparationFailure as exc:
        identity = {"status": "unavailable", "safe_error_code": exc.code, "sdk": None, "source": None}
    return {
        "mode": "read_only_plan", "profile": _profile_summary(profile),
        "identity": identity,
        "budget": {
            "scope": "shared_B_C", "cap_cny": "5", "currency": "CNY",
            "prior_spend": "unknown", "status": "unknown", "source": None,
            "real_aggregate_cost_cny": None,
        },
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


def build_preflight(budget_path: Path | None = None) -> dict[str, Any]:
    profile = load_profile()
    budget = validate_budget_evidence(budget_path)
    try:
        upstream, sdk = _source_and_sdk()
        identity = {"status": "verified_for_offline_integration", "sdk": sdk, "source": upstream}
    except PreparationFailure as exc:
        identity = {"status": "unavailable", "safe_error_code": exc.code, "sdk": None, "source": None}
    request_reserve = (
        Decimal(profile.input_reserve_tokens) * profile.input_price
        + Decimal(profile.max_output_tokens) * profile.output_price
    ) / Decimal(1_000_000)
    remaining = Decimal("5") - Decimal(budget["prior_spend_cny"]) if budget["status"] == "known" else None
    next_reserve_status = (
        "unknown" if remaining is None else
        "within_next_request_upper_bound" if remaining >= request_reserve else
        "insufficient_for_next_max_request_upper_bound"
    )
    ready = (budget["status"] == "known" and next_reserve_status == "within_next_request_upper_bound"
             and identity["status"] == "verified_for_offline_integration")
    return {
        "mode": "read_only_preflight", "profile": _profile_summary(profile), "identity": identity,
        "budget": {
            "scope": "shared_B_C", "cap_cny": "5", "currency": "CNY",
            "prior_spend_cny": budget["prior_spend_cny"], "source": budget["source"],
            "status": budget["status"], "safe_error_code": budget["code"],
            "remaining_cny": (str(Decimal("5") - Decimal(budget["prior_spend_cny"]))
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
                    synthetic_cap: Decimal = SYNTHETIC_REHEARSAL_CAP,
                    output_tokens: int | None = None) -> tuple[Any, Any, str | None]:
    try:
        from b_provider_transport import GuardFailure, SyntheticJournal
    except Exception:
        raise PreparationFailure("optional_sdk_layer_unavailable") from None
    try:
        from model_runner_adapter import _run_offline
    except Exception:
        raise PreparationFailure("optional_sdk_layer_unavailable") from None

    profile = load_profile()
    upstream, sdk = _source_and_sdk()
    try:
        journal = SyntheticJournal(SYNTHETIC_RUNS, run_id, initial_prior_cny=initial_prior,
                                   prior_source="synthetic-rehearsal-prior-v1", cap_cny=synthetic_cap)
    except GuardFailure as exc:
        raise PreparationFailure(exc.code, exc.phase) from None
    ledger = None
    result = None
    try:
        journal.set_metadata({
            "provider_profile": _profile_summary(profile), "sdk": sdk, "source_identity": upstream,
            "namespace": "synthetic", "real_budget_status": "unknown",
            "synthetic_rehearsal_budget_cny": str(synthetic_cap),
            "synthetic_rehearsal_budget_source": "fixed_offline_test_ceiling_not_shared_B_C_budget",
            "input_reservation_basis": "full_documented_context_ceiling_per_request_not_measured",
            "price_basis": "official_peak_cache_miss_upper_estimate_not_billed_cost",
            "retry_policy": {"http_client": 0, "agents_model": 0, "outer": 0, "synthetic_tool": 0},
            "real_usage": None, "real_cost_cny": None, "official_reward": None,
        })
        ledger, result = await _run_offline(scenario, prepared={
            "profile": profile, "journal": journal, "cap_cny": synthetic_cap,
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
    parser.add_argument("--budget-evidence", type=Path)
    parser.add_argument("--run-id")
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
        if args.mode == "plan":
            print(_json(build_plan()))
            return 0
        if args.mode == "preflight":
            result = build_preflight(args.budget_evidence)
            print(_json(result))
            return 0 if result["readiness"] == "technical_preflight_only" else 1
        if not args.run_id:
            parser.error("rehearse requires --run-id")
        journal, ledger, result = asyncio.run(_rehearse(args.scenario, args.run_id))
        success = ledger.error_code is None and result is not None
        print(_json({"mode": "synthetic_rehearsal", "status": "complete" if success else "incomplete",
                     "evidence": str(journal.run_path), "transport_send_count": ledger.transport_calls,
                     "safe_error_code": ledger.error_code, "cleanup_error_code": ledger.cleanup_error_code,
                     "real_usage": None, "real_cost_cny": None, "official_reward": None}))
        return 0 if success else 1
    except (ProfileFailure, PreparationFailure) as exc:
        code = exc.code
        print(_json({"status": "blocked" if args.mode != "rehearse" else "incomplete",
                     "safe_error_code": code, "credentials_read": False,
                     "real_usage": None, "real_cost_cny": None, "official_reward": None}))
        return 2 if getattr(exc, "phase", "preflight") == "preflight" else 1


if __name__ == "__main__":
    raise SystemExit(main())
