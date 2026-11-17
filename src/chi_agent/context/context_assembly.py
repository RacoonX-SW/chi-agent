"""Deterministic context assembly primitives.

This module is pure: it does not read files, call tools, or persist evidence.
The guard/runtime owns evidence writes and history validation; these helpers
only bound a single tool result and derive program-owned canonical records.
"""
from __future__ import annotations

import hashlib
import json

from chi_agent.context.output_recovery import classify

SCHEMA = "chi-context-assembly-v1"
TRUNCATE_SCHEMA = "chi-tool-truncation-v1"
RECORD_SCHEMA = "chi-tool-record-v1"
MAX_CODEPOINTS = 8192
MAX_BYTES = 32 * 1024
HEAD_CODEPOINTS = 4096
TAIL_CODEPOINTS = 1024


def canonical_sha(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _shrink_string(text, limit=2000):
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


def _shrink_json(value, *, max_items=10, max_string=2000, depth=0):
    if depth > 8:
        return _shrink_string(json.dumps(value, ensure_ascii=False), max_string)
    if type(value) is dict:
        result = {}
        for key, item in value.items():
            if type(item) is list and len(item) > max_items:
                kept = [_shrink_json(entry, max_items=max_items, max_string=max_string,
                                     depth=depth + 1) for entry in item[:max_items]]
                result[key] = kept
                result[key + "_total"] = len(item)
                result[key + "_omitted"] = len(item) - len(kept)
            else:
                result[key] = _shrink_json(item, max_items=max_items, max_string=max_string,
                                           depth=depth + 1)
        return result
    if type(value) is list:
        kept = [_shrink_json(entry, max_items=max_items, max_string=max_string,
                             depth=depth + 1) for entry in value[:max_items]]
        if len(value) > max_items:
            return {"items": kept, "total": len(value), "omitted": len(value) - len(kept)}
        return kept
    if type(value) is str:
        return _shrink_string(value, max_string)
    return value


def _json_truncate(text, *, tool=None, max_codepoints=MAX_CODEPOINTS, max_bytes=MAX_BYTES):
    parsed = _json_value(text)
    if parsed is None:
        return None
    for max_items, max_string in ((10, 2000), (5, 500), (3, 200)):
        shrunk = _shrink_json(parsed, max_items=max_items, max_string=max_string)
        rendered = json.dumps(shrunk, ensure_ascii=False, sort_keys=False, separators=(",", ":"),
                              allow_nan=False)
        if len(rendered) <= max_codepoints and len(rendered.encode("utf-8")) <= max_bytes:
            return rendered, {"schema": "chi-tool-json-truncation-v1", "truncated": True,
                              "tool": tool, "structured": True,
                              "original_chars": len(text),
                              "original_bytes": len(text.encode("utf-8")),
                              "note": "JSON kept valid; arrays/strings were shrunk"}
    fallback = {
        "schema": "chi-tool-result-truncated-v1",
        "truncated": True,
        "tool": tool,
        "structured": True,
        "original_chars": len(text),
        "original_bytes": len(text.encode("utf-8")),
        "preview": text[:4096],
        "note": "full JSON is in evidence; preview is bounded",
    }
    rendered = json.dumps(fallback, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return rendered, {"schema": "chi-tool-result-truncated-v1", "truncated": True,
                      "tool": tool, "structured": True,
                      "original_chars": len(text),
                      "original_bytes": len(text.encode("utf-8")),
                      "note": "structured fallback; full result is in evidence"}


def truncate_tool_text(text, *, tool=None, arguments=None,
                       max_codepoints=MAX_CODEPOINTS, max_bytes=MAX_BYTES,
                       head=HEAD_CODEPOINTS, tail=TAIL_CODEPOINTS):
    """Return (visible_text, metadata) for one tool result.

    JSON results are shrunk structurally so the visible text stays valid JSON;
    plain text keeps a stable head and tail plus a marker. The full text must be
    persisted before this function is called.
    """
    if type(text) is not str:
        raise ValueError("chi_assembly_text_invalid")
    raw = text.encode("utf-8")
    if len(text) <= max_codepoints and len(raw) <= max_bytes:
        return text, None
    structured = _json_truncate(text, tool=tool, max_codepoints=max_codepoints,
                                max_bytes=max_bytes)
    if structured is not None:
        return structured
    if head < 0 or tail < 0 or head + tail >= len(text):
        raise ValueError("chi_assembly_window_invalid")
    head_text = text[:head]
    tail_text = text[-tail:] if tail else ""
    marker = {
        "schema": TRUNCATE_SCHEMA,
        "truncated": True,
        "tool": tool,
        "original_chars": len(text),
        "original_bytes": len(raw),
        "visible_chars": head + tail,
        "next_offset": None,
        "offset_unit": ("lines for local-fs-read; tool-specific otherwise; "
                        "re-read with the original tool's offset/limit"),
        "note": "full result is in evidence; re-read with the normal tool/path",
    }
    visible = head_text + "\n\n[chi-truncated] " + json.dumps(
        marker, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n\n" + tail_text
    if len(visible.encode("utf-8")) > max_bytes or len(visible) > max_codepoints + 512:
        raise ValueError("chi_assembly_truncation_invalid")
    return visible, marker


def _json_value(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def key_ids_for(tool: str, arguments, result):
    """Derive stable business keys from program-visible args/result only."""
    keys = {}
    if type(tool) is not str or not tool:
        return keys
    args = arguments if type(arguments) is dict else {}
    value = _json_value(result) if type(result) is str else result
    result_id = {
        "docs.": "document_id",
        "cases.": "case_id",
        "auth.": "authorization_id",
        "forms.": "form_id",
        "payer_letter_center.": "letter_id",
        "p2p.": "request_id",
        "p2p_session.": "request_id",
        "review.": "review_id",
        "triage.": "triage_id",
        "determination.": "determination_id",
        "cm_assessment.": "assessment_id",
        "cm_care_plan.": "care_plan_id",
        "cm_outreach.": "call_id",
        "cm_intake.": "referral_id",
        "cm_chart.": "review_id",
        "payer_intake_hub.": "intake_case_id",
        "chart.": "patient_id",
    }
    id_key = next((name for prefix, name in result_id.items() if tool.startswith(prefix)), None)
    if tool in {"local-fs-write", "local-fs-edit"}:
        if type(args.get("path")) is str:
            keys["path"] = args["path"]
    elif tool == "local-confirm-patient":
        if type(args.get("patient_id")) is str:
            keys["patient_id"] = args["patient_id"]
    elif tool in {"cases.create_from_order"}:
        for name in ("order_id", "case_id"):
            if type(args.get(name)) is str:
                keys[name] = args[name]
    else:
        for name in ("case_id", "patient_id", "order_id", "request_id", "form_id",
                     "document_id", "bundle_id", "authorization_id", "letter_id",
                     "review_id", "triage_id", "determination_id", "intake_case_id",
                     "referral_id", "assessment_id", "care_plan_id", "call_id"):
            if type(args.get(name)) is str:
                keys[name] = args[name]
    if type(value) is dict:
        if id_key and type(value.get("id")) is str and id_key not in keys:
            keys[id_key] = value["id"]
        for name in ("id", "case_id", "patient_id", "order_id", "request_id", "form_id",
                     "document_id", "bundle_id", "authorization_id", "letter_id",
                     "review_id", "triage_id", "determination_id", "intake_case_id",
                     "referral_id", "assessment_id", "care_plan_id", "call_id"):
            if name not in keys and type(value.get(name)) is str:
                keys[name] = value[name]
    return keys


def canonical_record(call_id: str, tool: str, event: str, result: str, arguments=None) -> dict:
    """Build the program-owned record used instead of a model summary."""
    if type(call_id) is not str or not call_id or type(tool) is not str or not tool:
        raise ValueError("chi_assembly_record_invalid")
    if event not in {"returned", "returned_error", "refused", "failed"}:
        raise ValueError("chi_assembly_record_invalid")
    status = {"returned": "ok", "returned_error": "error",
              "refused": "refused", "failed": "unknown"}[event]
    return {
        "schema": RECORD_SCHEMA,
        "call_id": call_id,
        "tool": tool,
        "event": event,
        "status": status,
        "key_ids": key_ids_for(tool, arguments, result),
        "result_sha256": hashlib.sha256(result.encode("utf-8")).hexdigest(),
    }


def _selected_keys(tool: str):
    if tool.startswith("payer_intake_hub."):
        return {"id", "case_id", "status", "urgency", "received_at", "member_id"}
    if tool.startswith("triage."):
        return {"id", "case_id", "status", "urgency_level", "disposition", "sla_deadline"}
    if tool.startswith("review."):
        return {"id", "case_id", "line_number", "decision", "recommendation", "status"}
    if tool.startswith("cm_"):
        return {"id", "case_id", "status", "title", "updated_at"}
    if tool == "chart.list_candidate_orders":
        return {"id", "patient_id", "procedure_code", "description", "site_of_service", "status"}
    if tool.startswith("chart."):
        return {"id", "patient_id", "name", "dob", "status"}
    return None


def reduce_tool_result(tool: str, result: str, *, max_items: int = 10):
    """Conservatively reduce list payloads while preserving selection fields.

    Supports common list keys (``items``, ``result``, ``data``, ``records``,
    ``rows``). Unknown shapes are returned unchanged. The caller applies the
    8K/32KB bound afterwards, so this function never has to guess a byte budget.
    """
    value = _json_value(result)
    if type(value) is not dict:
        return result, None
    key = next((name for name in ("items", "result", "data", "records", "rows")
                if type(value.get(name)) is list), None)
    if key is None:
        return result, None
    items = value[key]
    if len(items) <= max_items:
        return result, None
    selected = _selected_keys(tool)
    kept = []
    for item in items[:max_items]:
        if type(item) is dict and selected is not None:
            kept.append({field: item[field] for field in item if field in selected})
        else:
            kept.append(item)
    reduced = dict(value)
    reduced[key] = kept
    reduced["total"] = len(items)
    reduced["omitted"] = len(items) - len(kept)
    return json.dumps(reduced, ensure_ascii=False, sort_keys=True, allow_nan=False), {
        "schema": SCHEMA,
        "reducer": "list_first_n_selected_fields",
        "tool": tool,
        "list_key": key,
        "total": len(items),
        "omitted": len(items) - len(kept),
    }


def _tool_message(message):
    return type(message) is dict and message.get("role") == "tool"


def project_messages(messages, *, records, events, canonical_tools, keep_recent_batches=2,
                     min_read_bytes=512, anchor=None, project_results=True):
    """Project older tool results into deterministic placeholders/records.

    ``messages`` is the complete source history validated by ToolContract. The
    returned messages keep the same assistant/tool_call_id structure; only tool
    contents change. The most recent batches stay complete. When ``anchor`` is
    provided, it is inserted as the second user message at index 2; the source
    history remains anchor-free. When ``project_results`` is false, only the
    anchor is injected and no old tool result is changed.
    """
    if type(messages) is not list or type(records) is not dict or type(events) is not dict:
        raise ValueError("chi_assembly_projection_invalid")
    if type(project_results) is not bool:
        raise ValueError("chi_assembly_projection_invalid")
    projected = json.loads(json.dumps(messages, ensure_ascii=False, allow_nan=False))
    anchor_sha = None
    if anchor is not None:
        if type(anchor) is not dict or type(anchor.get("text")) is not str \
                or type(anchor.get("sha256")) is not str:
            raise ValueError("chi_assembly_anchor_invalid")
        if len(projected) >= 2:
            projected.insert(2, {"role": "user", "content": anchor["text"]})
        anchor_sha = anchor["sha256"]
    batches = []
    index = 2
    while index < len(projected):
        message = projected[index]
        if type(message) is dict and message.get("role") == "assistant" and message.get("tool_calls"):
            ids = [call.get("id") for call in message["tool_calls"] if type(call) is dict]
            end = index + 1
            while end < len(projected) and _tool_message(projected[end]) \
                    and projected[end].get("tool_call_id") in ids:
                end += 1
            batches.append((index, end, ids))
            index = end
        else:
            index += 1
    keep_from = max(0, len(batches) - keep_recent_batches)
    seen = {}
    replaced = 0
    deduped = 0
    for batch_index, (start, end, ids) in enumerate(batches):
        if not project_results:
            break
        if batch_index >= keep_from:
            continue
        for position in range(start + 1, end):
            message = projected[position]
            call_id = message.get("tool_call_id")
            record = records.get(call_id)
            if type(record) is not dict or type(record.get("name")) is not str:
                continue
            tool = canonical_tools.get(record["name"], record["name"])
            result = record.get("result")
            if type(result) is not str:
                continue
            digest = hashlib.sha256(result.encode("utf-8")).hexdigest()
            event = events.get(call_id, "returned")
            try:
                effect = classify(tool)
            except ValueError:
                effect = "mutation"
            if effect == "read":
                if digest in seen:
                    reference = {
                        "schema": "chi-tool-result-ref-v1",
                        "call_id": call_id, "tool": tool, "result_sha256": digest,
                        "duplicate_of": seen[digest],
                        "note": "identical earlier result; re-read only if needed",
                    }
                    message["content"] = json.dumps(reference, ensure_ascii=False, sort_keys=True)
                    deduped += 1
                    replaced += 1
                    continue
                seen[digest] = call_id
                if len(result.encode("utf-8")) < min_read_bytes:
                    continue
                arguments = record.get("arguments") if type(record.get("arguments")) is dict else {}
                reference = {
                    "schema": "chi-tool-result-ref-v1",
                    "call_id": call_id, "tool": tool,
                    "path": arguments.get("path"),
                    "bytes": len(result.encode("utf-8")),
                    "result_sha256": digest,
                    "note": "old read result replaced in the wire view; re-read if needed",
                }
                message["content"] = json.dumps(reference, ensure_ascii=False, sort_keys=True)
                replaced += 1
            else:
                arguments = record.get("arguments") if type(record.get("arguments")) is dict else {}
                message["content"] = json.dumps(
                    canonical_record(call_id, tool, event, result, arguments),
                    ensure_ascii=False, sort_keys=True)
                replaced += 1
    source_bytes = len(json.dumps(messages, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"), allow_nan=False).encode("utf-8"))
    wire_bytes = len(json.dumps(projected, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode("utf-8"))
    return projected, {
        "schema": SCHEMA,
        "projection": "chi-context-projection-v1",
        "source_sha256": canonical_sha(messages),
        "projection_sha256": canonical_sha(projected),
        "source_bytes": source_bytes,
        "wire_bytes": wire_bytes,
        "saved_bytes": source_bytes - wire_bytes,
        "replaced": replaced,
        "deduped": deduped,
        "keep_recent_batches": keep_recent_batches,
        "anchor_sha256": anchor_sha,
    }
