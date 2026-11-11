"""Single-tool, read-only MCP probe for bootstrap-baseline A.

This script runs inside the fixed Python 3.12 task container. It intentionally
accepts only the container-local provider endpoint and the environment
controller's ignored evidence mount. It does not start a runner or a model.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Callable

ALLOWED_ENDPOINT = "http://127.0.0.1:8020/mcp"
ALLOWED_OUTPUT_DIR = Path("/logs/artifacts/probe")
ALLOWED_TOOL = "cases.list_cases"
UPSTREAM_SHA = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
CASE_STATUSES = frozenset(
    {
        "draft",
        "requirement_checked",
        "docs_needed",
        "ready_to_submit",
        "submitted",
        "pended_action_required",
        "under_review",
        "approved",
        "partially_approved",
        "denied",
        "resubmitted",
        "appealed",
        "appeal_upheld",
        "appeal_overturned",
        "external_appealed",
        "external_appeal_upheld",
        "external_appeal_overturned",
        "closed",
    }
)
ROOT_SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "$defs",
        "definitions",
    }
)
PROPERTY_SCHEMA_KEYWORDS = frozenset({"anyOf", "default", "title", "description"})
ENUM_SCHEMA_KEYWORDS = frozenset({"type", "enum", "title", "description"})
REF_SCHEMA_KEYWORDS = frozenset({"$ref", "title", "description"})
NULL_SCHEMA_KEYWORDS = frozenset({"type", "title", "description"})


class ProbeFailure(RuntimeError):
    """A safe-to-report probe failure with a bounded phase label."""

    def __init__(self, phase: str, reason: str, *, error_type: str | None = None):
        super().__init__(reason)
        self.phase = phase
        self.reason = reason
        self.error_type = error_type


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _write_json(path: Path, value: Any) -> str:
    data = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, default=_json_default)
    encoded = (data + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
    else:
        name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


def _tool_input_schema(tool: Any) -> Any:
    if isinstance(tool, dict):
        return tool.get("inputSchema")
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    return schema


def _resolve_ref(root: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError("external or unsupported schema reference")
    value: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            raise ValueError("unresolved schema reference")
        value = value[token]
    return value


def _validate_enum_branch(schema: Any, root: dict[str, Any], *, depth: int = 0) -> None:
    """Accept only an inline or local-ref string enum matching CaseStatus."""
    if depth > 2 or not isinstance(schema, dict):
        raise ValueError("unsupported status enum schema")
    if "$ref" in schema:
        if set(schema) - REF_SCHEMA_KEYWORDS:
            raise ValueError("unsupported keywords beside status enum reference")
        target = _resolve_ref(root, schema["$ref"])
        if not isinstance(target, dict) or set(target) - ENUM_SCHEMA_KEYWORDS:
            raise ValueError("referenced status enum contains unsupported constraints")
        enum_schema = target
    else:
        if set(schema) - ENUM_SCHEMA_KEYWORDS:
            raise ValueError("status enum contains unsupported constraints")
        enum_schema = schema
    enum = enum_schema.get("enum")
    if (
        enum_schema.get("type") != "string"
        or not isinstance(enum, list)
        or not all(isinstance(item, str) for item in enum)
        or frozenset(enum) != CASE_STATUSES
        or len(enum) != len(CASE_STATUSES)
    ):
        raise ValueError("status enum differs from the audited CaseStatus enum")


def _validate_optional_status_schema(schema: Any, root: dict[str, Any]) -> None:
    if not isinstance(schema, dict) or set(schema) - PROPERTY_SCHEMA_KEYWORDS:
        raise ValueError("status property contains unsupported constraints")
    if "default" in schema and schema["default"] is not None:
        raise ValueError("status default differs from the audited None default")
    branches = schema.get("anyOf")
    if not isinstance(branches, list) or len(branches) != 2:
        raise ValueError("status is not represented as a nullable enum")
    null_branches = [
        branch
        for branch in branches
        if isinstance(branch, dict) and branch.get("type") == "null"
    ]
    enum_branches = [branch for branch in branches if branch not in null_branches]
    if len(null_branches) != 1 or len(enum_branches) != 1:
        raise ValueError("status must allow exactly null or one CaseStatus enum")
    if set(null_branches[0]) - NULL_SCHEMA_KEYWORDS:
        raise ValueError("nullable status branch contains unsupported constraints")
    _validate_enum_branch(enum_branches[0], root)


def validate_cases_list_schema(schema: Any) -> None:
    """Fail closed unless the live schema matches the audited source signature."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("input schema is missing or is not an object schema")
    if set(schema) - ROOT_SCHEMA_KEYWORDS:
        raise ValueError("input schema contains unsupported constraints")
    if "required" in schema and (not isinstance(schema["required"], list) or schema["required"]):
        raise ValueError("cases.list_cases unexpectedly has required arguments")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or set(properties) != {"status"}:
        raise ValueError("cases.list_cases parameter set differs from the audited source")
    if schema.get("additionalProperties", False) is not False:
        raise ValueError("cases.list_cases schema permits unexpected arguments")
    for definitions_key in ("$defs", "definitions"):
        if definitions_key in schema and not isinstance(schema[definitions_key], dict):
            raise ValueError("input schema definitions are invalid")
    _validate_optional_status_schema(properties["status"], schema)


def _inventory_tools(result: Any) -> list[Any]:
    tools = getattr(result, "tools", None)
    if tools is None and isinstance(result, dict):
        tools = result.get("tools")
    if not isinstance(tools, list):
        raise ProbeFailure("list_tools", "server returned an invalid tool inventory")
    names = [_tool_name(tool) for tool in tools]
    if any(name is None for name in names) or len(names) != len(set(names)):
        raise ProbeFailure("list_tools", "server returned missing or duplicate tool names")
    return tools


def authorize_tool(name: str, inventory: set[str]) -> None:
    """Only the one reviewed read tool can pass this local policy gate."""
    if name != ALLOWED_TOOL or name not in inventory:
        raise ProbeFailure("schema_validation", "requested tool is not in the probe allowlist")


def _result_payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is None and isinstance(result, dict):
        structured = result.get("structuredContent", result.get("structured_content"))
    if structured is not None:
        return _model_dump(structured)

    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise ValueError("tool response has no structured object payload")
    block = content[0]
    text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
    if not isinstance(text, str):
        raise ValueError("tool response content is not a text JSON object")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("tool response text is not valid JSON") from exc


def _is_error(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("isError", result.get("is_error", False)))
    return bool(getattr(result, "isError", getattr(result, "is_error", False)))


def _validate_payload(payload: Any) -> int:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("tool response does not match the expected items object")
    if any(not isinstance(item, dict) for item in payload["items"]):
        raise ValueError("tool response items contain an invalid element")
    return len(payload["items"])


def _safe_raw_result(result: Any) -> Any:
    """Serialize the potentially sensitive result only to the ignored evidence directory."""
    data = _model_dump(result)
    try:
        json.dumps(data, ensure_ascii=False, default=_json_default)
    except (TypeError, ValueError):
        return {"serialization_error_type": "NonJsonMcpResult"}
    return data


def _elapsed_ms(start: float) -> int:
    return max(0, round((time.monotonic() - start) * 1000))


def _exception_leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in _exception_leaves(child)]
    return [exc]


def _nested_probe_failure_records(exc: BaseException) -> list[dict[str, Any]]:
    return [
        {"phase": leaf.phase, "reason": leaf.reason, "error_type": leaf.error_type}
        for leaf in _exception_leaves(exc)
        if isinstance(leaf, ProbeFailure)
    ]


def _same_probe_failure(leaves: list[BaseException]) -> ProbeFailure | None:
    if not leaves or not all(isinstance(leaf, ProbeFailure) for leaf in leaves):
        return None
    first = leaves[0]
    if all(
        leaf.phase == first.phase
        and leaf.reason == first.reason
        and leaf.error_type == first.error_type
        for leaf in leaves[1:]
    ):
        return first
    return None


async def _with_timeout(awaitable: Any, timeout_sec: float) -> Any:
    async with asyncio.timeout(timeout_sec):
        return await awaitable


async def execute_probe(
    *,
    endpoint: str,
    evidence_dir: Path,
    phase_timeout_sec: float = 10.0,
    transport_factory: Callable[[str], AbstractAsyncContextManager[Any]] | None = None,
    session_factory: Callable[..., AbstractAsyncContextManager[Any]] | None = None,
) -> dict[str, Any]:
    """Execute one initialize/list/call exchange and write private evidence."""
    if endpoint != ALLOWED_ENDPOINT:
        raise ProbeFailure("preflight", "endpoint must be the fixed task-local provider MCP URL")
    if not evidence_dir.is_absolute():
        raise ProbeFailure("preflight", "evidence output path must be absolute")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if transport_factory is None or session_factory is None:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:  # pragma: no cover - supplied by fixed upstream task image
            raise ProbeFailure("preflight", "MCP SDK is unavailable", error_type=type(exc).__name__) from None
        transport_factory = transport_factory or streamablehttp_client
        session_factory = session_factory or ClientSession

    timings: dict[str, int] = {}
    phase = "initialize"
    init_result: Any = None
    tools: list[Any] = []
    raw_result: Any = None
    payload: Any = None
    item_count: int | None = None
    schema_hash: str | None = None
    response_hash: str | None = None
    failure: ProbeFailure | None = None
    nested_failures: list[dict[str, Any]] = []
    exception_group_member_types: list[str] = []
    call_invoked = False
    call_response_received = False
    call_result_status = "not_attempted"
    started_total = time.monotonic()

    try:
        # Bound transport creation as well as the three individual protocol phases.
        async with asyncio.timeout(phase_timeout_sec * 3 + 5):
            async with transport_factory(endpoint) as streams:
                async with session_factory(streams[0], streams[1]) as session:
                    phase = "initialize"
                    started = time.monotonic()
                    try:
                        init_result = await _with_timeout(session.initialize(), phase_timeout_sec)
                    except TimeoutError:
                        raise ProbeFailure(phase, "initialize timed out", error_type="TimeoutError") from None
                    except Exception as exc:
                        raise ProbeFailure(phase, "initialize failed", error_type=type(exc).__name__) from None
                    finally:
                        timings[phase] = _elapsed_ms(started)

                    phase = "list_tools"
                    started = time.monotonic()
                    try:
                        list_result = await _with_timeout(session.list_tools(), phase_timeout_sec)
                    except TimeoutError:
                        raise ProbeFailure(phase, "tool discovery timed out", error_type="TimeoutError") from None
                    except Exception as exc:
                        raise ProbeFailure(phase, "tool discovery failed", error_type=type(exc).__name__) from None
                    finally:
                        timings[phase] = _elapsed_ms(started)
                    _write_json(
                        evidence_dir / "mcp-schema.json",
                        {
                            "upstream_sha": UPSTREAM_SHA,
                            "server_info": _model_dump(getattr(init_result, "serverInfo", None)),
                            "protocol_version": getattr(init_result, "protocolVersion", None),
                            "tools": [
                                {
                                    "name": _tool_name(tool),
                                    "inputSchema": _tool_input_schema(tool),
                                }
                                for tool in _inventory_tools(list_result)
                            ],
                        },
                    )
                    tools = _inventory_tools(list_result)
                    inventory = {_tool_name(tool) for tool in tools}
                    inventory.discard(None)

                    phase = "schema_validation"
                    started = time.monotonic()
                    try:
                        authorize_tool(ALLOWED_TOOL, inventory)
                        selected = next(tool for tool in tools if _tool_name(tool) == ALLOWED_TOOL)
                        schema = _tool_input_schema(selected)
                        validate_cases_list_schema(schema)
                        schema_hash = hashlib.sha256(_canonical_json(schema)).hexdigest()
                    except ProbeFailure:
                        raise
                    except Exception as exc:
                        raise ProbeFailure(phase, "live input schema is incompatible", error_type=type(exc).__name__) from None
                    finally:
                        timings[phase] = _elapsed_ms(started)

                    phase = "call_tool"
                    started = time.monotonic()
                    call_invoked = True
                    call_result_status = "unknown"
                    try:
                        raw_result = await _with_timeout(
                            session.call_tool(ALLOWED_TOOL, arguments={}), phase_timeout_sec
                        )
                        call_response_received = True
                        call_result_status = "response_received"
                    except TimeoutError:
                        raise ProbeFailure(phase, "tool call timed out; no retry was attempted", error_type="TimeoutError") from None
                    except Exception as exc:
                        raise ProbeFailure(phase, "tool call failed; no retry was attempted", error_type=type(exc).__name__) from None
                    finally:
                        timings[phase] = _elapsed_ms(started)
                    response_hash = _write_json(evidence_dir / "mcp-response.json", _safe_raw_result(raw_result))

                    phase = "response_validation"
                    started = time.monotonic()
                    if _is_error(raw_result):
                        call_result_status = "mcp_error"
                        raise ProbeFailure(phase, "MCP returned isError=true")
                    try:
                        payload = _result_payload(raw_result)
                        item_count = _validate_payload(payload)
                        call_result_status = "valid"
                    except Exception as exc:
                        call_result_status = "invalid_response"
                        raise ProbeFailure(phase, "tool response format is invalid", error_type=type(exc).__name__) from None
                    finally:
                        timings[phase] = _elapsed_ms(started)
    except ProbeFailure as exc:
        failure = exc
        phase = exc.phase
    except TimeoutError:
        failure = ProbeFailure(phase, "MCP transport timed out", error_type="TimeoutError")
        phase = failure.phase
    except BaseExceptionGroup as exc:
        # Avoid printing or persisting arbitrary library exception text.
        leaves = _exception_leaves(exc)
        nested_failures = _nested_probe_failure_records(exc)
        exception_group_member_types = sorted({type(leaf).__name__ for leaf in leaves})
        unwrapped = _same_probe_failure(leaves)
        failure = unwrapped or ProbeFailure(
            phase, "MCP transport failed", error_type=type(exc).__name__
        )
        phase = failure.phase
    except Exception as exc:
        # Avoid printing or persisting arbitrary library exception text.
        failure = ProbeFailure(phase, "MCP transport failed", error_type=type(exc).__name__)
        phase = failure.phase

    if not call_invoked:
        business_effect = "not_applicable"
        audit_effect = "not_attempted"
    elif call_result_status == "valid":
        business_effect = "none_expected_read_only"
        audit_effect = "expected_from_successful_handler"
    else:
        business_effect = "unknown"
        audit_effect = "unknown"

    summary = {
        "status": "failed" if failure else "success",
        "phase": failure.phase if failure else "complete",
        "reason": failure.reason if failure else None,
        "error_type": failure.error_type if failure else None,
        "tool": ALLOWED_TOOL,
        "arguments": {},
        "tool_inventory_count": len(tools),
        "items_count": item_count,
        "empty_items": item_count == 0 if item_count is not None else None,
        "call_invoked": call_invoked,
        "call_response_received": call_response_received,
        "call_result_status": call_result_status,
        "business_effect": business_effect,
        "audit_effect": audit_effect,
        "schema_sha256": schema_hash,
        "response_sha256": response_hash,
        "phase_elapsed_ms": timings,
        "total_elapsed_ms": _elapsed_ms(started_total),
        "upstream_sha": UPSTREAM_SHA,
        "model_calls": 0,
        "tool_retries": 0,
        "nested_probe_failures": nested_failures,
        "exception_group_member_types": exception_group_member_types,
    }
    _write_json(evidence_dir / "summary.json", summary)
    return summary


def _validate_cli_args(endpoint: str, output_dir: Path, phase_timeout_sec: float) -> None:
    if endpoint != ALLOWED_ENDPOINT:
        raise ProbeFailure("preflight", "endpoint must be the fixed task-local provider MCP URL")
    if output_dir != ALLOWED_OUTPUT_DIR:
        raise ProbeFailure("preflight", "output directory must be /logs/artifacts/probe")
    if not 0 < phase_timeout_sec <= 30:
        raise ProbeFailure("preflight", "phase timeout must be greater than 0 and at most 30 seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one fixed, read-only CHI-Bench MCP probe")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--phase-timeout-sec", required=False, type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        _validate_cli_args(args.endpoint, args.output_dir, args.phase_timeout_sec)
        summary = asyncio.run(
            execute_probe(
                endpoint=args.endpoint,
                evidence_dir=args.output_dir,
                phase_timeout_sec=args.phase_timeout_sec,
            )
        )
    except ProbeFailure as exc:
        # Never emit raw exception content or any MCP response data.
        print(
            json.dumps(
                {"status": "failed", "phase": exc.phase, "reason": exc.reason, "error_type": exc.error_type},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "phase": "internal", "reason": "probe failed", "error_type": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":  # pragma: no cover - exercised by container CLI
    raise SystemExit(main())
