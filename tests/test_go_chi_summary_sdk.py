import asyncio
import hashlib
import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from chi_agent.journal import ChiJournal, inspect_history
from chi_agent.runtime import run_chi
from test_go_chi_capabilities_runtime import Result, Server, completion


@pytest.mark.parametrize('version,summary_output,expected', [
    ('chi-input-summary-v1', 2, None),
    ('chi-input-summary-v1', 9000, 'chi_usage_over_limit'),
    ('chi-input-summary-v2', 9000, None),
    ('chi-input-summary-v2', 32768, None),
    ('chi-input-summary-v2', 32769, 'chi_usage_over_limit'),
])
def test_real_sdk_long_history_with_summary(tmp_path, version, summary_output, expected):
    (tmp_path / 'handbook').mkdir()
    (tmp_path / 'handbook' / 'policy.md').write_text('synthetic')
    (tmp_path / 'workspace' / 'CASE-A' / 'payer').mkdir(parents=True)
    instruction = tmp_path / 'instruction'
    instruction.write_text('Synthetic task')
    journal = ChiJournal(tmp_path / 'state', identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
        launch={'input_summary': version, 'role': 'payer',
                'instruction_sha256': hashlib.sha256(b'Synthetic task').hexdigest()})

    class LargeServer(Server):
        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            size = 6000
            return Result({'value': 'x' * size})

    server = LargeServer(('triage.get',))
    seen = []
    async def wire(request):
        body = json.loads(request.content)
        seen.append(body)
        if 'tools' not in body:
            source = json.loads(body['messages'][1]['content'])
            schema = source['output_schema']
            Draft202012Validator.check_schema(schema)
            assert schema['type'] == 'object' and schema['additionalProperties'] is False
            assert set(schema['required']) == {
                'schema', 'selection_sha256', 'protected_sha256', 'goal', 'facts',
                'uncertainties', 'actions', 'gaps', 'current_work', 'next_steps'}
            assert schema['properties']['facts']['minItems'] == 1
            assert schema['$defs']['statement']['additionalProperties'] is False
            assert schema['$defs']['reference']['additionalProperties'] is False

            def synthesize(node, key=None):
                if '$ref' in node:
                    return synthesize(schema['$defs'][node['$ref'].rsplit('/', 1)[1]], key)
                if 'const' in node:
                    return node['const']
                kind = node['type']
                if kind == 'object':
                    return {name: synthesize(node['properties'][name], name)
                            for name in node['required']}
                if kind == 'array':
                    return [synthesize(node['items'], key) for _ in range(node.get('minItems', 0))]
                if key in ('selection_sha256', 'protected_sha256'):
                    return source[key]
                if key in ('call_id', 'result_sha256'):
                    return source['sources'][0][key]
                return 'synthetic statement'

            candidate = synthesize(schema)
            Draft202012Validator(schema).validate(candidate)
            payload = completion(content=json.dumps(candidate))
            payload['usage']['completion_tokens'] = summary_output
            payload['usage']['total_tokens'] = payload['usage']['prompt_tokens'] + summary_output
        elif len(server.calls) < 4:
            payload = completion([(f'call_{len(server.calls)}', 'triage__get', {})])
        else:
            payload = completion()
        return httpx.Response(200, request=request, json=payload)
    budget = {'schema': 'chi-context-budget-v2', 'max_chars': 100000,
              'max_estimated_tokens': 50000, 'output_reserve_tokens': 8192, 'basis': 'synthetic'}
    async def run():
        return await run_chi(journal, 'synthetic-secret', role='payer', instruction='Synthetic task',
            mcp_url='http://synthetic.invalid/mcp', instruction_path=instruction, logs_dir=tmp_path / 'logs',
            workspace_root=tmp_path / 'workspace', handbook_root=tmp_path / 'handbook', tool_references=[],
            lower=httpx.MockTransport(wire), server_factory=lambda _: server, context_budget=budget)
    if expected:
        with pytest.raises(Exception, match=expected):
            asyncio.run(run())
        assert len(seen) == 4 and seen[3]['max_tokens'] == (8192 if version.endswith('v1') else 32768)
        assert journal.run['requests'][-1]['usage']['output_tokens'] == summary_output
        assert journal.state['pending'] is None
        assert journal.run['summary_events'][0]['status'] != 'installed'
        journal.finish('failed', expected)
        journal.close()
        raw = (tmp_path / 'state' / 'chi-accounting.json').read_bytes()
        assert inspect_history(tmp_path / 'state', 'a' * 64, hashlib.sha256(raw).hexdigest())['status'] == 'inspected'
        return
    result = asyncio.run(run())
    assert result == 'done'
    assert [item['purpose'] for item in journal.run['requests']] == ['main', 'main', 'main', 'summary', 'main', 'main']
    assert len(server.calls) == 4 and 'tools' not in seen[3]
    assert seen[3]['max_tokens'] == (8192 if version.endswith('v1') else 32768) and seen[3]['reasoning_effort'] == 'high'
    assert journal.run['requests'][3]['usage']['output_tokens'] == summary_output
    metrics = [json.loads(line) for line in (tmp_path / 'logs' / 'context.jsonl').read_text().splitlines()]
    summary_metric = next(m for m in metrics if m['purpose'] == 'summary')
    assert summary_metric['effective_output_reserve_tokens'] == (8192 if version.endswith('v1') else 32768)
    assert len([m for m in seen[4]['messages'] if m.get('role') == 'tool']) == 2
    assert len([m for m in seen[5]['messages'] if m.get('role') == 'tool']) == 3
    summary = json.loads((tmp_path / 'logs' / 'run_log.txt').read_text())
    assert summary['physical_requests']['summary'] == 1 and summary['logical_model_steps'] == 5
    journal.finish('complete')
    journal.close()
    raw = (tmp_path / 'state' / 'chi-accounting.json').read_bytes()
    assert inspect_history(tmp_path / 'state', 'a' * 64, hashlib.sha256(raw).hexdigest())['status'] == 'inspected'
