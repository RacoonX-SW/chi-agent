"""No-model, package-external role world preflight with owned Docker cleanup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from a_environment import _api_timeout, _docker, _task_environment, wait_world
from development_review import _checks
from evaluation_bundle import _check_components, _read_regular_bounded
from go_chi_operator_snapshot import capture_resources
from live_development import _capture_review_input
from role_cm_capture import capture_cm_review_input
from role_resource_preflight import validate

ROOT = Path('/workspace')
PORTS = {'provider': 8020, 'payer': 8100, 'cm': 8200}
PROBES = {'provider': 'chart.search_patients', 'payer': 'payer_intake_hub.list_intake_queue',
          'cm': 'cm_intake.list_referral_queue'}
MCP_PROGRAM = r'''
import asyncio, hashlib, json, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async def main():
    async with asyncio.timeout(45):
        async with streamablehttp_client(sys.argv[1]) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.list_tools()
                names = [t.name for t in result.tools]
                wanted = sys.argv[2]
                matched = [x for x in names if x in {wanted, wanted.replace('.', '__'), wanted.replace('.', '_'), wanted.replace('.', '-')}]
                if len(matched) != 1: raise ValueError('probe_tool_missing')
                result = await session.call_tool(matched[0], {})
                if result.isError: raise ValueError('probe_call_failed')
                raw = result.model_dump(mode='json')
                print(json.dumps({'tools_count': len(names), 'tool': wanted, 'response': raw}, ensure_ascii=True))
asyncio.run(main())
'''


def _inside(relative, *, must_exist=True):
    if type(relative) is not str or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('path_invalid')
    return _check_components(ROOT / relative, 'path_invalid', final_may_be_missing=not must_exist)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args(argv)
    raw = _read_regular_bounded(args.config, 16384, 'config_invalid')
    if hashlib.sha256(raw).hexdigest() != args.config_sha256: raise ValueError('config_hash_invalid')
    config = json.loads(raw)
    keys = {'schema', 'run_id', 'dataset_relative', 'manifest_relative', 'manifest_sha256', 'output_relative', 'world_image_id'}
    if (type(config) is not dict or set(config) != keys or config['schema'] != 'chi-role-world-preflight-v1'
            or type(config['run_id']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', config['run_id'])
            or type(config['world_image_id']) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', config['world_image_id'])):
        raise ValueError('config_invalid')
    dataset = _inside(config['dataset_relative'])
    manifest = validate(dataset, _inside(config['manifest_relative']), config['manifest_sha256'])
    output = _inside(config['output_relative'], must_exist=False)
    if output.exists() or not output.parent.is_dir() or dataset in output.parents: raise ValueError('output_invalid')
    host_root = Path(os.environ['HOST_PROJECT_ROOT'])
    if not host_root.is_absolute(): raise ValueError('host_root_invalid')
    def host(path): return str(host_root / path.relative_to(ROOT))
    client = _docker()
    image = client.images.get('chi-agent-a-world:py312-review-20261025-01')
    if image.id != config['world_image_id']: raise ValueError('world_image_invalid')
    container_name = 'chi-v-world-' + config['run_id']
    try: client.containers.get(container_name)
    except Exception as exc:
        if getattr(exc, 'status_code', None) != 404: raise
    else: raise ValueError('resource_exists')
    output.mkdir(mode=0o700)
    artifacts = output / 'world-artifacts'; artifacts.mkdir(); (artifacts / 'workspaces').mkdir()
    started = time.monotonic()
    record = {'schema': 'chi-role-world-preflight-result-v1', 'run_id': config['run_id'], 'role': manifest['role'],
              'started_unix_ms': time.time_ns() // 1000000,
              'status': 'started', 'official_reward': None, 'model_requests': 0, 'capture': {}, 'cleanup': 'not_created'}
    def save(): (output / 'result.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
    save()
    world = None
    resource_identity = {'world_id': Path(manifest['world']['path']).stem, 'world_sha256': manifest['world']['sha256'],
        'files': {'fixtures/expectations.json': next(x for x in manifest['files'] if x['path'] == manifest['task_path'] + '/fixtures/expectations.json')}}
    if manifest['role'] == 'cm':
        resource_identity['files']['fixtures/manifest.json'] = next(x for x in manifest['files'] if x['path'] == manifest['task_path'] + '/fixtures/manifest.json')
    def capture(root):
        if manifest['role'] == 'cm':
            return capture_cm_review_input(world, root, config['run_id'], task_id=manifest['task_id'],
                                           role='cm', resource_identity=resource_identity)
        return _capture_review_input(world, root, config['run_id'], {}, task_id=manifest['task_id'],
                                     resource_identity=resource_identity)
    try:
        volumes = {host(dataset / manifest['task_path']): {'bind': f"/opt/chi-bench/tasks/{manifest['task_id']}", 'mode': 'ro'},
                   host(artifacts): {'bind': '/logs/artifacts', 'mode': 'rw'}}
        for entry in manifest['files']:
            if '/shared/worlds/' in entry['path']:
                volumes[host(dataset / entry['path'])] = {'bind': '/opt/chi-bench/worlds/' + Path(entry['path']).name, 'mode': 'ro'}
        if manifest['role'] == 'cm':
            supply = output / 'world-supply'; supply.mkdir(mode=0o700)
            reference = supply / 'tool_reference.md'
            shutil.copyfile(dataset / manifest['tool_reference_path'], reference)
            expected = next(entry['sha256'] for entry in manifest['files'] if entry['path'] == manifest['tool_reference_path'])
            if hashlib.sha256(reference.read_bytes()).hexdigest() != expected: raise RuntimeError('reference_copy_invalid')
            volumes[host(reference)] = {'bind': '/opt/chi-bench-task-assets/tool_reference.md', 'mode': 'ro'}
        environment = _task_environment(); environment['CHI_BENCH_TASK_ID'] = manifest['task_id']
        world = client.containers.create(image=image.id, name=container_name, command=['sleep', 'infinity'],
            environment=environment, volumes=volumes, network_mode='none', detach=True,
            labels={'org.chi-agent.v-owner': config['run_id']})
        record['world_id'] = world.id
        world.start(); record['readiness_seconds'] = round(wait_world(world), 3)
        record['capture']['initial'] = capture(output / 'initial-capture')
        record['capture']['before_resources'] = capture_resources(world, output / 'resource-snapshots', 'before')
        if (record['capture']['initial'].get('status') != 'ready'
                or any(item.get('status') != 'ready' for item in record['capture']['before_resources'].values())):
            raise RuntimeError('initial_capture_unavailable')
        deadline = time.monotonic() + 60
        mcp_started = time.monotonic()
        try:
            with _api_timeout(world.client, deadline):
                code, streams = world.exec_run(['python', '-c', MCP_PROGRAM, f"http://127.0.0.1:{PORTS[manifest['role']]}/mcp",
                                         PROBES[manifest['role']]], demux=True)
        finally:
            record['mcp_elapsed_ms'] = max(0, int((time.monotonic() - mcp_started) * 1000))
        data = streams[0] if isinstance(streams, tuple) else None
        if code != 0 or not isinstance(data, bytes) or len(data) > 16 * 1024 * 1024: raise RuntimeError('mcp_probe_unavailable')
        probe = json.loads(data)
        if type(probe) is not dict or set(probe) != {'tools_count', 'tool', 'response'}: raise RuntimeError('mcp_probe_unavailable')
        (output / 'mcp-response.json').write_bytes(data)
        record['mcp'] = {'tools_count': probe['tools_count'], 'tool': probe['tool'], 'response_file': 'mcp-response.json',
                         'response_sha256': hashlib.sha256(data).hexdigest()}
        record['capture']['after_resources'] = capture_resources(world, output / 'resource-snapshots', 'after')
        record['capture']['final'] = capture(output / 'final-capture')
        if (record['capture']['final'].get('status') != 'ready'
                or any(item.get('status') != 'ready' for item in record['capture']['after_resources'].values())):
            raise RuntimeError('final_capture_unavailable')
        record['resources_unchanged'] = all(record['capture']['before_resources'][side]['sha256'] ==
            record['capture']['after_resources'][side]['sha256'] for side in ('provider', 'payer'))
        if not record['resources_unchanged']: raise RuntimeError('resources_changed')
        cap = output / 'final-capture' / config['run_id']
        try:
            checks = _checks(json.loads((cap / 'exported_state.json').read_bytes()), json.loads((cap / 'expectations.json').read_bytes()))
            record['deterministic_checks'] = {'status': 'complete' if checks else 'not_applicable', 'checks': checks}
        except Exception:
            record['deterministic_checks'] = {'status': 'unavailable'}
        record['status'] = 'complete' if record['deterministic_checks']['status'] != 'unavailable' else 'incomplete'
    except Exception as exc:
        record['status'] = 'failed'
        code = str(exc)
        safe_codes = {'reference_copy_invalid', 'initial_capture_unavailable', 'mcp_probe_unavailable', 'final_capture_unavailable', 'resources_changed'}
        record['safe_error_code'] = code if code in safe_codes else 'world_preflight_failed'
    finally:
        if world is not None:
            try:
                logs = world.logs(stdout=True, stderr=True)
                if type(logs) is bytes and len(logs) <= 16 * 1024 * 1024:
                    (output / 'world-container.log').write_bytes(logs)
                    record['world_log'] = {'status': 'ready', 'sha256': hashlib.sha256(logs).hexdigest()}
                else: record['world_log'] = {'status': 'unavailable'}
            except Exception:
                record['world_log'] = {'status': 'unavailable'}
            if 'final' not in record['capture']:
                try:
                    if 'after_resources' not in record['capture']:
                        record['capture']['after_resources'] = capture_resources(world, output / 'resource-snapshots', 'after')
                    record['capture']['final'] = capture(output / 'final-capture')
                except Exception:
                    record['capture']['final'] = {'status': 'unavailable'}
            try:
                world.reload()
                if world.attrs.get('State', {}).get('Running'): world.stop(timeout=10)
                world.remove(force=False); record['cleanup'] = 'removed'
            except Exception:
                record['cleanup'] = 'failed'; record['status'] = 'incomplete'
        record['finished_unix_ms'] = time.time_ns() // 1000000
        record['elapsed_ms'] = max(0, int((time.monotonic() - started) * 1000))
        save()
    return 0 if record['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
