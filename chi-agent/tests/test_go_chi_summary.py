import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from go_chi_evidence import write_tool
from go_chi_journal import ChiJournal, inspect_history
from go_chi_recovery import canonical_sha
from go_chi_summary import (derive_view, protected_snapshot, select_closed, validate_candidate,
                            validate_source, verify_tool_actions)
from opencode_go_provider import GoFailure
from request_budget import feedback


class SummaryPrimitives(unittest.TestCase):
    def setUp(self):
        self.messages = [{'role': 'system', 'content': 'system' + feedback(3, False)[0]},
                         {'role': 'user', 'content': 'task'}]
        for index in range(3):
            self.messages.extend([
                {'role': 'assistant', 'content': None, 'tool_calls': [
                    {'id': f'call_{index}', 'type': 'function',
                     'function': {'name': 'read', 'arguments': '{}'}}]},
                {'role': 'tool', 'tool_call_id': f'call_{index}', 'content': f'result {index}'},
            ])
        self.selection = select_closed(self.messages)
        self.protected = {'schema': 'example'}
        self.candidate = {'schema': 'chi-summary-candidate-v1',
                          'selection_sha256': canonical_sha(self.selection),
                          'protected_sha256': canonical_sha(self.protected),
                          'goal': 'goal', 'current_work': 'work', 'next_steps': [],
                          'facts': [{'text': 'fact', 'sources': self.selection['sources']}],
                          'uncertainties': [], 'actions': [], 'gaps': []}

    def test_selection_binds_raw_tool_result_and_retains_two_batches(self):
        self.assertEqual(self.selection['end'], 4)
        self.assertEqual(self.selection['sources'][0]['result_sha256'],
                         hashlib.sha256(b'result 0').hexdigest())
        body = {'messages': self.messages}
        view = derive_view(body, used=3, claimed=False, selection=self.selection,
                           protected=self.protected, candidate=self.candidate,
                           candidate_protected_sha256=canonical_sha(self.protected), summary_was_sent=True)
        self.assertEqual(view['messages'][0]['content'], 'system' + feedback(4, False)[0])
        self.assertEqual(view['messages'][3:], self.messages[4:])
        self.assertEqual(body['messages'], self.messages)

    def test_candidate_rejects_duplicate_keys_and_unknown_reference(self):
        kwargs = {'selection_sha256': canonical_sha(self.selection),
                  'protected_sha256': canonical_sha(self.protected), 'sources': self.selection['sources']}
        with self.assertRaises(ValueError):
            validate_candidate('{"schema":1,"schema":2}', **kwargs)
        self.candidate['facts'][0]['sources'] = [{'call_id': 'bogus', 'result_sha256': '0' * 64}]
        with self.assertRaises(ValueError):
            validate_candidate(json.dumps(self.candidate), **kwargs)

    def test_reuse_keeps_fixed_prefix_with_updated_protection_and_feedback(self):
        self.messages[0]['content'] = 'system' + feedback(5, False)[0]
        self.messages.extend([
            {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'call_3', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'call_3', 'content': 'result 3'},
        ])
        view = derive_view({'messages': self.messages}, used=5, claimed=False,
                           selection=self.selection, protected={'schema': 'changed'},
                           candidate=self.candidate,
                           candidate_protected_sha256=canonical_sha(self.protected))
        self.assertEqual(view['messages'][0]['content'], 'system' + feedback(5, False)[0])
        self.assertEqual(view['messages'][3:], self.messages[4:])
        self.messages[3]['content'] = 'tampered'
        with self.assertRaises(ValueError):
            derive_view({'messages': self.messages}, used=5, claimed=False,
                        selection=self.selection, protected=self.protected,
                        candidate=self.candidate,
                        candidate_protected_sha256=canonical_sha(self.protected))

    def test_partial_and_unsupported_content_fail_closed(self):
        with self.assertRaises(ValueError):
            select_closed(self.messages[:-1])
        self.messages[3]['content'] = [{'type': 'text', 'text': 'result 0'}]
        with self.assertRaises(ValueError):
            select_closed(self.messages)

    def test_actions_bind_arguments_result_and_real_tool_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = write_tool(root, 'run', 'call_0', 'result 0', ())
            arguments = hashlib.sha256(b'{}').hexdigest()
            result = hashlib.sha256(b'result 0').hexdigest()
            events = [{'call_id': 'call_0', 'tool': 'cases.list_cases', 'event': 'started',
                       'arguments_sha256': arguments},
                      {'call_id': 'call_0', 'tool': 'cases.list_cases', 'event': 'returned',
                       'result_sha256': result, 'result_evidence_sha256': evidence}]
            records = [{'id': 'call_0', 'name': 'read', 'arguments': {}, 'result': 'result 0'}]
            mapping = {'read': 'cases.list_cases'}
            actions = verify_tool_actions(records, events, mapping, root=root, run='run')
            self.assertEqual(actions[0]['result_sha256'], result)
            records[0]['arguments'] = {'changed': True}
            with self.assertRaises(ValueError):
                verify_tool_actions(records, events, mapping, root=root, run='run')

    def test_launch_gating_and_legacy_field_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            common = dict(identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
            journal = ChiJournal(root, **common)
            self.assertNotIn('summary_events', journal.run)
            journal.finish('failed')
            journal.close()
            common.update(attempt='b', run='s')
            journal = ChiJournal(root, **common, launch={'input_summary': 'chi-input-summary-v1'})
            self.assertEqual(journal.run['summary_events'], [])
            journal.finish('failed')
            journal.close()
            common.update(attempt='c', run='t')
            with self.assertRaises(GoFailure):
                ChiJournal(root, **common, launch={'input_summary': 'chi-input-summary-v1',
                                                  'output_recovery': 'chi-output-recovery-v1'})

    def test_selection_is_anchored_in_prior_wires_and_tool_evidence(self):
        usage = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
                 'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}}
        tools = [{'type': 'function', 'function': {'name': 'read', 'description': 'Read.',
                  'strict': False, 'parameters': {'type': 'object', 'properties': {}}}}]
        mapping = {'read': 'cases.list_cases'}
        with tempfile.TemporaryDirectory() as temp:
            journal = ChiJournal(Path(temp), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                launch={'input_summary': 'chi-input-summary-v1', 'role': 'payer',
                        'instruction_sha256': hashlib.sha256(b'task').hexdigest()})
            history = [{'role': 'system', 'content': ''}, {'role': 'user', 'content': 'task'}]
            for index in range(3):
                history[0]['content'] = 'system' + feedback(index, False)[0]
                body = {'model': 'deepseek-v4.1-flash', 'messages': history, 'tools': tools,
                        'max_tokens': 8192, 'reasoning_effort': 'high', 'thinking': {'type': 'enabled'}}
                call = {'id': f'call_{index}', 'type': 'function',
                        'function': {'name': 'read', 'arguments': '{}'}}
                message = {'role': 'assistant', 'content': None, 'tool_calls': [call]}
                response = {'model': 'deepseek-v4.1-flash', 'choices': [
                    {'finish_reason': 'tool_calls', 'message': message}], 'usage': usage}
                journal.reserve(json.dumps(body).encode(), 'main')
                journal.record_response(json.dumps(response).encode(), 200, 1)
                journal.settle(usage)
                journal.record_diagnostic('ok', 1)
                result = ('x' * 5000) if index == 0 else f'result {index}'
                journal.start_tool(call['id'], 'cases.list_cases', {})
                journal.record_tool(call['id'], 'cases.list_cases', result)
                history.extend([message, {'role': 'tool', 'tool_call_id': call['id'], 'content': result}])
            history[0]['content'] = 'system' + feedback(3, False)[0]
            body = {'model': 'deepseek-v4.1-flash', 'messages': history, 'tools': tools,
                    'max_tokens': 8192, 'reasoning_effort': 'high', 'thinking': {'type': 'enabled'}}
            contract, _ = validate_source(root=journal.root, run=journal.run, body=body, used=3,
                                          claimed=False, canonical_tools=mapping)
            tampered = json.loads(json.dumps(body))
            tampered['messages'][0]['content'] = 'system' + feedback(3, True)[0]
            with self.assertRaises(ValueError):
                validate_source(root=journal.root, run=journal.run, body=tampered, used=3,
                                claimed=True, canonical_tools=mapping)
            protected = protected_snapshot(journal=journal, contract=contract, canonical_tools=mapping,
                                           role='payer', instruction='task', system='system',
                                           patient_binding=None, task_state=None)
            permit, summary = journal.select_summary(body, protected, mapping, source_raw=json.dumps(body).encode())
            self.assertEqual(permit, 0)
            self.assertNotIn('tools', summary)
            payload = json.loads(summary['messages'][1]['content'])
            self.assertEqual(payload['instruction'], 'task')
            journal.reserve(json.dumps(summary).encode(), 'summary', summary_permit=permit)
            self.assertEqual(journal.run['summary_events'][0]['summary_round'], 4)
            candidate = {'schema': 'chi-summary-candidate-v1', 'selection_sha256': payload['selection_sha256'],
                         'protected_sha256': payload['protected_sha256'], 'goal': 'goal', 'current_work': 'work',
                         'facts': [{'text': 'fact', 'sources': payload['sources']}],
                         'uncertainties': [], 'actions': [], 'gaps': [], 'next_steps': []}
            response = {'model': 'deepseek-v4.1-flash', 'choices': [{'finish_reason': 'stop', 'message': {
                'role': 'assistant', 'content': json.dumps(candidate)}}], 'usage': usage}
            journal.record_response(json.dumps(response).encode(), 200, 1)
            journal.settle(usage)
            journal.record_diagnostic('ok', 1)
            from go_chi_context import DEFAULT_BUDGET
            journal.install_summary(protected, context_limit=DEFAULT_BUDGET)
            projection, wire = journal.project_summary(body, json.dumps(body).encode(), protected,
                                                       source_used=3, context_limit=DEFAULT_BUDGET)
            journal.reserve(wire, 'main', summary_projection=projection)
            journal.close()
            accounting = Path(temp) / 'chi-accounting.json'
            before = accounting.read_bytes()
            inspected = inspect_history(Path(temp), 'a' * 64, hashlib.sha256(before).hexdigest())
            self.assertEqual(inspected['pending_request']['purpose'], 'main')
            self.assertEqual(accounting.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
