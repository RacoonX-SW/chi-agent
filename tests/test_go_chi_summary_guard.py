import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal, inspect_history
from request_budget import feedback

USAGE = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
         'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}}
TOOLS = [{'type': 'function', 'function': {'name': 'read', 'description': 'Read.', 'strict': False,
          'parameters': {'type': 'object', 'properties': {}}}}]
SECRET = 'synthetic-secret-value'
SESSION = 'chi-' + 'a' * 32


class SummaryGuardTest(unittest.TestCase):
    def test_projected_main_follows_one_summary_and_inspects(self):
        async def run(root, failure=None):
            journal = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                launch={'input_summary': 'chi-input-summary-v1', 'role': 'payer',
                        'instruction_sha256': hashlib.sha256(b'task').hexdigest()})
            sent = []
            async def respond(request):
                data = json.loads(request.content)
                sent.append(data)
                if 'tools' not in data:
                    if failure == 'cancel':
                        raise asyncio.CancelledError()
                    input_data = json.loads(data['messages'][1]['content'])
                    candidate = {'schema': 'chi-summary-candidate-v1',
                        'selection_sha256': input_data['selection_sha256'],
                        'protected_sha256': input_data['protected_sha256'], 'goal': 'goal', 'current_work': 'work',
                        'facts': [{'text': 'fact', 'sources': input_data['sources']}],
                        'uncertainties': [], 'actions': [], 'gaps': [], 'next_steps': []}
                    message = {'role': 'assistant', 'content': '{bad' if failure == 'invalid' else json.dumps(candidate)}
                    reason = 'stop'
                elif len(sent) <= 3:
                    call = {'id': f'call_{len(sent)}', 'type': 'function',
                            'function': {'name': 'read', 'arguments': '{}'}}
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [call]}
                    reason = 'tool_calls'
                else:
                    message = {'role': 'assistant', 'content': 'done'}
                    reason = 'stop'
                return httpx.Response(200, request=request, json={'model': 'deepseek-v4.1-flash',
                    'choices': [{'finish_reason': reason, 'message': message}], 'usage': USAGE})
            budget = {'schema': 'chi-context-budget-v2', 'max_chars': 100000,
                      'max_estimated_tokens': 25000, 'output_reserve_tokens': 8192,
                      'basis': 'synthetic'}
            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(respond), tools=TOOLS,
                system='system', instruction='task', claimed=lambda: False, confirmation=lambda: None,
                canonical_tools={'read': 'cases.list_cases'}, summary_snapshot=lambda: (None, None),
                context_limit=budget)
            history = [{'role': 'system', 'content': ''}, {'role': 'user', 'content': 'task'}]
            for index in range(4):
                history[0]['content'] = 'system' + feedback(index, False)[0]
                body = {'model': 'deepseek-v4.1-flash', 'messages': history, 'tools': TOOLS,
                        'max_tokens': 8192, 'reasoning_effort': 'high', 'thinking': {'type': 'enabled'}}
                request = httpx.Request('POST', 'https://opencode.ai/inference/go/openai/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + SECRET, 'User-Agent': 'chi-agent',
                             'X-OpenCode-Session': SESSION}, json=body)
                if index == 3 and failure:
                    expected = asyncio.CancelledError if failure == 'cancel' else Exception
                    with self.assertRaises(expected):
                        await guard.handle_async_request(request)
                    self.assertEqual(len(sent), 4)
                    self.assertEqual(guard.error, 'chi_cancelled' if failure == 'cancel' else 'chi_summary_invalid')
                    self.assertEqual(journal.run['summary_events'][0]['status'],
                                     'requested' if failure == 'cancel' else 'rejected')
                    self.assertEqual(journal.run['requests'][-1]['status'], 'pending' if failure == 'cancel' else 'settled')
                    journal.finish('failed', guard.error)
                    journal.close()
                    raw = (root / 'chi-accounting.json').read_bytes()
                    report = inspect_history(root, 'a' * 64, hashlib.sha256(raw).hexdigest())
                    self.assertEqual(report['input_summaries'][0]['status'],
                                     'requested' if failure == 'cancel' else 'rejected')
                    return
                response = await guard.handle_async_request(request)
                if index < 3:
                    message = response.json()['choices'][0]['message']
                    call_id = message['tool_calls'][0]['id']
                    result = 'x' * (9000 if index == 0 else 2000)
                    journal.start_tool(call_id, 'cases.list_cases', {})
                    guard.contract.record_result(call_id, result)
                    journal.record_tool(call_id, 'cases.list_cases', result)
                    history.extend([message, {'role': 'tool', 'tool_call_id': call_id, 'content': result}])
            self.assertEqual([item['purpose'] for item in journal.run['requests']],
                             ['main', 'main', 'main', 'summary', 'main'])
            self.assertNotIn('tools', sent[3])
            self.assertEqual(sent[4]['messages'][0]['content'], 'system' + feedback(4, False)[0])
            self.assertEqual(sent[4]['messages'][3:], history[4:])
            journal.finish('complete')
            journal.close()
            raw = (root / 'chi-accounting.json').read_bytes()
            self.assertEqual(inspect_history(root, 'a' * 64, hashlib.sha256(raw).hexdigest())['status'], 'inspected')
        for failure in (None, 'invalid', 'cancel'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                asyncio.run(run(Path(temp), failure))


if __name__ == '__main__':
    unittest.main()
