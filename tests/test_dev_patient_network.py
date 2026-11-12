"""Synthetic loopback MCP -> official CM service -> development broker."""
import asyncio
import importlib.util
import json
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn
from agents.models.openai_chatcompletions import Converter
from mcp.server.fastmcp import FastMCP

HAVE_ANTHROPIC = importlib.util.find_spec("anthropic") is not None
if HAVE_ANTHROPIC:
    from chi_bench.conversation.message import STOP_SIGNAL
    from chi_bench.conversation.session import ConversationSession
    from chi_bench.services.cm_outreach import CMOutreachService
    from scripts.development.patient_bootstrap import install
    from scripts.development.patient_broker import PatientBroker
else:
    STOP_SIGNAL = ConversationSession = CMOutreachService = None
    install = PatientBroker = None
from chi_agent.tool_contract import ToolContract
from chi_agent.journal import ChiJournal
from chi_agent.mcp_tools import MCPBridge, selected_server


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_network_chain():
    asyncio.run(_network_chain())


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_network_failure_rolls_back_and_blocks():
    asyncio.run(_network_chain(fail=True))


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_network_wait_exceeds_original_five_seconds():
    asyncio.run(_network_chain(delay=6))


async def _network_chain(fail=False, delay=0):
    now = datetime.now(timezone.utc)
    session = ConversationSession(session_id='synthetic-session', case_id='synthetic-case', patient_name='Fictional',
                                  reason_for_call='appointment', created_at=now)
    class Store:
        data = {('cm_conversation_sessions', 'synthetic-session'): session.model_dump(mode='json'),
                ('cm_cases', 'synthetic-case'): {'patient_id': 'fictional'},
                ('cm_manifests', 'synthetic-case'): {'outreach_scenario': {'reason_for_call': 'appointment'}}}
        def get_resource(self, side, typ, ident): return self.data.get((typ, ident))
        def save_resource(self, side, typ, ident, value): self.data[(typ, ident)] = value
    store = Store()
    service = CMOutreachService(SimpleNamespace(store=store, now=now, _require_loaded=lambda: None))
    service._persona_resolved = True
    service._persona_contract = SimpleNamespace(patient_profile='A fictional person scheduling an appointment.')
    mcp = FastMCP('synthetic', stateless_http=True)
    @mcp.tool(name='cm_outreach__send_message')
    async def send_message(session_id: str, message: str):
        return (await service.send_message(session_id, message)).model_dump(mode='json')
    def listen():
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(); sock.setblocking(False)
        return sock, sock.getsockname()[1]
    sockets = []; tasks = []; servers = []
    async def start(app):
        sock, port = listen(); sockets.append(sock)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False, lifespan='on'))
        servers.append(server); tasks.append(asyncio.create_task(server.serve(sockets=[sock])))
        for _ in range(100):
            if server.started: return port
            await asyncio.sleep(.01)
        raise RuntimeError('synthetic_server_start_failed')
    with tempfile.TemporaryDirectory() as d:
        journal = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                             launch={'role': 'cm', 'aux_contract': 'patient-simulator-v1'})
        calls = []
        async def answer(req):
            calls.append(req)
            if delay: await asyncio.sleep(delay)
            if fail: raise httpx.ReadTimeout('synthetic')
            return httpx.Response(200, request=req, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1,
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2, 'cost': 0,
                          'opencode': {'billing_source': 'go', 'list_cost': 0, 'allowance': 0}},
                'model': 'deepseek-v4.1-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': 'Goodbye ' + STOP_SIGNAL}}]})
        broker = PatientBroker(journal, 'synthetic-secret', 'c' * 32, asyncio.Lock(), lambda: httpx.MockTransport(answer))
        restore = None
        try:
            broker_port = await start(broker.app())
            restore = install(broker_url=f'http://127.0.0.1:{broker_port}/patient', capability='c' * 32, run_id='r')
            mcp_port = await start(mcp.streamable_http_app())
            async with selected_server(f'http://127.0.0.1:{mcp_port}/mcp', auxiliary=True) as server:
                bridge = MCPBridge(server, 'cm', await server.list_tools(), auxiliary=broker)
                bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]),
                                               journal=journal, secret='synthetic-secret', session='chi-' + 'f' * 32)
                args = json.dumps({'session_id': 'synthetic-session', 'message': 'Hello'})
                call = {'id': 'parent', 'type': 'function', 'function': {'name': 'cm_outreach__send_message', 'arguments': args}}
                bridge.guard.contract.accept_batch({'role': 'assistant', 'content': None, 'tool_calls': [call]})
                response = await asyncio.wait_for(bridge.invoke('cm_outreach__send_message', args), timeout=15)
                stored = store.data[('cm_conversation_sessions', 'synthetic-session')]
                assert len(calls) == 1
                if fail:
                    assert broker.fatal and journal.state['pending'] == {'run': 'r', 'round': 1}
                    assert stored['status'] == 'active' and stored['messages'] == []
                    assert 'error' in response.lower()
                else:
                    assert 'Goodbye' in response
                    assert stored['status'] == 'ended' and stored['termination_reason'] == 'patient_ended'
        finally:
            if restore: restore()
            await broker.close()
            for server in servers: server.should_exit = True
            await asyncio.gather(*tasks, return_exceptions=True)
            for sock in sockets: sock.close()
            journal.finish('failed'); journal.close()
