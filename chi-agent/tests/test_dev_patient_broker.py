import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest

from dev_patient_broker import PatientBroker
from go_chi_journal import ChiJournal


def test_broker_authorizes_parent_and_rejects_replay():
    asyncio.run(_broker())


async def _broker():
    with tempfile.TemporaryDirectory() as d:
        journal = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
            launch={'role': 'cm', 'aux_contract': 'patient-simulator-v1'})
        requests = []
        async def reply(req):
            requests.append(req)
            return httpx.Response(200, request=req, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1,
                'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
                          'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}},
                'model': 'deepseek-v4.1-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': 'hello'}}]})
        broker = PatientBroker(journal, 'synthetic-secret', 'c' * 32, asyncio.Lock(), lambda: httpx.MockTransport(reply))
        journal.start_tool('parent', 'cm_outreach.send_message', {'session_id': 'ses'})
        broker.begin('parent', 'cm_outreach.send_message', {'session_id': 'ses'})
        messages = [{'role': 'system', 'content': 'test'}, {'role': 'user', 'content': 'hi'}]
        with pytest.raises(ValueError): await broker.respond('wrong', 'r', 'ses', messages)
        with pytest.raises(ValueError): await broker.respond('c' * 32, 'r', 'other', messages)
        result = await broker.respond('c' * 32, 'r', 'ses', messages)
        assert result == {'content': 'hello', 'token_usage': 5}
        with pytest.raises(ValueError): await broker.respond('c' * 32, 'r', 'ses', messages)
        assert len(requests) == 1
        broker.end('parent')
        journal.record_tool('parent', 'cm_outreach.send_message', 'returned')
        await broker.close()
        journal.finish('failed'); journal.close()
        check = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='b', run='s')
        check.finish('failed'); check.close()


def test_bridge_callback_does_not_reenter_dispatch_lock():
    asyncio.run(_callback())


async def _callback():
    from types import SimpleNamespace
    from agents.models.openai_chatcompletions import Converter
    from go_chi_contract import ToolContract
    from go_chi_mcp import MCPBridge
    from mcp.types import CallToolResult, TextContent
    with tempfile.TemporaryDirectory() as d:
        journal = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
            launch={'role': 'cm', 'aux_contract': 'patient-simulator-v1'})
        async def reply(req):
            return httpx.Response(200, request=req, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1,
                'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
                          'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}},
                'model': 'deepseek-v4.1-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': 'hello'}}]})
        broker = PatientBroker(journal, 'synthetic-secret', 'c' * 32, asyncio.Lock(), lambda: httpx.MockTransport(reply))
        class Server:
            async def call_tool(self, name, args):
                result = await broker.respond('c' * 32, 'r', args['session_id'],
                    [{'role': 'system', 'content': 'test'}, {'role': 'user', 'content': 'hello'}])
                return CallToolResult(content=[TextContent(type='text', text=result['content'])], isError=False)
        schema = {'type': 'object', 'properties': {'session_id': {'type': 'string'}}, 'required': ['session_id'], 'additionalProperties': False}
        bridge = MCPBridge(Server(), 'cm', [SimpleNamespace(name='cm_outreach.send_message', description='', inputSchema=schema)], auxiliary=broker)
        bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]),
                                       journal=journal, secret='synthetic-secret', session='chi-' + 'f' * 32)
        call = {'id': 'parent', 'type': 'function', 'function': {'name': 'cm_outreach__send_message', 'arguments': '{"session_id":"ses"}'}}
        bridge.guard.contract.accept_batch({'role': 'assistant', 'content': None, 'tool_calls': [call]})
        assert 'hello' in await asyncio.wait_for(bridge.invoke('cm_outreach__send_message', '{"session_id":"ses"}'), timeout=2)
        assert journal.run['requests'][0]['parent_call_id'] == 'parent'
        await broker.close(); journal.finish('failed'); journal.close()


def test_concurrent_broker_call_refused_before_dispatch():
    asyncio.run(_concurrent())


async def _concurrent():
    with tempfile.TemporaryDirectory() as d:
        journal = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                             launch={'role': 'cm', 'aux_contract': 'patient-simulator-v1'})
        arrived, release = asyncio.Event(), asyncio.Event()
        async def reply(req):
            arrived.set(); await release.wait()
            return httpx.Response(200, request=req, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1,
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2, 'cost': 0,
                          'opencode': {'billing_source': 'go', 'list_cost': 0, 'allowance': 0}},
                'model': 'deepseek-v4.1-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': 'hi'}}]})
        broker = PatientBroker(journal, 'synthetic-secret', 'c' * 32, asyncio.Lock(), lambda: httpx.MockTransport(reply))
        journal.start_tool('parent', 'cm_outreach.send_message', {'session_id': 'ses'})
        broker.begin('parent', 'cm_outreach.send_message', {'session_id': 'ses'})
        messages = [{'role': 'system', 'content': 'test'}, {'role': 'user', 'content': 'hi'}]
        first = asyncio.create_task(broker.respond('c' * 32, 'r', 'ses', messages))
        await arrived.wait()
        with pytest.raises(ValueError): await broker.respond('c' * 32, 'r', 'ses', messages)
        release.set(); await first
        assert len(journal.run['requests']) == 1
        broker.end('parent'); journal.record_tool('parent', 'cm_outreach.send_message', 'ok')
        await broker.close(); journal.finish('failed'); journal.close()
