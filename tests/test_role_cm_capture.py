import hashlib
import io
import json
import tarfile
from contextlib import nullcontext

import pytest

import role_cm_capture as capture


def _tar(name, raw):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        info = tarfile.TarInfo(name); info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
    return stream.getvalue()


@pytest.mark.parametrize('mode', ['valid', 'wrong_role', 'wrong_actor', 'wrong_world', 'wrong_world_payload',
                                  'wrong_fixture_actor', 'wrong_fixture_task', 'wrong_hash', 'bad_list', 'bad_member', 'extra_key'])
def test_cm_capture_retains_exact_export_and_checks_world(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(capture, '_api_timeout', lambda *a: nullcontext())
    obj = {key: [] for key in capture.CM_LISTS}; obj['task_actor'] = 'care_manager'
    obj['cm_referrals'] = [{'synthetic': True}]
    if mode == 'wrong_actor': obj['task_actor'] = 'payer'
    if mode == 'bad_list': obj['cm_cases'] = {}
    if mode == 'bad_member': obj['cm_cases'] = [3]
    if mode == 'extra_key': obj['world_id'] = 'world'
    exported = json.dumps(obj, indent=2).encode() + b'\n'
    fixture = {'task_id': 'task', 'task_actor': 'care_manager', 'world_id': 'world'}
    if mode == 'wrong_fixture_actor': fixture['task_actor'] = 'payer'
    if mode == 'wrong_fixture_task': fixture['task_id'] = 'other'
    if mode == 'wrong_world': fixture['world_id'] = 'other'
    fixture_raw = json.dumps(fixture).encode()
    world_raw = b'{"world_id":"other"}' if mode == 'wrong_world_payload' else b'{"world_id":"world"}'
    expected_raw = b'{}'
    dig = lambda raw: hashlib.sha256(raw).hexdigest()
    identity = {'world_id': 'world', 'world_sha256': dig(world_raw), 'files': {
        'fixtures/manifest.json': {'sha256': dig(fixture_raw)},
        'fixtures/expectations.json': {'sha256': dig(expected_raw)}}}
    if mode == 'wrong_hash': identity['world_sha256'] = 'f' * 64
    paths = {'/opt/chi-bench/tasks/task/fixtures/manifest.json': _tar('manifest.json', fixture_raw),
             '/opt/chi-bench/tasks/task/fixtures/expectations.json': _tar('expectations.json', expected_raw),
             '/opt/chi-bench/worlds/world.json': _tar('world.json', world_raw)}
    class World:
        client = object()
        id = 'synthetic-world'
        def exec_run(self, *args, **kwargs): return 0, exported
        def get_archive(self, path): return iter([paths[path]]), {}
    result = capture.capture_cm_review_input(World(), tmp_path / 'captures', 'run', task_id='task',
        role='payer' if mode == 'wrong_role' else 'cm', resource_identity=identity)
    if mode == 'valid':
        assert result['status'] == 'ready'
        folder = tmp_path / 'captures/run'
        assert (folder / 'exported_state.json').read_bytes() == exported
        manifest = json.loads((folder / 'manifest.json').read_bytes())
        assert manifest['world_identity_source'] == 'mounted_fixture_manifest_and_world_file'
        assert manifest['sha256']['exported_state.json'] == dig(exported)
        assert 'world_id' not in json.loads((folder / 'exported_state.json').read_bytes())
    else:
        assert result == {'status': 'unavailable', 'safe_error_code': 'cm_review_input_capture_failed'}
        assert not (tmp_path / 'captures/run').exists()
