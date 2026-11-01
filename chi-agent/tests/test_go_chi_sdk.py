import tempfile
import unittest
from pathlib import Path

import httpx
from agents import Agent, ModelRetrySettings, ModelSettings, Runner, set_tracing_disabled
from agents.tool import FunctionTool
from agents.tracing import get_trace_provider
from agents.models.openai_chatcompletions import Converter, OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal
from go_chi_policy import TIME_POLICY
from model_runner_adapter import _patch_empty_history_compatibility
from opencode_go_provider import _same_route_reasoning
from request_budget import feedback


class SDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_b_continues_when_only_fee_details_missing(self):
        import json
        from opencode_go_provider import SYSTEM, INSTRUCTION, _offline_responder
        from go_chi_policy import FEE_POLICY
        from go_chi_runtime import coding_tools, run_coding_b
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity='a'*64, evaluation='e', task='synthetic', attempt='a', run='b',
                                 kind='coding_b', launch={'kind': 'coding_b', 'fee_policy': FEE_POLICY})
            holder = {}; tools = coding_tools(lambda: holder['guard']); original = _offline_responder(); requests = []
            def answer(request):
                requests.append(request)
                response = original(request); payload = json.loads(response.content)
                payload['usage'].pop('opencode', None); payload['usage'].pop('cost', None)
                return httpx.Response(200, request=request, json=payload)
            guard = ChiGuard(journal, 'synthetic-secret', 'chi-'+'a'*32, httpx.MockTransport(answer),
                tools=[Converter.tool_to_openai(t) for t in tools], system=SYSTEM, instruction=INSTRUCTION,
                claimed=lambda: False, confirmation=lambda: None)
            holder['guard'] = guard
            client = AsyncOpenAI(api_key='synthetic-secret', base_url='https://opencode.ai/inference/go/openai/v1',
                default_headers={'User-Agent': 'chi-agent', 'X-OpenCode-Session': 'chi-'+'a'*32},
                http_client=httpx.AsyncClient(transport=guard), max_retries=0)
            try:
                self.assertTrue(await run_coding_b(client, guard, tools))
                self.assertEqual(len(requests), 3); self.assertIsNone(journal.state['halted'])
                self.assertEqual(journal.usage_totals()['billing_details_warnings'], 3)
                self.assertFalse(journal.usage_totals()['billing_complete'])
                journal.finish('failed'); journal.close()
                again = ChiJournal(Path(directory), identity='a'*64, evaluation='e', task='other', attempt='b', run='next')
                again.finish('failed'); again.close()
            finally:
                await client.close(); journal.close()

    async def test_coding_tool_reasoning_variants_through_sdk(self):
        import json
        from opencode_go_provider import SYSTEM, INSTRUCTION
        from go_chi_runtime import coding_tools, run_coding_b
        for variant in ('absent', 'null', 'empty', 'text'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                journal = ChiJournal(Path(directory), identity='a' * 64, evaluation='e', task='synthetic', attempt='a', run='b', kind='coding_b')
                holder, requests, responses = {}, [], []
                tools = coding_tools(lambda: holder['guard'])
                async def answer(request):
                    requests.append(json.loads(request.content))
                    n = len(requests)
                    message = ({'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'inspect-1', 'type': 'function',
                        'function': {'name': 'inspect_code', 'arguments': '{}'}}]} if n == 1 else
                        {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'verify-1', 'type': 'function',
                        'function': {'name': 'verify_patch', 'arguments': json.dumps({'code': 'def add(a, b):\n    return a + b\n'})}}]} if n == 2 else
                        {'role': 'assistant', 'content': 'done'})
                    if n < 3 and variant != 'absent':
                        message['reasoning_content'] = {'null': None, 'empty': '', 'text': 'synthetic reasoning'}[variant]
                    payload = {'id': 'synthetic', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-v4.1-flash',
                        'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if n < 3 else 'stop'}],
                        'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
                                  'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}}}
                    responses.append(payload)
                    return httpx.Response(200, request=request, json=payload)
                guard = ChiGuard(journal, 'synthetic-secret', 'chi-' + 'a' * 32, httpx.MockTransport(answer),
                    tools=[Converter.tool_to_openai(t) for t in tools], system=SYSTEM, instruction=INSTRUCTION,
                    claimed=lambda: False, confirmation=lambda: None)
                holder['guard'] = guard
                client = AsyncOpenAI(api_key='synthetic-secret', base_url='https://opencode.ai/inference/go/openai/v1',
                    default_headers={'User-Agent': 'chi-agent', 'X-OpenCode-Session': 'chi-' + 'a' * 32},
                    http_client=httpx.AsyncClient(transport=guard), max_retries=0)
                try:
                    self.assertEqual(await run_coding_b(client, guard, tools), 'done')
                    self.assertEqual(len(requests), 3)
                    history = requests[1]['messages'][2]
                    self.assertEqual(history['content'], '')
                    if variant in ('absent', 'null'):
                        self.assertNotIn('reasoning_content', history)
                    else:
                        self.assertEqual(history['reasoning_content'], '' if variant == 'empty' else 'synthetic reasoning')
                    evidence = json.loads((Path(directory) / 'wire-evidence/b/001-response.json').read_text())
                    self.assertEqual(json.loads(evidence['body_utf8']), responses[0])
                    journal.finish('complete')
                finally:
                    await client.close(); journal.close()

    async def test_b_sdk_preserves_guard_error_for_bad_reasoning(self):
        from opencode_go_provider import SYSTEM, INSTRUCTION, GoFailure
        from go_chi_runtime import coding_tools, run_coding_b
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity='a' * 64, evaluation='e', task='synthetic', attempt='a', run='b', kind='coding_b')
            holder = {}; tools = coding_tools(lambda: holder['guard'])
            async def answer(request):
                return httpx.Response(200, request=request, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 0,
                    'model': 'deepseek-v4.1-flash', 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                        'role': 'assistant', 'content': '', 'reasoning_content': 17, 'tool_calls': [{'id': 'call', 'type': 'function',
                        'function': {'name': 'inspect_code', 'arguments': '{}'}}]}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
                              'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}}})
            guard = ChiGuard(journal, 'synthetic-secret', 'chi-' + 'a' * 32, httpx.MockTransport(answer),
                tools=[Converter.tool_to_openai(t) for t in tools], system=SYSTEM, instruction=INSTRUCTION,
                claimed=lambda: False, confirmation=lambda: None)
            holder['guard'] = guard
            client = AsyncOpenAI(api_key='synthetic-secret', base_url='https://opencode.ai/inference/go/openai/v1',
                default_headers={'User-Agent': 'chi-agent', 'X-OpenCode-Session': 'chi-' + 'a' * 32},
                http_client=httpx.AsyncClient(transport=guard), max_retries=0)
            try:
                with self.assertRaisesRegex(GoFailure, 'chi_tool_batch_invalid'):
                    await run_coding_b(client, guard, tools)
                self.assertEqual(guard.error, 'chi_tool_batch_invalid')
                self.assertEqual(journal.run['requests'][0]['status'], 'settled')
                self.assertEqual(journal.run['tool_events'], [])
                journal.finish('failed', guard.error)
            finally:
                await client.close(); journal.close()

    async def test_synthetic_sdk_tool_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_trace_state = get_trace_provider()._manual_disabled
            set_tracing_disabled(True)
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            holder = {}
            async def invoke(_context, _payload):
                holder["guard"].contract.record_result("call_1", "observed")
                return "observed"
            tool = FunctionTool(name="read", description="Read", params_json_schema={"type": "object", "properties": {}, "additionalProperties": False},
                                on_invoke_tool=invoke, strict_json_schema=False)
            tool_def = Converter.tool_to_openai(tool)
            calls = []
            async def respond(request):
                calls.append(request)
                msg = ({"role": "assistant", "content": None, "reasoning_content": "reason", "tool_calls":
                        [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}
                       if len(calls) == 1 else {"role": "assistant", "content": "done"})
                return httpx.Response(200, request=request, json={"id": "cmpl-test", "object": "chat.completion", "created": 0,
                    "model": "deepseek-v4.1-flash", "choices": [{"index": 0, "message": msg,
                    "finish_reason": "tool_calls" if len(calls) == 1 else "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                              "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}})
            guard = ChiGuard(journal, "synthetic-secret", "chi-" + "a" * 32, httpx.MockTransport(respond),
                             tools=[tool_def], system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            holder["guard"] = guard
            client = AsyncOpenAI(api_key="synthetic-secret", base_url="https://opencode.ai/inference/go/openai/v1",
                default_headers={"User-Agent": "chi-agent", "X-OpenCode-Session": "chi-" + "a" * 32},
                http_client=httpx.AsyncClient(transport=guard), max_retries=0)
            class BudgetModel(OpenAIChatCompletionsModel):
                async def get_response(self, system_instructions, *args, **kwargs):
                    return await super().get_response(system_instructions + feedback(len(journal.run["requests"]), False)[0], *args, **kwargs)
            old_message, old_history = _patch_empty_history_compatibility(Converter, "https://opencode.ai/inference/go/openai", "deepseek-v4.1-flash")
            try:
                model = BudgetModel(model="deepseek-v4.1-flash", openai_client=client, should_replay_reasoning_content=_same_route_reasoning)
                agent = Agent(name="test", instructions="system", model=model, tools=[tool], model_settings=ModelSettings(
                    max_tokens=8192, reasoning={"effort": "high"}, extra_body={"thinking": {"type": "enabled"}},
                    extra_headers={"User-Agent": "chi-agent"}, retry=ModelRetrySettings(max_retries=0)))
                result = await Runner.run(agent, "instruction", max_turns=50)
                self.assertEqual(result.final_output, "done")
                self.assertEqual(len(calls), 2)
                journal.finish("complete")
            finally:
                Converter.message_to_output_items = old_message
                Converter.items_to_messages = old_history
                await client.close()
                journal.close()
                set_tracing_disabled(previous_trace_state)

    async def test_coding_b_uses_go_chi_guard_and_sdk(self):
        from opencode_go_provider import INSTRUCTION, SYSTEM, SCHEMAS, DESCRIPTIONS, _offline_responder, _matches_patch
        with tempfile.TemporaryDirectory() as directory:
            previous_trace_state = get_trace_provider()._manual_disabled
            set_tracing_disabled(True)
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="synthetic", attempt="a", run="b", kind="coding_b")
            holder = {}
            def create_tool(name):
                async def invoke(_context, payload):
                    import json
                    args = json.loads(payload)
                    pending = [r for r in holder["guard"].contract.records if r["name"] == name and r["result"] is None]
                    if len(pending) != 1:
                        raise RuntimeError("unvalidated call")
                    answer = ("def add(a, b):\n    return a - b\n" if name == "inspect_code" else
                              "verification:pass" if _matches_patch(args["code"]) else "verification:fail")
                    holder["guard"].contract.record_result(pending[0]["id"], answer)
                    return answer
                return FunctionTool(name=name, description=DESCRIPTIONS[name], params_json_schema=SCHEMAS[name],
                                    on_invoke_tool=invoke, strict_json_schema=False)
            tools = [create_tool(name) for name in ("inspect_code", "verify_patch")]
            guard = ChiGuard(journal, "synthetic-secret", "chi-" + "a" * 32, httpx.MockTransport(_offline_responder()),
                             tools=[Converter.tool_to_openai(tool) for tool in tools], system=SYSTEM, instruction=INSTRUCTION,
                             claimed=lambda: False, confirmation=lambda: None)
            holder["guard"] = guard
            client = AsyncOpenAI(api_key="synthetic-secret", base_url="https://opencode.ai/inference/go/openai/v1",
                default_headers={"User-Agent": "chi-agent", "X-OpenCode-Session": "chi-" + "a" * 32},
                http_client=httpx.AsyncClient(transport=guard), max_retries=0)
            old_message, old_history = _patch_empty_history_compatibility(Converter, "https://opencode.ai/inference/go/openai", "deepseek-v4.1-flash")
            try:
                model = OpenAIChatCompletionsModel(model="deepseek-v4.1-flash", openai_client=client, should_replay_reasoning_content=_same_route_reasoning)
                agent = Agent(name="b", instructions=SYSTEM, model=model, tools=tools, model_settings=ModelSettings(
                    max_tokens=1024, reasoning={"effort": "high"}, extra_body={"thinking": {"type": "enabled"}},
                    extra_headers={"User-Agent": "chi-agent"}, retry=ModelRetrySettings(max_retries=0)))
                result = await Runner.run(agent, INSTRUCTION, max_turns=6)
                self.assertTrue(result.final_output)
                self.assertEqual(len(journal.run["requests"]), 3)
                journal.finish("complete")
            finally:
                Converter.message_to_output_items = old_message
                Converter.items_to_messages = old_history
                await client.close()
                journal.close()
                set_tracing_disabled(previous_trace_state)

    async def test_fixed_b_runtime(self):
        from opencode_go_provider import INSTRUCTION, SYSTEM, _offline_responder
        from go_chi_runtime import coding_tools, run_coding_b
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="synthetic", attempt="a", run="b", kind="coding_b")
            holder = {}
            tools = coding_tools(lambda: holder["guard"])
            lower = _offline_responder(); timeouts = []
            def answer(request):
                timeouts.append(dict(request.extensions['timeout']))
                return lower(request)
            guard = ChiGuard(journal, "synthetic-secret", "chi-" + "a" * 32, httpx.MockTransport(answer),
                             tools=[Converter.tool_to_openai(t) for t in tools], system=SYSTEM, instruction=INSTRUCTION,
                             claimed=lambda: False, confirmation=lambda: None)
            holder["guard"] = guard
            client = AsyncOpenAI(api_key="synthetic-secret", base_url="https://opencode.ai/inference/go/openai/v1",
                default_headers={"User-Agent": "chi-agent", "X-OpenCode-Session": "chi-" + "a" * 32},
                http_client=httpx.AsyncClient(transport=guard), max_retries=0)
            try:
                self.assertTrue(await run_coding_b(client, guard, tools))
                self.assertEqual(len(journal.run["requests"]), 3)
                self.assertEqual(timeouts, [{'connect': TIME_POLICY['connect_seconds'],
                    'read': TIME_POLICY['main_read_seconds'], 'write': TIME_POLICY['write_seconds'],
                    'pool': TIME_POLICY['pool_seconds']}] * 3)
                journal.finish("complete")
            finally:
                await client.close()
                journal.close()
