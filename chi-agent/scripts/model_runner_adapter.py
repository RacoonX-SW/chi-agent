#!/usr/bin/env python3
"""Offline-only integration of the pinned OpenAI Agents SDK with CHI runner.

The executable mode always uses httpx.MockTransport and synthetic tools.  The
candidate DeepSeek route is configuration metadata; this module never reads a
provider credential or opens a network transport.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
import importlib.metadata
import io
import json
import os
import re
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from b_model_adapter import CANDIDATE_PROFILE, ProbeFailure

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "chi-bench"
VENDOR_SRC = VENDOR / "src"
UPSTREAM_SHA = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
EXPECTED_SOURCE_BLOBS = {
    "src/chi_bench/experiment/agents/openai_agents_runner.py": "87657b79b535f340714542a745c1354b4e54dad0",
    "src/chi_bench/experiment/agents/openai_agents_local_tools.py": "2783c35f7732f5eff73a022b16d2885e17c4dbde",
    "src/chi_bench/experiment/agents/nemotron_tool_protocol.py": "d6fcab0173ab6c4df9f4a00e0c00ce4982c8ad15",
}
RUNS_ROOT = Path(os.environ.get("CHI_MODEL_RUNS_DIR", str(ROOT / "runs" / "model-runner")))
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SYNTHETIC_TOOLS = {
    "synthetic_lookup": {"required": {"key": str}},
    "synthetic_format": {"required": {"text": str}},
}
MAX_ROUNDS = 3
MAX_INPUT_TOKENS = 65_536  # Offline UTF-8 byte estimate only.
MAX_OUTPUT_TOKENS = 128
CAP_CNY = 5.0  # Synthetic fixture cap; not the shared runtime budget.
SYNTHETIC_PRIOR_SPEND_CNY = 0.0
SYNTHETIC_INPUT_PRICE = 1.0
SYNTHETIC_OUTPUT_PRICE = 1.0
SYNTHETIC_USD_TO_CNY = 7.2


class IntegrationFailure(Exception):
    """A safe, fixed-classification offline failure."""

    def __init__(self, code: str, phase: str):
        super().__init__(code)
        self.code = code
        self.phase = phase


@dataclass
class Ledger:
    scenario: str
    initial_cost_cny: float = SYNTHETIC_PRIOR_SPEND_CNY
    transport_calls: int = 0
    rounds: int = 0
    usage_complete: bool = True
    known_input_tokens: int = 0
    known_output_tokens: int = 0
    known_cost_cny: float = 0.0
    aggregate_input_tokens: int | None = 0
    aggregate_output_tokens: int | None = 0
    aggregate_cost_cny: float | None = 0.0
    effects: list[dict[str, Any]] | None = None
    requests: list[dict[str, Any]] | None = None
    tool_exchanges: list[dict[str, Any]] | None = None
    pending_calls: list[dict[str, Any]] | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        self.effects = []
        self.requests = []
        self.tool_exchanges = []
        self.pending_calls = []


def _upstream_identity() -> dict[str, Any]:
    import subprocess

    try:
        head = subprocess.run(
            ["git", "-C", str(VENDOR), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(VENDOR), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        blobs = {}
        for relative in EXPECTED_SOURCE_BLOBS:
            path = VENDOR / relative
            blobs[relative] = hashlib.sha1(
                b"blob " + str(path.stat().st_size).encode() + b"\0" + path.read_bytes()
            ).hexdigest()
    except Exception:
        raise IntegrationFailure("upstream_identity_unavailable", "preflight") from None
    if head != UPSTREAM_SHA or status.strip() or blobs != EXPECTED_SOURCE_BLOBS:
        raise IntegrationFailure("upstream_identity_mismatch", "preflight")
    return {"commit": head, "clean": True, "source_blobs": blobs}


def _sdk_identity() -> dict[str, str]:
    versions = {
        "openai-agents": importlib.metadata.version("openai-agents"),
        "openai": importlib.metadata.version("openai"),
        "httpx": importlib.metadata.version("httpx"),
    }
    if versions["openai-agents"] != "0.13.6" or versions["openai"] != "2.36.0":
        raise IntegrationFailure("sdk_version_mismatch", "preflight")
    return versions


def _message(call_id: str, name: str, arguments: dict[str, Any], reasoning: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": f"Synthetic step {call_id}",
        "reasoning_content": reasoning,
        "tool_calls": [{
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, separators=(",", ":"))},
        }],
    }


def _response(number: int, *, message: dict[str, Any], usage: dict[str, int] | None = None,
              finish_reason: str | None = None, model: str | None = None) -> dict[str, Any]:
    if finish_reason is None:
        finish_reason = "tool_calls" if message.get("tool_calls") else "stop"
    value: dict[str, Any] = {
        "id": f"chatcmpl-synthetic-{number}",
        "object": "chat.completion",
        "created": 1_798_000_000 + number,
        "model": model or CANDIDATE_PROFILE["model"],
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    }
    if usage is not None:
        value["usage"] = usage
    return value


def _scenario_response(scenario: str, number: int) -> dict[str, Any]:
    if scenario == "missing-usage" and number == 1:
        usage = None
    elif scenario == "invalid-final-usage" and number == 3:
        usage = {"prompt_tokens": 0, "completion_tokens": -1, "total_tokens": 0}
    elif scenario == "over-output" and number == 1:
        usage = {"prompt_tokens": 12, "completion_tokens": MAX_OUTPUT_TOKENS + 1,
                 "total_tokens": MAX_OUTPUT_TOKENS + 13}
    elif scenario == "over-cap" and number == 1:
        usage = {"prompt_tokens": 1_000_000, "completion_tokens": MAX_OUTPUT_TOKENS,
                 "total_tokens": 1_000_128}
    elif scenario == "over-input" and number == 1:
        usage = {"prompt_tokens": MAX_INPUT_TOKENS + 1, "completion_tokens": 5,
                 "total_tokens": MAX_INPUT_TOKENS + 6}
    else:
        usage = {"prompt_tokens": 12 + number * 8, "completion_tokens": 5 + number,
                 "total_tokens": 17 + number * 9}
    if number == 1:
        if scenario == "mismatched-response-model":
            message = _message("call-wrong-model", "synthetic_lookup", {"key": "sample"}, "opaque-reason-1")
            return _response(1, message=message, usage=usage, model="another-model")
        elif scenario in {"empty-history", "none-history"}:
            message = _message("call-empty", "synthetic_lookup", {"key": "sample"}, "" if scenario == "empty-history" else "opaque-reason-1")
            message["content"] = "" if scenario == "empty-history" else None
        elif scenario == "batch-valid-then-invalid":
            message = _message("call-batch-ok", "synthetic_lookup", {"key": "sample"}, "opaque-reason-1")
            message["tool_calls"].append({
                "id": "call-batch-bad", "type": "function",
                "function": {"name": "missing_tool", "arguments": "{}"},
            })
        elif scenario == "invalid-finish":
            message = _message("call-invalid-finish", "synthetic_lookup", {"key": "sample"}, "opaque-reason-1")
        else:
            message = _message("call-1", "synthetic_lookup", {"key": "sample"}, "opaque-reason-1")
        return _response(1, message=message, usage=usage,
                         finish_reason="stop" if scenario == "invalid-finish" else None)
    if number == 2:
        call_id = "call-1" if scenario == "duplicate-call-id" else "call-2"
        return _response(2, message=_message(call_id, "synthetic_format", {"text": "synthetic-value"}, "opaque-reason-2"), usage=usage)
    return _response(3, message={
        "role": "assistant",
        "content": "Offline synthetic completion: synthetic-formatted:synthetic-value",
        "reasoning_content": "opaque-reason-final",
    }, usage=usage)


def _usage(response: dict[str, Any]) -> tuple[int, int] | None:
    raw = response.get("usage")
    if not isinstance(raw, dict):
        return None
    incoming, outgoing = raw.get("prompt_tokens"), raw.get("completion_tokens")
    total = raw.get("total_tokens")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (incoming, outgoing, total)):
        return None
    if total < incoming + outgoing:
        return None
    return incoming, outgoing


def _account_usage(ledger: Ledger, usage: tuple[int, int] | None) -> None:
    if usage is None:
        ledger.usage_complete = False
        ledger.aggregate_input_tokens = None
        ledger.aggregate_output_tokens = None
        ledger.aggregate_cost_cny = None
        raise IntegrationFailure("usage_unknown", "response_accounting")
    incoming, outgoing = usage
    ledger.known_input_tokens += incoming
    ledger.known_output_tokens += outgoing
    cost = ((incoming * SYNTHETIC_INPUT_PRICE + outgoing * SYNTHETIC_OUTPUT_PRICE) / 1_000_000) * SYNTHETIC_USD_TO_CNY
    ledger.known_cost_cny = round(ledger.known_cost_cny + cost, 12)
    if ledger.usage_complete:
        ledger.aggregate_input_tokens = ledger.known_input_tokens
        ledger.aggregate_output_tokens = ledger.known_output_tokens
        ledger.aggregate_cost_cny = ledger.known_cost_cny


def _mark_unknown_usage(ledger: Ledger) -> None:
    ledger.usage_complete = False
    ledger.aggregate_input_tokens = None
    ledger.aggregate_output_tokens = None
    ledger.aggregate_cost_cny = None


def _budget_check(ledger: Ledger, request_body: dict[str, Any]) -> int:
    from run_baseline import evaluate_budget

    estimate_bytes = len(json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if estimate_bytes > MAX_INPUT_TOKENS:
        raise IntegrationFailure("input_estimate_limit", "request_guard")
    if ledger.rounds >= MAX_ROUNDS:
        raise IntegrationFailure("round_limit", "request_guard")
    max_tokens = request_body.get("max_tokens")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        raise IntegrationFailure("output_limit", "request_guard")
    status, _reason = evaluate_budget(
        CAP_CNY, MAX_ROUNDS, MAX_OUTPUT_TOKENS,
        rounds_used=ledger.rounds,
        cumulative_cost_cny=ledger.initial_cost_cny + ledger.known_cost_cny,
        input_price_usd_per_million=SYNTHETIC_INPUT_PRICE,
        output_price_usd_per_million=SYNTHETIC_OUTPUT_PRICE,
        max_input_tokens_per_request=MAX_INPUT_TOKENS,
        usd_to_cny=SYNTHETIC_USD_TO_CNY,
        pricing_version="synthetic-model-runner-profile-v1",
        fx_rate_source="synthetic-profile-v1",
    )
    if status != "within_budget":
        raise IntegrationFailure("budget_exhausted", "request_guard")
    if request_body.get("model") != CANDIDATE_PROFILE["model"]:
        raise IntegrationFailure("request_model_mismatch", "request_guard")
    return estimate_bytes


def _check_returned_usage(usage: tuple[int, int], ledger: Ledger) -> None:
    incoming, outgoing = usage
    if ledger.initial_cost_cny + ledger.known_cost_cny > CAP_CNY:
        raise IntegrationFailure("returned_usage_over_budget", "response_accounting")
    if outgoing > MAX_OUTPUT_TOKENS:
        raise IntegrationFailure("returned_usage_over_output_limit", "response_accounting")
    if incoming > MAX_INPUT_TOKENS:
        raise IntegrationFailure("returned_usage_over_input_limit", "response_accounting")


def _validate_response(response: dict[str, Any], ledger: Ledger) -> None:
    model = response.get("model")
    if model != CANDIDATE_PROFILE["model"]:
        raise IntegrationFailure("response_model_mismatch", "response_validation")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise IntegrationFailure("response_shape_invalid", "response_validation")
    choice = choices[0]
    message = choice.get("message")
    finish = choice.get("finish_reason")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise IntegrationFailure("response_shape_invalid", "response_validation")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise IntegrationFailure("response_shape_invalid", "response_validation")
    calls = message.get("tool_calls")
    if finish == "tool_calls":
        if not isinstance(calls, list) or not calls:
            raise IntegrationFailure("finish_reason_invalid", "response_validation")
        seen = {effect["call_id"] for effect in ledger.effects or []}
        parsed: list[tuple[str, str, dict[str, Any]]] = []
        batch: set[str] = set()
        for call in calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                raise IntegrationFailure("tool_batch_invalid", "response_validation")
            call_id = call.get("id")
            function = call.get("function")
            if not isinstance(call_id, str) or not call_id or call_id in seen or call_id in batch:
                raise IntegrationFailure("tool_call_id_invalid", "response_validation")
            if not isinstance(function, dict) or function.get("name") not in SYNTHETIC_TOOLS:
                raise IntegrationFailure("tool_unknown", "response_validation")
            name = function["name"]
            try:
                arguments = json.loads(function.get("arguments"))
            except (TypeError, ValueError):
                raise IntegrationFailure("tool_arguments_invalid", "response_validation") from None
            required = SYNTHETIC_TOOLS[name]["required"]
            if not isinstance(arguments, dict) or set(arguments) != set(required) or any(type(arguments[k]) is not t for k, t in required.items()):
                raise IntegrationFailure("tool_arguments_invalid", "response_validation")
            parsed.append((call_id, name, arguments))
            batch.add(call_id)
        if not isinstance(message.get("reasoning_content"), str):
            raise IntegrationFailure("reasoning_missing", "response_validation")
    elif finish == "stop":
        if calls:
            raise IntegrationFailure("finish_reason_invalid", "response_validation")
    else:
        raise IntegrationFailure("finish_reason_invalid", "response_validation")
    usage = _usage(response)
    if usage is None:
        raise IntegrationFailure("usage_unknown", "response_accounting")
    if not ledger.usage_complete:
        raise IntegrationFailure("usage_unknown", "response_accounting")
    if finish == "tool_calls":
        ledger.pending_calls.extend({"call_id": call_id, "tool": name, "arguments": arguments}
                                    for call_id, name, arguments in parsed)


class MockWire:
    """Captures actual SDK bytes and serves only fixed synthetic responses."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.seen_ids: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        ledger = self.ledger
        failure_scenarios = {
            "http-429": (1, 429, "http_rate_limited"),
            "http-503": (1, 503, "http_unavailable"),
            "post-tool-429": (2, 429, "http_rate_limited"),
            "post-tool-503": (2, 503, "http_unavailable"),
        }
        failure = failure_scenarios.get(ledger.scenario)
        if failure and ledger.rounds == failure[0]:
            _, status, code = failure
            ledger.error_code = code
            _mark_unknown_usage(ledger)
            return httpx.Response(status,
                                  headers={"Retry-After": "0"}, json={"error": {"message": "synthetic"}})
        if ledger.scenario in {"connect-error", "post-tool-connect-error"} and ledger.rounds == (2 if ledger.scenario.startswith("post-tool-") else 1):
            ledger.error_code = "transport_connect_error"
            _mark_unknown_usage(ledger)
            raise httpx.ConnectError("synthetic")
        if ledger.scenario in {"timeout", "post-tool-timeout"} and ledger.rounds == (2 if ledger.scenario.startswith("post-tool-") else 1):
            ledger.error_code = "transport_timeout"
            _mark_unknown_usage(ledger)
            raise httpx.ReadTimeout("synthetic")

        response = _scenario_response(ledger.scenario, ledger.rounds)
        # Count returned usage before protocol validation; the SDK does not see
        # malformed/incomplete/over-limit responses and cannot dispatch tools.
        try:
            usage = _usage(response)
            if usage is None:
                _account_usage(ledger, None)
            _account_usage(ledger, usage)
            _check_returned_usage(usage, ledger)
            _validate_response(response, ledger)
        except IntegrationFailure as exc:
            ledger.error_code = exc.code
            raise
        return httpx.Response(200, json=response, request=request)

    def _observe_tool_history(self, body: dict[str, Any]) -> None:
        messages = body.get("messages", [])
        calls: dict[str, tuple[str, str]] = {}
        for message in messages:
            if message.get("role") != "assistant":
                continue
            for call in message.get("tool_calls", []):
                function = call.get("function", {})
                calls[call.get("id")] = (function.get("name"), function.get("arguments"))
        for message in messages:
            if message.get("role") != "tool":
                continue
            call_id = message.get("tool_call_id")
            name, arguments = calls.get(call_id, (None, None))
            content = message.get("content")
            self.ledger.tool_exchanges.append({
                "call_id": call_id, "tool": name, "arguments": arguments,
                "result": content, "provenance": "observed_in_sdk_serialized_history",
            })
            for effect in self.ledger.effects or []:
                if effect.get("call_id") is None and effect.get("result") == content and effect.get("tool") == name:
                    effect["call_id"] = call_id
                    break


class BudgetedMockTransport(httpx.AsyncBaseTransport):
    """Enforce request limits before invoking the underlying mock transport."""

    def __init__(self, ledger: Ledger, wire: MockWire):
        self.ledger = ledger
        self._inner = httpx.MockTransport(wire)
        self._wire = wire

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ledger = self.ledger
        try:
            raw_body = request.content
            body = json.loads(raw_body)
            estimate = _budget_check(ledger, body)
        except IntegrationFailure as exc:
            ledger.error_code = exc.code
            raise
        except Exception:
            ledger.error_code = "request_serialization_invalid"
            raise IntegrationFailure(ledger.error_code, "request_guard") from None

        # Passing this point is the only path that counts as an HTTP send.
        ledger.rounds += 1
        ledger.requests.append({
            "url": str(request.url), "method": request.method,
            "body": body, "body_sha256": hashlib.sha256(raw_body).hexdigest(),
            "utf8_bytes": len(raw_body), "offline_byte_estimate": estimate,
            "provenance": "synthetic_mocktransport",
        })
        self._wire._observe_tool_history(body)
        ledger.transport_calls += 1
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def _patch_empty_history_compatibility(converter: Any, endpoint: str, model: str):
    """Patch only SDK conversion points that drop legal empty strings.

    SDK 0.13.6 drops both ``content=''`` and ``reasoning_content=''`` when it
    converts Chat Completions into Responses items. Its actual conversion and
    serialization remain authoritative; these wrappers restore the two exact
    empty values and carry endpoint provenance needed by the replay callback.
    """
    from openai.types.responses import ResponseOutputMessage, ResponseOutputText, ResponseReasoningItem
    from openai.types.responses.response_reasoning_item import Summary

    old_message = converter.__dict__["message_to_output_items"]
    old_items = converter.__dict__["items_to_messages"]

    def patched_message_to_output_items(cls, message, provider_data=None):
        metadata = dict(provider_data or {})
        metadata["origin_endpoint"] = endpoint
        items = old_message.__func__(cls, message, provider_data=metadata)
        if getattr(message, "reasoning_content", None) == "":
            reasoning = ResponseReasoningItem(
                id="offline-empty-reasoning",
                summary=[Summary(text="", type="summary_text")],
                type="reasoning",
                provider_data={"model": model, "origin_endpoint": endpoint},
            )
            items.insert(0, reasoning)
        if getattr(message, "content", None) == "":
            empty_message = ResponseOutputMessage(
                id="offline-empty-content",
                content=[ResponseOutputText(text="", type="output_text", annotations=[], logprobs=[])],
                role="assistant", type="message", status="completed",
                provider_data={"model": model, "origin_endpoint": endpoint},
            )
            call_index = next((i for i, item in enumerate(items) if getattr(item, "type", None) == "function_call"), len(items))
            items.insert(call_index, empty_message)
        return items

    def patched_items_to_messages(cls, items, *args, **kwargs):
        result = old_items.__func__(cls, items, *args, **kwargs)
        target_model = kwargs.get("model", args[0] if args else None)
        target_endpoint = kwargs.get("base_url", None)
        replay = kwargs.get("should_replay_reasoning_content")
        if target_model != model or (target_endpoint or "").rstrip("/") != endpoint + "/v1" or replay is None:
            return result
        empty_pending = False
        for item in items if not isinstance(items, str) else []:
            is_reasoning = cls.maybe_reasoning_message(item)
            if is_reasoning:
                data = is_reasoning.get("provider_data", {})
                summaries = is_reasoning.get("summary", [])
                empty_pending = (
                    data.get("model") == model
                    and data.get("origin_endpoint") == endpoint
                    and any(isinstance(s, dict) and s.get("text") == "" for s in summaries)
                )
                continue
            if empty_pending:
                function_call = cls.maybe_function_tool_call(item)
                if function_call:
                    call_id = function_call.get("call_id")
                    for message in result:
                        if message.get("role") == "assistant" and any(c.get("id") == call_id for c in message.get("tool_calls", [])):
                            message["reasoning_content"] = ""
                            break
                if cls.maybe_function_tool_call_output(item):
                    empty_pending = False
        return result

    converter.message_to_output_items = classmethod(patched_message_to_output_items)
    converter.items_to_messages = classmethod(patched_items_to_messages)
    return old_message, old_items


def _same_route_reasoning(context: Any) -> bool:
    provider_data = getattr(getattr(context, "reasoning", None), "provider_data", {})
    return (
        getattr(context, "model", None) == CANDIDATE_PROFILE["model"]
        and (getattr(context, "base_url", "") or "").rstrip("/")
        == CANDIDATE_PROFILE["endpoint"] + "/v1"
        and getattr(getattr(context, "reasoning", None), "origin_model", None)
        == CANDIDATE_PROFILE["model"]
        and provider_data.get("origin_endpoint") == CANDIDATE_PROFILE["endpoint"]
    )


def _tool_specs(ledger: Ledger):
    from agents import function_tool

    @function_tool
    async def synthetic_lookup(key: str) -> str:
        """Read one value from a fixed synthetic fixture."""
        if key != "sample":
            return "synthetic-key-not-found"
        pending = next((call for call in ledger.pending_calls or []
                        if call["tool"] == "synthetic_lookup" and call["arguments"] == {"key": key}), None)
        if pending is None:
            raise IntegrationFailure("tool_dispatch_unvalidated", "tool_execution")
        ledger.pending_calls.remove(pending)
        ledger.effects.append({"tool": "synthetic_lookup", "call_id": pending["call_id"], "result": "synthetic-value"})
        return "synthetic-value"

    @function_tool
    async def synthetic_format(text: str) -> str:
        """Format one string using a fixed synthetic transformation."""
        result = f"synthetic-formatted:{text}"
        pending = next((call for call in ledger.pending_calls or []
                        if call["tool"] == "synthetic_format" and call["arguments"] == {"text": text}), None)
        if pending is None:
            raise IntegrationFailure("tool_dispatch_unvalidated", "tool_execution")
        ledger.pending_calls.remove(pending)
        ledger.effects.append({"tool": "synthetic_format", "call_id": pending["call_id"], "result": result})
        return result

    return [synthetic_lookup, synthetic_format]


async def _run_offline(scenario: str) -> tuple[Ledger, str | None]:
    identity = _upstream_identity()
    sdk = _sdk_identity()
    if str(VENDOR_SRC) not in sys.path:
        sys.path.insert(0, str(VENDOR_SRC))
    from agents import ModelRetrySettings, ModelSettings
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from agents.models.openai_chatcompletions import Converter
    from openai import AsyncOpenAI
    import agents.mcp as agents_mcp
    from agents.tracing import get_trace_provider
    from chi_bench.experiment.agents import openai_agents_runner as official_runner
    import chi_bench.experiment.agents.openai_agents_local_tools as local_tools_module
    from agents.mcp.util import MCPUtil

    ledger = Ledger(scenario)
    wire = MockWire(ledger)
    old_env = {key: os.environ.get(key) for key in (
        "OPENAI_AGENTS_MODEL", "OPENAI_AGENTS_API_MODE", "OPENAI_AGENTS_MAX_TURNS",
        "OPENAI_AGENTS_REASONING_EFFORT", "OPENAI_AGENTS_MAX_RETRIES", "OPENAI_BASE_URL",
    )}
    old_context = official_runner._agent_model_context
    old_settings = official_runner._build_model_settings
    old_tools = local_tools_module.build_local_tools
    old_mcp_class = agents_mcp.MCPServerStreamableHttp
    old_invoke = MCPUtil.__dict__["invoke_mcp_tool"]
    old_to_tool = MCPUtil.__dict__["to_function_tool"]
    old_sanitizer_flag = getattr(MCPUtil, "_chi_bench_name_sanitizer_installed", False)
    trace_provider = get_trace_provider()
    old_tracing_state = (trace_provider._disabled, trace_provider._manual_disabled, trace_provider._env_disabled)
    old_converter = _patch_empty_history_compatibility(
        Converter, CANDIDATE_PROFILE["endpoint"], CANDIDATE_PROFILE["model"]
    )

    class SyntheticMCP:
        name = "chi_bench-synthetic"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return False
        async def list_tools(self, *_args, **_kwargs):
            return []

    client_transport = BudgetedMockTransport(ledger, wire)
    client_http = httpx.AsyncClient(transport=client_transport)
    openai_client = AsyncOpenAI(
        api_key="offline-synthetic-placeholder",
        base_url=CANDIDATE_PROFILE["endpoint"] + "/v1",
        http_client=client_http,
        max_retries=0,
    )
    sdk_model = OpenAIChatCompletionsModel(
        model=CANDIDATE_PROFILE["model"], openai_client=openai_client,
        should_replay_reasoning_content=_same_route_reasoning,
    )

    @asynccontextmanager
    async def model_context(_model: str, _api_mode: str):
        yield sdk_model

    def model_settings(_effort: str | None = None, *, separate_reasoning: bool = False):
        del separate_reasoning
        return ModelSettings(
            max_tokens=MAX_OUTPUT_TOKENS,
            reasoning={"effort": "high"},
            extra_body={"thinking": {"type": "enabled"}},
            retry=ModelRetrySettings(max_retries=0),
        )

    def safe_mcp_factory(*_args, **_kwargs):
        return SyntheticMCP()

    try:
        os.environ.update({
            "OPENAI_AGENTS_MODEL": CANDIDATE_PROFILE["model"],
            "OPENAI_AGENTS_API_MODE": "chat_completions",
            "OPENAI_AGENTS_MAX_TURNS": str(MAX_ROUNDS),
            "OPENAI_AGENTS_REASONING_EFFORT": "high",
            "OPENAI_AGENTS_MAX_RETRIES": "0",
        })
        os.environ.pop("OPENAI_BASE_URL", None)
        official_runner._agent_model_context = model_context
        official_runner._build_model_settings = model_settings
        agents_mcp.MCPServerStreamableHttp = safe_mcp_factory
        local_tools_module.build_local_tools = lambda _logs: _tool_specs(ledger)
        # run_agent globally patches SDK MCPUtil helpers. Restore exact class
        # descriptors and its sentinel even when the runner raises.
        result_text = None
        with tempfile.TemporaryDirectory(prefix="chi-model-runner-") as temp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                await official_runner.run_agent(
                    "Use the supplied synthetic tools to look up sample and format the result.",
                    "http://synthetic.invalid/mcp", logs_dir=Path(temp),
                )
            except SystemExit:
                ledger.error_code = ledger.error_code or "official_runner_failed"
            except IntegrationFailure as exc:
                ledger.error_code = ledger.error_code or exc.code
            except Exception:
                ledger.error_code = ledger.error_code or "official_runner_failed"
            if ledger.error_code is None:
                output_path = Path(temp) / "run_output.txt"
                if output_path.is_file():
                    result_text = output_path.read_text(encoding="utf-8")
        if ledger.error_code is None and ledger.rounds == 3:
            if result_text is None:
                ledger.error_code = "final_output_missing"
        if ledger.error_code is None and ledger.rounds != 3:
            ledger.error_code = "unexpected_round_count"
        return ledger, result_text
    finally:
        official_runner._agent_model_context = old_context
        official_runner._build_model_settings = old_settings
        agents_mcp.MCPServerStreamableHttp = old_mcp_class
        local_tools_module.build_local_tools = old_tools
        MCPUtil.invoke_mcp_tool = old_invoke
        MCPUtil.to_function_tool = old_to_tool
        Converter.message_to_output_items = old_converter[0]
        Converter.items_to_messages = old_converter[1]
        trace_provider._disabled, trace_provider._manual_disabled, trace_provider._env_disabled = old_tracing_state
        if old_sanitizer_flag:
            MCPUtil._chi_bench_name_sanitizer_installed = True
        else:
            with contextlib.suppress(AttributeError):
                delattr(MCPUtil, "_chi_bench_name_sanitizer_installed")
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        with contextlib.suppress(Exception):
            await openai_client.close()


def _evidence(run_id: str, ledger: Ledger, result: str | None, sdk_identity: dict[str, str], upstream: dict[str, Any]) -> dict[str, Any]:
    success = ledger.error_code is None and result is not None
    return {
        "schema": "model-runner-offline-evidence-v1",
        "provenance": "offline_synthetic_mocktransport_official_runner",
        "run_id": run_id,
        "scenario": ledger.scenario,
        "candidate": {
            "name": "deepseek-flash", "endpoint": "https://api.deepseek.com",
            "api": "chat_completions", "key_env": "OPENAI_API_KEY",
            "thinking": {"type": "enabled"}, "reasoning_effort": "high",
            "max_tokens": MAX_OUTPUT_TOKENS,
        },
        "sdk": sdk_identity,
        "upstream": upstream,
        "limits": {
            "max_rounds": MAX_ROUNDS, "max_input_bytes_as_token_estimate": MAX_INPUT_TOKENS,
            "max_output_tokens": MAX_OUTPUT_TOKENS, "synthetic_cap_cny": CAP_CNY,
            "retry_policy": {"http_client": 0, "agents_model": 0, "outer": 0, "synthetic_tool": 0},
            "tracing": "disabled_by_fixed_official_runner",
        },
        "requests": ledger.requests,
        "observed_tool_history": ledger.tool_exchanges,
        "transport_send_count": ledger.transport_calls,
        "rounds": ledger.rounds,
        "effects": ledger.effects,
        "accounting": {
            "provenance": "synthetic_fixture_only",
            "synthetic_prior_spend_cny": ledger.initial_cost_cny,
            "known_prefix_usage": {"input_tokens": ledger.known_input_tokens, "output_tokens": ledger.known_output_tokens},
            "known_prefix_cost_cny": ledger.known_cost_cny,
            "usage_complete": ledger.usage_complete,
            "aggregate_usage": ({"input_tokens": ledger.aggregate_input_tokens, "output_tokens": ledger.aggregate_output_tokens}
                                if ledger.aggregate_input_tokens is not None and ledger.aggregate_output_tokens is not None else None),
            "aggregate_cost_cny": ledger.aggregate_cost_cny,
            "real_usage": None, "real_cost_cny": None,
        },
        "outcome": {
            "status": "offline_synthetic_completion" if success else "incomplete",
            "safe_error_code": ledger.error_code,
            "task_outcome": "unknown", "official_reward": None,
            "final_response": result,
        },
    }


def _write_evidence(run_id: str, evidence: dict[str, Any]) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise IntegrationFailure("run_id_invalid", "preflight")
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    target = RUNS_ROOT / f"{run_id}.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def _plan() -> dict[str, Any]:
    return {
        "mode": "read_only_plan", "entry": "chi_bench.experiment.agents.openai_agents_runner.run_agent",
        "route": {"candidate": CANDIDATE_PROFILE["model"], "endpoint": CANDIDATE_PROFILE["endpoint"],
                  "api": CANDIDATE_PROFILE["api"], "key_env": "OPENAI_API_KEY"},
        "real_api_enabled": False, "official_grading": False,
        "limits": {"max_rounds": MAX_ROUNDS, "max_input_bytes_as_token_estimate": MAX_INPUT_TOKENS,
                   "max_output_tokens": MAX_OUTPUT_TOKENS, "retry": 0},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "offline", "live"))
    parser.add_argument("--run-id")
    parser.add_argument("--scenario", default="success", choices=(
        "success", "http-429", "http-503", "connect-error", "timeout", "missing-usage",
        "invalid-final-usage", "over-output", "over-cap", "over-input", "batch-valid-then-invalid",
        "invalid-finish", "duplicate-call-id",
        "empty-history", "none-history",
        "mismatched-response-model",
        "post-tool-429", "post-tool-503", "post-tool-connect-error", "post-tool-timeout",
    ))
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(json.dumps(_plan(), ensure_ascii=False, indent=2))
        return 0
    if args.mode == "live":
        print(json.dumps({"status": "rejected", "code": "live_execution_disabled"}, indent=2))
        return 2
    if not args.run_id:
        parser.error("offline mode requires --run-id")
    try:
        upstream = _upstream_identity()
        sdk = _sdk_identity()
        ledger, result = asyncio.run(_run_offline(args.scenario))
        evidence = _evidence(args.run_id, ledger, result, sdk, upstream)
        path = _write_evidence(args.run_id, evidence)
    except IntegrationFailure as exc:
        print(json.dumps({"status": "rejected", "code": exc.code}, indent=2))
        return 2
    print(json.dumps({"status": evidence["outcome"]["status"], "evidence": str(path),
                      "transport_send_count": ledger.transport_calls,
                      "safe_error_code": ledger.error_code}, indent=2))
    return 0 if evidence["outcome"]["status"] == "offline_synthetic_completion" else 1


if __name__ == "__main__":
    raise SystemExit(main())
