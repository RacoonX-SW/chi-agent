import copy
import hashlib
import json
from unittest.mock import patch

import pytest

from go_chi_journal import inspect_history
from go_chi_recovery import derive_view
from opencode_go_provider import GoFailure
from test_go_chi_recovery_journal import USAGE, digest, new, settle_continuation, submit_parent


@pytest.mark.parametrize('mode', ['partial', 'regenerate'])
def test_bind_settle_reopen_inspect_and_preserve_parent(tmp_path, mode):
    j = new(tmp_path); _, _, view = submit_parent(j, mode)
    files = {p.name: p.read_bytes() for p in (tmp_path / 'wire-evidence' / 'r').iterdir()}
    permit = j.issue_recovery(view)
    settle_continuation(j, view, permit)
    assert j.run['recovery_events'][0]['continuation_round'] == 2
    assert j.run['requests'][1]['purpose'] == 'continuation'
    for name, raw in files.items(): assert (tmp_path / 'wire-evidence' / 'r' / name).read_bytes() == raw
    j.finish('complete'); j.close()
    assert inspect_history(tmp_path, 'a' * 64, digest(tmp_path))['status'] == 'inspected'
    j = new(tmp_path, attempt='b', run='s'); j.finish('failed'); j.close()


@pytest.mark.parametrize('case', ['missing', 'bool', 'bad_index', 'wrong_body', 'secret'])
def test_bad_continuation_fails_closed(tmp_path, case):
    j = new(tmp_path); _, _, view = submit_parent(j); j.issue_recovery(view)
    raw = json.dumps(view).encode()
    if case == 'wrong_body':
        view['tools'][0]['function']['strict'] = 0
        raw = json.dumps(view).encode()
    index = {'missing': None, 'bool': True, 'bad_index': 1}.get(case, 0)
    with pytest.raises(GoFailure):
        j.reserve(raw, 'continuation', recovery_permit=index, secrets=('thought',) if case == 'secret' else ())
    assert len(j.run['requests']) == 1
    with pytest.raises(GoFailure, match='chi_recovery_persistence_failed'):
        j.reserve(raw, 'continuation', recovery_permit=0)
    j.close()


def test_unused_permit_blocks_intervening_and_complete(tmp_path):
    j = new(tmp_path); _, _, view = submit_parent(j); j.issue_recovery(view)
    for purpose in ('main', 'confirmation', 'patient_simulator'):
        with pytest.raises(GoFailure): j.reserve(b'{}', purpose)
    with pytest.raises(GoFailure): j.finish('complete')
    j.finish('failed'); j.close()
    assert inspect_history(tmp_path, 'a' * 64, digest(tmp_path))['status'] == 'inspected'


def test_bound_permit_cannot_repeat_or_be_parent(tmp_path):
    j = new(tmp_path); _, _, view = submit_parent(j); permit = j.issue_recovery(view)
    j.reserve(json.dumps(view).encode(), 'continuation', recovery_permit=permit)
    response = {'model': 'deepseek-v4.1-flash', 'choices': [{'finish_reason': 'length',
                'message': {'role': 'assistant', 'content': 'again'}}], 'usage': USAGE}
    j.record_response(json.dumps(response).encode(), 200, 1); j.settle(USAGE); j.record_diagnostic('ok', 1)
    with pytest.raises(GoFailure, match='chi_recovery_invalid'): j.issue_recovery(view)
    with pytest.raises(GoFailure): j.reserve(json.dumps(view).encode(), 'continuation', recovery_permit=permit)
    j.close()


@pytest.mark.parametrize('mutation', ['bool', 'missing', 'wrong_parent', 'same_as_parent', 'non_continuation', 'unlinked'])
def test_bad_binding_rejected_by_replay(tmp_path, mutation):
    j = new(tmp_path); _, _, view = submit_parent(j); settle_continuation(j, view, j.issue_recovery(view)); j.close()
    path = tmp_path / 'chi-accounting.json'; state = json.loads(path.read_text()); run = state['attempts'][0]
    event = run['recovery_events'][0]
    if mutation == 'bool': event['continuation_round'] = True
    elif mutation == 'missing': event['continuation_round'] = None
    elif mutation == 'wrong_parent': event['parent_round'] = 2
    elif mutation == 'same_as_parent': event['continuation_round'] = 1
    elif mutation == 'non_continuation': run['requests'][1]['purpose'] = 'main'
    else: run['recovery_events'] = []
    path.write_text(json.dumps(state))
    with pytest.raises(GoFailure, match='chi_history_invalid'): inspect_history(tmp_path, 'a' * 64, digest(tmp_path))


@pytest.mark.parametrize('point', ['marker', 'evidence', 'persist'])
def test_continuation_reserve_persistence_failure_never_reused(tmp_path, point):
    j = new(tmp_path); _, _, view = submit_parent(j); j.issue_recovery(view)
    target = {'marker': 'go_chi_journal.ChiJournal._mark_tool_inflight',
              'evidence': 'go_chi_journal.write_evidence', 'persist': 'go_chi_journal.ChiJournal._persist'}[point]
    with patch(target, side_effect=OSError('fault')):
        with pytest.raises(Exception): j.reserve(json.dumps(view).encode(), 'continuation', recovery_permit=0)
    with pytest.raises(GoFailure, match='chi_recovery_persistence_failed'):
        j.reserve(json.dumps(view).encode(), 'continuation', recovery_permit=0)
    j.close()
    if point != 'marker':
        with pytest.raises(GoFailure, match='chi_history_invalid'): new(tmp_path, attempt='b', run='s')


def test_shared_limit_includes_continuation(tmp_path):
    j = new(tmp_path)
    _, _, view = submit_parent(j); settle_continuation(j, view, j.issue_recovery(view))
    for _ in range(48):
        j.reserve(b'{}', 'main'); j.record_response(json.dumps({'usage': USAGE}).encode(), 200, 1)
        j.settle(USAGE); j.record_diagnostic('ok', 1)
    with pytest.raises(GoFailure, match='chi_request_limit'): j.reserve(b'{}', 'main')
    assert len(j.run['requests']) == 50
    j.finish('failed'); j.close()
    assert inspect_history(tmp_path, 'a' * 64, digest(tmp_path))['status'] == 'inspected'


def test_continuation_wire_tamper_rejected_even_if_hashes_updated(tmp_path):
    j = new(tmp_path); _, _, view = submit_parent(j); settle_continuation(j, view, j.issue_recovery(view)); j.close()
    state_path = tmp_path / 'chi-accounting.json'; state = json.loads(state_path.read_text())
    item = state['attempts'][0]['requests'][1]
    evidence_path = tmp_path / 'wire-evidence' / 'r' / '002-request.json'
    evidence = json.loads(evidence_path.read_text()); body = json.loads(evidence['body_utf8'])
    body['tools'][0]['function']['strict'] = 0
    body_raw = json.dumps(body).encode(); evidence['body_utf8'] = body_raw.decode()
    evidence['raw_sha256'] = item['request_sha256'] = hashlib.sha256(body_raw).hexdigest()
    raw = (json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    evidence_path.write_bytes(raw); item['request_evidence_sha256'] = hashlib.sha256(raw).hexdigest()
    state_path.write_text(json.dumps(state))
    with pytest.raises(GoFailure, match='chi_history_invalid'):
        inspect_history(tmp_path, 'a' * 64, digest(tmp_path))


def test_old_run_seal_and_record_stay_unchanged(tmp_path):
    j = new(tmp_path); j.finish('failed'); old_record = copy.deepcopy(j.run); j.close()
    seal = (tmp_path / 'run-seals' / 'r.json').read_bytes()
    j = new(tmp_path, attempt='b', run='s'); _, _, view = submit_parent(j)
    settle_continuation(j, view, j.issue_recovery(view)); j.finish('complete')
    assert j.state['attempts'][0] == old_record
    j.close()
    assert (tmp_path / 'run-seals' / 'r.json').read_bytes() == seal
    assert inspect_history(tmp_path, 'a' * 64, digest(tmp_path))['status'] == 'inspected'


def test_unbound_permit_cannot_be_sealed_complete_or_followed_in_replay(tmp_path):
    j = new(tmp_path); _, _, view = submit_parent(j); j.issue_recovery(view); j.close()
    path = tmp_path / 'chi-accounting.json'; state = json.loads(path.read_text())
    state['attempts'][0]['status'] = 'complete'; path.write_text(json.dumps(state))
    with pytest.raises(GoFailure, match='chi_history_invalid'):
        inspect_history(tmp_path, 'a' * 64, digest(tmp_path))
