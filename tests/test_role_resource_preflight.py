import hashlib
import json
from pathlib import Path

import pytest

from role_resource_preflight import validate


def _case(tmp_path, count):
    root = tmp_path / 'data'
    prefix = 'prior_auth_um/tasks/example'
    files = {f'{prefix}/instruction.md': ('public', b'instruction'),
             f'{prefix}/tool_reference.md': ('public', b'reference'),
             f'{prefix}/task.toml': ('world_only', b''),
             f'{prefix}/fixtures/manifest.json': ('world_only', b'{"world_id":"healthverse-pa-v2-payer"}'),
             f'{prefix}/fixtures/expectations.json': ('world_only', b'{}'),
             'prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json': ('world_only', b'{}'),
             'prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json': ('world_only', b'{"world_id":"healthverse-pa-v2-payer"}')}
    for n in range(count):
        files[f'{prefix}/fixtures/request/{n}.pdf'] = ('public', b'pdf')
    for name, (_, raw) in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    entries = [{'path': name, 'visibility': visibility, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
               for name, (visibility, raw) in files.items()]
    world = 'prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json'
    manifest = {'schema': 'chi-role-resources-v1', 'revision': 'a' * 40, 'task_id': 'example',
                'family': 'prior_auth_um', 'actor': 'payer', 'role': 'payer', 'task_path': prefix,
                'world': {'path': world, 'sha256': hashlib.sha256(files[world][1]).hexdigest(),
                          'source': 'shared'},
                'files': entries, 'instruction_path': f'{prefix}/instruction.md',
                'tool_reference_path': f'{prefix}/tool_reference.md'}
    path = tmp_path / 'manifest.json'
    raw = json.dumps(manifest).encode()
    path.write_bytes(raw)
    return root, path, hashlib.sha256(raw).hexdigest(), prefix


def test_payer_four_file_closure_and_hash(tmp_path):
    root, path, digest, prefix = _case(tmp_path, 4)
    assert validate(root, path, digest)['role'] == 'payer'
    (root / prefix / 'fixtures/request/extra.txt').write_text('extra')
    with pytest.raises(ValueError, match='task_closure_invalid'):
        validate(root, path, digest)
    (root / prefix / 'fixtures/request/extra.txt').unlink()
    (root / prefix / 'fixtures/request/0.pdf').write_bytes(b'changed')
    with pytest.raises(Exception):
        validate(root, path, digest)


def test_payer_five_file_closure(tmp_path):
    root, path, digest, _ = _case(tmp_path, 5)
    assert validate(root, path, digest)['role'] == 'payer'


@pytest.mark.parametrize('count', [0, 21])
def test_payer_out_of_bounds_request_count_is_rejected(tmp_path, count):
    root, path, digest, _ = _case(tmp_path, count)
    with pytest.raises(ValueError, match='request_inputs_invalid'):
        validate(root, path, digest)


def test_missing_file_after_manifest_is_rejected(tmp_path):
    root, path, digest, prefix = _case(tmp_path, 5)
    (root / prefix / 'fixtures/request/0.pdf').unlink()
    with pytest.raises(Exception):
        validate(root, path, digest)
