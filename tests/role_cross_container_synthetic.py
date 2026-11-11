"""Prepare a disposable copy and exercise the real operator with synthetic HTTP.

Run only inside the controller with /source read-only, /workspace an empty
disposable sandbox, HOST_PROJECT_ROOT pointing at that sandbox, and Docker socket.
The synthetic runner has no public network and never receives a real key.
"""
import hashlib
import json
import os
import argparse
import shutil
import sys
from pathlib import Path

import docker
from docker.types import Mount

source, root = Path('/source'), Path('/workspace')
host = Path(os.environ['HOST_PROJECT_ROOT'])
parser = argparse.ArgumentParser()
parser.add_argument('--role', choices=('provider', 'payer', 'cm'), default='cm')
parser.add_argument('--scenario', choices=('success', 'patient-failure'), default='success')
args = parser.parse_args()
role = args.role
fail_patient = args.scenario == 'patient-failure'
if fail_patient and role != 'cm': raise SystemExit('scenario_role_invalid')
if not host.is_absolute() or not host.name.startswith('cross-container-sandbox-') or any(root.iterdir()):
    raise SystemExit('synthetic_sandbox_required')
def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, symlinks=True)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
copy(source / 'scripts', root / 'scripts')
copy(source / 'tests', root / 'tests')
copy(source / 'vendor/chi-bench', root / 'vendor/chi-bench')
copy(source / 'data/skills/managed-care-operations-handbook', root / 'data/skills/managed-care-operations-handbook')
copy(source / 'runs/representative-role-baseline-root/resources/dataset', root / 'runs/representative-role-baseline-root/resources/dataset')
copy(source / 'runs/unified-role-cm-lifecycle-root/evidence/history-copy-original', root / 'runs/opencode-go-development')
manifest_src = source / f'runs/representative-role-baseline-root/evidence/role-resources-{role}.json'
manifest = root / f'runs/representative-role-baseline-root/evidence/role-resources-{role}.json'
manifest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(manifest_src, manifest)
for name in ('profiles', 'docs'):
    copy(source / name, root / name)
for name in ('requirements-model.lock', 'requirements-pdf.lock'):
    shutil.copyfile(source / name, root / name)
sys.path.insert(0, str(root / 'scripts'))
sys.path.insert(0, str(root / 'vendor/chi-bench/src'))
from go_chi_bundle import build_bundle
bundle = root / 'bundle'
bundle_hash = build_bundle(bundle, source_root=root).manifest_sha256
client = docker.from_env()
image = client.images.get('chi-agent-dev:latest')
world_image = client.images.get('chi-agent-a-world:py312-review-20261025-01')
def hostpath(path): return str(host / path.relative_to(root))
common = {hostpath(bundle): {'bind': '/package', 'mode': 'ro'},
          hostpath(root / 'vendor/chi-bench'): {'bind': '/package/vendor/chi-bench', 'mode': 'ro'},
          'chi-h-root-model-deps-20261027-v1': {'bind': '/model-deps', 'mode': 'ro'},
          'chi-k-pdf-deps-20261027-v1': {'bind': '/pdf-deps', 'mode': 'ro'}}
env = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/model-deps:/pdf-deps:/package/vendor/chi-bench/src:/package/scripts'}
preflight = client.containers.run(image.id, ['/usr/local/bin/python', '-S', '/package/scripts/go_chi_entry.py', 'preflight', '--bundle-sha256', bundle_hash],
    volumes=common, environment=env, network_disabled=True, remove=True)
identity = json.loads(preflight)['identity_sha256']
baseline = json.loads((source / 'runs/unified-role-cm-lifecycle-root/evidence/history-baseline.json').read_bytes())
qroot = root / 'runs/opencode-go-development'
volumes = dict(common, **{hostpath(qroot): {'bind': '/prior-go', 'mode': 'rw'}})
rebind = ['/usr/local/bin/python', '-S', '/package/scripts/go_chi_entry.py', 'rebind-history', '--bundle-sha256', bundle_hash,
          '--history-mode', 'local', '--local-q-root', '/prior-go', '--output-root', '/prior-go/chi-evaluation',
          '--expected-old-identity', baseline['identity'], '--expected-accounting-sha256', baseline['accounting_sha256'],
          '--migration-reason', 'disposable synthetic HTTP integration copy']
client.containers.run(image.id, rebind, volumes=volumes, environment=env, network_disabled=True, remove=True)
logs = root / 'b-logs'; logs.mkdir()
volumes.update({hostpath(logs): {'bind': '/logs', 'mode': 'rw'},
    hostpath(root / 'tests/role_synthetic_runner.py'): {'bind': '/dev-scripts/synthetic.py', 'mode': 'ro'},
    hostpath(root / 'scripts/role_runner.py'): {'bind': '/dev-scripts/role_runner.py', 'mode': 'ro'},
    hostpath(root / 'scripts/dev_patient_broker.py'): {'bind': '/dev-scripts/dev_patient_broker.py', 'mode': 'ro'}})
b_command = ['/usr/local/bin/python', '-S', '/dev-scripts/synthetic.py', 'coding-b', '--bundle-sha256', bundle_hash,
             '--evaluation-id', 'synthetic-eval', '--task-id', 'synthetic-coding-b', '--attempt-id', 'b1', '--run-id', 'synthetic-b',
             '--output-root', '/prior-go/chi-evaluation', '--logs-dir', '/logs/result', '--history-mode', 'local', '--local-q-root', '/prior-go']
b_env = dict(env, OPENCODE_API_KEY='synthetic-key')
client.containers.run(image.id, b_command, volumes=volumes, environment=b_env, network_disabled=True, remove=True)

import role_operator
class Containers:
    def __init__(self, real): self.real = real
    def __getattr__(self, name): return getattr(self.real, name)
    def create(self, *args, **kwargs):
        if kwargs.get('name', '').startswith('chi-w-runner-'):
            kwargs['command'][2] = '/dev-scripts/synthetic.py'
            kwargs['mounts'].append(Mount(target='/dev-scripts/synthetic.py', source=hostpath(root / 'tests/role_synthetic_runner.py'), type='bind', read_only=True))
            kwargs['environment']['SYNTHETIC_ROLE'] = role
            if fail_patient: kwargs['environment']['SYNTHETIC_PATIENT_FAILURE'] = '1'
        return self.real.create(*args, **kwargs)
class Networks:
    def __init__(self, real): self.real = real
    def __getattr__(self, name): return getattr(self.real, name)
    def get(self, name):
        if name == 'bridge':
            class NoExternalNetwork:
                def connect(self, runner): pass
            return NoExternalNetwork()
        return self.real.get(name)
class DockerProxy:
    containers = Containers(client.containers)
    networks = Networks(client.networks)
    images = client.images
    volumes = client.volumes
    def close(self): client.close()
role_operator._docker = lambda: DockerProxy()
os.environ['OPENCODE_API_KEY'] = 'synthetic-key'
model = json.loads(manifest.read_bytes())
run_id = 'synthetic-' + role
config = {'schema': 'chi-role-operator-v1', 'run_id': run_id, 'evaluation_id': 'synthetic-eval',
          'task_id': model['task_id'], 'attempt_id': 'c1', 'role': role, 'bundle_relative': 'bundle',
          'bundle_sha256': bundle_hash, 'runtime_identity': identity, 'runner_image_id': image.id, 'world_image_id': world_image.id,
          'dataset_relative': 'runs/representative-role-baseline-root/resources/dataset',
          'manifest_relative': f'runs/representative-role-baseline-root/evidence/role-resources-{role}.json',
          'manifest_sha256': digest(manifest), 'output_relative': 'result',
          'dev_sha256': {n: digest(root / 'scripts' / n) for n in role_operator.DEV_FILES}, 'operator_timeout_seconds': 2040}
config_path = root / 'config.json'; config_path.write_text(json.dumps(config, sort_keys=True))
code = role_operator.main(['--config', str(config_path), '--config-sha256', digest(config_path)])
result = json.loads((root / 'result/orchestration.json').read_bytes())
if fail_patient:
    assert code == 1 and result['status'] == 'failed' and result['primary_error'] == 'runner_failed', result
else:
    assert code == 0 and result['status'] == 'complete', result
assert result['world_quiescence'] == 'confirmed' and result['cleanup'] == {'runner': 'removed', 'world': 'removed', 'network': 'removed', 'client': 'closed'}
assert type(result['elapsed_ms']) is int and result['elapsed_ms'] >= 0
assert result['capture_error'] is None and result['capture']['final']['status'] == 'ready'
assert not (root / 'result/world-supply/capability').exists()
state = json.loads((qroot / 'chi-evaluation/chi-accounting.json').read_bytes())
run = next(a for a in state['attempts'] if a['run'] == run_id)
if role != 'cm':
    assert all(r['purpose'] == 'main' and r['status'] == 'settled' for r in run['requests'])
    assert len(run['requests']) == (2 if role == 'provider' else 3)
    if role == 'payer':
        assert result['payer_projection'] == {'status': 'ready', 'count': 4}
        doc = json.loads((qroot / f'chi-evaluation/tool-evidence/{run_id}/call_2.json').read_bytes())
        assert isinstance(doc['body_utf8'], str) and doc['body_utf8'].strip() and not doc['body_utf8'].startswith('ERROR:')
    print(json.dumps({'status': 'passed', 'role': role, 'synthetic_http_only': True, 'external_network': False,
                      'bundle_sha256': bundle_hash, 'identity_sha256': identity, 'official_reward': None}))
    raise SystemExit(0)
assert [r['purpose'] for r in run['requests']] == ['main'] * 5 + ['patient_simulator'] + ([] if fail_patient else ['main'])
assert all(r['status'] == 'settled' for r in run['requests'])
aux = run['requests'][5]
assert any(e.get('tool') == 'cm_outreach.send_message' and e.get('call_id') == aux['parent_call_id']
           for e in run['tool_events'])
captured = json.loads((root / 'result/final-capture/synthetic-cm/exported_state.json').read_bytes())
sessions = captured['cm_conversation_sessions']
assert len(sessions) == 1
if fail_patient:
    assert sessions[0]['status'] == 'active' and sessions[0]['messages'] == []
else:
    assert sessions[0]['status'] == 'ended' and sessions[0]['termination_reason'] == 'patient_ended'
    assert [m['role'] for m in sessions[0]['messages']] == ['care_manager', 'patient']
result_metrics = json.loads((root / 'result/runner-logs/result/run_result.json').read_bytes())
assert (result_metrics['turns'], result_metrics['input_tokens'], result_metrics['output_tokens']) == ((5, 15, 10) if fail_patient else (6, 18, 12))
if not fail_patient:
    wire = qroot / 'chi-evaluation/wire-evidence/synthetic-cm/007-request.json'
    final_request = json.loads(json.loads(wire.read_bytes())['body_utf8'])
    assert 'Already sent before this request: 5.' in final_request['messages'][0]['content']
print(json.dumps({'status': 'passed', 'synthetic_http_only': True, 'external_network': False,
                  'patient_failure': fail_patient, 'bundle_sha256': bundle_hash, 'identity_sha256': identity, 'official_reward': None}))
