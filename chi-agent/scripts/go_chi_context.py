"""Input composition measurement and a conservative pre-send context budget.

This module does not rewrite history and does not claim a real tokenizer. It
records character/byte composition and an explicit 4-chars-per-token estimate,
then stops before dispatch when the configured conservative budget is exceeded.
The service-reported prompt_tokens remain the authoritative post-response
measurement and are recorded separately by the journal.
"""
from __future__ import annotations

import json
import math

SCHEMA = "chi-context-v1"
DEFAULT_BUDGET = {
    "schema": "chi-context-budget-v1",
    "max_chars": 3_500_000,
    "max_estimated_tokens": 1_000_000,
    "output_reserve_tokens": 8192,
    "basis": "conservative 4-chars-per-token estimate; configured_unverified",
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


def measure_request(body: dict) -> dict:
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
    total_chars = system_chars + instruction_chars + tools_chars + history_chars
    total_bytes = len(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8"))
    return {
        "schema": SCHEMA,
        "messages": len(messages),
        "system_chars": system_chars,
        "instruction_chars": instruction_chars,
        "tools_chars": tools_chars,
        "history_chars": history_chars,
        "tool_result_chars": tool_result_chars,
        "reasoning_chars": reasoning_chars,
        "total_chars": total_chars,
        "total_bytes": total_bytes,
        "estimated_tokens": int(math.ceil(total_chars / 4)),
        "max_tokens": body.get("max_tokens"),
        "token_estimate": "chars_div_4_not_tokenizer",
    }


def check_budget(metric: dict, budget: dict | None) -> str | None:
    if budget is None:
        return None
    if (type(budget) is not dict or budget.get("schema") != "chi-context-budget-v1"
            or type(budget.get("max_chars")) is not int or budget["max_chars"] < 1
            or type(budget.get("max_estimated_tokens")) is not int
            or budget["max_estimated_tokens"] < 1
            or type(budget.get("output_reserve_tokens")) is not int
            or budget["output_reserve_tokens"] < 0):
        return "chi_context_budget_invalid"
    if metric["total_chars"] > budget["max_chars"]:
        return "chi_context_budget_exceeded"
    if metric["estimated_tokens"] + budget["output_reserve_tokens"] > budget["max_estimated_tokens"]:
        return "chi_context_budget_exceeded"
    return None
