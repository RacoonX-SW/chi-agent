#!/usr/bin/env python3
"""One reviewed Go CHI development attempt; never bundled with the agent."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

from a_environment import _docker, _task_environment, wait_world
from b_provider_transport import _reject_symlink_ancestors
from development_review import _checks
from evaluation_bundle import _check_components, _read_regular_bounded
from go_chi_operator_snapshot import capture_resources
from go_chi_policy import TIME_POLICY
from live_development import _capture_review_input
from docker.types import Mount
from chi_bench.verifier.task_runtime import collect_all_verifier_checks  # preflight the delayed verifier import

ROOT = Path('/workspace')
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


def _sha(path):
    return hashlib.sha256(_read_regular_bounded(path, 64 * 1024 * 1024, 'operator_input_invalid')).hexdigest()


def _inside(relative, *, exists=True):
    if type(relative) is not str or not relative or Path(relative).is_absolute(): raise ValueError('path')
    path = ROOT / relative
    if '..' in Path(relative).parts or (exists and not path.exists()): raise ValueError('path')
    return _check_components(path, 'operator_input_invalid', final_may_be_missing=not exists)


def _load_config(path, expected):
    raw = _read_regular_bounded(path, 1024 * 1024, 'operator_config_invalid')
    if not SHA.fullmatch(expected) or hashlib.sha256(raw).hexdigest() != expected: raise ValueError('config_hash')
    c = json.loads(raw)
    keys = {'kind', 'run_id', 'evaluation_id', 'task_id', 'attempt_id', 'bundle_relative', 'bundle_sha256',
            'runtime_identity', 'runner_image_id', 'world_image_id', 'resource_relative', 'resource_manifest_sha256',
            'resource_identity_relative', 'resource_identity_sha256', 'output_relative', 'timeout_seconds'}
    if type(c) is not dict or set(c) != keys or c['kind'] not in {'b', 'c'}: raise ValueError('config')
    if any(type(c[k]) is not str or not ID.fullmatch(c[k]) for k in ('run_id', 'evaluation_id', 'task_id', 'attempt_id')): raise ValueError('id')
    if any(type(c[k]) is not str or not SHA.fullmatch(c[k]) for k in ('bundle_sha256', 'runtime_identity')): raise ValueError('identity')
    resource_fields = ('resource_relative', 'resource_manifest_sha256', 'resource_identity_relative', 'resource_identity_sha256')
    if c['kind'] == 'b' and any(c[k] is not None for k in resource_fields): raise ValueError('resource')
    if c['kind'] == 'c' and (any(type(c[k]) is not str or not c[k] for k in resource_fields)
            or any(not SHA.fullmatch(c[k]) for k in ('resource_manifest_sha256', 'resource_identity_sha256'))): raise ValueError('resource')
    if any(type(c[k]) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', c[k]) for k in ('runner_image_id', 'world_image_id')): raise ValueError('image')
    minimum = TIME_POLICY['b_operator_seconds' if c['kind'] == 'b' else 'chi_operator_seconds']
    if type(c['timeout_seconds']) is not int or not minimum <= c['timeout_seconds'] <= TIME_POLICY['operator_max_seconds']: raise ValueError('timeout')
    if c['kind'] == 'b' and c['task_id'] != 'synthetic-coding-b': raise ValueError('task')
    return c


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args(argv)
    # Imports above deliberately precede output creation, credentials, and world creation.
    c = _load_config(args.config, args.config_sha256)
    bundle = _inside(c['bundle_relative'])
    task = resource_identity = None
    if c['kind'] == 'c':
        resource = _inside(c['resource_relative'])
        manifest_path = resource / 'resource-manifest.json'
        if _sha(manifest_path) != c['resource_manifest_sha256']: raise ValueError('resource_manifest')
        manifest = json.loads(manifest_path.read_bytes())
        files = manifest['files'] if manifest.get('task_id') == c['task_id'] else manifest['tasks'][c['task_id']]
        identity_path = _inside(c['resource_identity_relative'])
        if _sha(identity_path) != c['resource_identity_sha256']: raise ValueError('resource_identity')
        resource_identity = json.loads(identity_path.read_bytes())
        if (resource_identity.get('task_id') != c['task_id'] or resource_identity.get('files') != files
                or type(resource_identity.get('world_id')) is not str
                or type(resource_identity.get('world_sha256')) is not str
                or not SHA.fullmatch(resource_identity['world_sha256'])): raise ValueError('resource_identity')
        task = resource / 'prior_auth_provider/tasks' / c['task_id']
        for name, expected in files.items():
            path = task / name
            _check_components(path, 'operator_input_invalid', final_may_be_missing=False)
            if Path(name).is_absolute() or '..' in Path(name).parts or path.stat().st_size != expected['size'] or _sha(path) != expected['sha256']: raise ValueError('resource_hash')
    output = _inside(c['output_relative'], exists=False)
    if output.exists() or not output.parent.is_dir(): raise ValueError('output_exists')
    client = _docker()
    runner_image = client.images.get('chi-agent-dev:latest')
    world_image = client.images.get('chi-agent-a-world:py312-review-20261025-01')
    if runner_image.id != c['runner_image_id'] or world_image.id != c['world_image_id']: raise ValueError('image_identity')
    for name in ('chi-h-root-model-deps-20261027-v1', 'chi-k-pdf-deps-20261027-v1'):
        client.volumes.get(name)
    for path in (ROOT / 'vendor/chi-bench', ROOT / 'runs/opencode-go-development',
                 ROOT / 'data/skills/managed-care-operations-handbook'):
        _reject_symlink_ancestors(path, 'operator_input_invalid')
        if not path.is_dir(): raise ValueError('required_path')
    for name in (f'chi-s-runner-{c["run_id"]}', f'chi-s-world-{c["run_id"]}'):
        try: client.containers.get(name)
        except Exception as exc:
            if getattr(exc, 'status_code', None) != 404: raise
        else: raise ValueError('resource_exists')
    host_root = Path(os.environ['HOST_PROJECT_ROOT'])
    if not host_root.is_absolute(): raise ValueError('host_root')
    def host(path): return str(host_root / path.relative_to(ROOT))
    # Import and verify the candidate in its own mount layout, without credentials or network.
    preflight = client.containers.run(image=runner_image.id,
        command=['/usr/local/bin/python', '-S', '/package/scripts/go_chi_entry.py', 'preflight', '--bundle-sha256', c['bundle_sha256']],
        environment={'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/model-deps:/pdf-deps:/package/vendor/chi-bench/src'},
        volumes={host(bundle): {'bind': '/package', 'mode': 'ro'},
                 host(ROOT / 'vendor/chi-bench'): {'bind': '/package/vendor/chi-bench', 'mode': 'ro'},
                 'chi-h-root-model-deps-20261027-v1': {'bind': '/model-deps', 'mode': 'ro'},
                 'chi-k-pdf-deps-20261027-v1': {'bind': '/pdf-deps', 'mode': 'ro'}},
        network_disabled=True, remove=True, read_only=True, tmpfs={'/tmp': 'rw,nosuid,size=128m'},
        cap_drop=['ALL'], security_opt=['no-new-privileges:true'], working_dir='/tmp')
    identity = json.loads(preflight)
    if identity.get('identity_sha256') != c['runtime_identity']: raise ValueError('runtime_identity')
    output.mkdir(mode=0o700)
    (output / 'runner-logs').mkdir()
    record = {'schema': 'chi-s-operator-v1', 'run_id': c['run_id'], 'kind': c['kind'], 'status': 'started',
              'config_sha256': args.config_sha256, 'official_reward': None, 'primary_error': None,
              'capture_error': None, 'cleanup_error': None, 'capture': {}, 'cleanup': {},
              'started_unix': time.time(), 'automatic_retries': 0}
    runner = world = network = None
    def save(): (output / 'orchestration.json').write_text(json.dumps(record, sort_keys=True, indent=2))
    save()
    try:
        labels = {'org.chi-agent.s-owner': c['run_id']}
        volumes = {host(bundle): {'bind': '/package', 'mode': 'ro'},
                   host(ROOT / 'vendor/chi-bench'): {'bind': '/package/vendor/chi-bench', 'mode': 'ro'},
                   host(ROOT / 'runs/opencode-go-development'): {'bind': '/prior-go', 'mode': 'rw'},
                   host(output / 'runner-logs'): {'bind': '/runner-logs', 'mode': 'rw'},
                   'chi-h-root-model-deps-20261027-v1': {'bind': '/model-deps', 'mode': 'ro'},
                   'chi-k-pdf-deps-20261027-v1': {'bind': '/pdf-deps', 'mode': 'ro'}}
        mounts = []
        mcp = None
        if c['kind'] == 'c':
            artifacts = output / 'world-artifacts'; artifacts.mkdir(); (artifacts / 'workspaces').mkdir()
            network = client.networks.create(f'chi-s-net-{c["run_id"]}', driver='bridge', internal=True, labels=labels)
            record['network_id'] = network.id
            env = _task_environment(); env['CHI_BENCH_TASK_ID'] = c['task_id']
            world = client.containers.create(image=world_image.id, name=f'chi-s-world-{c["run_id"]}', command=['sleep', 'infinity'],
                environment=env, labels=labels, volumes={host(task): {'bind': f'/opt/chi-bench/tasks/{c["task_id"]}', 'mode': 'ro'},
                host(artifacts): {'bind': '/logs/artifacts', 'mode': 'rw'}}, network=network.name, detach=True)
            record['world_id'] = world.id
            world.start(); record['readiness_seconds'] = round(wait_world(world), 3)
            record['capture']['initial_review_input'] = _capture_review_input(world, output / 'initial-capture', c['run_id'], identity,
                                                                                 task_id=c['task_id'], resource_identity=resource_identity)
            if record['capture']['initial_review_input'].get('status') != 'ready': raise RuntimeError('initial_world_identity_unavailable')
            record['capture']['before_resources'] = capture_resources(world, output / 'resource-snapshots', 'before')
            save()
            if any(x['status'] != 'ready' for x in record['capture']['before_resources'].values()): raise RuntimeError('before_snapshot_unavailable')
            mcp = f'http://{world.name}:8020/mcp'
            volumes.update({host(task / 'instruction.md'): {'bind': '/input/instruction.md', 'mode': 'ro'},
                host(task / 'tool_reference.md'): {'bind': '/input/tool_reference.md', 'mode': 'ro'},
                host(ROOT / 'data/skills/managed-care-operations-handbook'): {'bind': '/workspace/skills/managed-care-operations-handbook', 'mode': 'ro'},
                host(artifacts): {'bind': '/logs/artifacts', 'mode': 'rw'}})
            for alias in ('healthverse-task-assets', 'chi-bench-task-assets'):
                mounts.append(Mount(target=f'/opt/{alias}/tool_reference.md', source=host(task / 'tool_reference.md'), type='bind', read_only=True))
        # Only the selected Go credential enters the runner, after all preflight and before snapshot.
        secret = os.environ.get('OPENCODE_API_KEY')
        if not secret: raise RuntimeError('credential_missing')
        command = ['/usr/local/bin/python', '-S', '/package/scripts/go_chi_entry.py', 'coding-b' if c['kind'] == 'b' else 'live',
            '--bundle-sha256', c['bundle_sha256'], '--evaluation-id', c['evaluation_id'], '--task-id', c['task_id'],
            '--attempt-id', c['attempt_id'], '--run-id', c['run_id'], '--output-root', '/prior-go/chi-evaluation',
            '--logs-dir', '/runner-logs/result', '--history-mode', 'local', '--local-q-root', '/prior-go']
        if mcp:
            command += ['--role', 'provider', '--instruction-file', '/input/instruction.md', '--mcp-url', mcp,
                '--workspace-root', '/logs/artifacts/workspaces', '--handbook-root', '/workspace/skills/managed-care-operations-handbook']
            for path in ('/input/tool_reference.md', '/opt/healthverse-task-assets/tool_reference.md', '/opt/chi-bench-task-assets/tool_reference.md'):
                command += ['--tool-reference', path]
        runner = client.containers.create(image=runner_image.id, name=f'chi-s-runner-{c["run_id"]}', command=command,
            environment={'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/model-deps:/pdf-deps:/package/vendor/chi-bench/src', 'OPENCODE_API_KEY': secret},
            volumes=volumes, mounts=mounts, network='bridge', detach=True, working_dir='/tmp', read_only=True,
            tmpfs={'/tmp': 'rw,nosuid,size=128m'}, cap_drop=['ALL'], security_opt=['no-new-privileges:true'], labels=labels)
        record['runner_id'] = runner.id
        if network is not None: network.connect(runner)
        runner.start()
        try: record['runner_exit_code'] = runner.wait(timeout=c['timeout_seconds']).get('StatusCode')
        except Exception:
            record['primary_error'] = 'runner_wait_failed_or_timeout'
            runner.stop(timeout=10)
        if record.get('runner_exit_code') != 0 and record['primary_error'] is None: record['primary_error'] = 'runner_failed'
    except Exception as exc:
        safe = {'initial_world_identity_unavailable', 'before_snapshot_unavailable', 'credential_missing'}
        record['primary_error'] = record['primary_error'] or (str(exc) if str(exc) in safe else 'operator_execution_failed')
    finally:
        quiescent = runner is None
        if runner is not None:
            try:
                runner.reload()
                if runner.attrs.get('State', {}).get('Running'): runner.stop(timeout=10); runner.reload()
                quiescent = runner.attrs.get('State', {}).get('Running') is False
                (output / 'container.log').write_bytes(runner.logs(stdout=True, stderr=True))
            except Exception: record['capture']['runner_quiescence'] = 'unavailable'
        if world is not None and quiescent:
            try: record['capture']['after_resources'] = capture_resources(world, output / 'resource-snapshots', 'after')
            except Exception: record['capture']['after_resources'] = {'status': 'unavailable'}
            try: record['capture']['review_input'] = _capture_review_input(world, output / 'capture', c['run_id'], identity,
                                                                           task_id=c['task_id'], resource_identity=resource_identity)
            except Exception: record['capture']['review_input'] = {'status': 'unavailable'}
            if record['capture']['review_input'].get('status') == 'ready':
                try:
                    cap = output / 'capture' / c['run_id']
                    checks = _checks(json.loads((cap / 'exported_state.json').read_bytes()),
                                     json.loads((cap / 'expectations.json').read_bytes()))
                    record['deterministic_checks'] = {'status': 'complete' if checks else 'not_applicable', 'checks': checks}
                except Exception: record['deterministic_checks'] = {'status': 'unavailable'}
        elif world is not None: record['capture']['review_input'] = {'status': 'unavailable', 'reason': 'runner_not_quiescent'}
        for label, container in (('runner', runner), ('world', world)):
            if container is None: continue
            try:
                container.reload()
                if container.attrs.get('State', {}).get('Running'): container.stop(timeout=10)
                container.remove(force=False); record['cleanup'][label] = 'removed'
            except Exception: record['cleanup'][label] = 'failed'
        if network is not None:
            try: network.remove(); record['cleanup']['network'] = 'removed'
            except Exception: record['cleanup']['network'] = 'failed'
        if c['kind'] == 'c':
            after = record['capture'].get('after_resources', {})
            if (record['capture'].get('review_input', {}).get('status') != 'ready'
                    or any(after.get(side, {}).get('status') != 'ready' for side in ('provider', 'payer'))
                    or not isinstance(record.get('deterministic_checks'), dict)
                    or record['deterministic_checks'].get('status') == 'unavailable'):
                record['capture_error'] = 'capture_or_checks_unavailable'
        if record['capture'].get('runner_quiescence') == 'unavailable':
            record['capture_error'] = record['capture_error'] or 'runner_quiescence_or_log_unavailable'
        if any(value != 'removed' for value in record['cleanup'].values()):
            record['cleanup_error'] = 'resource_cleanup_failed'
        record['status'] = ('failed' if record['primary_error'] is not None else
                            'incomplete' if record['capture_error'] or record['cleanup_error'] else 'complete')
        record['elapsed_seconds'] = round(time.time() - record['started_unix'], 3)
        save()
    return 0 if record['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
