"""Capture the CM export and its independently evidenced initialization world."""
from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import time
from pathlib import Path

from scripts.development.world_environment import _api_timeout
from chi_agent.provider_transport import _reject_symlink_ancestors
from chi_agent.evaluation_bundle import _fsync_dir, _write_exclusive

CM_LISTS = frozenset({'cm_cases', 'cm_referrals', 'cm_chart_reviews', 'cm_outreach_records',
    'cm_conversation_sessions', 'cm_assessments', 'cm_care_plans', 'audit_logs', 'state_transitions'})
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}')
SHA = re.compile(r'[0-9a-f]{64}')
EXPORT_PROGRAM = ("import sys,urllib.request; "
    "r=urllib.request.urlopen('http://127.0.0.1:8023/export',timeout=20); "
    "b=r.read(16777217); sys.exit(2) if len(b)>16777216 else sys.stdout.buffer.write(b)")


def _object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    if type(value) is not dict: raise ValueError('object_invalid')
    return value


def capture_cm_review_input(world, capture_root: Path, run_id: str, *, task_id: str,
                            role: str, resource_identity: dict) -> dict:
    """Capture exact export bytes; world identity comes from actual mounted files."""
    deadline = time.monotonic() + 60
    try:
        if (role != 'cm' or not ID.fullmatch(run_id) or not ID.fullmatch(task_id)
                or type(resource_identity) is not dict or set(resource_identity) != {'world_id', 'world_sha256', 'files'}
                or type(resource_identity['world_id']) is not str or not ID.fullmatch(resource_identity['world_id'])
                or type(resource_identity['world_sha256']) is not str or not SHA.fullmatch(resource_identity['world_sha256'])):
            raise ValueError('identity_invalid')
        files = resource_identity['files']
        if type(files) is not dict or set(files) != {'fixtures/manifest.json', 'fixtures/expectations.json'}:
            raise ValueError('identity_invalid')
        for entry in files.values():
            if type(entry) is not dict or type(entry.get('sha256')) is not str or not SHA.fullmatch(entry['sha256']):
                raise ValueError('identity_invalid')
        with _api_timeout(world.client, deadline):
            code, exported = world.exec_run(['python', '-c', EXPORT_PROGRAM], demux=False)
        if time.monotonic() > deadline or code != 0 or type(exported) is not bytes or len(exported) > 16 * 1024 * 1024:
            raise ValueError('export_invalid')
        data = _object(exported)
        if (set(data) != CM_LISTS | {'task_actor'} or data['task_actor'] != 'care_manager'
                or any(type(data[name]) is not list or any(type(item) is not dict for item in data[name]) for name in CM_LISTS)):
            raise ValueError('export_invalid')

        def archive_file(path, filename, maximum):
            chunks = bytearray()
            archive = None
            try:
                with _api_timeout(world.client, deadline):
                    archive, _ = world.get_archive(path)
                    for chunk in archive:
                        if time.monotonic() > deadline: raise TimeoutError
                        chunks.extend(chunk)
                        if len(chunks) > maximum + 1024 * 1024: raise ValueError('archive_too_large')
            finally:
                if archive is not None and callable(getattr(archive, 'close', None)): archive.close()
            if time.monotonic() > deadline: raise TimeoutError
            with tarfile.open(fileobj=io.BytesIO(chunks), mode='r:*') as tar:
                members = tar.getmembers()
                if len(members) != 1 or members[0].name != filename or not members[0].isfile() or members[0].size > maximum:
                    raise ValueError('archive_invalid')
                handle = tar.extractfile(members[0])
                if handle is None: raise ValueError('archive_invalid')
                raw = handle.read(maximum + 1)
            if len(raw) > maximum: raise ValueError('archive_invalid')
            return raw

        fixture = archive_file(f'/opt/chi-bench/tasks/{task_id}/fixtures/manifest.json', 'manifest.json', 16 * 1024 * 1024)
        expectations = archive_file(f'/opt/chi-bench/tasks/{task_id}/fixtures/expectations.json', 'expectations.json', 16 * 1024 * 1024)
        filename = resource_identity['world_id'] + '.json'
        shared_world = archive_file('/opt/chi-bench/worlds/' + filename, filename, 64 * 1024 * 1024)
        fixture_data, world_data = _object(fixture), _object(shared_world)
        _object(expectations)
        if (fixture_data.get('task_actor') != 'care_manager' or fixture_data.get('task_id') != task_id
                or fixture_data.get('world_id') != resource_identity['world_id']
                or world_data.get('world_id') != resource_identity['world_id']
                or hashlib.sha256(fixture).hexdigest() != files['fixtures/manifest.json']['sha256']
                or hashlib.sha256(expectations).hexdigest() != files['fixtures/expectations.json']['sha256']
                or hashlib.sha256(shared_world).hexdigest() != resource_identity['world_sha256']):
            raise ValueError('world_identity_invalid')
        capture_root = Path(capture_root)
        _reject_symlink_ancestors(capture_root, 'cm_capture_invalid')
        capture_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _reject_symlink_ancestors(capture_root, 'cm_capture_invalid')
        target = capture_root / run_id
        target.mkdir(mode=0o700, exist_ok=False)
        payloads = {'exported_state.json': exported, 'fixture_manifest.json': fixture,
                    'expectations.json': expectations, 'shared_world.json': shared_world}
        for name, raw in payloads.items(): _write_exclusive(target / name, raw)
        _fsync_dir(target)
        manifest = {'schema': 'chi-cm-review-capture-v1', 'status': 'ready', 'run_id': run_id, 'task_id': task_id,
                    'runtime_role': role, 'world_container_id': world.id, 'world_id': resource_identity['world_id'],
                    'world_identity_source': 'mounted_fixture_manifest_and_world_file',
                    'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()},
                    'official_reward': None}
        raw_manifest = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
        _write_exclusive(target / 'manifest.json', raw_manifest)
        _fsync_dir(target); _fsync_dir(capture_root)
        return {'status': 'ready', 'manifest_sha256': hashlib.sha256(raw_manifest).hexdigest()}
    except Exception:
        return {'status': 'unavailable', 'safe_error_code': 'cm_review_input_capture_failed'}
