"""Input composition measurement and a conservative pre-send context budget.

This module does not rewrite history and does not claim a real tokenizer. It
records character/byte composition and an explicit UTF-8 byte upper estimate,
then stops before dispatch when the configured conservative budget is exceeded.
The service-reported prompt_tokens remain the authoritative post-response
measurement and are recorded separately by the journal.
"""
from __future__ import annotations

import json

SCHEMA = "chi-context-v2"
DEFAULT_BUDGET = {
    "schema": "chi-context-budget-v2",
    "max_chars": 3_500_000,
    "max_estimated_tokens": 1_000_000,
    "output_reserve_tokens": 8192,
    "basis": "utf8 byte upper estimate; configured_unverified",
}


def _chars(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False))


def _content_chars(message: dict) -> int:
    content = message.get("content")
    if type(content) is str:
        return len(content)
    if type(content) is list:
        return sum(len(item.get("text", "")) for item in content if type(item) is dict)
    return 0


def measure_request(body: dict, raw: bytes | None = None) -> dict:
    """Measure one already-validated OpenAI chat-completions body."""
    if type(body) is not dict or type(body.get("messages")) is not list:
        raise ValueError("context_body_invalid")
    messages = body["messages"]
    system_chars = _content_chars(messages[0]) if messages and messages[0].get("role") == "system" else 0
    instruction_chars = (_content_chars(messages[1])
                         if len(messages) > 1 and messages[1].get("role") == "user" else 0)
    history = messages[2:] if len(messages) > 1 else []
    history_chars = sum(_content_chars(message) for message in history)
    tool_result_chars = sum(_content_chars(message) for message in history
                            if message.get("role") == "tool")
    reasoning_chars = sum(len(message.get("reasoning_content", ""))
                          for message in messages
                          if type(message.get("reasoning_content")) is str)
    tools_chars = _chars(body["tools"]) if body.get("tools") is not None else 0
    # Components overlap and are informational only; total is the complete JSON.
    tool_calls = [m["tool_calls"] for m in messages if type(m) is dict and m.get("tool_calls") is not None]
    tool_call_chars = _chars(tool_calls) if tool_calls else 0
    tool_arguments_chars = sum(len(c["function"]["arguments"]) for calls in tool_calls if type(calls) is list
                               for c in calls if type(c) is dict and type(c.get("function")) is dict
                               and type(c["function"].get("arguments")) is str)
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    total_chars = len(canonical)
    total_bytes = len(canonical.encode("utf-8"))
    if raw is not None:
        if type(raw) is not bytes:
            raise ValueError("context_wire_invalid")
        parsed = json.loads(raw)
        if json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) != canonical:
            raise ValueError("context_wire_invalid")
    raw_bytes = len(raw) if raw is not None else total_bytes
    return {
        "schema": SCHEMA,
        "messages": len(messages),
        "system_chars": system_chars,
        "instruction_chars": instruction_chars,
        "tools_chars": tools_chars,
        "history_chars": history_chars,
        "tool_result_chars": tool_result_chars,
        "reasoning_chars": reasoning_chars,
        "tool_call_chars": tool_call_chars,
        "tool_arguments_chars": tool_arguments_chars,
        "total_chars": total_chars,
        "total_bytes": total_bytes,
        "raw_bytes": raw_bytes,
        "estimated_tokens": max(total_bytes, raw_bytes),
        "max_tokens": body.get("max_tokens"),
        "token_estimate": "utf8_bytes_upper_estimate_not_tokenizer",
    }


def check_budget(metric: dict, budget: dict | None) -> str | None:
    # Retain the original v1 calculation when explicitly inspecting old data.
    if (type(metric) is dict and metric.get("schema") == "chi-context-v1"
            and type(budget) is dict and budget.get("schema") == "chi-context-budget-v1"):
        if (type(budget.get("max_chars")) is not int or budget["max_chars"] < 1
                or type(budget.get("max_estimated_tokens")) is not int or budget["max_estimated_tokens"] < 1
                or type(budget.get("output_reserve_tokens")) is not int or budget["output_reserve_tokens"] < 0
                or type(metric.get("total_chars")) is not int or metric["total_chars"] < 0
                or type(metric.get("estimated_tokens")) is not int or metric["estimated_tokens"] < 0):
            return "chi_context_budget_invalid"
        if (metric["total_chars"] > budget["max_chars"] or metric["estimated_tokens"] +
                budget["output_reserve_tokens"] > budget["max_estimated_tokens"]):
            return "chi_context_budget_exceeded"
        return None
    if (type(budget) is not dict or set(budget) != {"schema", "max_chars", "max_estimated_tokens", "output_reserve_tokens", "basis"}
            or budget.get("schema") != "chi-context-budget-v2"
            or type(budget.get("max_chars")) is not int or budget["max_chars"] < 1
            or type(budget.get("max_estimated_tokens")) is not int or budget["max_estimated_tokens"] < 1
            or type(budget.get("output_reserve_tokens")) is not int or budget["output_reserve_tokens"] < 0
            or type(budget.get("basis")) is not str or not budget["basis"]):
        return "chi_context_budget_invalid"
    counts = {"messages", "system_chars", "instruction_chars", "tools_chars", "history_chars",
              "tool_result_chars", "reasoning_chars", "tool_call_chars", "tool_arguments_chars",
              "total_chars", "total_bytes", "raw_bytes", "estimated_tokens"}
    keys = counts | {"schema", "token_estimate", "max_tokens"}
    if (type(metric) is not dict or set(metric) not in (keys, keys | {"effective_output_reserve_tokens"})
            or metric.get("schema") != SCHEMA
            or metric.get("token_estimate") != "utf8_bytes_upper_estimate_not_tokenizer"
            or any(type(metric.get(k)) is not int or metric[k] < 0 for k in counts)
            or metric["total_chars"] > metric["total_bytes"]
            or metric["estimated_tokens"] != max(metric["total_bytes"], metric["raw_bytes"])
            or type(metric.get("max_tokens")) is not int or metric["max_tokens"] <= 0
            or ("effective_output_reserve_tokens" in metric and
                (type(metric["effective_output_reserve_tokens"]) is not int or
                 metric["effective_output_reserve_tokens"] != max(metric["max_tokens"], budget["output_reserve_tokens"])) )):
        return "chi_context_budget_invalid"
    metric["effective_output_reserve_tokens"] = max(metric["max_tokens"], budget["output_reserve_tokens"])
    if metric["total_chars"] > budget["max_chars"]:
        return "chi_context_budget_exceeded"
    if metric["estimated_tokens"] + metric["effective_output_reserve_tokens"] > budget["max_estimated_tokens"]:
        return "chi_context_budget_exceeded"
    return None
