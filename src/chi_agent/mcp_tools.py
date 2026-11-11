"""SDK MCP discovery and dispatch primitives for the Go CHI runner.

Callers must create a guard, install provider binding, and own persistence.
This module does not constitute a runnable or authorized entry point.
"""
from __future__ import annotations

import asyncio
import json
import re

from jsonschema import Draft202012Validator

from .opencode_go_provider import GoFailure
from .context_assembly import reduce_tool_result, truncate_tool_text
from .task_state import effect_for

CM_NAMES = {
    "cm_intake.list_referral_queue", "cm_intake.get_referral", "cm_intake.open_case", "cm_intake.disenroll_case",
    "cm_chart.get_chart_data", "cm_chart.submit_chart_review", "cm_outreach.start_outreach_call",
    "cm_outreach.send_message", "cm_outreach.get_transcript", "cm_outreach.end_outreach_call",
    "cm_assessment.start_assessment", "cm_assessment.save_section", "cm_assessment.complete_assessment",
    "cm_care_plan.create_draft", "cm_care_plan.save_care_plan", "cm_care_plan.finalize",
}


def selected_server(url: str, *, auxiliary=False):
    """Explicitly disable SDK retries for MCP reads and mutations alike."""
    import httpx
    from agents.mcp import MCPServerStreamableHttp
    def http_client(headers=None, timeout=None, auth=None):
        if auxiliary:
            timeout = httpx.Timeout(450, connect=10)
        return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth, trust_env=False,
                                 follow_redirects=False, transport=httpx.AsyncHTTPTransport(retries=0))
    params = {"url": url, "httpx_client_factory": http_client}
    options = {}
    if auxiliary:
        params.update(timeout=450, sse_read_timeout=450)
        options['client_session_timeout_seconds'] = 450
    return MCPServerStreamableHttp(name="chi_bench", params=params, cache_tools_list=True,
                                   max_retry_attempts=0, **options)


def role_allowlists():
    # This import uses the externally supplied pinned official source, never a bundled vendor tree.
    from chi_bench.mcp.catalog import provider_tool_names, payer_agent_tool_names
    return {"provider": set(provider_tool_names()), "payer": set(payer_agent_tool_names()), "cm": CM_NAMES}


class MCPBridge:
    def __init__(self, server, role, raw_tools, *, binding=None, auxiliary=None, state=None):
        from agents.tool import FunctionTool
        if role not in {"provider", "payer", "cm"} or (role == "provider" and binding is None):
            raise GoFailure("chi_mcp_role_invalid")
        self.server, self.role, self.binding, self.state = server, role, binding, state
        self.raw_names = {}
        self.tools = []
        self.guard = None
        self.auxiliary = auxiliary
        self.lock = asyncio.Lock()
        allowed = role_allowlists()
        names = set()
        for item in raw_tools:
            raw = getattr(item, "name", None)
            schema = getattr(item, "inputSchema", None)
            description = getattr(item, "description", None) or ""
            if type(raw) is not str or type(schema) is not dict or type(description) is not str:
                raise GoFailure("chi_mcp_schema_invalid")
            matching = {name for name in allowed[role]
                        if raw in {name, name.replace(".", "__"), name.replace(".", "_"), name.replace(".", "-")}}
            if len(matching) != 1:
                raise GoFailure("chi_mcp_role_mismatch")
            canonical = matching.pop()
            model_name = re.sub(r"[^a-zA-Z0-9_-]", "__", raw)
            if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", model_name)
                    or model_name in self.raw_names):
                raise GoFailure("chi_mcp_name_collision")
            try:
                Draft202012Validator.check_schema(schema)
            except Exception:
                raise GoFailure("chi_mcp_schema_invalid") from None
            self.raw_names[model_name] = (raw, canonical)
            names.add(canonical)
            if role == "provider":
                from .referral_field_guidance import append_description
                addition = append_description(canonical, description)
                if addition is not None:
                    description = addition[0]
            async def invoke(_context, payload, *, model_name=model_name):
                guard = self.guard
                call_id = getattr(_context, "tool_call_id", None)
                if guard is not None and type(call_id) is str:
                    reason = guard.contract.refusals.get(call_id)
                    if reason is not None:
                        record = next((item for item in guard.contract.records
                                       if item["id"] == call_id and item["result"] is None), None)
                        if record is None:
                            raise GoFailure("chi_mcp_call_unvalidated")
                        raw, canonical = self.raw_names[model_name]
                        result = "REFUSED: " + reason
                        guard.journal.refuse_tool(call_id, canonical, record["arguments"], result,
                                                  secrets=(guard.secret, guard.session))
                        guard.contract.record_result(call_id, result)
                        return result
                return await self.invoke(model_name, payload)
            self.tools.append(FunctionTool(name=model_name, description=description, params_json_schema=schema,
                                           on_invoke_tool=invoke, strict_json_schema=False))
        if not names or not names - set().union(*(allowed[r] for r in allowed if r != role)):
            raise GoFailure("chi_mcp_role_ambiguous")

    def batch(self, calls):
        """Precheck the full batch against the current provider binding."""
        if self.binding is None:
            return
        from .patient_identity_binding import Refusal
        for call in calls:
            mapped = self.raw_names.get(call["name"])
            if mapped is None:
                continue  # Trusted local tools have their own checks.
            try:
                self.binding.check(mapped[1], call["arguments"])
            except Refusal as exc:
                self.binding.batch_refusals[call["id"]] = str(exc)

    async def invoke(self, model_name, payload):
        if self.guard is None:
            raise GoFailure("chi_mcp_guard_missing")
        try:
            args = json.loads(payload)
        except Exception:
            raise GoFailure("chi_mcp_arguments_invalid") from None
        # Serialize dispatch so identical calls cannot race for a call ID and
        # provider relations are checked again immediately before any write.
        async with self.lock:
            fatal = getattr(self.guard, 'fatal_getter', lambda: None)()
            if fatal:
                raise GoFailure(fatal)
            pending = [r for r in self.guard.contract.records
                       if r["name"] == model_name and r["arguments"] == args and r["result"] is None]
            if not pending:
                raise GoFailure("chi_mcp_call_unvalidated")
            selected = pending[0]
            raw, canonical = self.raw_names[model_name]
            reason = self.guard.contract.refusals.get(selected["id"])
            if reason is not None:
                result = "REFUSED: " + reason
                self.guard.journal.refuse_tool(selected["id"], canonical, args, result,
                                               secrets=(self.guard.secret, self.guard.session))
                self.guard.contract.record_result(selected["id"], result)
                return result
            if self.binding is not None:
                from .patient_identity_binding import Refusal
                reason = self.binding.batch_refusals.get(selected["id"])
                if reason is None:
                    try:
                        self.binding.check(canonical, args)
                    except Refusal as exc:
                        reason = str(exc)
                if reason is not None:
                    result = "REFUSED: " + reason
                    self.guard.journal.refuse_tool(selected["id"], canonical, args, result,
                                                   secrets=(self.guard.secret, self.guard.session))
                    self.guard.contract.record_result(selected["id"], result)
                    return result
            warning = None
            if self.state is not None:
                drift = self.state.drift_check(canonical, "mcp", args)
                if drift is not None:
                    parts = drift.split(":")
                    severity = "hard" if parts[0] == "HARD" else "soft"
                    rule = parts[1]
                    count = int(parts[2]) if len(parts) > 2 else 1
                    self.state.drift_record(rule, selected["id"], severity,
                                            "stopped" if severity == "hard" else "refused")
                    self.guard.journal.record_drift(rule, selected["id"], count,
                                                    severity=severity,
                                                    outcome="stopped" if severity == "hard" else "refused")
                    if severity == "hard":
                        raise GoFailure("chi_drift_hard")
                    result = f"REFUSED: drift_{rule}:{count}"
                    self.guard.journal.refuse_tool(selected["id"], canonical, args, result,
                                                   secrets=(self.guard.secret, self.guard.session))
                    self.guard.contract.record_result(selected["id"], result)
                    return result
                stagnant = self.state.stagnation_block_reason(canonical, "mcp", args)
                if stagnant is not None:
                    result = "REFUSED: " + stagnant
                    self.guard.journal.refuse_tool(selected["id"], canonical, args, result,
                                                   secrets=(self.guard.secret, self.guard.session))
                    self.guard.contract.record_result(selected["id"], result)
                    return result
                blocked = self.state.block_mutation(canonical, "mcp", args)
                if blocked is not None:
                    result = "REFUSED: " + blocked
                    self.guard.journal.refuse_tool(selected["id"], canonical, args, result,
                                                   secrets=(self.guard.secret, self.guard.session))
                    self.guard.contract.record_result(selected["id"], result)
                    return result
                warning = self.state.stagnation_warning(canonical, "mcp", args)
            self.guard.journal.start_tool(selected["id"], canonical, args)
            try:
                if self.auxiliary is not None and canonical == 'cm_outreach.send_message':
                    self.auxiliary.begin(selected['id'], canonical, args)
                    try:
                        response = await self.server.call_tool(raw, args)
                    finally:
                        self.auxiliary.end(selected['id'])
                else:
                    response = await self.server.call_tool(raw, args)
                is_error = getattr(response, "isError", False)
                if type(is_error) is not bool:
                    raise GoFailure("chi_mcp_result_invalid")
                if is_error:
                    from mcp.types import CallToolResult, TextContent
                    if (not isinstance(response, CallToolResult) or type(response.content) is not list
                            or not response.content or not all(isinstance(item, TextContent)
                                                               and type(item.text) is str for item in response.content)):
                        raise GoFailure("chi_mcp_result_invalid")
                if self.binding is not None and not is_error:
                    self.binding.observe(selected["id"], canonical, args, response)
                value = response.model_dump(mode="json", exclude_none=True)
                content = getattr(response, "content", None)
                structured = getattr(response, "structuredContent", None)
                single_text = (type(content) is list and len(content) == 1
                               and getattr(content[0], "type", None) == "text"
                               and type(getattr(content[0], "text", None)) is str)
                if not is_error and single_text:
                    # The text block is the tool's primary result.  When the
                    # structured form carries the same payload, return the
                    # text once instead of also serializing structuredContent
                    # and the full model dump (which repeats it up to three
                    # times and can push the next request past the provider's
                    # latency budget).  binding.observe() already saw the raw
                    # response, so patient visibility checks keep structured
                    # content.  If the two forms differ, keep both.
                    result = content[0].text
                    if type(structured) is dict:
                        try:
                            same = json.loads(result) == structured
                        except Exception:
                            same = False
                        if not same:
                            result = result + "\n" + json.dumps(structured, ensure_ascii=False, allow_nan=False)
                elif not is_error and type(structured) is dict:
                    result = json.dumps(structured, ensure_ascii=False, allow_nan=False)
                else:
                    result = json.dumps(value, ensure_ascii=False, allow_nan=False)
                if warning:
                    result = result + "\n" + warning
                recorder = getattr(self.guard, "record_full_result", None)
                if callable(recorder):
                    recorder(selected["id"], result)
                reduced, _reducer = reduce_tool_result(canonical, result)
                visible, _truncation = truncate_tool_text(reduced, tool=canonical, arguments=args)
                self.guard.contract.record_result(selected["id"], visible)
                self.guard.journal.record_tool(selected["id"], canonical, result,
                                               event="returned_error" if is_error else "returned",
                                               secrets=(self.guard.secret, self.guard.session))
                if self.state is not None:
                    run_doc = getattr(self.guard.journal, "run", None)
                    rounds = len(run_doc.get("requests", [])) if isinstance(run_doc, dict) else 0
                    self.state.observe(call_id=selected["id"], tool=canonical, kind="mcp",
                                       arguments=args, result=result,
                                       event="returned_error" if is_error else "returned",
                                       round_number=rounds,
                                       scope=self.state.scope_for_arguments(args))
                return visible
            except BaseException as exc:
                code = ("chi_tool_cancelled" if isinstance(exc, asyncio.CancelledError) else
                        exc.code if isinstance(exc, GoFailure) else "chi_mcp_transport_error")
                fatal = None
                try:
                    getter = getattr(self.guard, "fatal_getter", None)
                    fatal = getter() if callable(getter) else None
                except Exception:
                    fatal = "chi_fatal_unknown"
                mutation_unknown = (self.state is not None
                                    and effect_for(canonical, "mcp") == "mutation"
                                    and not isinstance(exc, asyncio.CancelledError)
                                    and not fatal)
                result = ("UNKNOWN_WRITE_EFFECT: " + code) if mutation_unknown else code
                if mutation_unknown:
                    self.guard.contract.record_result(selected["id"], result)
                try:
                    self.guard.journal.record_tool(selected["id"], canonical, result, event="failed",
                                                   secrets=(self.guard.secret, self.guard.session))
                except Exception:
                    pass
                if self.state is not None:
                    try:
                        run_doc = getattr(self.guard.journal, "run", None)
                        rounds = len(run_doc.get("requests", [])) if isinstance(run_doc, dict) else 0
                        self.state.observe(call_id=selected["id"], tool=canonical, kind="mcp",
                                           arguments=args, result=result, event="failed",
                                           round_number=rounds,
                                           scope=self.state.scope_for_arguments(args))
                    except Exception:
                        pass
                if self.binding is not None:
                    self.binding.poisoned = True
                if mutation_unknown:
                    return result
                raise
