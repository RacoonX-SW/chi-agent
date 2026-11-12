import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.tools import replay_trace as replay

SUITE = Path('tests/fixtures/trace_replay_suite.json')


def write_suite(path, value):
    path.write_text(json.dumps(value))
    return path


def test_suite_snapshot_and_validation(tmp_path, monkeypatch):
    original = SUITE.read_bytes()
    calls = []
    real = Path.read_bytes
    def once(path):
        if path == SUITE:
            calls.append(path)
            return original
        return real(path)
    monkeypatch.setattr(Path, 'read_bytes', once)
    suite, digest = replay.load_suite(SUITE)
    assert digest == hashlib.sha256(original).hexdigest() and suite == json.loads(original)
    assert calls == [SUITE]
    for mutate in ('version', 'duplicate', 'event', 'response'):
        bad = copy.deepcopy(suite)
        if mutate == 'version': bad['version'] = 99
        elif mutate == 'duplicate': bad['cases'][1]['id'] = bad['cases'][0]['id']
        elif mutate == 'event': del bad['cases'][0]['events'][0]['purpose']
        else: bad['cases'][0]['events'][0]['response'] = {'choices': []}
        with pytest.raises(ValueError): replay.load_suite(write_suite(tmp_path/'bad.json', bad))


def test_run_actual_sdk_and_no_overwrite(tmp_path):
    out = tmp_path/'run'
    assert replay.run(SUITE, out) == 0
    report = json.loads((out/'report.json').read_text())
    assert report['passed'] == report['planned'] == 4
    assert [c['status'] for c in report['cases']] == ['passed'] * 4
    assert all((out / case / 'state').is_dir() for case in report['case_ids'])
    before = {p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()}
    assert replay.main(['run','--suite',str(SUITE),'--output-dir',str(out)]) == 2
    assert {p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('mutation,reason', [('tool','tool_or_arguments_mismatch'),('args','tool_or_arguments_mismatch'),('early','missing_event'),('purpose','request_mismatch')])
def test_first_divergence(tmp_path, mutation, reason):
    suite = json.loads(SUITE.read_bytes()); suite['cases'] = [suite['cases'][0]]
    events = suite['cases'][0]['events']
    if mutation == 'tool':
        events[2]['tool'] = 'triage.get'
        events[2]['arguments'] = {'case_id': 'unexpected'}
    elif mutation == 'args': events[2]['arguments'] = {'different': True}
    elif mutation == 'early': events.append(copy.deepcopy(events[0]))
    else: events[1]['purpose'] = 'main'
    assert replay.run(write_suite(tmp_path/'suite.json',suite),tmp_path/'out') == 1
    case = json.loads((tmp_path/'out/report.json').read_text())['cases'][0]
    assert case['status'] == 'failed' and case['first_divergence']['reason'] == reason
    if mutation in ('tool','args'): assert case['observed']['dispatches'] == ['triage.get']


def test_failed_assertion_and_not_executed(tmp_path, monkeypatch):
    suite = json.loads(SUITE.read_bytes()); suite['cases'] = suite['cases'][:2]
    suite['cases'][0]['assertions']['claim'] = True
    original = replay.execute
    def execute(case, directory, on_start):
        if case['id'] == 'unknown_write': raise OSError('do not leak')
        return original(case, directory, on_start)
    monkeypatch.setattr(replay, 'execute', execute)
    assert replay.run(write_suite(tmp_path/'suite.json',suite),tmp_path/'out') == 1
    report = json.loads((tmp_path/'out/report.json').read_text())
    assert report['planned'] == 2 and report['passed'] == 0
    assert report['failed'] == 1 and report['not_executed'] == 1
    replay.validate_report(report)
    invalid = copy.deepcopy(report); invalid['failed'] = 2
    with pytest.raises(ValueError, match='invalid_report_counts'): replay.validate_report(invalid)
    assert report['cases'][0]['first_divergence']['assertion'] == 'claim'
    assert report['cases'][1]['status'] == 'not_executed'


def test_compare_conditions_and_first_difference(tmp_path):
    assert replay.run(SUITE, tmp_path/'out') == 0
    report = json.loads((tmp_path/'out/report.json').read_text())
    a = write_suite(tmp_path/'a.json', report)
    b = write_suite(tmp_path/'b.json', report)
    assert replay.compare(a,b)['differences'] == []
    for field in ('events','assertions'):
        changed = copy.deepcopy(report); changed['source'] = 'b' * 64
        changed['cases'][0][field][0]['changed'] = True
        write_suite(b, changed)
        diff = replay.compare(a,b)['differences']
        assert len(diff) == 1 and diff[0]['id'] == 'truncated' and diff[0]['field'] == field and diff[0]['index'] == 0
        assert diff[0]['baseline_status'] == diff[0]['candidate_status'] == 'passed'
    for field in ('suite_sha256','evaluator','environment','case_ids'):
        changed = copy.deepcopy(report); changed[field] = 'wrong'
        write_suite(b, changed)
        with pytest.raises(ValueError): replay.compare(a,b)
    write_suite(b, {'schema': replay.SCHEMA})
    assert replay.main(['compare','--baseline',str(a),'--candidate',str(b)]) == 2


def test_missing_assertion_is_not_null(tmp_path):
    suite = json.loads(SUITE.read_bytes())
    suite['cases'] = suite['cases'][:1]
    suite['cases'][0]['assertions'] = {'does_not_exist': None}
    assert replay.run(write_suite(tmp_path/'suite.json', suite), tmp_path/'out') == 1
    result = json.loads((tmp_path/'out/report.json').read_text())['cases'][0]
    assert result['assertions'][0]['missing'] is True
    assert result['assertions'][0]['passed'] is False


def test_post_start_error_is_failed(tmp_path, monkeypatch):
    suite = json.loads(SUITE.read_bytes())
    suite['cases'] = suite['cases'][:1]
    def fail(case, directory, on_start):
        on_start()
        raise OSError('synthetic')
    monkeypatch.setattr(replay, 'execute', fail)
    assert replay.run(write_suite(tmp_path/'suite.json', suite), tmp_path/'out') == 1
    case = json.loads((tmp_path/'out/report.json').read_text())['cases'][0]
    assert case['status'] == 'failed' and case['first_divergence']['phase'] == 'execution'


def test_workspace_substitution_quotes():
    response = {'choices': [{'message': {'tool_calls': [{'function': {
        'arguments': json.dumps({'path': '$WORKSPACE/a'})}}]}}]}
    result = replay.copy_response(response, Path('/tmp/quote"and\\slash'))
    assert json.loads(result['choices'][0]['message']['tool_calls'][0]['function']['arguments']) == {
        'path': '/tmp/quote"and\\slash/a'}


def test_unexpected_tool_reaches_fake_server_and_preserves_first_divergence(tmp_path):
    suite = json.loads(SUITE.read_bytes())
    suite['cases'] = suite['cases'][:1]
    case = suite['cases'][0]
    case['tools'].append('review.get_nurse_review_data')
    call = case['events'][1]['response']['choices'][0]['message']['tool_calls'][0]
    call['function']['name'] = 'review__get_nurse_review_data'
    assert replay.run(write_suite(tmp_path/'suite.json', suite), tmp_path/'out') == 1
    result = json.loads((tmp_path/'out/report.json').read_text())['cases'][0]
    assert result['first_divergence']['reason'] == 'tool_or_arguments_mismatch'
    assert result['first_divergence']['step'] == 3
    assert result['observed']['dispatches'] == ['review.get_nurse_review_data']


def test_boolean_numbers_are_not_equal_in_mcp_and_assertions(tmp_path):
    suite = json.loads(SUITE.read_bytes())
    suite['cases'] = suite['cases'][:1]
    case = suite['cases'][0]
    call = case['events'][1]['response']['choices'][0]['message']['tool_calls'][0]
    call['function']['arguments'] = '{"case_id":"CASE-A", "x":true}'
    case['events'][2]['arguments']['x'] = 1
    assert replay.run(write_suite(tmp_path/'suite.json', suite), tmp_path/'out') == 1
    case_result = json.loads((tmp_path/'out/report.json').read_text())['cases'][0]
    assert case_result['first_divergence']['reason'] == 'tool_or_arguments_mismatch'
    suite = json.loads(SUITE.read_bytes())
    suite['cases'] = suite['cases'][:1]
    suite['cases'][0]['assertions']['claim'] = 0
    assert replay.run(write_suite(tmp_path/'suite2.json', suite), tmp_path/'out2') == 1
    case_result = json.loads((tmp_path/'out2/report.json').read_text())['cases'][0]
    assert case_result['first_divergence']['assertion'] == 'claim'
    assert next(x for x in case_result['assertions'] if x['assertion'] == 'claim')['passed'] is False
    assert not replay.json_equal({'a': [True]}, {'a': [1]})


@pytest.mark.parametrize('constant', ['NaN', 'Infinity', '-Infinity', '1e999'])
def test_nonfinite_json_rejected(tmp_path, constant):
    path = tmp_path/'suite.json'
    path.write_text('{"version":1,"cases":[],"invalid":' + constant + '}')
    with pytest.raises(ValueError, match='nonfinite_json_number'):
        replay.load_suite(path)
    with pytest.raises(ValueError, match='nonfinite_json_number'):
        replay.compare(path, path)


def test_raw_arguments_preserved_without_substitution():
    for raw in ('{"x":1,"x":2}', '{ invalid', '{ "x" : 1 }',
                '{"x":"$WORKSPACE", "x":2}'):
        response = {'choices': [{'message': {'tool_calls': [{'function': {'arguments': raw}}]}}]}
        result = replay.copy_response(response, Path('/tmp/test'))
        assert result['choices'][0]['message']['tool_calls'][0]['function']['arguments'] == raw


def test_journal_closed_after_log_parse_error(tmp_path, monkeypatch):
    suite = json.loads(SUITE.read_bytes())
    suite['cases'] = suite['cases'][:1]
    closed = []
    original_close = replay.ChiJournal.close
    original_read = Path.read_text
    def close(journal):
        closed.append(True)
        return original_close(journal)
    def read(path, *args, **kwargs):
        if path.name == 'run_log.txt':
            return '{broken'
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(replay.ChiJournal, 'close', close)
    monkeypatch.setattr(Path, 'read_text', read)
    assert replay.run(write_suite(tmp_path/'suite.json', suite), tmp_path/'out') == 1
    assert closed == [True]
    report = json.loads((tmp_path/'out/report.json').read_bytes())
    assert (report['passed'], report['failed'], report['not_executed']) == (0, 1, 0)


def test_compare_shows_statuses_for_divergent_case(tmp_path):
    assert replay.run(SUITE, tmp_path/'out') == 0
    baseline = json.loads((tmp_path/'out/report.json').read_bytes())
    candidate = copy.deepcopy(baseline)
    candidate['cases'][0]['status'] = 'failed'
    candidate['cases'][0]['first_divergence'] = {'phase': 'execution', 'reason': 'synthetic'}
    candidate['passed'] -= 1
    candidate['failed'] += 1
    a = write_suite(tmp_path/'a.json', baseline)
    b = write_suite(tmp_path/'b.json', candidate)
    difference = replay.compare(a, b)['differences'][0]
    assert difference['baseline_status'] == 'passed'
    assert difference['candidate_status'] == 'failed'
