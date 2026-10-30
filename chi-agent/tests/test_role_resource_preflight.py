import hashlib
import json
from pathlib import Path

import pytest

from role_resource_preflight import validate


def test_payer_closure_and_hash(tmp_path):
    root = tmp_path / 'data'
    prefix = 'prior_auth_um/tasks/example'
    files = {f'{prefix}/instruction.md': ('public', b'instruction'),
             f'{prefix}/tool_reference.md': ('public', b'reference'),
             f'{prefix}/task.toml': ('world_only', b''),
             f'{prefix}/fixtures/manifest.json': ('world_only', b'{"world_id":"healthverse-pa-v2-payer"}'),
             f'{prefix}/fixtures/expectations.json': ('world_only', b'{}'),
             'prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json': ('world_only', b'{}'),
             'prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json': ('world_only', b'{"world_id":"healthverse-pa-v2-payer"}')}
    for n in range(4): files[f'{prefix}/fixtures/request/{n}.pdf'] = ('public', b'pdf')
    for name, (_, raw) in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    entries = [{'path': name, 'visibility': visibility, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
               for name, (visibility, raw) in files.items()]
    world = 'prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json'
    m = {'schema': 'chi-role-resources-v1', 'revision': 'a' * 40, 'task_id': 'example',
         'family': 'prior_auth_um', 'actor': 'payer', 'role': 'payer', 'task_path': prefix,
         'world': {'path': world, 'sha256': hashlib.sha256(files[world][1]).hexdigest(), 'source': 'shared'},
         'files': entries, 'instruction_path': f'{prefix}/instruction.md', 'tool_reference_path': f'{prefix}/tool_reference.md'}
    path = tmp_path / 'manifest.json'
    raw = json.dumps(m).encode(); path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    assert validate(root, path, digest)['role'] == 'payer'
    (root / prefix / 'fixtures/request/extra.txt').write_text('extra')
    with pytest.raises(ValueError, match='task_closure_invalid'): validate(root, path, digest)
    (root / prefix / 'fixtures/request/extra.txt').unlink()
    (root / prefix / 'fixtures/request/0.pdf').write_bytes(b'changed')
    with pytest.raises(Exception): validate(root, path, digest)
