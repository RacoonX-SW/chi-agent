import copy
import hashlib
import json
from unittest.mock import patch

import pytest

from go_chi_journal import ChiJournal, inspect_history
from go_chi_recovery import POLICY, derive_view
from opencode_go_provider import GoFailure
from request_budget import feedback

IDENTITY = 'a' * 64
USAGE = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 0,
         'opencode': {'billing_source': 'go', 'list_cost': 0.1, 'allowance': 0.1}}


def new(root, attempt='a', run='r'):
    return ChiJournal(root, identity=IDENTITY, evaluation='e', task='t', attempt=attempt, run=run,
                      launch={'output_recovery': POLICY})


def submit_parent(j, mode='partial', *, status=200, diagnostic='ok'):
    used = sum(x['purpose'] != 'patient_simulator' for x in j.run['requests'])
    body = {'model': 'deepseek-v4.1-flash', 'messages': [
        {'role': 'system', 'content': 'system' + feedback(used, j.run['claim_done'])[0]},
        {'role': 'user', 'content': 'task'}], 'max_tokens': 8192,
        'tools': [{'type': 'function', 'function': {'name': 'tool', 'strict': False}}]}
    message = {'role': 'assistant', 'content': 'part', 'reasoning_content': 'thought'}
    if mode == 'regenerate':
        message = {'role': 'assistant', 'tool_calls': [{'id': 'partial', 'type': 'function',
                   'function': {'name': 'tool', 'arguments': '{'}}]}
    response = {'model': 'deepseek-v4.1-flash', 'choices': [{'finish_reason': 'length', 'message': message}], 'usage': USAGE}
    j.reserve(json.dumps(body).encode(), 'main')
    j.record_response(json.dumps(response).encode(), status, 1)
    j.settle(USAGE)
    j.record_diagnostic(diagnostic, 1)
    return body, response, derive_view(body, response, old_used=used, claimed=j.run['claim_done'])


def settle_continuation(j, view, permit):
    j.reserve(json.dumps(view, indent=2).encode(), 'continuation', recovery_permit=permit)
    j.record_response(json.dumps({'usage': USAGE}).encode(), 200, 1)
    j.settle(USAGE)
    j.record_diagnostic('ok', 1)


def digest(root):
    return hashlib.sha256((root / 'chi-accounting.json').read_bytes()).hexdigest()


@pytest.mark.parametrize('mode', ['partial', 'regenerate'])
def test_permit_evidence_and_replay(tmp_path, mode):
    j = new(tmp_path)
    _, _, view = submit_parent(j, mode)
    parent = {p.name: p.read_bytes() for p in (tmp_path / 'wire-evidence' / 'r').iterdir()}
    assert j.issue_recovery(view) == 0
    assert j.run['recovery_events'][0]['continuation_round'] is None
    for name, content in parent.items(): assert (tmp_path / 'wire-evidence' / 'r' / name).read_bytes() == content
    j.finish('failed'); j.close()
    before = (tmp_path / 'chi-accounting.json').read_bytes()
    assert inspect_history(tmp_path, IDENTITY, digest(tmp_path))['status'] == 'inspected'
    assert (tmp_path / 'chi-accounting.json').read_bytes() == before
    j = new(tmp_path, attempt='b', run='s'); j.finish('failed'); j.close()


def test_limits_and_duplicate_are_consumed(tmp_path):
    j = new(tmp_path)
    _, _, first = submit_parent(j)
    j.issue_recovery(first)
    with pytest.raises(GoFailure, match='chi_recovery_limit'): j.issue_recovery(first)
    settle_continuation(j, first, 0)
    _, _, second = submit_parent(j, 'regenerate')
    assert j.issue_recovery(second) == 1
    settle_continuation(j, second, 1)
    _, _, third = submit_parent(j)
    with pytest.raises(GoFailure, match='chi_recovery_limit'): j.issue_recovery(third)
    assert len(j.run['requests']) == 5
    j.finish('failed'); j.close()
    assert inspect_history(tmp_path, IDENTITY, digest(tmp_path))['status'] == 'inspected'


@pytest.mark.parametrize('change', ['view', 'view_bool', 'http', 'diagnostic', 'pending', 'secret'])
def test_bad_issue_no_new_request_or_permit(tmp_path, change):
    j = new(tmp_path)
    _, _, view = submit_parent(j, status=500 if change == 'http' else 200,
                               diagnostic='chi_timeout' if change == 'diagnostic' else 'ok')
    if change == 'view': view['messages'][-1]['content'] = 'changed'
    if change == 'view_bool': view['tools'][0]['function']['strict'] = 0
    if change == 'pending': j.reserve(b'{}', 'main')
    with pytest.raises(GoFailure, match='chi_recovery_invalid'):
        j.issue_recovery(view, secrets=('thought',) if change == 'secret' else ())
    assert len(j.run['requests']) == (2 if change == 'pending' else 1)
    assert j.run['recovery_events'] == []
    if change == 'pending': assert j.state['pending'] is not None
    j.close()


@pytest.mark.parametrize('change', ['bool_parent', 'extra', 'hash', 'duplicate', 'continuation', 'view', 'schema'])
def test_replay_rejects_tamper(tmp_path, change):
    j = new(tmp_path); _, _, view = submit_parent(j); j.issue_recovery(view); j.close()
    state_path = tmp_path / 'chi-accounting.json'
    state = json.loads(state_path.read_text()); event = state['attempts'][0]['recovery_events'][0]
    file = tmp_path / 'wire-evidence' / 'r' / '001-recovery.json'
    if change in {'view', 'schema'}:
        doc = json.loads(file.read_text())
        if change == 'view': doc['view_body']['tools'][0]['function']['strict'] = 0
        else: doc['view_version'] = 'other'
        raw = (json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
        file.write_bytes(raw); event['permit_sha256'] = hashlib.sha256(raw).hexdigest()
    elif change == 'bool_parent': event['parent_round'] = True
    elif change == 'extra': event['extra'] = 'x'
    elif change == 'hash': event['permit_sha256'] = '0' * 64
    elif change == 'duplicate': state['attempts'][0]['recovery_events'].append(copy.deepcopy(event))
    else: event['continuation_round'] = 2
    state_path.write_text(json.dumps(state))
    with pytest.raises(GoFailure, match='chi_history_invalid'): inspect_history(tmp_path, IDENTITY, digest(tmp_path))
    with pytest.raises(GoFailure, match='chi_history_invalid'): new(tmp_path, attempt='b', run='s')


@pytest.mark.parametrize('failure', ['write', 'persist'])
def test_persistence_failure_has_no_retry(tmp_path, failure):
    j = new(tmp_path); _, _, view = submit_parent(j)
    before = len(j.run['requests'])
    target = 'go_chi_journal.write_evidence' if failure == 'write' else 'go_chi_journal.ChiJournal._persist'
    with patch(target, side_effect=OSError('fault')):
        with pytest.raises(GoFailure, match='chi_recovery_persistence_failed'): j.issue_recovery(view)
    with pytest.raises(GoFailure, match='chi_recovery_persistence_failed'): j.issue_recovery(view)
    with pytest.raises(GoFailure, match='chi_recovery_persistence_failed'): j.reserve(b'{}', 'main')
    assert len(j.run['requests']) == before
    j.close()
    if failure == 'persist':
        with pytest.raises(GoFailure, match='chi_history_invalid'): new(tmp_path, attempt='b', run='s')


def test_orphan_recovery_evidence_rejected(tmp_path):
    j = new(tmp_path); submit_parent(j); j.close()
    (tmp_path / 'wire-evidence' / 'r' / '001-recovery.json').write_text('{}')
    with pytest.raises(GoFailure, match='chi_history_invalid'): new(tmp_path, attempt='b', run='s')
