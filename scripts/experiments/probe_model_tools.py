#!/usr/bin/env python3
"""Run a bounded, offline-only synthetic Chat Completions protocol probe."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chi_agent.model_adapter import (
    BudgetProfile,
    CANDIDATE_PROFILE,
    ProbeFailure,
    build_request,
    estimate_input_token_upper_bound,
    execute_synthetic_tool,
    extract_assistant_message,
    make_assistant_message,
    parse_usage,
    validate_tool_batch,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = PROJECT_ROOT / "runs" / "b-model"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
HARD_MAX_ROUNDS = 30
HARD_MAX_OUTPUT_TOKENS = 8192
HARD_MAX_INPUT_TOKENS = 65_536


def _response(message: dict[str, Any], *, usage: dict[str, int] | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {
        "id": "synthetic-response-id",
        "model": CANDIDATE_PROFILE["model"],
        "choices": [{"index": 0, "message": copy.deepcopy(message), "finish_reason": "stop" if "tool_calls" not in message else "tool_calls"}],
    }
    if usage is not None:
        response["usage"] = copy.deepcopy(usage)
    return response


class SyntheticScenarioTransport:
    """Small fixed fixture transport; it cannot perform network I/O."""

    def __init__(self, scenario: str):
        self.scenario = scenario
        self.calls = 0

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        del request
        self.calls += 1
        if self.scenario == "post-tool-rejection" and self.calls == 2:
            raise PermissionError("synthetic transport rejection")
        if self.scenario == "post-tool-timeout" and self.calls == 2:
            raise TimeoutError("synthetic transport timeout")
        if self.scenario == "missing-usage" and self.calls == 1:
            return _response(
                make_assistant_message(
                    content="Synthetic first step.", reasoning_content="synthetic reasoning 1",
                    call_id="synthetic-call-1", name="synthetic_lookup", arguments={"key": "sample"},
                ),
            )
        if self.scenario == "invalid-call" and self.calls == 1:
            message = make_assistant_message(
                content="Synthetic invalid call.", reasoning_content="synthetic reasoning 1",
                call_id="synthetic-call-1", name="unknown_synthetic_tool", arguments={},
            )
            return _response(message, usage={"prompt_tokens": 12, "completion_tokens": 5})
        if self.calls == 1:
            return _response(
                make_assistant_message(
                    content="Synthetic first step.", reasoning_content="opaque synthetic reasoning 1",
                    call_id="synthetic-call-1", name="synthetic_lookup", arguments={"key": "sample"},
                ),
                usage={"prompt_tokens": 12, "completion_tokens": 5},
            )
        if self.calls == 2:
            return _response(
                make_assistant_message(
                    content="Synthetic second step.", reasoning_content="opaque synthetic reasoning 2",
                    call_id="synthetic-call-2", name="synthetic_format", arguments={"text": "synthetic-value"},
                ),
                usage={"prompt_tokens": 20, "completion_tokens": 6},
            )
        return _response(
            {
                "role": "assistant",
                "content": "Offline synthetic completion: synthetic-formatted:synthetic-value",
                "reasoning_content": "opaque synthetic final reasoning",
            },
            usage={"prompt_tokens": 28, "completion_tokens": 8},
        )


def _safe_json_write(path: Path, evidence: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _budget_eval(profile: BudgetProfile, rounds_used: int, cumulative_cost: float | None):
    from scripts.experiments.run_baseline import evaluate_budget

    return evaluate_budget(
        profile.cap_cny,
        profile.max_rounds,
        profile.max_output_tokens,
        rounds_used=rounds_used,
        cumulative_cost_cny=cumulative_cost,
        input_price_usd_per_million=profile.input_price_usd_per_million,
        output_price_usd_per_million=profile.output_price_usd_per_million,
        max_input_tokens_per_request=profile.max_input_tokens,
        usd_to_cny=profile.usd_to_cny,
        pricing_version=profile.pricing_version,
        fx_rate_source=profile.fx_rate_source,
    )


def _accounting_record(profile: BudgetProfile) -> dict[str, Any]:
    return {
        "provenance": "synthetic_fixture_only",
        "synthetic_usage": None,
        "synthetic_cost_cny": None,
        "known_prefix_usage": {"input_tokens": 0, "output_tokens": 0},
        "known_prefix_cost_cny": 0.0,
        "usage_complete": True,
        "status": "not_yet_measured",
        "synthetic_budget_cap_cny": profile.cap_cny,
        "synthetic_input_price_usd_per_million": profile.input_price_usd_per_million,
        "synthetic_output_price_usd_per_million": profile.output_price_usd_per_million,
        "synthetic_usd_to_cny": profile.usd_to_cny,
        "pricing_version": profile.pricing_version,
        "pricing_source": "synthetic_fixture_profile",
        "fx_rate_source": profile.fx_rate_source,
    }


def _record_usage(
    evidence: dict[str, Any], response: Any, profile: BudgetProfile
) -> tuple[int, int] | None:
    accounting = evidence["accounting"]
    usage = parse_usage(response)
    if usage is None:
        accounting.update(
            synthetic_usage=None,
            synthetic_cost_cny=None,
            usage_complete=False,
            status="unknown_usage",
        )
        return None

    input_tokens, output_tokens = usage
    prefix = accounting["known_prefix_usage"]
    prefix["input_tokens"] += input_tokens
    prefix["output_tokens"] += output_tokens
    cost = (
        (
            input_tokens * profile.input_price_usd_per_million
            + output_tokens * profile.output_price_usd_per_million
        )
        / 1_000_000
    ) * profile.usd_to_cny
    accounting["known_prefix_cost_cny"] = round(
        accounting["known_prefix_cost_cny"] + cost, 12
    )
    if accounting["usage_complete"]:
        accounting["synthetic_usage"] = dict(prefix)
        accounting["synthetic_cost_cny"] = accounting["known_prefix_cost_cny"]
        accounting["status"] = "known_for_returned_responses"
    return input_tokens, output_tokens


def run_probe(
    *,
    run_dir: Path,
    transport,
    scenario: str,
    mode: str = "offline",
    max_rounds: int = HARD_MAX_ROUNDS,
    max_tokens: int = HARD_MAX_OUTPUT_TOKENS,
    max_input_tokens: int = HARD_MAX_INPUT_TOKENS,
) -> dict[str, Any]:
    """Execute only injected synthetic transport, saving evidence incrementally."""

    profile = BudgetProfile(
        max_rounds=max_rounds,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_tokens,
    )
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "provenance": "offline_synthetic",
        "run_id": run_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "scenario": scenario,
        "candidate": {**copy.deepcopy(CANDIDATE_PROFILE), "max_tokens": max_tokens},
        "limits": {
            "max_rounds": max_rounds,
            "max_input_tokens": max_input_tokens,
            "max_output_tokens": max_tokens,
            "input_bound_method": "serialized_request_utf8_byte_count",
            "input_bound_note": "Conservative local bound; tokenizer and provider framing are unverified.",
        },
        "accounting": _accounting_record(profile),
        "real_provider_usage": None,
        "real_provider_cost_cny": None,
        "official_reward": None,
        "provider_compatibility": "unverified",
        "reference_runner_integration": "unverified",
        "requests": [],
        "responses": [],
        "tool_executions": [],
        "tool_exchange_rounds": 0,
        "status": "running",
        "terminal_phase": None,
        "failure_code": None,
    }
    evidence_path = run_dir / "evidence.json"

    def save() -> None:
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat() if evidence["status"] != "running" else None
        _safe_json_write(evidence_path, evidence)

    if mode != "offline":
        evidence.update(status="refused_live_mode", terminal_phase="mode_guard", failure_code="live_mode_disabled")
        save()
        return evidence
    if type(max_rounds) is not int or not (1 <= max_rounds <= HARD_MAX_ROUNDS):
        evidence.update(status="stopped_invalid_limits", terminal_phase="configuration", failure_code="invalid_round_limit")
        save()
        return evidence
    if type(max_tokens) is not int or not (1 <= max_tokens <= HARD_MAX_OUTPUT_TOKENS):
        evidence.update(status="stopped_invalid_limits", terminal_phase="configuration", failure_code="invalid_output_limit")
        save()
        return evidence
    if type(max_input_tokens) is not int or not (1 <= max_input_tokens <= HARD_MAX_INPUT_TOKENS):
        evidence.update(status="stopped_invalid_limits", terminal_phase="configuration", failure_code="invalid_input_limit")
        save()
        return evidence

    messages: list[dict[str, Any]] = [{"role": "user", "content": "Perform a synthetic two-step tool exchange."}]
    seen_call_ids: set[str] = set()

    for request_index in range(max_rounds):
        budget_status, _budget_reason = _budget_eval(
            profile, request_index, evidence["accounting"]["known_prefix_cost_cny"]
        )
        evidence["accounting"]["last_budget_status"] = budget_status
        if budget_status != "within_budget":
            evidence.update(status=budget_status, terminal_phase="budget_before_request", failure_code=budget_status)
            save()
            return evidence

        request = build_request(messages, max_tokens=max_tokens)
        input_bound = estimate_input_token_upper_bound(request)
        evidence["requests"].append({"request": copy.deepcopy(request), "input_token_upper_bound": input_bound})
        if input_bound > max_input_tokens:
            evidence.update(status="stopped_input_limit", terminal_phase="budget_before_transport", failure_code="input_bound_exceeded")
            save()
            return evidence
        save()

        try:
            response = transport(request)
        except TimeoutError:
            evidence["responses"].append({"request_index": request_index, "transport_status": "timeout", "exception_class": "TimeoutError"})
            evidence.update(status="transport_timeout", terminal_phase="transport_after_tool" if evidence["tool_executions"] else "transport", failure_code="transport_timeout")
            save()
            return evidence
        except Exception as exc:
            class_name = type(exc).__name__
            safe_class = class_name if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", class_name) else "OtherException"
            evidence["responses"].append({"request_index": request_index, "transport_status": "rejected", "exception_class": safe_class})
            evidence.update(status="transport_rejected", terminal_phase="transport_after_tool" if evidence["tool_executions"] else "transport", failure_code="transport_rejected")
            save()
            return evidence

        evidence["responses"].append({"request_index": request_index, "transport_status": "returned", "response": copy.deepcopy(response)})
        usage = _record_usage(evidence, response, profile)
        try:
            message = extract_assistant_message(response)
        except ProbeFailure as failure:
            evidence.update(status="rejected_response", terminal_phase=failure.phase, failure_code=failure.code)
            save()
            return evidence

        raw_calls = message.get("tool_calls")
        if raw_calls is None or raw_calls == []:
            has_tool_calls = False
        elif isinstance(raw_calls, list):
            has_tool_calls = True
        else:
            evidence.update(status="rejected_response", terminal_phase="response_validation", failure_code="invalid_tool_batch")
            save()
            return evidence
        choice = response["choices"][0]
        finish_reason = choice.get("finish_reason")
        if has_tool_calls != (finish_reason == "tool_calls"):
            evidence.update(status="rejected_response", terminal_phase="response_validation", failure_code="finish_reason_tool_call_mismatch")
            save()
            return evidence

        if usage is None:
            evidence.update(status="unverified_unknown_usage", terminal_phase="response_accounting", failure_code="missing_synthetic_usage")
            save()
            return evidence
        input_tokens, output_tokens = usage
        if input_tokens > input_bound or output_tokens > max_tokens:
            evidence.update(status="stopped_response_usage_limit", terminal_phase="response_accounting", failure_code="synthetic_usage_exceeded_request_bound")
            save()
            return evidence
        if evidence["accounting"]["known_prefix_cost_cny"] > profile.cap_cny:
            evidence.update(status="stopped_budget_exhausted", terminal_phase="response_accounting", failure_code="synthetic_cost_exceeded_cap")
            save()
            return evidence

        if has_tool_calls:
            try:
                validated_calls = validate_tool_batch(message, seen_call_ids)
            except ProbeFailure as failure:
                evidence.update(status="rejected_response", terminal_phase=failure.phase, failure_code=failure.code)
                save()
                return evidence
            # Commit the exact assistant message to history only after the full
            # batch has passed validation. Tool results pair with original IDs.
            messages.append(copy.deepcopy(message))
            for call_id, name, arguments in validated_calls:
                result = execute_synthetic_tool(name, arguments)
                seen_call_ids.add(call_id)
                tool_record = {"name": name, "tool_call_id": call_id, "arguments": copy.deepcopy(arguments), "result": result, "provenance": "synthetic"}
                evidence["tool_executions"].append(tool_record)
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            evidence["tool_exchange_rounds"] += 1
            save()
            continue

        # Empty/null tool_calls are normal SDK final-message shapes.
        if "reasoning_content" not in message or not isinstance(message["reasoning_content"], str):
            evidence.update(status="rejected_response", terminal_phase="response_validation", failure_code="missing_reasoning_content")
            save()
            return evidence
        messages.append(copy.deepcopy(message))
        evidence["final_message"] = copy.deepcopy(message)
        evidence["history"] = copy.deepcopy(messages)
        if finish_reason != "stop":
            evidence.update(status="incomplete_response", terminal_phase="final_response", failure_code="final_finish_reason_not_stop")
        elif not isinstance(message["content"], str) or not message["content"].strip():
            evidence.update(status="incomplete_response", terminal_phase="final_response", failure_code="final_content_unavailable")
        elif evidence["tool_exchange_rounds"] < 2:
            evidence.update(status="incomplete_response", terminal_phase="final_response", failure_code="insufficient_tool_exchange_rounds")
        else:
            evidence.update(status="offline_synthetic_completion", terminal_phase="complete", failure_code=None)
        save()
        return evidence

    evidence.update(status="stopped_round_limit", terminal_phase="request_limit", failure_code="round_limit_exhausted")
    save()
    return evidence


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--scenario", choices=("success", "post-tool-rejection", "post-tool-timeout", "missing-usage", "invalid-call"), default="success")
    parser.add_argument("--run-id", default=None, help="Safe, unique local evidence directory name")
    parser.add_argument("--max-rounds", type=int, default=HARD_MAX_ROUNDS)
    parser.add_argument("--max-tokens", type=int, default=HARD_MAX_OUTPUT_TOKENS)
    parser.add_argument("--max-input-tokens", type=int, default=HARD_MAX_INPUT_TOKENS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = args.run_id or f"offline-{uuid.uuid4().hex[:12]}"
    if not RUN_ID_RE.fullmatch(run_id):
        print("ERROR: run id must contain only letters, digits, '_' or '-' and be at most 64 characters")
        return 2
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_ROOT / run_id
    try:
        run_dir.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        print("ERROR: evidence run id already exists; refusing to overwrite")
        return 2
    except OSError:
        print("ERROR: could not create evidence directory")
        return 2

    transport = SyntheticScenarioTransport(args.scenario)
    evidence = run_probe(
        run_dir=run_dir,
        transport=transport,
        scenario=args.scenario,
        mode=args.mode,
        max_rounds=args.max_rounds,
        max_tokens=args.max_tokens,
        max_input_tokens=args.max_input_tokens,
    )
    print(f"status={evidence['status']} evidence={run_dir / 'evidence.json'}")
    return 0 if evidence["status"] == "offline_synthetic_completion" else 1


if __name__ == "__main__":
    sys.exit(main())
