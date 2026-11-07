"""Offline request-contract primitives for a future Go CHI runtime.

This module deliberately provides no transport, journal, or live entry point.
Callers must persist actual provider usage and validate the full request before
using these primitives in a runtime.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from jsonschema import Draft202012Validator
from go_chi_diagnostics import build_cause
from request_budget import feedback

CALL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ContractFailure(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _parse(text):
    return json.loads(text, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def _same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _canonical_calls(calls):
    """Return calls with only canonical keys, tolerating an optional position index.

    Some OpenAI-compatible endpoints add ``index`` to non-streamed tool calls.
    The field carries no scheduling meaning here, so it is validated when present
    and dropped before a batch is committed; every other unknown key still fails.
    """
    if type(calls) is not list:
        raise ValueError("tool_calls_invalid")
    canonical = []
    for call in calls:
        if type(call) is not dict:
            raise ValueError("tool_call_invalid")
        extra = set(call) - {"id", "type", "function", "index"}
        if extra:
            raise ValueError("tool_call_unknown_field")
        if "index" in call and (type(call["index"]) is not int or call["index"] < 0):
            raise ValueError("tool_call_index_invalid")
        canonical.append({"id": call.get("id"), "type": call.get("type"), "function": call.get("function")})
    return canonical


def _same_assistant(candidate, stored):
    """Compare a replayable assistant message, ignoring the optional call index."""
    if type(candidate) is not dict or type(stored) is not dict:
        return False
    try:
        calls = _canonical_calls(candidate.get("tool_calls"))
    except ValueError:
        return False
    normalized = {key: value for key, value in candidate.items() if key != "tool_calls"}
    normalized["tool_calls"] = calls
    return _same(normalized, stored)


def _local_schema_references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$id", "$anchor", "$dynamicAnchor"}:
                return False
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (type(item) is not str or not item.startswith("#/")):
                return False
            if not _local_schema_references(item):
                return False
    elif isinstance(value, list):
        return all(_local_schema_references(item) for item in value)
    return True


class ToolContract:
    """Freeze tool definitions and validate each whole batch before dispatch."""

    RECOVERABLE_SCHEMA_LIMIT = 2
    RECOVERABLE_JSON_LIMIT = 2
    RECOVERABLE_TOTAL_LIMIT = 3

    def __init__(self, definitions: list[dict[str, Any]]):
        self.definitions = copy.deepcopy(definitions)
        self.schemas: dict[str, dict] = {}
        self.seen: set[str] = set()
        self.records: list[dict] = []
        self.batches: list[dict] = []
        self.refusals: dict[str, str] = {}
        self.schema_refusals = 0
        self.json_refusals = 0
        self.total_refusals = 0
        try:
            if not isinstance(definitions, list) or not definitions:
                raise ValueError
            for tool in self.definitions:
                fn = tool["function"]
                if (set(tool) != {"type", "function"} or tool["type"] != "function"
                        or set(fn) != {"name", "description", "parameters", "strict"}
                        or not isinstance(fn["name"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", fn["name"])
                        or fn["name"] in self.schemas or not isinstance(fn["description"], str)
                        or fn["strict"] is not False or type(fn["parameters"]) is not dict):
                    raise ValueError
                if not _local_schema_references(fn["parameters"]):
                    raise ValueError
                Draft202012Validator.check_schema(fn["parameters"])
                self.schemas[fn["name"]] = fn["parameters"]
        except Exception:
            raise ContractFailure("tool_definitions_invalid") from None

    def accept_batch(self, message: dict, *, recover_schema: bool = False) -> list[dict]:
        """Validate all IDs and arguments before committing any batch record.

        The first proven failure determines the finite diagnostic cause; the
        accepted set and the no-partial-commit rule are unchanged. With
        recover_schema, a JSON-valid but schema-invalid batch is accepted
        atomically with per-call refusals so the model can correct it once.
        """
        def fail(reason: str):
            failure = ContractFailure("tool_batch_invalid")
            failure.cause = build_cause("tool_batch", reason)
            raise failure

        try:
            if (type(message) is not dict or message.get("role") != "assistant"
                    or ("reasoning_content" in message and type(message["reasoning_content"]) is not str)
                    or message.get("content") is not None and type(message["content"]) is not str
                    or type(message.get("tool_calls")) is not list or not message["tool_calls"]):
                fail("assistant_shape")
            if any(record["result"] is None for record in self.records):
                fail("unfinished_batch")
            try:
                canonical = _canonical_calls(message["tool_calls"])
            except ValueError:
                fail("call_shape")
            calls, ids, failure_kind, failure_reason = [], set(), None, None
            for call in canonical:
                if set(call) != {"id", "type", "function"} or call["type"] != "function":
                    fail("call_shape")
                call_id, fn = call["id"], call["function"]
                if type(fn) is not dict or set(fn) != {"name", "arguments"}:
                    fail("function_shape")
                if type(call_id) is not str or not CALL_ID.fullmatch(call_id):
                    fail("call_id_invalid")
                if call_id in ids or call_id in self.seen:
                    fail("call_id_reused")
                if fn["name"] not in self.schemas:
                    fail("tool_unknown")
                if type(fn["arguments"]) is not str:
                    fail("arguments_json")
                try:
                    arguments = _parse(fn["arguments"])
                except Exception:
                    if not recover_schema:
                        fail("arguments_json")
                    arguments = {"__chi_invalid_json__": True}
                    if failure_reason is None:
                        failure_kind = "json"
                        failure_reason = (f"chi_tool_arguments_json_invalid: "
                                          f"{fn['name']}: invalid JSON")
                else:
                    errors = sorted(Draft202012Validator(self.schemas[fn["name"]]).iter_errors(arguments),
                                    key=lambda error: list(error.absolute_path))
                    if errors:
                        if not recover_schema:
                            fail("arguments_schema")
                        if failure_reason is None:
                            failure_kind = "schema"
                            failure_reason = self._schema_refusal(fn["name"], errors[0])
                ids.add(call_id)
                calls.append({"id": call_id, "name": fn["name"], "arguments": arguments, "result": None})
            if failure_reason is not None:
                class_limit = (self.RECOVERABLE_JSON_LIMIT if failure_kind == "json"
                               else self.RECOVERABLE_SCHEMA_LIMIT)
                class_count = (self.json_refusals if failure_kind == "json"
                               else self.schema_refusals)
                if class_count >= class_limit or self.total_refusals >= self.RECOVERABLE_TOTAL_LIMIT:
                    fail("arguments_json" if failure_kind == "json" else "arguments_schema")
                if failure_kind == "json":
                    self.json_refusals += 1
                else:
                    self.schema_refusals += 1
                self.total_refusals += 1
                for call in calls:
                    self.refusals[call["id"]] = failure_reason
        except ContractFailure:
            raise
        except Exception:
            failure = ContractFailure("tool_batch_invalid")
            failure.cause = build_cause("other", "unspecified")
            raise failure from None
        self.seen.update(ids)
        self.records.extend(calls)
        stored = {key: copy.deepcopy(value) for key, value in message.items() if key != "tool_calls"}
        stored["tool_calls"] = copy.deepcopy(canonical)
        self.batches.append({"message": stored, "ids": [c["id"] for c in calls]})
        return copy.deepcopy(calls)

    @staticmethod
    def _schema_refusal(tool: str, error) -> str:
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        if error.validator == "required" and isinstance(error.instance, dict):
            missing = [name for name in error.validator_value if name not in error.instance]
            detail = "missing required field(s) " + ", ".join(missing)
        elif error.validator == "additionalProperties" and isinstance(error.instance, dict):
            allowed = set(error.schema.get("properties", {}))
            unexpected = [name for name in error.instance if name not in allowed]
            detail = ("unknown field(s) " + ", ".join(unexpected) if unexpected
                      else "unknown field(s)")
        elif error.validator == "type":
            detail = "expected " + str(error.validator_value)
        elif error.validator == "enum":
            detail = "expected one of " + ", ".join(str(value) for value in error.validator_value)
        else:
            detail = "failed " + str(error.validator)
        return f"chi_tool_arguments_invalid: {tool}: {detail} at {path}"

    def record_result(self, call_id: str, result: Any) -> None:
        pending = [record for record in self.records if record["id"] == call_id and record["result"] is None]
        text_blocks = (type(result) is list and bool(result) and all(
            type(item) is dict and set(item) == {"type", "text"}
            and item["type"] == "text" and type(item["text"]) is str for item in result))
        if len(pending) != 1 or not (type(result) is str or text_blocks):
            raise ContractFailure("tool_result_invalid")
        pending[0]["result"] = copy.deepcopy(result)

    def definitions_match(self, definitions: list[dict]) -> bool:
        return _same(definitions, self.definitions)

    def validate_history(self, messages: list[dict], *, system: str, instruction: str,
                         used: int, claimed: bool, coding_probe: bool = False) -> None:
        """Reject stale budget feedback or history not produced by accepted calls."""
        try:
            suffix = "" if coding_probe else feedback(used, claimed)[0]
            if (type(messages) is not list or len(messages) < 2
                    or not _same(messages[0], {"role": "system", "content": system + suffix})
                    or not _same(messages[1], {"role": "user", "content": instruction})):
                raise ValueError
            by_id = {record["id"]: record for record in self.records}
            index = 2
            for batch in self.batches:
                if index >= len(messages) or not _same_assistant(messages[index], batch["message"]):
                    raise ValueError
                index += 1
                pending = set(batch["ids"])
                while pending:
                    if index >= len(messages):
                        raise ValueError
                    item = messages[index]
                    if (type(item) is not dict or set(item) != {"role", "tool_call_id", "content"}
                            or item["role"] != "tool" or item["tool_call_id"] not in pending
                            or by_id[item["tool_call_id"]]["result"] is None
                            or not _same(by_id[item["tool_call_id"]]["result"], item["content"])):
                        raise ValueError
                    pending.remove(item["tool_call_id"])
                    index += 1
            if index != len(messages):
                raise ValueError
        except Exception:
            raise ContractFailure("request_history_invalid") from None
