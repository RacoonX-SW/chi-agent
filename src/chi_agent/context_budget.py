"""Input composition measurement and a conservative pre-send context budget.

v3 separates byte measurement from two token estimates: a conservative UTF-8
upper bound used for the hard gate, and a calibrated estimate used for reporting.
It does not claim a real tokenizer. The service-reported prompt_tokens remain the
authoritative post-response measurement and are recorded by the journal.

Legacy v1/v2 metrics and budgets remain readable for inspection. They are never
migrated or re-graded.
"""
from __future__ import annotations

import json
import math

from .runtime_policy import DEFAULT_CONTEXT_MODEL, context_profile

SCHEMA_V1 = "chi-context-v1"
SCHEMA_V2 = "chi-context-v2"
SCHEMA = "chi-context-v3"
BUDGET_SCHEMA_V1 = "chi-context-budget-v1"
BUDGET_SCHEMA_V2 = "chi-context-budget-v2"
BUDGET_SCHEMA = "chi-context-budget-v3"
TOKEN_ESTIMATE_V2 = "utf8_bytes_upper_estimate_not_tokenizer"
TOKEN_ESTIMATE_V3 = "utf8_bytes_upper_and_calibrated_not_tokenizer"


def _default_budget():
    profile = context_profile(DEFAULT_CONTEXT_MODEL)
    return {
        "schema": BUDGET_SCHEMA,
        "model": profile["model"],
        "provider_context_tokens": profile["provider_context_tokens"],
        "window_safety_fraction": profile["window_safety_fraction"],
        "output_reserve_tokens": profile["output_reserve_tokens"],
        "bytes_per_token_floor": profile["bytes_per_token_floor"],
        "bytes_per_token_observed": profile["bytes_per_token_observed"],
        "max_context_bytes": profile["max_context_bytes"],
        "max_input_tokens": profile["max_input_tokens"],
        "basis": ("utf8 byte upper estimate for the hard gate; calibrated estimate for reporting; "
                  "configured_unverified"),
    }


DEFAULT_BUDGET_V3 = _default_budget()
# Legacy v2 default retained for reading and for un-migrated offline callers.
DEFAULT_BUDGET = {
    "schema": BUDGET_SCHEMA_V2,
    "max_chars": 3_500_000,
    "max_estimated_tokens": 1_000_000,
    "output_reserve_tokens": 8192,
    "basis": "utf8 byte upper estimate; configured_unverified (legacy v2)",
}
DEFAULT_BUDGET_V3["basis"] = ("utf8 byte upper estimate for the hard gate; calibrated estimate for reporting; "
                              "configured_unverified")


def budget_from_bytes(value, base=None):
    """Legacy byte-cap override: 1..3,500,000 maps to max_context_bytes."""
    if type(value) is not int or not 1 <= value <= 3_500_000:
        raise ValueError("chi_context_budget_invalid")
    budget = dict(base if type(base) is dict else DEFAULT_BUDGET_V3)
    floor = budget.get("bytes_per_token_floor")
    window_cap = (math.floor(budget["provider_context_tokens"] * budget["window_safety_fraction"])
                  - budget["output_reserve_tokens"])
    byte_cap = math.floor(value / float(floor))
    budget["max_context_bytes"] = value
    budget["max_input_tokens"] = min(window_cap, max(1, byte_cap))
    return budget


def budget_from_input_tokens(value, base=None):
    """New token-cap override: 1..1,000,000 maps to max_input_tokens."""
    if type(value) is not int or not 1 <= value <= 1_000_000:
        raise ValueError("chi_context_budget_invalid")
    budget = dict(base if type(base) is dict else DEFAULT_BUDGET_V3)
    window_cap = (math.floor(budget["provider_context_tokens"] * budget["window_safety_fraction"])
                  - budget["output_reserve_tokens"])
    if value > window_cap:
        raise ValueError("chi_context_budget_invalid")
    budget["max_input_tokens"] = value
    return budget


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


def _bounded_bytes(value: int, floor: float) -> int:
    if type(value) is not int or value < 0 or type(floor) not in (int, float) or floor <= 0:
        raise ValueError("context_measurement_invalid")
    return math.ceil(value / float(floor))


def measure_request(body: dict, raw: bytes | None = None, budget: dict | None = None) -> dict:
    """Measure one already-validated OpenAI chat-completions body.

    Without a v3 budget this returns the legacy v2 metric so old offline
    callers and evidence keep their original semantics. A v3 budget returns the
    dual-track metric used by new runs.
    """
    if type(body) is not dict or type(body.get("messages")) is not list:
        raise ValueError("context_body_invalid")
    active = budget if budget is not None else DEFAULT_BUDGET
    v3 = type(active) is dict and active.get("schema") == BUDGET_SCHEMA
    floor = active.get("bytes_per_token_floor") if v3 else None
    observed = active.get("bytes_per_token_observed") if v3 else None
    if v3 and (type(floor) not in (int, float) or type(observed) not in (int, float)
               or floor <= 0 or observed <= 0):
        raise ValueError("context_budget_invalid")
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
    measured = max(total_bytes, raw_bytes)
    base = {
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
        "max_tokens": body.get("max_tokens"),
    }
    if not v3:
        return {
            "schema": SCHEMA_V2,
            **base,
            "estimated_tokens": measured,
            "token_estimate": TOKEN_ESTIMATE_V2,
        }
    upper = _bounded_bytes(measured, floor)
    calibrated = int(round(measured / float(observed)))
    return {
        "schema": SCHEMA,
        **base,
        "estimated_tokens_upper": upper,
        "estimated_tokens_calibrated": calibrated,
        "bytes_per_token_floor": float(floor),
        "bytes_per_token_observed": float(observed),
        "token_estimate": TOKEN_ESTIMATE_V3,
    }


def _legacy_check(metric: dict, budget: dict) -> str | None:
    schema = metric.get("schema") if type(metric) is dict else None
    budget_schema = budget.get("schema") if type(budget) is dict else None
    if schema == SCHEMA_V1 and budget_schema == BUDGET_SCHEMA_V1:
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
    if schema == SCHEMA_V2 and budget_schema == BUDGET_SCHEMA_V2:
        if (set(budget) != {"schema", "max_chars", "max_estimated_tokens", "output_reserve_tokens", "basis"}
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
                or metric.get("schema") != SCHEMA_V2
                or metric.get("token_estimate") != TOKEN_ESTIMATE_V2
                or any(type(metric.get(k)) is not int or metric[k] < 0 for k in counts)
                or metric["total_chars"] > metric["total_bytes"]
                or metric["estimated_tokens"] != max(metric["total_bytes"], metric["raw_bytes"])
                or type(metric.get("max_tokens")) is not int or metric["max_tokens"] <= 0
                or ("effective_output_reserve_tokens" in metric and
                    (type(metric["effective_output_reserve_tokens"]) is not int or
                     metric["effective_output_reserve_tokens"] != max(metric["max_tokens"], budget["output_reserve_tokens"])))):
            return "chi_context_budget_invalid"
        metric["effective_output_reserve_tokens"] = max(metric["max_tokens"], budget["output_reserve_tokens"])
        if metric["total_chars"] > budget["max_chars"]:
            return "chi_context_budget_exceeded"
        if metric["estimated_tokens"] + metric["effective_output_reserve_tokens"] > budget["max_estimated_tokens"]:
            return "chi_context_budget_exceeded"
        return None
    return "chi_context_budget_invalid"


def _v3_budget_valid(budget: dict) -> bool:
    keys = {"schema", "model", "provider_context_tokens", "window_safety_fraction",
            "output_reserve_tokens", "bytes_per_token_floor", "bytes_per_token_observed",
            "max_context_bytes", "max_input_tokens", "basis"}
    if type(budget) is not dict or set(budget) != keys or budget.get("schema") != BUDGET_SCHEMA:
        return False
    if type(budget.get("model")) is not str or not budget["model"]:
        return False
    ints = ("provider_context_tokens", "output_reserve_tokens", "max_context_bytes", "max_input_tokens")
    if any(type(budget.get(k)) is not int or budget[k] <= 0 for k in ints):
        return False
    if type(budget.get("window_safety_fraction")) not in (int, float) or not 0 < budget["window_safety_fraction"] <= 1:
        return False
    if type(budget.get("bytes_per_token_floor")) not in (int, float) or budget["bytes_per_token_floor"] <= 0:
        return False
    if type(budget.get("bytes_per_token_observed")) not in (int, float) \
            or budget["bytes_per_token_observed"] < budget["bytes_per_token_floor"]:
        return False
    if type(budget.get("basis")) is not str or not budget["basis"]:
        return False
    window_cap = math.floor(budget["provider_context_tokens"] * budget["window_safety_fraction"]) \
        - budget["output_reserve_tokens"]
    byte_cap = max(1, math.floor(budget["max_context_bytes"] / budget["bytes_per_token_floor"]))
    return budget["max_input_tokens"] <= min(window_cap, byte_cap)


def _v3_metric_valid(metric: dict, budget: dict) -> bool:
    counts = {"messages", "system_chars", "instruction_chars", "tools_chars", "history_chars",
              "tool_result_chars", "reasoning_chars", "tool_call_chars", "tool_arguments_chars",
              "total_chars", "total_bytes", "raw_bytes", "estimated_tokens_upper",
              "estimated_tokens_calibrated"}
    keys = counts | {"schema", "bytes_per_token_floor", "bytes_per_token_observed", "max_tokens",
                     "token_estimate"}
    allowed = (keys, keys | {"effective_output_reserve_tokens"})
    if type(metric) is not dict or set(metric) not in allowed or metric.get("schema") != SCHEMA:
        return False
    if metric.get("token_estimate") != TOKEN_ESTIMATE_V3:
        return False
    if any(type(metric.get(k)) is not int or metric[k] < 0 for k in counts):
        return False
    if type(metric.get("bytes_per_token_floor")) not in (int, float) \
            or float(metric["bytes_per_token_floor"]) != float(budget["bytes_per_token_floor"]):
        return False
    if type(metric.get("bytes_per_token_observed")) not in (int, float) \
            or float(metric["bytes_per_token_observed"]) != float(budget["bytes_per_token_observed"]):
        return False
    if metric["total_chars"] > metric["total_bytes"]:
        return False
    measured = max(metric["total_bytes"], metric["raw_bytes"])
    if metric["estimated_tokens_upper"] != math.ceil(measured / float(budget["bytes_per_token_floor"])):
        return False
    if metric["estimated_tokens_calibrated"] != int(round(measured / float(budget["bytes_per_token_observed"]))):
        return False
    if metric["estimated_tokens_upper"] < metric["estimated_tokens_calibrated"]:
        return False
    if type(metric.get("max_tokens")) is not int or metric["max_tokens"] <= 0:
        return False
    return True


def check_budget(metric: dict, budget: dict | None) -> str | None:
    """Return a stable refusal code, or None when the request fits.

    v3 hard gate uses the conservative token upper bound and the byte ceiling.
    The calibrated estimate never relaxes the gate.
    """
    legacy = _legacy_check(metric, budget) if type(budget) is dict else "chi_context_budget_invalid"
    if legacy is not None and (type(budget) is not dict or budget.get("schema") not in {BUDGET_SCHEMA_V1, BUDGET_SCHEMA_V2}):
        if not _v3_budget_valid(budget):
            return "chi_context_budget_invalid"
        if not _v3_metric_valid(metric, budget):
            return "chi_context_budget_invalid"
        metric["effective_output_reserve_tokens"] = max(metric["max_tokens"], budget["output_reserve_tokens"])
        if (metric["estimated_tokens_upper"] > budget["max_input_tokens"]
                or metric["total_bytes"] > budget["max_context_bytes"]):
            return "chi_context_budget_exceeded"
        return None
    return legacy


def budget_pressure(metric: dict, budget: dict) -> bool:
    """Return True when the history has reached the 80% compression trigger."""
    if type(budget) is dict and budget.get("schema") == BUDGET_SCHEMA \
            and _v3_metric_valid(metric, budget):
        return metric["estimated_tokens_upper"] >= math.floor(0.8 * budget["max_input_tokens"])
    if type(metric) is dict and metric.get("schema") == SCHEMA_V2 and type(budget) is dict \
            and budget.get("schema") == BUDGET_SCHEMA_V2:
        reserve = max(metric.get("max_tokens", 0), budget.get("output_reserve_tokens", 0))
        return metric.get("estimated_tokens", 0) + reserve >= math.floor(0.8 * budget.get("max_estimated_tokens", 0))
    return False


def calibration(metric: dict, prompt_tokens: int) -> dict:
    """Record the observed bytes/token ratio without changing runtime thresholds."""
    if (type(metric) is not dict or type(prompt_tokens) is not int or prompt_tokens <= 0
            or type(metric.get("total_bytes")) is not int):
        raise ValueError("context_calibration_invalid")
    actual = round(metric["total_bytes"] / prompt_tokens, 4)
    floor = metric.get("bytes_per_token_floor", DEFAULT_BUDGET_V3["bytes_per_token_floor"])
    warning = "chi_context_bytes_per_token_below_floor" if actual < float(floor) else None
    return {
        "prompt_tokens_observed": prompt_tokens,
        "bytes_per_token_actual": actual,
        "bytes_per_token_floor": float(floor),
        "warning": warning,
    }
