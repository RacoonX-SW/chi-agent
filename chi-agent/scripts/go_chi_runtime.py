"""SDK execution helpers for Go CHI; caller owns all preflight and resources."""
from __future__ import annotations

import json

from opencode_go_provider import (GoFailure, SYSTEM as B_SYSTEM, INSTRUCTION as B_INSTRUCTION,
                                  SCHEMAS as B_SCHEMAS, DESCRIPTIONS as B_DESCRIPTIONS,
                                  _matches_patch, _same_route_reasoning)
from model_runner_adapter import _patch_empty_history_compatibility


def coding_tools(guard_getter):
    """Build the two fixed, synthetic coding tools used by the B contract."""
    from agents.tool import FunctionTool
    def tool(name):
        async def invoke(_context, payload):
            try:
                args = json.loads(payload)
                guard = guard_getter()
                pending = [record for record in guard.contract.records
                           if record["name"] == name and record["arguments"] == args and record["result"] is None]
                if len(pending) != 1:
                    raise ValueError
                guard.journal.start_tool(pending[0]["id"], name, args)
                if name == "inspect_code":
                    result = "def add(a, b):\n    return a - b\n"
                else:
                    result = "verification:pass" if _matches_patch(args["code"]) else "verification:fail"
                guard.contract.record_result(pending[0]["id"], result)
                guard.journal.record_tool(pending[0]["id"], name, result, secrets=(guard.secret, guard.session))
                return result
            except BaseException as exc:
                if "pending" in locals() and len(pending) == 1:
                    code = "chi_tool_cancelled" if isinstance(exc, __import__("asyncio").CancelledError) else "chi_b_dispatch_failed"
                    try: guard.journal.record_tool(pending[0]["id"], name, code, event="failed",
                                                   secrets=(guard.secret, guard.session))
                    except Exception: pass
                if isinstance(exc, __import__("asyncio").CancelledError):
                    raise
                raise GoFailure("chi_b_dispatch_invalid") from None
        return FunctionTool(name=name, description=B_DESCRIPTIONS[name], params_json_schema=B_SCHEMAS[name],
                            on_invoke_tool=invoke, strict_json_schema=False)
    return [tool("inspect_code"), tool("verify_patch")]


async def run_coding_b(client, guard, tools):
    """Run only the fixed coding probe through an already guarded client."""
    from agents import Agent, ModelSettings, ModelRetrySettings, Runner, set_tracing_disabled
    from agents.tracing import get_trace_provider
    from agents.models.openai_chatcompletions import Converter, OpenAIChatCompletionsModel
    if guard.journal.run["kind"] != "coding_b":
        raise GoFailure("chi_b_contract_invalid")
    prior_trace = get_trace_provider()._manual_disabled
    set_tracing_disabled(True)
    old = _patch_empty_history_compatibility(Converter, "https://opencode.ai/inference/go/openai", "deepseek-v4.1-flash")
    try:
        model = OpenAIChatCompletionsModel(model="deepseek-v4.1-flash", openai_client=client,
                                           should_replay_reasoning_content=_same_route_reasoning)
        agent = Agent(name="chi-go-coding-b", instructions=B_SYSTEM, model=model, tools=tools,
                      model_settings=ModelSettings(max_tokens=1024, reasoning={"effort": "high"},
                          extra_body={"thinking": {"type": "enabled"}}, extra_headers={"User-Agent": "chi-agent"},
                          retry=ModelRetrySettings(max_retries=0)))
        try:
            result = await Runner.run(agent, input=B_INSTRUCTION, max_turns=6)
        except Exception:
            if guard.error is not None:
                raise GoFailure(guard.error) from None
            raise
        if guard.error is not None or not isinstance(result.final_output, str) or not result.final_output.strip():
            raise GoFailure(guard.error or "chi_b_incomplete")
        if len(guard.contract.records) != 2 or guard.contract.records[-1]["result"] != "verification:pass":
            raise GoFailure("chi_b_incomplete")
        return result.final_output
    finally:
        Converter.message_to_output_items, Converter.items_to_messages = old
        set_tracing_disabled(prior_trace)


async def run_chi(journal, secret, *, role, instruction, mcp_url, instruction_path,
                  logs_dir, workspace_root, handbook_root, tool_references, lower,
                  server_factory=None, auxiliary=None, evidence_shadow=None):
    """Run one role using a previously preflighted journal and injected transport.

    No authorization or bundle/source verification is performed here. The
    caller must perform those checks before constructing a live transport.
    """
    import contextvars
    import re
    import uuid
    import time
    import httpx
    from openai import AsyncOpenAI
    from agents import Agent, ModelSettings, ModelRetrySettings, Runner, set_tracing_disabled
    from agents.tracing import get_trace_provider
    from agents.models.openai_chatcompletions import Converter, OpenAIChatCompletionsModel
    from chi_bench.experiment.agents import openai_agents_runner as official
    from go_chi_guard import ChiGuard
    from go_chi_mcp import MCPBridge, selected_server
    from go_chi_resources import workspace_path
    from go_chi_tools import local_tools
    from patient_identity_binding import PatientBinding
    from request_budget import feedback

    if journal.run["kind"] != "chi" or role not in {"provider", "payer", "cm"}:
        raise GoFailure("chi_run_contract_invalid")
    if auxiliary is not None and (role != 'cm' or auxiliary.journal is not journal
            or journal.run['launch'].get('aux_contract') != 'patient-simulator-v1'):
        raise GoFailure('chi_run_contract_invalid')
    if not isinstance(secret, str) or not secret.strip() or not isinstance(instruction, str) or not instruction.strip():
        raise GoFailure("chi_run_input_invalid")
    if evidence_shadow not in {None, "off", "shadow"}:
        raise GoFailure("chi_evidence_shadow_invalid")
    if evidence_shadow == "off":
        evidence_shadow = None
    if evidence_shadow == "shadow" and role != "payer":
        raise GoFailure("chi_evidence_shadow_role_invalid")
    if lower is None:
        raise GoFailure("chi_transport_missing")
    logs_dir = __import__("pathlib").Path(logs_dir)
    logs_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    run_started = time.monotonic()
    context = contextvars.ContextVar("chi_confirmation", default=None)
    holder, exchanges = {}, []
    binding = PatientBinding(instruction, journal) if role == "provider" else None
    factory = server_factory or (lambda url: selected_server(url, auxiliary=auxiliary is not None))
    prior_trace = get_trace_provider()._manual_disabled
    set_tracing_disabled(True)
    old = _patch_empty_history_compatibility(Converter, "https://opencode.ai/inference/go/openai", "deepseek-v4.1-flash")
    client = None
    run_result, failure = None, None
    try:
        async with factory(mcp_url) as server:
            raw_tools = await server.list_tools()
            bridge = MCPBridge(server, role, raw_tools, binding=binding, auxiliary=auxiliary)
            local = local_tools(role=role, workspace_root=workspace_root, instruction_path=instruction_path,
                                tool_references=tool_references, handbook_root=handbook_root,
                                journal=journal, binding=binding, guard_getter=lambda: holder.get("guard"),
                                client_getter=lambda: holder.get("client"), confirmation_context=context,
                                exchanges=exchanges, dispatch_lock=bridge.lock, instruction=instruction,
                                evidence_shadow=evidence_shadow)
            tools = bridge.tools + local
            definitions = [Converter.tool_to_openai(tool) for tool in tools]
            if len({tool.name for tool in tools}) != len(tools):
                raise GoFailure("chi_tool_name_collision")

            def before_batch(calls):
                if any(call["name"] == "local-confirm-patient" for call in calls) and len(calls) != 1:
                    for call in calls:
                        holder["guard"].contract.refusals[call["id"]] = "confirmation_must_be_called_alone"
                    return
                bridge.batch(calls)
                if binding is not None:
                    for call in calls:
                        if call["name"] not in {"local-fs-write", "local-fs-edit"}:
                            continue
                        path = workspace_path(workspace_root, call["arguments"].get("path"), role)
                        if (path is None or binding.bound is None or binding.poisoned
                                or binding.cases.get(path.relative_to(workspace_root).parts[0]) != binding.bound):
                            binding.batch_refusals[call["id"]] = "workspace_case_unverified"

            def observed_request(messages, used):
                by_id = {}
                for message in messages[2:]:
                    if message.get("role") == "assistant":
                        for call in message.get("tool_calls", []):
                            by_id[call["id"]] = call["function"]
                    elif message.get("role") == "tool":
                        call_id = message["tool_call_id"]
                        fn, content = by_id[call_id], message["content"]
                        if isinstance(content, list):
                            content = "".join(part["text"] for part in content)
                        if not any(item["call_id"] == call_id for item in exchanges):
                            exchanges.append({"call_id": call_id, "tool": fn["name"], "arguments": fn["arguments"],
                                              "result": content, "observed_at_request_round": used})

            session = "chi-" + uuid.uuid4().hex
            guard = ChiGuard(journal, secret, session, lower, tools=definitions, system=official.SYSTEM_PROMPT,
                             instruction=instruction, claimed=lambda: journal.run["claim_done"],
                             confirmation=context.get, before_batch=before_batch, observed_request=observed_request,
                             run_started=run_started, billing_lock=auxiliary.billing_lock if auxiliary else None,
                             fatal_getter=(lambda: auxiliary.fatal) if auxiliary else None)
            holder["guard"] = guard
            bridge.guard = guard
            client = AsyncOpenAI(api_key=secret, base_url="https://opencode.ai/inference/go/openai/v1",
                default_headers={"User-Agent": "chi-agent", "X-OpenCode-Session": session}, max_retries=0,
                http_client=httpx.AsyncClient(transport=guard, trust_env=False, follow_redirects=False,
                                              timeout=httpx.Timeout(60.0, connect=10.0)))
            holder["client"] = client
            class BudgetModel(OpenAIChatCompletionsModel):
                async def get_response(self, system_instructions, *args, **kwargs):
                    if system_instructions != official.SYSTEM_PROMPT:
                        raise GoFailure("chi_system_prompt_invalid")
                    try:
                        suffix = feedback(sum(item['purpose'] != 'patient_simulator' for item in journal.run['requests']), journal.run["claim_done"])[0]
                    except ValueError:
                        raise GoFailure("chi_request_limit") from None
                    return await super().get_response(system_instructions + suffix, *args, **kwargs)
            model = BudgetModel(model="deepseek-v4.1-flash", openai_client=client,
                                should_replay_reasoning_content=_same_route_reasoning)
            agent = Agent(name="chi-go-evaluation", instructions=official.SYSTEM_PROMPT, model=model, tools=tools,
                          model_settings=ModelSettings(max_tokens=8192, reasoning={"effort": "high"},
                              extra_body={"thinking": {"type": "enabled"}}, extra_headers={"User-Agent": "chi-agent"},
                              retry=ModelRetrySettings(max_retries=0)))
            run_result = await Runner.run(agent, input=instruction, max_turns=50)
            if guard.error is not None or (auxiliary and auxiliary.fatal) or not isinstance(run_result.final_output, str) or not run_result.final_output.strip():
                raise GoFailure(guard.error or (auxiliary.fatal if auxiliary else None) or "chi_final_missing")
    except BaseException as exc:
        failure = getattr(locals().get("guard"), "error", None) or (auxiliary.fatal if auxiliary else None) or (exc.code if isinstance(exc, GoFailure) else "chi_runner_failed")
        if isinstance(exc, __import__("asyncio").CancelledError):
            raise
    finally:
        Converter.message_to_output_items, Converter.items_to_messages = old
        set_tracing_disabled(prior_trace)
        if client is not None:
            try:
                await client.close()
            except Exception:
                failure = failure or "chi_cleanup_failed"
        try:
            agent_requests = [item for item in journal.run['requests'] if item['purpose'] != 'patient_simulator']
            settled = [item for item in agent_requests if item["status"] == "settled"]
            input_tokens = sum(item["usage"]["input_tokens"] for item in settled)
            output_tokens = sum(item["usage"]["output_tokens"] for item in settled)
            output = run_result.final_output if run_result is not None and failure is None else None
            official.write_result(logs_dir=logs_dir, input_tokens=input_tokens,
                                  output_tokens=output_tokens, cached_tokens=None, cost_usd=None,
                                  turns=len(agent_requests), final_output=output,
                                  model="deepseek-v4.1-flash", error=failure)
            if output:
                (logs_dir / "run_output.txt").write_text(output, encoding="utf-8")
            if run_result is not None:
                official._dump_trace(trace_path=logs_dir / "trace.jsonl", instruction=instruction,
                                     system_prompt=official.SYSTEM_PROMPT, result=run_result,
                                     model="deepseek-v4.1-flash")
        except Exception:
            failure = failure or "chi_log_persistence_failed"
        try:
            summary = {"status": "incomplete" if failure else "complete", "safe_error_code": failure,
                       "provider_requests": len(agent_requests),
                       "tool_events": len(journal.run["tool_events"]),
                       "elapsed_ms": int((time.monotonic() - run_started) * 1000), "official_reward": None}
            if auxiliary is not None:
                aux = [item for item in journal.run['requests'] if item['purpose'] == 'patient_simulator']
                summary['patient_simulator_requests'] = len(aux)
                summary['patient_simulator_input_tokens_known'] = sum(item['usage']['input_tokens'] for item in aux if item['status'] == 'settled')
                summary['patient_simulator_output_tokens_known'] = sum(item['usage']['output_tokens'] for item in aux if item['status'] == 'settled')
            (logs_dir / "run_log.txt").write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
        except Exception:
            failure = failure or "chi_log_persistence_failed"
    if failure is not None:
        raise GoFailure(failure)
    return run_result.final_output
