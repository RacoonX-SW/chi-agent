import asyncio
import json
from pathlib import Path

import httpx
import pytest

import opencode_go_provider as go


def run(root, name, responder):
    return asyncio.run(go._run_probe(root, name, 'synthetic-secret', lower=httpx.MockTransport(responder)))


def read(root, name):
    return json.loads((root / name).read_text())


def test_sdk_tool_cycle_and_separate_sessions(tmp_path):
    sessions = []
    for name in ('one', 'two'):
        responder = go._offline_responder()
        requests = []
        def capture(req):
            requests.append(req)
            return responder(req)
        result = run(tmp_path, name, capture)
        assert result['status'] == 'complete'
        assert len(requests) == 3
        assert all(r.headers['user-agent'] == 'chi-agent' for r in requests)
        assert all(str(r.url) == go.PROFILE['base_url'] + '/chat/completions' for r in requests)
        assert len({r.headers['x-opencode-session'] for r in requests}) == 1
        sessions.append(requests[0].headers['x-opencode-session'])
        record = read(tmp_path, f'runs/{name}.json')
        assert len(record['requests']) == 3
        assert len(record['tool_events']) == 2
        assert all(e['status'] == 'settled' for e in record['requests'])
    assert sessions[0] != sessions[1]
    state = read(tmp_path, 'accounting.json')
    assert state['pending'] is None and state['known_input_tokens'] == 60
    for path in tmp_path.rglob('*.json'):
        data = path.read_text()
        assert 'synthetic-secret' not in data
        assert all(session not in data for session in sessions)


@pytest.mark.parametrize('fault,expected', [('model', 'go_response_model_mismatch'), ('balance', 'billing_source_unexpected'), ('missing', 'billing_details_unknown')])
def test_known_usage_settled_before_refusal(tmp_path, fault, expected):
    responder = go._offline_responder()
    calls = []
    def reply(req):
        calls.append(1)
        data = json.loads(responder(req).read())
        if fault == 'model': data['model'] = 'unexpected'
        if fault == 'balance':
            data['usage']['opencode']['billing_source'] = 'balance'
            data['usage']['cost'] = 0.25
        if fault == 'missing': del data['usage']['opencode']['allowance']
        return httpx.Response(200, request=req, json=data)
    result = run(tmp_path, 'fault', reply)
    assert result['status'] == 'failed' and result['safe_error_code'] == expected
    assert len(calls) == 1
    state = read(tmp_path, 'accounting.json')
    assert state['pending'] is None and state['known_input_tokens'] == 10
    assert read(tmp_path, 'runs/fault.json')['requests'][0]['status'] == 'settled'
    if fault != 'model':
        assert state['halted'] == expected
        with pytest.raises(go.GoFailure): run(tmp_path, 'next', go._offline_responder())
    else:
        assert run(tmp_path, 'next', go._offline_responder())['status'] == 'complete'


@pytest.mark.parametrize('fault', ['usage', 'http', 'timeout', 'cancel'])
def test_unknown_usage_stops_all_followups(tmp_path, fault):
    calls = []
    responder = go._offline_responder()
    def reply(req):
        calls.append(1)
        if fault == 'http': return httpx.Response(429, request=req)
        if fault == 'timeout': raise httpx.ReadTimeout('synthetic')
        if fault == 'cancel': raise asyncio.CancelledError()
        data = json.loads(responder(req).read()); del data['usage']
        return httpx.Response(200, request=req, json=data)
    if fault == 'cancel':
        with pytest.raises(asyncio.CancelledError): run(tmp_path, 'fault', reply)
    else: assert run(tmp_path, 'fault', reply)['status'] == 'failed'
    assert len(calls) == 1
    state = read(tmp_path, 'accounting.json')
    assert state['pending']['status'] == 'unknown' and state['usage_complete'] is False
    entry = read(tmp_path, 'runs/fault.json')['requests'][0]
    assert 'request_body' in entry
    if fault == 'usage': assert 'response_body' in entry and 'response_sha256' in entry
    with pytest.raises(go.GoFailure): run(tmp_path, 'next', go._offline_responder())


def test_lock_duplicate_and_history_tamper(tmp_path):
    identity = go.source_identity()
    journal = go.GoJournal(tmp_path, 'locked', identity)
    with pytest.raises(go.GoFailure): go.GoJournal(tmp_path, 'other', identity)
    journal.finish('failed', 'synthetic', 0); journal.close()
    with pytest.raises(go.GoFailure): go.GoJournal(tmp_path, 'locked', identity)
    assert run(tmp_path, 'valid', go._offline_responder())['status'] == 'complete'
    state = read(tmp_path, 'accounting.json'); state['known_input_tokens'] = 0
    (tmp_path / 'accounting.json').write_text(json.dumps(state))
    with pytest.raises(go.GoFailure): go.GoJournal(tmp_path, 'tamper', identity)


def test_tracing_state_restored(tmp_path):
    from agents import set_tracing_disabled
    from agents.tracing import get_trace_provider
    provider = get_trace_provider()
    original = provider._manual_disabled
    try:
        set_tracing_disabled(False)
        assert run(tmp_path, 'tracing', go._offline_responder())['status'] == 'complete'
        assert provider._manual_disabled is False
    finally:
        set_tracing_disabled(original)


def test_wire_tampering_never_dispatches(tmp_path):
    captured = []
    original = go._offline_responder()
    def capture(req):
        captured.append(req)
        return original(req)
    assert run(tmp_path / 'source', 'source', capture)['status'] == 'complete'
    req = captured[0]
    body = json.loads(req.content)
    variants = []
    for field, value in [('model', 'other'), ('stream', True), ('max_tokens', 8192)]:
        changed = dict(body); changed[field] = value
        variants.append((str(req.url), dict(req.headers), changed))
    variants.append(('https://example.com/inference/go/openai/v1/chat/completions', dict(req.headers), body))
    headers = dict(req.headers); headers['user-agent'] = 'spoof'; variants.append((str(req.url), headers, body))
    journal = go.GoJournal(tmp_path / 'guard', 'guard', go.source_identity())
    calls = []
    session = req.headers['x-opencode-session']
    guard = go.GoGuard(journal, 'synthetic-secret', session, httpx.MockTransport(lambda request: calls.append(request)))
    try:
        for url, headers, content in variants:
            raw = json.dumps(content).encode()
            request = httpx.Request('POST', url, headers=headers, content=raw)
            with pytest.raises(go.GoFailure): guard._validate(request, raw)
        assert calls == [] and journal.state['pending'] is None
    finally:
        journal.finish('failed', 'synthetic', 0); journal.close()


def test_plan_preflight_are_read_only(tmp_path, monkeypatch):
    root = tmp_path / 'not-created'
    monkeypatch.setattr(go, 'DEFAULT_ROOT', root)
    monkeypatch.setenv('OPENCODE_API_KEY', 'synthetic-secret')
    assert go.plan()['credentials_read'] is False
    assert go.preflight()['ledger_status'] == 'not_initialized'
    assert not root.exists()


def test_crash_after_evidence_before_pending_clear_blocks_next(tmp_path, monkeypatch):
    identity = go.source_identity()
    journal = go.GoJournal(tmp_path, 'crash', identity)
    journal.reserve(1, b'synthetic')
    atomic = go._atomic
    def fail_state(path, data, **kwargs):
        if path == journal.state_path and data.get('pending') is None:
            raise OSError('synthetic failure')
        return atomic(path, data, **kwargs)
    monkeypatch.setattr(go, '_atomic', fail_state)
    with pytest.raises(OSError):
        journal.settle(10, 3, {'charged_usd': '0', 'list_cost_usd': '0.1', 'allowance_usd': '0.1', 'billing_source': 'go'}, None)
    journal.close()
    assert read(tmp_path, 'accounting.json')['pending'] is not None
    assert read(tmp_path, 'runs/crash.json')['requests'][0]['status'] == 'settled'
    with pytest.raises(go.GoFailure): go.GoJournal(tmp_path, 'next', identity)


def test_known_over_limit_usage_is_settled(tmp_path):
    responder = go._offline_responder()
    def reply(req):
        data = json.loads(responder(req).read())
        data['usage']['completion_tokens'] = go.PROFILE['max_output_tokens'] + 1
        data['usage']['total_tokens'] = data['usage']['prompt_tokens'] + data['usage']['completion_tokens']
        return httpx.Response(200, request=req, json=data)
    result = run(tmp_path, 'over-limit', reply)
    assert result['safe_error_code'] == 'go_usage_over_limit'
    state = read(tmp_path, 'accounting.json')
    assert state['pending'] is None and state['known_output_tokens'] == go.PROFILE['max_output_tokens'] + 1


def test_preflight_empty_root_and_orphan_history(tmp_path, monkeypatch):
    monkeypatch.setattr(go, 'DEFAULT_ROOT', tmp_path)
    assert go.preflight()['ledger_status'] == 'not_initialized'
    (tmp_path / '.lock').touch()
    assert go.preflight()['ledger_status'] == 'not_initialized'
    (tmp_path / 'orphan.json').write_text('{}')
    with pytest.raises(go.GoFailure): go.preflight()


def test_response_evidence_and_secret_refusal_after_settlement(tmp_path):
    responder = go._offline_responder()
    def reply(req):
        data = json.loads(responder(req).read())
        data['choices'][0]['message']['reasoning_content'] = 'synthetic-secret'
        data['usage']['prompt_tokens_details'] = {'cached_tokens': 0}
        return httpx.Response(200, request=req, json=data)
    result = run(tmp_path, 'secret', reply)
    assert result['safe_error_code'] == 'go_secret_in_body'
    state = read(tmp_path, 'accounting.json')
    assert state['pending'] is None and state['known_input_tokens'] == 10
    entry = read(tmp_path, 'runs/secret.json')['requests'][0]
    assert entry['response_redacted'] == 'secret_detected' and 'response_body' not in entry
    assert 'synthetic-secret' not in (tmp_path / 'runs/secret.json').read_text()


def test_estimated_billing_is_not_recorded_as_actual_charge(tmp_path):
    responder = go._offline_responder()
    def reply(req):
        data = json.loads(responder(req).read())
        data['usage']['opencode']['estimated'] = True
        data['usage']['cost'] = 0.7
        return httpx.Response(200, request=req, json=data)
    assert run(tmp_path, 'estimate', reply)['safe_error_code'] == 'billing_details_unknown'
    state = read(tmp_path, 'accounting.json')
    assert state['pending'] is None and state['charged_complete'] is False
    assert state['charged_usd_known'] == '0'
    assert read(tmp_path, 'runs/estimate.json')['requests'][0]['response_body']['usage']['opencode']['estimated'] is True


def test_empty_content_and_reasoning_through_real_sdk(tmp_path):
    responder = go._offline_responder()
    def reply(req):
        data = json.loads(responder(req).read())
        if data['choices'][0]['finish_reason'] == 'tool_calls':
            data['choices'][0]['message']['content'] = ''
            data['choices'][0]['message']['reasoning_content'] = ''
        return httpx.Response(200, request=req, json=data)
    assert run(tmp_path, 'empty', reply)['status'] == 'complete'
    record = read(tmp_path, 'runs/empty.json')
    assert record['requests'][0]['response_body']['choices'][0]['message']['content'] == ''
    assert record['requests'][1]['request_body']['messages'][2]['reasoning_content'] == ''
    assert record['final_output']


def test_wire_history_completeness_and_content_provenance(tmp_path):
    captured = []
    responder = go._offline_responder()
    def reply(req):
        captured.append(req)
        return responder(req)
    assert run(tmp_path / 'source', 'source', reply)['status'] == 'complete'
    req = captured[2]
    body = json.loads(req.content)
    journal = go.GoJournal(tmp_path / 'guard', 'guard', go.source_identity())
    guard = go.GoGuard(journal, 'synthetic-secret', req.headers['x-opencode-session'], httpx.MockTransport(lambda _: None))
    guard.call_records = {
        'inspect-1': {'name':'inspect_code', 'arguments':{}, 'reasoning_content':'synthetic', 'content':None, 'result':'def add(a, b):\n    return a - b\n'},
        'verify-1': {'name':'verify_patch', 'arguments':{'code':'def add(a, b):\n    return a + b\n'}, 'reasoning_content':'synthetic', 'content':None, 'result':'verification:pass'}}
    guard.inspection_call = 'inspect-1'
    guard._validate(req, req.content)
    import copy
    variants = []
    b = copy.deepcopy(body); del b['messages'][2:4]; variants.append(b)
    b = copy.deepcopy(body); b['messages'][2]['reasoning_content'] = 'forged'; variants.append(b)
    b = copy.deepcopy(body); b['messages'][2]['extra'] = 'forged'; variants.append(b)
    b = copy.deepcopy(body); b['messages'].extend(copy.deepcopy(b['messages'][2:4])); variants.append(b)
    b = copy.deepcopy(body); b['messages'][2:6] = b['messages'][4:6] + b['messages'][2:4]; variants.append(b)
    b = copy.deepcopy(body); b['tools'][0]['function']['description'] = 'forged'; variants.append(b)
    try:
        for b in variants:
            raw = json.dumps(b).encode()
            bad = httpx.Request('POST', str(req.url), headers=dict(req.headers), content=raw)
            with pytest.raises(go.GoFailure): guard._validate(bad, raw)
        assert journal.state['pending'] is None
    finally:
        journal.finish('failed', 'synthetic', 0); journal.close()
