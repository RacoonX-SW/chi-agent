import hashlib
import json
from pathlib import Path

import pytest

from chi_agent.journal import ChiJournal, _recovery_enabled, inspect_history
from chi_agent.opencode_go_provider import GoFailure

IDENTITY = 'a' * 64
POLICY = 'chi-output-recovery-v1'


def create(root, *, launch=None, kind='chi', attempt='a', run='r'):
    return ChiJournal(root, identity=IDENTITY, evaluation='e', task='t', attempt=attempt,
                      run=run, kind=kind, launch=launch)


def digest(root):
    return hashlib.sha256((root / 'chi-accounting.json').read_bytes()).hexdigest()


def test_off_preserves_old_run_fields(tmp_path):
    j = create(tmp_path)
    assert set(j.run) == {'evaluation', 'task', 'attempt', 'run', 'kind', 'status', 'requests',
                          'patient_binding_events', 'claim_done', 'tool_events', 'safe_error_code', 'launch'}
    j.finish('failed'); j.close()
    assert inspect_history(tmp_path, IDENTITY, digest(tmp_path))['status'] == 'inspected'


def test_on_empty_events_finish_reopen_and_inspect(tmp_path):
    j = create(tmp_path, launch={'output_recovery': POLICY})
    assert j.run['recovery_events'] == []
    j.finish('failed'); j.close()
    before = (tmp_path / 'chi-accounting.json').read_bytes()
    assert inspect_history(tmp_path, IDENTITY, digest(tmp_path))['status'] == 'inspected'
    assert (tmp_path / 'chi-accounting.json').read_bytes() == before
    j = create(tmp_path, attempt='b', run='s')
    assert j.state['attempts'][0]['recovery_events'] == []
    j.finish('failed'); j.close()


@pytest.mark.parametrize('kind,launch', [
    ('chi', {'output_recovery': 'wrong'}), ('chi', {'output_recovery': True}),
    ('chi', {'output_recovery': None}), ('coding_b', {'output_recovery': POLICY}),
    ('patient_probe', {'aux_contract': 'patient-simulator-v1', 'output_recovery': POLICY}),
])
def test_invalid_launch_rejected_before_state_created(tmp_path, kind, launch):
    with pytest.raises(GoFailure, match='chi_identity_invalid'):
        create(tmp_path, kind=kind, launch=launch)
    assert not (tmp_path / 'chi-accounting.json').exists()


@pytest.mark.parametrize('change', ['unknown', 'missing', 'nonempty', 'not_list', 'bad_version', 'wrong_kind', 'off_extra'])
def test_invalid_persisted_run_rejected(tmp_path, change):
    j = create(tmp_path, launch={'output_recovery': POLICY})
    j.close()
    path = tmp_path / 'chi-accounting.json'
    state = json.loads(path.read_text())
    run = state['attempts'][0]
    if change == 'unknown': run['unexpected'] = 1
    elif change == 'missing': del run['recovery_events']
    elif change == 'nonempty': run['recovery_events'] = [{}]
    elif change == 'not_list': run['recovery_events'] = False
    elif change == 'bad_version': run['launch']['output_recovery'] = True
    elif change == 'wrong_kind': run['kind'] = 'coding_b'
    elif change == 'off_extra': del run['launch']['output_recovery']
    path.write_text(json.dumps(state))
    with pytest.raises(GoFailure, match='chi_history_invalid'):
        inspect_history(tmp_path, IDENTITY, digest(tmp_path))
    with pytest.raises(GoFailure, match='chi_history_invalid'):
        create(tmp_path, attempt='b', run='s')


def test_helper_does_not_mutate_launch():
    launch = {'output_recovery': POLICY}
    assert _recovery_enabled(launch, 'chi') is True
    assert launch == {'output_recovery': POLICY}
    assert _recovery_enabled({}, 'chi') is False
