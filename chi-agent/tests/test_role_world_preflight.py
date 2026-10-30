import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

import role_world_preflight as operator


@pytest.mark.parametrize('mode,role', [('success', 'cm'), ('mcp_failure', 'cm'), ('resources_changed', 'cm'), ('success', 'provider')])
def test_owned_world_capture_and_cleanup(tmp_path, monkeypatch, mode, role):
    monkeypatch.setattr(operator, 'ROOT', tmp_path)
    monkeypatch.setenv('HOST_PROJECT_ROOT', '/host/project')
    dataset = tmp_path / 'dataset'; dataset.mkdir()
    ref = dataset / 'care_management/shared/tool_reference.md'; ref.parent.mkdir(parents=True); ref.write_bytes(b'reference')
    manifest_file = tmp_path / 'manifest.json'; manifest_file.write_text('{}')
    (tmp_path / 'output').mkdir()
    manifest = {'task_id': 'task', 'task_path': 'care_management/tasks/task', 'role': role,
        'world': {'path': 'care_management/shared/worlds/world.json', 'sha256': 'a' * 64},
        'tool_reference_path': 'care_management/shared/tool_reference.md',
        'files': [{'path': 'care_management/tasks/task/fixtures/expectations.json', 'sha256': 'b' * 64},
                  {'path': 'care_management/tasks/task/fixtures/manifest.json', 'sha256': 'd' * 64},
                  {'path': 'care_management/shared/tool_reference.md', 'sha256': hashlib.sha256(b'reference').hexdigest()},
                  {'path': 'care_management/shared/worlds/world.json', 'sha256': 'a' * 64}]}
    monkeypatch.setattr(operator, 'validate', lambda *a: manifest)
    monkeypatch.setattr(operator, 'wait_world', lambda *a: 0.1)
    monkeypatch.setattr(operator, '_api_timeout', lambda *a: nullcontext())
    calls = []
    def capture(world, root, run, identity, **kwargs):
        calls.append(root.name)
        target = root / run; target.mkdir(parents=True)
        (target / 'exported_state.json').write_text('{}')
        (target / 'expectations.json').write_text('{}')
        return {'status': 'ready'}
    monkeypatch.setattr(operator, '_capture_review_input', capture)
    cm_calls = []
    def cm_capture(world, root, run, **kwargs):
        cm_calls.append(kwargs['role'])
        return capture(world, root, run, {}, **kwargs)
    monkeypatch.setattr(operator, 'capture_cm_review_input', cm_capture)
    monkeypatch.setattr(operator, 'capture_resources', lambda w, o, p: {s: {'status': 'ready', 'sha256': ('b' if mode == 'resources_changed' and p == 'after' and s == 'payer' else 'a') * 64} for s in ('provider', 'payer')})
    monkeypatch.setattr(operator, '_checks', lambda *a: {'synthetic': True})
    class NotFound(Exception): status_code = 404
    class World:
        id = 'world-id'
        client = object()
        attrs = {'State': {'Running': True}}
        removed = False
        def start(self): pass
        def reload(self): pass
        def stop(self, **kw): self.attrs['State']['Running'] = False
        def remove(self, **kw): self.removed = True
        def logs(self, **kw): return b'synthetic log'
        def exec_run(self, *args, **kw):
            return (1, (b'', b'error')) if mode == 'mcp_failure' else (0, (b'{"tools_count":1,"tool":"cm_intake.list_referral_queue","response":{}}', b''))
    world = World()
    class Containers:
        def get(self, name): raise NotFound()
        def create(self, **kwargs):
            assert kwargs['network_mode'] == 'none' and 'network_disabled' not in kwargs
            assert 'OPENCODE_API_KEY' not in kwargs['environment']
            return world
    client = SimpleNamespace(images=SimpleNamespace(get=lambda name: SimpleNamespace(id='sha256:' + '1' * 64)), containers=Containers())
    monkeypatch.setattr(operator, '_docker', lambda: client)
    config = {'schema': 'chi-role-world-preflight-v1', 'run_id': 'run', 'dataset_relative': 'dataset',
              'manifest_relative': 'manifest.json', 'manifest_sha256': 'a' * 64, 'output_relative': 'output/run',
              'world_image_id': 'sha256:' + '1' * 64}
    raw = json.dumps(config).encode(); path = tmp_path / 'config.json'; path.write_bytes(raw)
    result = operator.main(['--config', str(path), '--config-sha256', hashlib.sha256(raw).hexdigest()])
    record = json.loads((tmp_path / 'output/run/result.json').read_text())
    assert result == (0 if mode == 'success' else 1) and record['cleanup'] == 'removed' and world.removed
    assert calls == ['initial-capture', 'final-capture']
    assert cm_calls == (['cm', 'cm'] if role == 'cm' else [])
    assert (tmp_path / 'output/run/world-container.log').read_bytes() == b'synthetic log'
    if mode != 'mcp_failure': assert (tmp_path / 'output/run/mcp-response.json').is_file()
    if mode == 'resources_changed':
        assert record['resources_unchanged'] is False and record['safe_error_code'] == 'resources_changed'
    assert record['finished_unix_ms'] >= record['started_unix_ms']
    assert record['elapsed_ms'] >= 0 and record['mcp_elapsed_ms'] >= 0
    assert record['model_requests'] == 0 and record['official_reward'] is None
