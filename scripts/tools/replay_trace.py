"""Offline synthetic execution replay; never constructs a live transport."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import re
import sys
from pathlib import Path
from types import SimpleNamespace
import httpx
from chi_agent.accounting.journal import ChiJournal
import chi_agent.agent.runtime as runtime
run_chi = runtime.run_chi
ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'chi-trace-replay-v1'

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError('nonfinite_json_number')


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('nonfinite_json_number')
    return number


def parse_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=reject_constant, parse_float=finite_float)


def json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right


def load_suite(path):
    raw = Path(path).read_bytes()
    suite = parse_json(raw)
    if (not isinstance(suite, dict) or set(suite) != {'version', 'cases'}
            or type(suite['version']) is not int or suite['version'] != 1
            or not isinstance(suite['cases'], list) or not suite['cases']):
        raise ValueError('invalid_suite')
    ids = set()
    for case in suite['cases']:
        required = {'id', 'role', 'options', 'tools', 'events', 'assertions'}
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError('invalid_case')
        case_id = case['id']
        if not isinstance(case_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', case_id) or case_id in ids:
            raise ValueError('invalid_case_id')
        ids.add(case_id)
        tools = case['tools']
        if (case['role'] != 'payer' or not isinstance(case['options'], dict)
                or not isinstance(tools, list) or not tools
                or not all(isinstance(x, str) and x for x in tools)
                or len(tools) != len(set(tools))
                or not isinstance(case['events'], list) or not case['events']
                or not isinstance(case['assertions'], dict) or not case['assertions']
                or not all(isinstance(k, str) and k for k in case['assertions'])):
            raise ValueError('invalid_case')
        options = case['options']
        if (set(options) - {'context_policy', 'output_recovery'}
                or options.get('context_policy') not in (None, 'chi-context-v3')
                or options.get('output_recovery') not in (None, 'chi-output-recovery-v1')):
            raise ValueError('invalid_options')
        for event in case['events']:
            if not isinstance(event, dict) or event.get('type') not in ('model', 'mcp'):
                raise ValueError('invalid_event')
            if event['type'] == 'mcp':
                if (set(event) != {'type', 'tool', 'arguments', 'result'}
                        or event['tool'] not in tools or not isinstance(event['arguments'], dict)
                        or event['result'] not in ('ok', 'timeout')):
                    raise ValueError('invalid_mcp_event')
                continue
            if (set(event) != {'type', 'purpose', 'accepted_ids', 'no_tool_calls', 'response'}
                    or event['purpose'] not in ('main', 'continuation')
                    or not isinstance(event['accepted_ids'], list)
                    or not all(isinstance(x, str) and x for x in event['accepted_ids'])
                    or len(event['accepted_ids']) != len(set(event['accepted_ids']))
                    or type(event['no_tool_calls']) is not bool
                    or not isinstance(event['response'], dict)):
                raise ValueError('invalid_model_event')
            response = event['response']
            choices = response.get('choices')
            if (not isinstance(choices, list) or len(choices) != 1
                    or not isinstance(choices[0], dict)
                    or choices[0].get('finish_reason') not in ('stop', 'tool_calls', 'length')
                    or not isinstance(choices[0].get('message'), dict)
                    or not isinstance(response.get('usage'), dict)):
                raise ValueError('invalid_model_response')
            calls = choices[0]['message'].get('tool_calls', [])
            if not isinstance(calls, list):
                raise ValueError('invalid_tool_calls')
            for call in calls:
                if (not isinstance(call, dict) or not isinstance(call.get('id'), str)
                        or call.get('type') != 'function' or not isinstance(call.get('function'), dict)
                        or not isinstance(call['function'].get('name'), str)
                        or not isinstance(call['function'].get('arguments'), str)):
                    raise ValueError('invalid_tool_call')
    return suite, hashlib.sha256(raw).hexdigest()


def tree_hash(paths):
    h = hashlib.sha256()
    for path in sorted(paths):
        rel = path.relative_to(ROOT).as_posix().encode()
        content = path.read_bytes()
        h.update(len(rel).to_bytes(8, 'big'))
        h.update(rel)
        h.update(len(content).to_bytes(8, 'big'))
        h.update(content)
    return h.hexdigest()

def identity():
    if not Path(runtime.__file__).resolve().is_relative_to((ROOT / 'src/chi_agent').resolve()):
        raise ValueError('runtime_source_outside_snapshot')
    return {
        'source': tree_hash(list((ROOT / 'src/chi_agent').rglob('*.py'))),
        'evaluator': tree_hash([Path(__file__).resolve()]),
        'environment': {
            'python': sys.version.split()[0],
            **{name: importlib.metadata.version(name)
               for name in ('openai', 'openai-agents', 'mcp', 'httpx')},
        },
    }

class Alignment(Exception):
    pass

class Replay:

    def __init__(self, case):
        self.case = case
        self.index = 0
        self.first = None
        self.received = []
        self.events = []
        self.journal = None

    def mismatch(self, phase, reason):
        if self.first is None:
            self.first = {'step': self.index + 1, 'phase': phase, 'reason': reason}
        raise Alignment(reason)

    def next(self, phase):
        if self.first:
            raise Alignment('already_diverged')
        if self.index >= len(self.case['events']):
            self.mismatch(phase, 'unexpected_request')
        event = self.case['events'][self.index]
        if event['type'] != phase:
            self.mismatch(phase, 'unexpected_phase')
        return event

    async def wire(self, request):
        event = self.next('model')
        body = json.loads(request.content)
        purpose = self.journal.run['requests'][-1]['purpose']
        ids = [m.get('tool_call_id') for m in body.get('messages', []) if m.get('role') == 'tool']
        if (purpose != event['purpose'] or body.get('model') != 'deepseek-v4.1-flash'
                or not all(i in ids for i in event['accepted_ids'])):
            self.mismatch('model', 'request_mismatch')
        if event.get('no_tool_calls') and any((m.get('tool_calls') for m in body.get('messages', []))):
            self.mismatch('model', 'history_not_closed')
        self.index += 1
        self.events.append({'step': self.index, 'phase': 'model', 'purpose': purpose})
        response = copy_response(event['response'], self.workspace)
        return httpx.Response(200, request=request, json=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def list_tools(self):
        return [SimpleNamespace(name=n, description='Synthetic tool', inputSchema={'type': 'object', 'properties': {}, 'additionalProperties': True}) for n in self.case['tools']]

    async def call_tool(self, name, arguments):
        self.received.append({'tool': name, 'arguments': arguments})
        event = self.next('mcp')
        if name != event['tool'] or not json_equal(arguments, event['arguments']):
            self.mismatch('mcp', 'tool_or_arguments_mismatch')
        self.index += 1
        self.events.append({'step': self.index, 'phase': 'mcp', 'tool': name, 'result': event['result']})
        if event['result'] == 'timeout':
            raise TimeoutError('synthetic timeout')
        return Result()

def copy_response(response, workspace):
    response = json.loads(json.dumps(response))
    message = response['choices'][0]['message']
    for call in message.get('tool_calls', []):
        function = call['function']
        raw = function['arguments']
        if '$WORKSPACE' not in raw:
            continue
        try:
            arguments = parse_json(raw)
        except (ValueError, TypeError):
            continue
        function['arguments'] = json.dumps(substitute_workspace(arguments, workspace))
    return response

def substitute_workspace(value, workspace):
    if isinstance(value, str):
        return value.replace('$WORKSPACE', str(workspace))
    if isinstance(value, list):
        return [substitute_workspace(item, workspace) for item in value]
    if isinstance(value, dict):
        return {key: substitute_workspace(item, workspace) for (key, item) in value.items()}
    return value

class Result:
    isError = False
    structuredContent = {'case_id': 'CASE-A', 'status': 'nurse recommendation submitted'}
    content = []

    def model_dump(self, **kwargs):
        return {'structuredContent': self.structuredContent, 'content': [], 'isError': False}

def execute(case, directory, on_start=lambda : None):
    directory.mkdir()
    workspace = directory / 'workspace'
    (workspace / 'CASE-A/payer').mkdir(parents=True)
    (workspace / 'CASE-A/payer/input.txt').write_text('Synthetic case CASE-A')
    handbook = directory / 'handbook'
    handbook.mkdir()
    (handbook / 'policy.md').write_text('Synthetic policy')
    instruction = directory / 'instruction.txt'
    instruction.write_text('Synthetic payer task')
    replay = Replay(case)
    replay.workspace = workspace
    launch = {'role': 'payer', **case['options']}
    journal = ChiJournal(
        directory / 'state', identity='a' * 64, evaluation='synthetic',
        task=case['id'], attempt='a', run='r', launch=launch,
    )
    try:
        replay.journal = journal
        outcome = 'complete'
        on_start()
        try:
            asyncio.run(run_chi(
                journal, 'synthetic-secret', role='payer',
                instruction='Synthetic payer task', mcp_url='http://synthetic.invalid/mcp',
                instruction_path=instruction, logs_dir=directory / 'logs',
                workspace_root=workspace, handbook_root=handbook, tool_references=[],
                lower=httpx.MockTransport(replay.wire), server_factory=lambda _: replay,
            ))
        except Exception as exc:
            outcome = getattr(exc, 'code', 'execution_error')
        if outcome == 'execution_error' and replay.first is None:
            replay.first = {'phase': 'execution', 'reason': 'execution_error'}
        if replay.first is None and replay.index < len(case['events']):
            replay.first = {'step': replay.index + 1, 'phase': case['events'][replay.index]['type'], 'reason': 'missing_event'}
        log_path = directory / 'logs/run_log.txt'
        log = json.loads(log_path.read_text()) if log_path.exists() else {}
        state_path = directory / 'logs/task-state/task-state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        tool_events = [
            {'call_id': event['call_id'], 'tool': event['tool'], 'event': event['event']}
            for event in journal.run['tool_events']
        ]
        completion = log.get('completion', {})
        observed = {
            'outcome': outcome,
            'dispatches': [entry['tool'] for entry in replay.received],
            'claim': bool(journal.run['claim_done']),
            'tool_events': tool_events,
            'requests': [{'purpose': req['purpose'], 'status': req['status']}
                         for req in journal.run['requests']],
            'unknowns': [item['status'] for item in state.get('unknowns', [])],
            'completion': {key: completion.get(key)
                           for key in ('reason', 'verification', 'business_effect')},
            'verified_status_call_id': (state.get('claim') or {}).get('verified_status_call_id'),
        }
        replay.events.extend({'phase': 'tool_event', **event} for event in tool_events)
        replay.events.extend({'phase': 'request_result', **req} for req in observed['requests'])
        replay.events.append({
            'phase': 'result', 'outcome': outcome, 'claim': observed['claim'],
            'unknowns': observed['unknowns'], 'completion': observed['completion'],
            'verified_status_call_id': observed['verified_status_call_id'],
        })
        checks = []
        for (key, expectation) in case['assertions'].items():
            value = observed
            missing = False
            try:
                for part in key.split('/'):
                    value = value[int(part)] if isinstance(value, list) else value[part]
            except (KeyError, IndexError, ValueError, TypeError):
                value = None
                missing = True
            if isinstance(expectation, dict) and 'prefix' in expectation:
                passed = not missing and isinstance(value, str) and value.startswith(expectation['prefix'])
            else:
                passed = not missing and json_equal(value, expectation)
            checks.append({'assertion': key, 'expected': expectation, 'observed': value, 'missing': missing, 'passed': passed})
            if not passed and replay.first is None:
                replay.first = {'phase': 'assertion', 'assertion': key, 'expected': expectation, 'observed': value, 'missing': missing}
        journal.finish('complete' if outcome == 'complete' else 'failed')
        return {
            'id': case['id'], 'status': 'passed' if replay.first is None else 'failed',
            'first_divergence': replay.first, 'events': replay.events,
            'observed': observed, 'assertions': checks,
        }
    finally:
        journal.close()

def run(suite_path, output):
    (suite, digest) = load_suite(suite_path)
    ident = identity()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for case in suite['cases']:
        started = []
        try:
            results.append(execute(case, output / case['id'], lambda : started.append(True)))
        except Exception:
            status = 'failed' if started else 'not_executed'
            phase = 'execution' if started else 'setup'
            results.append({'id': case['id'], 'status': status, 'first_divergence': {'phase': phase, 'reason': 'case_execution_failed' if started else 'case_setup_failed'}, 'events': [], 'assertions': []})
    report = {
        'schema': SCHEMA,
        'evidence': 'synthetic_offline',
        'suite_sha256': digest,
        'case_ids': [case['id'] for case in suite['cases']],
        **ident,
        'planned': len(results),
        'passed': sum(case['status'] == 'passed' for case in results),
        'failed': sum(case['status'] == 'failed' for case in results),
        'not_executed': sum(case['status'] == 'not_executed' for case in results),
        'cases': results,
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return 0 if report['passed'] == report['planned'] else 1

def validate_report(report):
    if not isinstance(report, dict) or report.get('schema') != SCHEMA or report.get('evidence') != 'synthetic_offline':
        raise ValueError('invalid_report')
    for key in ('source', 'evaluator', 'suite_sha256'):
        if not isinstance(report.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', report[key]):
            raise ValueError('invalid_report_identity')
    environment = report.get('environment')
    if (not isinstance(environment, dict)
            or set(environment) != {'python', 'openai', 'openai-agents', 'mcp', 'httpx'}
            or not all(isinstance(value, str) and value for value in environment.values())):
        raise ValueError('invalid_report_environment')
    ids, cases = report.get('case_ids'), report.get('cases')
    if (not isinstance(ids, list) or not ids
            or not all(isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]*', value) for value in ids)
            or len(ids) != len(set(ids)) or not isinstance(cases, list)
            or len(cases) != len(ids)):
        raise ValueError('invalid_report_cases')
    for case, case_id in zip(cases, ids):
        if (not isinstance(case, dict) or case.get('id') != case_id
                or case.get('status') not in ('passed', 'failed', 'not_executed')
                or not isinstance(case.get('events'), list)
                or not all(isinstance(event, dict) for event in case['events'])
                or not isinstance(case.get('assertions'), list)
                or not all(isinstance(check, dict) for check in case['assertions'])
                or 'first_divergence' not in case
                or (case['status'] == 'passed' and case['first_divergence'] is not None)
                or (case['status'] != 'passed' and not isinstance(case['first_divergence'], dict))):
            raise ValueError('invalid_report_case')
    if type(report.get('planned')) is not int or report['planned'] != len(cases):
        raise ValueError('invalid_report_counts')
    for status in ('passed', 'failed', 'not_executed'):
        if (type(report.get(status)) is not int
                or report[status] != sum(case['status'] == status for case in cases)):
            raise ValueError('invalid_report_counts')



def compare(a, b):
    left = parse_json(Path(a).read_bytes())
    right = parse_json(Path(b).read_bytes())
    for report in (left, right):
        validate_report(report)
    for key in ('suite_sha256', 'case_ids', 'evaluator', 'environment'):
        if left.get(key) is None or left.get(key) != right.get(key):
            raise ValueError('incompatible_' + key)
    differences = []
    for (x, y) in zip(left['cases'], right['cases']):
        for field in ('events', 'assertions'):
            for i in range(max(len(x[field]), len(y[field]))):
                l = x[field][i] if i < len(x[field]) else None
                r = y[field][i] if i < len(y[field]) else None
                if not json_equal(l, r):
                    differences.append({'id': x['id'], 'field': field, 'index': i,
                                        'baseline': l, 'candidate': r,
                                        'baseline_status': x['status'],
                                        'candidate_status': y['status']})
                    break
            if differences and differences[-1]['id'] == x['id']:
                break
        else:
            if x['status'] != y['status'] or not json_equal(x['first_divergence'], y['first_divergence']):
                differences.append({'id': x['id'], 'field': 'result',
                                    'baseline': x['first_divergence'],
                                    'candidate': y['first_divergence'],
                                    'baseline_status': x['status'],
                                    'candidate_status': y['status']})
    return {'baseline_source': left['source'], 'candidate_source': right['source'], 'differences': differences}

def main(argv=None):
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('run')
    p.add_argument('--suite', required=True)
    p.add_argument('--output-dir', required=True)
    p = subs.add_parser('compare')
    p.add_argument('--baseline', required=True)
    p.add_argument('--candidate', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'run':
            return run(args.suite, args.output_dir)
        print(json.dumps(compare(args.baseline, args.candidate), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print('input_error: ' + str(exc), file=sys.stderr)
        return 2
if __name__ == '__main__':
    sys.exit(main())
