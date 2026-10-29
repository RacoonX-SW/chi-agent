import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import go_chi_operator as operator
except ModuleNotFoundError as exc:
    if exc.name not in {'docker', 'docker.types'}: raise
    operator = None


class NotFound(Exception):
    status_code = 404


class Container:
    def __init__(self, name, code=0):
        self.name, self.code = name, code
        self.id = name + '-id'
        self.attrs = {'State': {'Running': False}}
        self.removed = False
    def start(self): self.attrs['State']['Running'] = True
    def wait(self, timeout): self.attrs['State']['Running'] = False; return {'StatusCode': self.code}
    def reload(self): pass
    def stop(self, timeout): self.attrs['State']['Running'] = False
    def logs(self, **kwargs): return b'synthetic log'
    def remove(self, force): self.removed = True


class Client:
    def __init__(self, identity):
        self.identity = identity
        self.containers = self
        self.images = SimpleNamespace(get=lambda name: SimpleNamespace(id='sha256:' + ('a' if 'dev' in name else 'b') * 64))
        self.volumes = SimpleNamespace(get=lambda name: object())
        self.networks = SimpleNamespace(create=lambda *a, **k: SimpleNamespace(id='network-id', name='network', connect=lambda _: None, remove=lambda: None))
        self.created = []
    def get(self, name): raise NotFound()
    def run(self, **kwargs): return json.dumps({'identity_sha256': self.identity}).encode()
    def create(self, **kwargs):
        c = Container(kwargs['name'], code=2 if 'runner' in kwargs['name'] else 0)
        self.created.append(c)
        return c


@unittest.skipIf(operator is None, 'Docker SDK is provided by the controller image')
class OperatorTests(unittest.TestCase):
    def test_failed_preflight_creates_no_world_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ('bundle', 'vendor/chi-bench', 'runs/opencode-go-development', 'data/skills/managed-care-operations-handbook', 'output'):
                (root / path).mkdir(parents=True)
            config = {'kind': 'b', 'run_id': 'run', 'evaluation_id': 'e', 'task_id': 'synthetic-coding-b', 'attempt_id': 'a',
                'bundle_relative': 'bundle', 'bundle_sha256': 'd' * 64, 'runtime_identity': 'e' * 64,
                'runner_image_id': 'sha256:' + 'a' * 64, 'world_image_id': 'sha256:' + 'b' * 64,
                'resource_relative': None, 'resource_manifest_sha256': None, 'resource_identity_relative': None,
                'resource_identity_sha256': None, 'output_relative': 'output/run', 'timeout_seconds': 30}
            path = root / 'config.json'; path.write_text(json.dumps(config))
            client = Client(config['runtime_identity'])
            with patch.object(operator, 'ROOT', root), patch.object(operator, '_docker', return_value=client), \
                 patch.object(client, 'run', side_effect=RuntimeError('missing dependency')), \
                 patch.dict(os.environ, {'HOST_PROJECT_ROOT': '/host/project'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'missing dependency'):
                    operator.main(['--config', str(path), '--config-sha256', hashlib.sha256(path.read_bytes()).hexdigest()])
            self.assertEqual(client.created, [])
            self.assertFalse((root / 'output/run').exists())

    def test_failed_runner_captures_before_cleanup_and_preserves_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ('bundle', 'vendor/chi-bench', 'runs/opencode-go-development', 'data/skills/managed-care-operations-handbook', 'output'):
                (root / path).mkdir(parents=True)
            task = root / 'resource/prior_auth_provider/tasks/t'; task.mkdir(parents=True)
            payload = b'synthetic'; (task / 'instruction.md').write_bytes(payload)
            files = {'instruction.md': {'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}}
            manifest = root / 'resource/resource-manifest.json'; manifest.write_text(json.dumps({'task_id': 't', 'files': files}))
            resource_identity = root / 'identity.json'
            resource_identity.write_text(json.dumps({'task_id': 't', 'files': files, 'world_id': 'world', 'world_sha256': 'c' * 64}))
            config = {'kind': 'c', 'run_id': 'run', 'evaluation_id': 'e', 'task_id': 't', 'attempt_id': 'a',
                'bundle_relative': 'bundle', 'bundle_sha256': 'd' * 64, 'runtime_identity': 'e' * 64,
                'runner_image_id': 'sha256:' + 'a' * 64, 'world_image_id': 'sha256:' + 'b' * 64,
                'resource_relative': 'resource', 'resource_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                'resource_identity_relative': 'identity.json', 'resource_identity_sha256': hashlib.sha256(resource_identity.read_bytes()).hexdigest(),
                'output_relative': 'output/run', 'timeout_seconds': 30}
            config_path = root / 'config.json'; config_path.write_text(json.dumps(config))
            config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
            client = Client(config['runtime_identity']); phases = []
            def snapshot(world, out, phase):
                self.assertFalse(world.removed)
                phases.append(phase)
                return {side: {'status': 'ready'} for side in ('provider', 'payer')}
            def capture(world, out, run, identity, **kwargs):
                self.assertFalse(world.removed)
                phases.append('capture')
                return {'status': 'unavailable'} if 'initial-capture' not in str(out) else {'status': 'ready'}
            with patch.object(operator, 'ROOT', root), patch.object(operator, '_docker', return_value=client), \
                 patch.object(operator, 'wait_world', return_value=0.1), patch.object(operator, 'capture_resources', side_effect=snapshot), \
                 patch.object(operator, '_capture_review_input', side_effect=capture), \
                 patch.dict(os.environ, {'HOST_PROJECT_ROOT': '/host/project', 'OPENCODE_API_KEY': 'synthetic'}):
                rc = operator.main(['--config', str(config_path), '--config-sha256', config_hash])
            record = json.loads((root / 'output/run/orchestration.json').read_text())
            self.assertEqual(rc, 1)
            self.assertEqual(record['primary_error'], 'runner_failed')
            self.assertEqual(record['capture']['review_input']['status'], 'unavailable')
            self.assertEqual(record['capture_error'], 'capture_or_checks_unavailable')
            self.assertEqual(phases, ['capture', 'before', 'after', 'capture'])
            self.assertTrue(all(item.removed for item in client.created))
