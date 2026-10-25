"""Offline-only Chat Completions protocol adapter for stage B.

This module has no HTTP or SDK transport. Callers must inject a transport,
which keeps the production probe independent of credentials and networking.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable


CANDIDATE_PROFILE: dict[str, Any] = {
    "model": "deepseek-flash",
    "endpoint": "https://api.deepseek.com",
    "api": "chat_completions",
    "thinking": {"type": "enabled"},
    "reasoning_effort": "high",
    "max_tokens": 8192,
}

SYNTHETIC_TOOLS: dict[str, dict[str, Any]] = {
    "synthetic_lookup": {
        "required": {"key": str},
        "description": "Look up a value in a fixed synthetic fixture.",
    },
    "synthetic_format": {
        "required": {"text": str},
        "description": "Format a string using a fixed synthetic operation.",
    },
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "synthetic_lookup",
            "description": SYNTHETIC_TOOLS["synthetic_lookup"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "synthetic_format",
            "description": SYNTHETIC_TOOLS["synthetic_format"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
]

SYNTHETIC_LOOKUP_VALUES = {"sample": "synthetic-value"}
CALL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ProbeFailure(Exception):
    """A fixed-classification probe failure safe to include in local evidence."""

    def __init__(self, code: str, phase: str):
        super().__init__(code)
        self.code = code
        self.phase = phase


@dataclass(frozen=True)
class BudgetProfile:
    """Explicit synthetic accounting inputs; never provider price/usage data."""

    cap_cny: float = 5.0
    max_rounds: int = 30
    max_input_tokens: int = 65_536
    max_output_tokens: int = 8192
    input_price_usd_per_million: float = 1.0
    output_price_usd_per_million: float = 1.0
    usd_to_cny: float = 7.2
    pricing_version: str = "synthetic-profile-v1"
    fx_rate_source: str = "synthetic-profile-v1"


Transport = Callable[[dict[str, Any]], dict[str, Any]]


def estimate_input_token_upper_bound(request: dict[str, Any]) -> int:
    """Bound input conservatively by UTF-8 byte count, not a tokenizer result.

    Provider-specific chat framing and tokenizer behavior are unverified. The
    serialized request bytes, including tool schemas, are used as a deliberately
    conservative local bound and are never reported as measured token usage.
    """

    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return len(encoded)


def build_request(messages: list[dict[str, Any]], *, max_tokens: int) -> dict[str, Any]:
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ProbeFailure("invalid_output_limit", "request_validation")
    request = copy.deepcopy(CANDIDATE_PROFILE)
    request["max_tokens"] = max_tokens
    request["messages"] = copy.deepcopy(messages)
    request["tools"] = copy.deepcopy(TOOL_SCHEMAS)
    return request


def extract_assistant_message(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ProbeFailure("invalid_response_shape", "response_validation")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProbeFailure("invalid_response_shape", "response_validation")
    message = choices[0].get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ProbeFailure("invalid_response_shape", "response_validation")
    if "content" not in message or message["content"] is not None and not isinstance(message["content"], str):
        raise ProbeFailure("invalid_assistant_content", "response_validation")
    return copy.deepcopy(message)


def validate_tool_batch(
    message: dict[str, Any], seen_call_ids: set[str]
) -> list[tuple[str, str, dict[str, Any]]]:
    """Validate every call before allowing any synthetic tool to execute."""

    calls = message.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        raise ProbeFailure("invalid_tool_batch", "response_validation")
    if "reasoning_content" not in message or not isinstance(message["reasoning_content"], str):
        raise ProbeFailure("missing_reasoning_content", "response_validation")

    parsed: list[tuple[str, str, dict[str, Any]]] = []
    batch_ids: set[str] = set()
    for call in calls:
        if not isinstance(call, dict):
            raise ProbeFailure("invalid_tool_call", "response_validation")
        if call.get("type") != "function":
            raise ProbeFailure("unsupported_tool_call_type", "response_validation")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not CALL_ID_RE.fullmatch(call_id):
            raise ProbeFailure("invalid_tool_call_id", "response_validation")
        if call_id in seen_call_ids or call_id in batch_ids:
            raise ProbeFailure("duplicate_tool_call_id", "response_validation")
        function = call.get("function")
        if not isinstance(function, dict):
            raise ProbeFailure("invalid_tool_call", "response_validation")
        name = function.get("name")
        tool_spec = SYNTHETIC_TOOLS.get(name) if isinstance(name, str) else None
        if tool_spec is None:
            raise ProbeFailure("unknown_tool", "response_validation")
        raw_arguments = function.get("arguments")
        if not isinstance(raw_arguments, str):
            raise ProbeFailure("invalid_tool_arguments", "response_validation")
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, ValueError):
            raise ProbeFailure("invalid_tool_arguments", "response_validation") from None
        if not isinstance(arguments, dict):
            raise ProbeFailure("invalid_tool_arguments", "response_validation")
        required: dict[str, type] = tool_spec["required"]
        if set(arguments) != set(required):
            raise ProbeFailure("invalid_tool_arguments", "response_validation")
        for key, expected in required.items():
            if not isinstance(arguments[key], expected):
                raise ProbeFailure("invalid_tool_argument_type", "response_validation")
        parsed.append((call_id, name, arguments))
        batch_ids.add(call_id)
    return parsed


def execute_synthetic_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "synthetic_lookup":
        value = SYNTHETIC_LOOKUP_VALUES.get(arguments["key"])
        if value is None:
            return "synthetic-key-not-found"
        return value
    if name == "synthetic_format":
        return f"synthetic-formatted:{arguments['text']}"
    raise ProbeFailure("unknown_tool", "tool_execution")


def parse_usage(response: Any) -> tuple[int, int] | None:
    if not isinstance(response, dict):
        return None
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        return None
    return input_tokens, output_tokens


def make_assistant_message(
    *,
    content: str | None,
    reasoning_content: str,
    call_id: str,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Helper for local, deterministic synthetic scenarios and tests."""

    return {
        "role": "assistant",
        "content": content,
        "reasoning_content": reasoning_content,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
                },
            }
        ],
    }
