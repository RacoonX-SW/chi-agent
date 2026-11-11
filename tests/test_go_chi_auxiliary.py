import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest

from go_chi_auxiliary import AuxiliaryTransport
from go_chi_journal import ChiJournal
from opencode_go_provider import GoFailure

SECRET = 'synthetic-secret'
SESSION = 'chi-' + 'a' * 32
URL = 'https://opencode.ai/inference/go/openai/v1/chat/completions'
USAGE = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
         'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}}


def request():
    return httpx.Request('POST', URL, headers={'Authorization': 'Bearer ' + SECRET, 'User-Agent': 'chi-agent',
        'X-OpenCode-Session': SESSION}, json={'model': 'deepseek-v4.1-flash',
        'messages': [{'role': 'system', 'content': 'synthetic'}, {'role': 'user', 'content': 'hello'}],
        'max_tokens': 8192, 'reasoning_effort': 'high', 'thinking': {'type': 'enabled'}})


def test_probe_accounted_and_limit():
    asyncio.run(probe_accounted_and_limit())


async def probe_accounted_and_limit():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
        async def reply(req):
            return httpx.Response(200, request=req, json={'usage': USAGE, 'model': 'deepseek-v4.1-flash',
                'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'hello'}}]})
        transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(reply), asyncio.Lock(), lambda: None)
        for _ in range(2): await transport.handle_async_request(request())
        with pytest.raises(GoFailure, match='chi_aux_request_limit'): await transport.handle_async_request(request())
        assert len(j.run['requests']) == 2 and j.state['pending'] is None
        j.finish('failed'); j.close()
        check = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='b', run='s')
        check.finish('failed'); check.close()


def test_unknown_blocks_following_attempt():
    asyncio.run(unknown_blocks_following_attempt())


async def unknown_blocks_following_attempt():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
        async def reply(req): raise httpx.ReadTimeout('synthetic')
        transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(reply), asyncio.Lock(), lambda: None)
        with pytest.raises(GoFailure): await transport.handle_async_request(request())
        assert j.state['pending'] == {'run': 'r', 'round': 1}
        j.finish('failed'); j.close()
        with pytest.raises(GoFailure, match='chi_usage_unknown'):
            ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='b', run='s')


def test_nested_crash_remains_auditable_and_blocked():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       launch={'aux_contract': 'patient-simulator-v1', 'role': 'cm'})
        j.start_tool('call1', 'cm_outreach.send_message', {'session_id': 's'})
        j.reserve(b'{}', 'patient_simulator', parent_call_id='call1')
        j.close()
        with pytest.raises(GoFailure, match='chi_usage_unknown'):
            ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='b', run='s')


@pytest.mark.parametrize('mode', ['missing_fees', 'non_go', 'missing_usage', 'truncated'])
def test_auxiliary_billing_and_invalid_content(mode):
    asyncio.run(_billing_case(mode))


async def _billing_case(mode):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1', 'fee_policy': 'go-chi-record-incomplete-fees-v1'})
        usage = dict(USAGE)
        if mode == 'missing_fees': usage = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}
        if mode == 'non_go': usage['opencode'] = {'billing_source': 'non-go', 'list_cost': 0.1, 'allowance': 0.1}
        async def reply(req):
            payload = {'usage': usage, 'model': 'deepseek-v4.1-flash', 'choices': [{'finish_reason': 'length' if mode == 'truncated' else 'stop',
                       'message': {'role': 'assistant', 'content': 'hello'}}]}
            if mode == 'missing_usage': payload.pop('usage')
            return httpx.Response(200, request=req, json=payload)
        transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(reply), asyncio.Lock(), lambda: None)
        if mode == 'missing_fees':
            await transport.handle_async_request(request())
            assert j.state['pending'] is None and j.state['halted'] is None
            assert j.run['requests'][0]['billing']['charged_usd'] is None
        else:
            with pytest.raises(GoFailure): await transport.handle_async_request(request())
            if mode == 'missing_usage': assert j.state['pending'] is not None
            elif mode == 'non_go': assert j.state['halted'] == 'billing_source_unexpected'
            else: assert j.state['pending'] is None and j.run['requests'][0]['status'] == 'settled'
        j.finish('failed'); j.close()


def test_agent_and_auxiliary_limits_are_independent():
    import json
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       launch={'role': 'cm', 'aux_contract': 'patient-simulator-v1'})
        def settle(purpose, parent=None):
            j.reserve(b'{}', purpose, parent_call_id=parent)
            j.record_response(json.dumps({'usage': USAGE}).encode(), 200, 1)
            j.settle(USAGE); j.record_diagnostic('ok', 1)
        for _ in range(48): settle('main')
        settle('confirmation'); settle('confirmation')
        with pytest.raises(GoFailure, match='chi_request_limit'): j.reserve(b'{}', 'main')
        for index in range(10):
            call = f'call{index}'
            j.start_tool(call, 'cm_outreach.send_message', {'session_id': 's'})
            settle('patient_simulator', call)
            j.record_tool(call, 'cm_outreach.send_message', 'ok')
        j.start_tool('extra', 'cm_outreach.send_message', {'session_id': 's'})
        with pytest.raises(GoFailure, match='chi_aux_request_limit'):
            j.reserve(b'{}', 'patient_simulator', parent_call_id='extra')
        j.record_tool('extra', 'cm_outreach.send_message', 'refused')
        j.finish('failed'); j.close()
        check = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='b', run='s')
        check.finish('failed'); check.close()


def test_confirmation_limit_before_agent_limit():
    import json
    with tempfile.TemporaryDirectory() as d:
        j = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
        for _ in range(2):
            j.reserve(b'{}', 'confirmation'); j.record_response(json.dumps({'usage': USAGE}).encode(), 200, 1)
            j.settle(USAGE); j.record_diagnostic('ok', 1)
        with pytest.raises(GoFailure, match='chi_confirmation_limit'): j.reserve(b'{}', 'confirmation')
        j.finish('failed'); j.close()


def test_cancelled_auxiliary_keeps_pending():
    asyncio.run(_cancelled_auxiliary())


async def _cancelled_auxiliary():
    with tempfile.TemporaryDirectory() as d:
        j = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
        arrived = asyncio.Event()
        async def slow(_request):
            arrived.set(); await asyncio.Event().wait()
        transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(slow), asyncio.Lock(), lambda: None)
        task = asyncio.create_task(transport.handle_async_request(request()))
        await arrived.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert j.state['pending'] == {'run': 'r', 'round': 1} and transport.error == 'chi_aux_cancelled'
        j.finish('failed'); j.close()


def test_patient_context_budget_records_actual_wire_and_blocks_before_send():
    async def exercise():
        from go_chi_context import DEFAULT_BUDGET
        with tempfile.TemporaryDirectory() as d:
            j = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                           kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
            sent, metrics, wires = [], [], []
            async def reply(req):
                sent.append(req)
                return httpx.Response(200, request=req, json={'usage': USAGE, 'model': 'deepseek-v4.1-flash',
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'hello'}}]})
            transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(reply), asyncio.Lock(), lambda: None,
                context_recorder=lambda metric, purpose: metrics.append((metric, purpose)),
                wire_recorder=lambda item: wires.append(dict(item)))
            req = request()
            await transport.handle_async_request(req)
            assert metrics[0][1] == 'patient_simulator'
            assert metrics[0][0]['raw_bytes'] == len(req.content)
            assert metrics[0][0]['effective_output_reserve_tokens'] == 8192
            assert len(sent) == 1
            assert len(wires) == 1 and wires[0]['purpose'] == 'patient_simulator' and wires[0]['status'] == 'settled'
            blocked = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(reply), asyncio.Lock(), lambda: None,
                context_limit=dict(DEFAULT_BUDGET, max_estimated_tokens=8192))
            with pytest.raises(GoFailure, match='chi_context_budget_exceeded'):
                await blocked.handle_async_request(request())
            assert len(sent) == 1 and len(j.run['requests']) == 1
            j.finish('failed'); j.close()
    asyncio.run(exercise())


def test_patient_context_budget_accepts_v3_budget():
    async def exercise():
        from go_chi_context import DEFAULT_BUDGET_V3, budget_from_bytes
        with tempfile.TemporaryDirectory() as d:
            j = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                           kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
            sent = []
            async def reply(req):
                sent.append(req)
                return httpx.Response(200, request=req, json={'usage': USAGE, 'model': 'deepseek-v4.1-flash',
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'hello'}}]})
            transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(reply), asyncio.Lock(), lambda: None,
                context_limit=budget_from_bytes(1500000, DEFAULT_BUDGET_V3))
            await transport.handle_async_request(request())
            assert len(sent) == 1 and len(j.run['requests']) == 1
            j.finish('failed'); j.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["cancelled", "network", "unknown_usage", "invalid_response"])
def test_auxiliary_failures_keep_code_cause_and_diagnostic(mode):
    asyncio.run(_auxiliary_failure(mode))


async def _auxiliary_failure(mode):
    import json
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                       kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
        if mode == 'cancelled':
            async def lower(_request):
                raise asyncio.CancelledError()
        elif mode == 'network':
            async def lower(_request):
                raise httpx.ConnectError("synthetic")
        elif mode == 'unknown_usage':
            async def lower(req):
                return httpx.Response(200, request=req, json={'model': 'deepseek-v4.1-flash',
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'hi'}}]})
        else:
            async def lower(req):
                return httpx.Response(200, request=req, json={'usage': USAGE, 'model': 'deepseek-v4.1-flash',
                    'choices': [{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': 'hi'}}]})
        transport = AuxiliaryTransport(j, SECRET, SESSION, httpx.MockTransport(lower), asyncio.Lock(), lambda: None)
        expected = {'cancelled': 'chi_aux_cancelled', 'network': 'chi_aux_transport_error',
                    'unknown_usage': 'chi_usage_unknown', 'invalid_response': 'chi_aux_response_invalid'}[mode]
        with pytest.raises(BaseException):
            await transport.handle_async_request(request())
        assert transport.error == expected, transport.error
        doc = json.loads((root / 'wire-evidence/r/001-diagnostic.json').read_text())
        assert doc['schema'] == 'chi-go-diagnostic-v2'
        assert doc['code'] == expected
        assert doc['cause']['schema'] == 'chi-safe-cause-v1'
        if mode == 'cancelled':
            assert doc['cause'] == {'schema': 'chi-safe-cause-v1', 'stage': 'transport', 'reason': 'cancelled'}
        elif mode == 'network':
            assert doc['cause']['reason'] == 'request_error'
        elif mode == 'unknown_usage':
            assert doc['cause'] == {'schema': 'chi-safe-cause-v1', 'stage': 'usage', 'reason': 'unknown'}
        else:
            assert doc['cause'] == {'schema': 'chi-safe-cause-v1', 'stage': 'response', 'reason': 'shape_invalid'}
        entry = j.run['requests'][0]
        assert entry['status'] == ('settled' if mode == 'invalid_response' else 'pending')
        assert (j.state['pending'] is not None) == (mode != 'invalid_response')
        j.finish('failed', expected); j.close()
