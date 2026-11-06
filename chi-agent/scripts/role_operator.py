"""Hash-bound development operator for one role; never part of a bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from a_environment import _docker, _task_environment, wait_world
from b_provider_transport import _reject_symlink_ancestors
from development_review import _checks
from evaluation_bundle import _check_components, _read_regular_bounded
from go_chi_operator_snapshot import capture_resources
from live_development import _capture_review_input
from role_cm_capture import capture_cm_review_input
from role_resource_preflight import bounded_request_count, validate
from go_chi_resources import workspace_path
from docker.types import Mount
from chi_bench.verifier.task_runtime import collect_all_verifier_checks  # fail before world startup if verifier is unavailable

ROOT = Path('/workspace')
PORTS = {'provider': 8020, 'payer': 8100, 'cm': 8200}
DEV_FILES = ('role_runner.py', 'dev_patient_broker.py', 'dev_patient_cb',
             'dev_patient_bootstrap.py', 'dev_patient_adapter.py')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
SHA = re.compile(r'[0-9a-f]{64}')


def _inside(relative, *, exists=True):
    if type(relative) is not str or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('path_invalid')
    return _check_components(ROOT / relative, 'path_invalid', final_may_be_missing=not exists)


def _sha(path):
    return hashlib.sha256(_read_regular_bounded(path, 64 * 1024 * 1024, 'input_invalid')).hexdigest()


def _config(path, expected):
    raw = _read_regular_bounded(path, 65536, 'config_invalid')
    if not SHA.fullmatch(expected) or hashlib.sha256(raw).hexdigest() != expected: raise ValueError('config_hash_invalid')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate_key')
            result[key] = value
        return result
    c = json.loads(raw, object_pairs_hook=unique)
    keys = {'schema', 'run_id', 'evaluation_id', 'task_id', 'attempt_id', 'role', 'bundle_relative',
            'bundle_sha256', 'runtime_identity', 'runner_image_id', 'world_image_id', 'dataset_relative',
            'manifest_relative', 'manifest_sha256', 'output_relative', 'dev_sha256', 'operator_timeout_seconds'}
    optional = {'history_mode', 'state_relative', 'local_q_root', 'input_summary', 'output_recovery',
                'requirements'}
    if (type(c) is not dict or not keys <= set(c) <= keys | optional
            or c['schema'] != 'chi-role-operator-v1'):
        raise ValueError('config_invalid')
    if c.get('history_mode', 'local') not in {'local', 'external'}:
        raise ValueError('config_invalid')
    for field, versions in (('input_summary', ('chi-input-summary-v1', 'chi-input-summary-v2')),
                            ('output_recovery', ('chi-output-recovery-v1',))):
        if field in c and (type(c[field]) is not str or c[field] not in versions):
            raise ValueError('config_invalid')
    if 'input_summary' in c and 'output_recovery' in c:
        raise ValueError('config_invalid')
    if 'requirements' in c and (c['requirements'] != 'chi-requirements-v1'
                                or 'input_summary' in c or 'output_recovery' in c):
        raise ValueError('config_invalid')
    if c['role'] not in PORTS or any(type(c[k]) is not str or not ID.fullmatch(c[k]) for k in ('run_id', 'evaluation_id', 'task_id', 'attempt_id')): raise ValueError('config_invalid')
    if any(type(c[k]) is not str or not SHA.fullmatch(c[k]) for k in ('bundle_sha256', 'runtime_identity', 'manifest_sha256')): raise ValueError('config_invalid')
    if any(type(c[k]) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', c[k]) for k in ('runner_image_id', 'world_image_id')): raise ValueError('config_invalid')
    if c['operator_timeout_seconds'] != 2040 or type(c['operator_timeout_seconds']) is not int: raise ValueError('config_invalid')
    if type(c['dev_sha256']) is not dict or set(c['dev_sha256']) != set(DEV_FILES): raise ValueError('config_invalid')
    if any(type(v) is not str or not SHA.fullmatch(v) for v in c['dev_sha256'].values()): raise ValueError('config_invalid')
    mode = c.get('history_mode', 'local')
    if mode == 'external':
        if (type(c.get('state_relative')) is not str or not c['state_relative']
                or 'local_q_root' in c):
            raise ValueError('config_invalid')
    else:
        if 'state_relative' in c:
            raise ValueError('config_invalid')
        if 'local_q_root' in c and (type(c['local_q_root']) is not str or not c['local_q_root']):
            raise ValueError('config_invalid')
    return c


def _payer_projection(artifacts, manifest):
    expected = {Path(item['path']).name: item for item in manifest['files'] if '/fixtures/request/' in item['path']}
    found = [p for p in (artifacts / 'workspaces').rglob('*') if p.is_file() and p.parent.name == 'incoming_request']
    # The public task layout is not fixed at four request files (t022 has five).
    # Use the frozen manifest count, but keep a bounded, exact and duplicate-free
    # projection so missing/extra/duplicate files still fail.
    count = len(expected)
    if (not bounded_request_count(count) or len(found) != count
            or len({p.name for p in found}) != count
            or {p.name for p in found} != set(expected)):
        raise ValueError('payer_projection_invalid')
    for path in found:
        _check_components(path, 'payer_projection_invalid', final_may_be_missing=False)
        item = expected[path.name]
        if (workspace_path(artifacts / 'workspaces', str(path), 'payer') != path
                or workspace_path(artifacts / 'workspaces', str(path), 'provider') is not None
                or path.stat().st_size != item['size'] or _sha(path) != item['sha256']):
            raise ValueError('payer_projection_invalid')
    return {'status': 'ready', 'count': len(found)}


def _validation_flags(c):
    flags = []
    if c.get('input_summary') is not None:
        flags += ['--input-summary', c['input_summary']]
    if c.get('output_recovery') is not None:
        flags += ['--output-recovery', c['output_recovery']]
    if c.get('requirements') is not None:
        flags += ['--requirements', c['requirements']]
    return flags


def main(argv=None):
    started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args(argv)
    c = _config(args.config, args.config_sha256)
    dataset, bundle = _inside(c['dataset_relative']), _inside(c['bundle_relative'])
    manifest = validate(dataset, _inside(c['manifest_relative']), c['manifest_sha256'])
    if manifest['task_id'] != c['task_id'] or manifest['role'] != c['role']: raise ValueError('role_mismatch')
    source = ROOT / 'scripts'
    for name, digest in c['dev_sha256'].items():
        if _sha(source / name) != digest: raise ValueError('dev_identity_invalid')
    output = _inside(c['output_relative'], exists=False)
    if output.exists() or not output.parent.is_dir() or any(output == p or output in p.parents or p in output.parents for p in (dataset, bundle, ROOT / 'runs/opencode-go-development')): raise ValueError('output_invalid')
    mode = c.get('history_mode', 'local')
    state = qroot = None
    if mode == 'external':
        state = _inside(c['state_relative'])
        if (not state.is_dir() or any(state == p or state in p.parents or p in state.parents
                                      for p in (dataset, bundle, output, ROOT / 'runs/opencode-go-development'))):
            raise ValueError('history_invalid')
    else:
        qroot = _inside(c.get('local_q_root', 'runs/opencode-go-development'))
        if (not qroot.is_dir() or any(qroot == p or qroot in p.parents or p in qroot.parents
                                      for p in (dataset, bundle, output))):
            raise ValueError('history_invalid')
    for path in (ROOT / 'vendor/chi-bench', ROOT / 'runs/opencode-go-development', ROOT / 'data/skills/managed-care-operations-handbook'):
        _reject_symlink_ancestors(path, 'input_invalid')
        if not path.is_dir(): raise ValueError('input_invalid')
    host_root = Path(os.environ['HOST_PROJECT_ROOT'])
    if not host_root.is_absolute(): raise ValueError('host_root_invalid')
    def host(path): return str(host_root / path.relative_to(ROOT))
    client = _docker()
    runner_image = client.images.get('chi-agent-dev:latest')
    world_image = client.images.get('chi-agent-a-world:py312-review-20261025-01')
    if runner_image.id != c['runner_image_id'] or world_image.id != c['world_image_id']: raise ValueError('image_identity_invalid')
    for name in ('chi-h-root-model-deps-20261027-v1', 'chi-k-pdf-deps-20261027-v1'): client.volumes.get(name)
    names = {kind: f'chi-w-{kind}-{c["run_id"]}' for kind in ('runner', 'world', 'net')}
    for kind in ('runner', 'world'):
        try: client.containers.get(names[kind])
        except Exception as exc:
            if getattr(exc, 'status_code', None) != 404: raise
        else: raise ValueError('resource_exists')
    try: client.networks.get(names['net'])
    except Exception as exc:
        if getattr(exc, 'status_code', None) != 404: raise
    else: raise ValueError('resource_exists')
    common = {host(bundle): {'bind': '/package', 'mode': 'ro'},
              host(ROOT / 'vendor/chi-bench'): {'bind': '/package/vendor/chi-bench', 'mode': 'ro'},
              'chi-h-root-model-deps-20261027-v1': {'bind': '/model-deps', 'mode': 'ro'},
              'chi-k-pdf-deps-20261027-v1': {'bind': '/pdf-deps', 'mode': 'ro'}}
    env = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/model-deps:/pdf-deps:/package/vendor/chi-bench/src:/package/scripts'}
    result = client.containers.run(image=runner_image.id, command=['/usr/local/bin/python', '-S', '/package/scripts/go_chi_entry.py', 'preflight', '--bundle-sha256', c['bundle_sha256']], environment=env, volumes=common,
        network_disabled=True, remove=True, read_only=True, tmpfs={'/tmp': 'rw,nosuid,size=128m'}, cap_drop=['ALL'], security_opt=['no-new-privileges:true'], working_dir='/tmp')
    identity = json.loads(result)
    if identity.get('identity_sha256') != c['runtime_identity']: raise ValueError('runtime_identity_invalid')
    output.mkdir(mode=0o700)
    artifacts = output / 'world-artifacts'; artifacts.mkdir(); (artifacts / 'workspaces').mkdir()
    logs = output / 'runner-logs'; logs.mkdir()
    supply = output / 'world-supply'; supply.mkdir(mode=0o700)
    record = {'schema': 'chi-role-operator-result-v1', 'run_id': c['run_id'], 'role': c['role'], 'config_sha256': args.config_sha256,
              'status': 'started', 'official_reward': None, 'primary_error': None, 'capture_error': None, 'cleanup_error': None,
              'capture': {}, 'cleanup': {}, 'started_unix_ms': time.time_ns() // 1000000, 'automatic_retries': 0}
    def save(): (output / 'orchestration.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
    save()
    network = world = runner = None
    capability_path = None
    entries = {x['path']: x for x in manifest['files']}
    task = dataset / manifest['task_path']
    resource_identity = {'world_id': Path(manifest['world']['path']).stem, 'world_sha256': manifest['world']['sha256'],
                         'files': {'fixtures/expectations.json': entries[manifest['task_path'] + '/fixtures/expectations.json']}}
    if c['role'] == 'cm': resource_identity['files']['fixtures/manifest.json'] = entries[manifest['task_path'] + '/fixtures/manifest.json']
    def capture(root):
        if c['role'] == 'cm': return capture_cm_review_input(world, root, c['run_id'], task_id=c['task_id'], role='cm', resource_identity=resource_identity)
        return _capture_review_input(world, root, c['run_id'], identity, task_id=c['task_id'], resource_identity=resource_identity)
    try:
        labels = {'org.chi-agent.w-owner': c['run_id']}
        network = client.networks.create(names['net'], driver='bridge', internal=True, labels=labels)
        record['network_id'] = network.id
        world_volumes = {host(task): {'bind': f'/opt/chi-bench/tasks/{c["task_id"]}', 'mode': 'ro'}, host(artifacts): {'bind': '/logs/artifacts', 'mode': 'rw'}}
        for entry in manifest['files']:
            if '/shared/worlds/' in entry['path']:
                world_volumes[host(dataset / entry['path'])] = {'bind': '/opt/chi-bench/worlds/' + Path(entry['path']).name, 'mode': 'ro'}
        reference = supply / 'tool_reference.md'
        shutil.copyfile(dataset / manifest['tool_reference_path'], reference)
        if _sha(reference) != entries[manifest['tool_reference_path']]['sha256']: raise ValueError('reference_invalid')
        if c['role'] == 'cm': world_volumes[host(reference)] = {'bind': '/opt/chi-bench-task-assets/tool_reference.md', 'mode': 'ro'}
        world_env = _task_environment(); world_env['CHI_BENCH_TASK_ID'] = c['task_id']
        if c['role'] == 'cm':
            capability_path = supply / 'capability'; capability = secrets.token_urlsafe(48)
            capability_path.write_text(capability, encoding='ascii'); capability_path.chmod(0o600)
            record['capability_sha256'] = hashlib.sha256(capability.encode()).hexdigest()
            world_volumes.update({host(source / 'dev_patient_cb'): {'bind': '/workspace/.venv/bin/cb', 'mode': 'ro'},
                host(source): {'bind': '/opt/chi-dev-scripts', 'mode': 'ro'}, host(capability_path): {'bind': '/run/chi-dev/capability', 'mode': 'ro'}})
            world_env.update(CHI_DEV_PATIENT_SIMULATOR='go-v1', CHI_DEV_CAPABILITY_FILE='/run/chi-dev/capability', CHI_DEV_RUN_ID=c['run_id'],
                             CHI_DEV_BROKER_URL=f'http://{names["runner"]}:8765/patient', PYTHONPATH='/opt/chi-dev-scripts')
        world = client.containers.create(image=world_image.id, name=names['world'], command=['sleep', 'infinity'], environment=world_env,
                                         volumes=world_volumes, network=network.name, detach=True, labels=labels)
        record['world_id'] = world.id
        world.start(); record['readiness_seconds'] = round(wait_world(world), 3)
        record['capture']['initial'] = capture(output / 'initial-capture')
        record['capture']['before_resources'] = capture_resources(world, output / 'resource-snapshots', 'before')
        if record['capture']['initial'].get('status') != 'ready' or any(v.get('status') != 'ready' for v in record['capture']['before_resources'].values()): raise ValueError('initial_capture_unavailable')
        if c['role'] == 'payer': record['payer_projection'] = _payer_projection(artifacts, manifest)
        secret = os.environ.get('OPENCODE_API_KEY')
        if not secret: raise ValueError('credential_missing')
        volumes = dict(common)
        history_volume = ({host(state): {'bind': '/state', 'mode': 'rw'}} if mode == 'external'
                          else {host(qroot): {'bind': '/prior-go', 'mode': 'rw'}})
        volumes.update(history_volume)
        volumes.update({host(logs): {'bind': '/runner-logs', 'mode': 'rw'},
            host(artifacts): {'bind': '/logs/artifacts', 'mode': 'rw'}, host(dataset / manifest['instruction_path']): {'bind': '/input/instruction.md', 'mode': 'ro'},
            host(reference): {'bind': '/input/tool_reference.md', 'mode': 'ro'}, host(ROOT / 'data/skills/managed-care-operations-handbook'): {'bind': '/workspace/skills/managed-care-operations-handbook', 'mode': 'ro'},
            host(source / 'role_runner.py'): {'bind': '/dev-scripts/role_runner.py', 'mode': 'ro'},
            host(source / 'dev_patient_broker.py'): {'bind': '/dev-scripts/dev_patient_broker.py', 'mode': 'ro'}})
        if capability_path is not None: volumes[host(capability_path)] = {'bind': '/run/chi-capability', 'mode': 'ro'}
        mounts = [Mount(target=f'/opt/{alias}/tool_reference.md', source=host(reference), type='bind', read_only=True)
                  for alias in ('healthverse-task-assets', 'chi-bench-task-assets')]
        runner_env = dict(env, OPENCODE_API_KEY=secret, CHI_DEV_WORLD_HOST=names['world'])
        history_args = (['--output-root', '/state', '--history-mode', 'external'] if mode == 'external'
                        else ['--output-root', '/prior-go/chi-evaluation', '--history-mode', 'local',
                              '--local-q-root', '/prior-go'])
        command = ['/usr/local/bin/python', '-S', '/dev-scripts/role_runner.py', 'live', '--bundle-sha256', c['bundle_sha256'],
                   '--evaluation-id', c['evaluation_id'], '--task-id', c['task_id'], '--attempt-id', c['attempt_id'], '--run-id', c['run_id'],
                   '--logs-dir', '/runner-logs/result'] + history_args + [
                   '--role', c['role'], '--instruction-file', '/input/instruction.md', '--mcp-url', f'http://{names["world"]}:{PORTS[c["role"]]}/mcp',
                   '--workspace-root', '/logs/artifacts/workspaces', '--handbook-root', '/workspace/skills/managed-care-operations-handbook', '--tool-reference', '/input/tool_reference.md'] + _validation_flags(c)
        for alias in ('healthverse-task-assets', 'chi-bench-task-assets'):
            command += ['--tool-reference', f'/opt/{alias}/tool_reference.md']
        runner = client.containers.create(image=runner_image.id, name=names['runner'], command=command, environment=runner_env, volumes=volumes,
            mounts=mounts, network=network.name, detach=True, working_dir='/tmp', read_only=True, tmpfs={'/tmp': 'rw,nosuid,size=128m'}, cap_drop=['ALL'], security_opt=['no-new-privileges:true'], labels=labels)
        record['runner_id'] = runner.id
        client.networks.get('bridge').connect(runner)
        runner.start()
        try: record['runner_exit_code'] = runner.wait(timeout=2040).get('StatusCode')
        except Exception: record['primary_error'] = 'runner_wait_failed_or_timeout'
        if record.get('runner_exit_code') != 0 and record['primary_error'] is None: record['primary_error'] = 'runner_failed'
    except Exception as exc:
        safe = {'reference_invalid', 'initial_capture_unavailable', 'payer_projection_invalid', 'credential_missing'}
        record['primary_error'] = record['primary_error'] or (str(exc) if str(exc) in safe else 'operator_execution_failed')
    finally:
        quiescent = runner is None
        if runner is not None:
            try:
                runner.reload()
                if runner.attrs.get('State', {}).get('Running'): runner.stop(timeout=10); runner.reload()
                quiescent = runner.attrs.get('State', {}).get('Running') is False
                (output / 'runner-container.log').write_bytes(runner.logs(stdout=True, stderr=True))
            except Exception: quiescent = False
        state = {}
        try: state = json.loads(_read_regular_bounded(logs / 'lifecycle.json', 4096, 'lifecycle_invalid'))
        except Exception: pass
        world_quiescent = runner is None or (quiescent and state == {'broker_drained': True, 'world_quiescence': 'confirmed'})
        record['runner_quiescent'] = quiescent
        record['world_quiescence'] = 'confirmed' if world_quiescent else 'unproven'
        if world is not None:
            try: (output / 'world-container.log').write_bytes(world.logs(stdout=True, stderr=True))
            except Exception: record['capture_error'] = 'world_log_unavailable'
            if world_quiescent:
                try:
                    record['capture']['after_resources'] = capture_resources(world, output / 'resource-snapshots', 'after')
                    record['capture']['final'] = capture(output / 'final-capture')
                    cap = output / 'final-capture' / c['run_id']
                    checks = _checks(json.loads((cap / 'exported_state.json').read_bytes()), json.loads((cap / 'expectations.json').read_bytes()))
                    record['deterministic_checks'] = {'status': 'complete' if checks else 'not_applicable', 'checks': checks}
                    if record['capture']['final'].get('status') != 'ready' or any(v.get('status') != 'ready' for v in record['capture']['after_resources'].values()): raise ValueError
                except Exception: record['capture_error'] = 'final_capture_unavailable'
            else: record['capture_error'] = 'world_quiescence_unproven'
        for label, container in (('runner', runner), ('world', world)):
            if container is None: continue
            try:
                ident = container.id; container.reload()
                if container.attrs.get('State', {}).get('Running'): container.stop(timeout=10)
                container.remove(force=False)
                try: client.containers.get(ident)
                except Exception as exc:
                    if getattr(exc, 'status_code', None) != 404: raise
                else: raise ValueError('container_still_exists')
                record['cleanup'][label] = 'removed'
            except Exception: record['cleanup'][label] = 'failed'
        if network is not None:
            try:
                ident = network.id; network.remove()
                try: client.networks.get(ident)
                except Exception as exc:
                    if getattr(exc, 'status_code', None) != 404: raise
                else: raise ValueError('network_still_exists')
                record['cleanup']['network'] = 'removed'
            except Exception: record['cleanup']['network'] = 'failed'
        if capability_path is not None:
            try: capability_path.unlink()
            except Exception: record['cleanup']['capability'] = 'failed'
        try:
            client.close()
            record['cleanup']['client'] = 'closed'
        except Exception:
            record['cleanup']['client'] = 'failed'
        if any(v != ('closed' if k == 'client' else 'removed') for k, v in record['cleanup'].items()): record['cleanup_error'] = 'resource_cleanup_failed'
        record['status'] = 'failed' if record['primary_error'] else 'incomplete' if record['capture_error'] or record['cleanup_error'] else 'complete'
        record['finished_unix_ms'] = time.time_ns() // 1000000
        record['elapsed_ms'] = max(0, int((time.monotonic() - started) * 1000))
        save()
    return 0 if record['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
