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

    def __init__(self, definitions: list[dict[str, Any]]):
        self.definitions = copy.deepcopy(definitions)
        self.schemas: dict[str, dict] = {}
        self.seen: set[str] = set()
        self.records: list[dict] = []
        self.batches: list[dict] = []
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

    def accept_batch(self, message: dict) -> list[dict]:
        """Validate all IDs and arguments before committing any batch record."""
        try:
            if (type(message) is not dict or message.get("role") != "assistant"
                    or type(message.get("reasoning_content")) is not str
                    or message.get("content") is not None and type(message["content"]) is not str
                    or type(message.get("tool_calls")) is not list or not message["tool_calls"]):
                raise ValueError
            if any(record["result"] is None for record in self.records):
                raise ValueError
            calls, ids = [], set()
            for call in message["tool_calls"]:
                if type(call) is not dict or set(call) != {"id", "type", "function"} or call["type"] != "function":
                    raise ValueError
                call_id, fn = call["id"], call["function"]
                if (type(call_id) is not str or not CALL_ID.fullmatch(call_id)
                        or call_id in ids or call_id in self.seen or type(fn) is not dict
                        or set(fn) != {"name", "arguments"} or fn["name"] not in self.schemas
                        or type(fn["arguments"]) is not str):
                    raise ValueError
                arguments = _parse(fn["arguments"])
                if not Draft202012Validator(self.schemas[fn["name"]]).is_valid(arguments):
                    raise ValueError
                ids.add(call_id)
                calls.append({"id": call_id, "name": fn["name"], "arguments": arguments, "result": None})
        except Exception:
            raise ContractFailure("tool_batch_invalid") from None
        self.seen.update(ids)
        self.records.extend(calls)
        self.batches.append({"message": copy.deepcopy(message), "ids": [c["id"] for c in calls]})
        return copy.deepcopy(calls)

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
                if index >= len(messages) or not _same(messages[index], batch["message"]):
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
