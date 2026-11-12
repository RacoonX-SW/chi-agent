"""Package-external validation of an explicitly frozen role resource set."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from chi_agent.evaluation_bundle import _check_components, _read_regular_bounded

ROLE_MAP = {'prior_auth_provider': ('provider', 'provider'),
            'prior_auth_um': ('payer', 'payer'),
            'care_management': ('care_manager', 'cm')}
SHA = re.compile(r'[0-9a-f]{64}')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}')
REQUEST_MIN = 1
REQUEST_MAX = 20


def bounded_request_count(count) -> bool:
    return type(count) is int and not isinstance(count, bool) and REQUEST_MIN <= count <= REQUEST_MAX


def validate(dataset: Path, manifest_path: Path, expected_manifest_sha256: str) -> dict:
    raw = _read_regular_bounded(_check_components(manifest_path, 'manifest_invalid', final_may_be_missing=False),
                                1024 * 1024, 'manifest_invalid')
    if not SHA.fullmatch(expected_manifest_sha256) or hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError('manifest_hash_invalid')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate_key')
            result[key] = value
        return result
    manifest = json.loads(raw, object_pairs_hook=unique)
    keys = {'schema', 'revision', 'task_id', 'family', 'actor', 'role', 'task_path', 'world',
            'files', 'instruction_path', 'tool_reference_path'}
    if (type(manifest) is not dict or set(manifest) != keys or manifest['schema'] != 'chi-role-resources-v1'
            or not re.fullmatch(r'[0-9a-f]{40}', manifest['revision'])
            or manifest['family'] not in ROLE_MAP or (manifest['actor'], manifest['role']) != ROLE_MAP[manifest['family']]
            or type(manifest['task_id']) is not str or not ID.fullmatch(manifest['task_id'])
            or manifest['task_path'] != f"{manifest['family']}/tasks/{manifest['task_id']}"
            or type(manifest['files']) is not list or not manifest['files']): raise ValueError('manifest_invalid')
    root = _check_components(Path(dataset), 'resource_invalid', final_may_be_missing=False)
    if not root.is_dir(): raise ValueError('resource_invalid')
    entries = {}
    for item in manifest['files']:
        if (type(item) is not dict or set(item) != {'path', 'size', 'sha256', 'visibility'}
                or type(item['path']) is not str or type(item['size']) is not int or not 0 <= item['size'] <= 64 * 1024 * 1024
                or type(item['sha256']) is not str or not SHA.fullmatch(item['sha256'])
                or item['visibility'] not in {'public', 'world_only'}): raise ValueError('resource_invalid')
        rel = Path(item['path'])
        if (rel.is_absolute() or str(rel) != item['path'] or any(p in {'.', '..'} or p.startswith('.') for p in rel.parts)
                or item['path'] in entries): raise ValueError('resource_path_invalid')
        path = _check_components(root / rel, 'resource_invalid', final_may_be_missing=False)
        content = _read_regular_bounded(path, 64 * 1024 * 1024, 'resource_invalid', expected_size=item['size'])
        if hashlib.sha256(content).hexdigest() != item['sha256']: raise ValueError('resource_hash_invalid')
        entries[item['path']] = item
    world = manifest['world']
    if (type(world) is not dict or set(world) != {'path', 'sha256', 'source'}
            or world['source'] not in {'shared', 'per_task'} or world['path'] not in entries
            or entries[world['path']]['visibility'] != 'world_only' or entries[world['path']]['sha256'] != world['sha256']):
        raise ValueError('world_invalid')
    task = manifest['task_path'] + '/'
    pa_worlds = {'prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json',
                 'prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json'}
    cm_world = 'care_management/shared/worlds/healthverse-cm-curated25-v1.json'
    cm_ref = 'care_management/shared/tool_reference.md'
    if manifest['role'] == 'cm':
        allowed_shared = {cm_world, cm_ref}
        if world['source'] != 'shared' or world['path'] != cm_world or manifest['tool_reference_path'] != cm_ref:
            raise ValueError('world_invalid')
    else:
        allowed_shared = pa_worlds
        if world['source'] != 'shared' or world['path'] not in pa_worlds or not pa_worlds <= set(entries):
            raise ValueError('world_invalid')
        if manifest['tool_reference_path'] != task + 'tool_reference.md': raise ValueError('public_input_invalid')
    if any(not name.startswith(task) and name not in allowed_shared for name in entries): raise ValueError('resource_path_invalid')
    if any(entries[name]['visibility'] != 'world_only' for name in allowed_shared.intersection(entries) if name != cm_ref):
        raise ValueError('world_invalid')
    fixture_manifest = task + 'fixtures/manifest.json'
    if fixture_manifest not in entries or entries[fixture_manifest]['visibility'] != 'world_only': raise ValueError('world_invalid')
    task_data = json.loads(_read_regular_bounded(root / fixture_manifest, 16 * 1024 * 1024, 'resource_invalid'), object_pairs_hook=unique)
    world_data = json.loads(_read_regular_bounded(root / world['path'], 64 * 1024 * 1024, 'resource_invalid'), object_pairs_hook=unique)
    if (type(task_data) is not dict or type(world_data) is not dict or type(task_data.get('world_id')) is not str
            or task_data['world_id'] != world_data.get('world_id')
            or Path(world['path']).stem != task_data['world_id']): raise ValueError('world_invalid')
    for key in ('instruction_path', 'tool_reference_path'):
        if manifest[key] not in entries or entries[manifest[key]]['visibility'] != 'public': raise ValueError('public_input_invalid')
    if manifest['instruction_path'] != task + 'instruction.md': raise ValueError('public_input_invalid')
    expected_public = {manifest['instruction_path'], manifest['tool_reference_path']}
    request_prefix = task + 'fixtures/request/'
    pdfs = [name for name in entries if name.startswith(request_prefix)]
    if manifest['role'] == 'payer':
        if (not bounded_request_count(len(pdfs))
                or any(not n.lower().endswith('.pdf') or '/' in n[len(request_prefix):] for n in pdfs)):
            raise ValueError('request_inputs_invalid')
    elif pdfs:
        raise ValueError('request_inputs_invalid')
    expected_public.update(pdfs)
    base_task = {task + 'instruction.md', task + 'task.toml', task + 'fixtures/manifest.json',
                 task + 'fixtures/expectations.json'}
    if manifest['role'] != 'cm': base_task.add(task + 'tool_reference.md')
    if {name for name in entries if name.startswith(task)} != base_task | set(pdfs):
        raise ValueError('task_closure_invalid')
    if {name for name, entry in entries.items() if entry['visibility'] == 'public'} != expected_public:
        raise ValueError('public_input_invalid')
    task_dir = root / manifest['task_path']
    actual = set()
    for path in task_dir.rglob('*'):
        if path.is_symlink(): raise ValueError('resource_path_invalid')
        if path.is_file(): actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir(): raise ValueError('resource_path_invalid')
    if actual != {name for name in entries if name.startswith(task)}: raise ValueError('task_closure_invalid')
    return manifest
