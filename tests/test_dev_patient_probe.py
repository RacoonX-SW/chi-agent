import hashlib
import json
import sys
from pathlib import Path

import pytest

import scripts.experiments.probe_patient_simulator as probe
import chi_agent.cli as go_chi_entry
import chi_agent.accounting.journal as go_chi_journal
import chi_agent.accounting.local_history as go_chi_local


def test_missing_credential_leaves_safe_failure(tmp_path, monkeypatch):
    bundle = tmp_path / 'bundle'; (bundle / 'scripts').mkdir(parents=True)
    qroot = tmp_path / 'q'; qroot.mkdir()
    output = tmp_path / 'output'
    root = Path(probe.__file__).parent
    source_hash = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
    config = {'schema': 'chi-synthetic-patient-probe-v1', 'bundle': str(bundle), 'bundle_sha256': 'a' * 64,
        'runtime_identity': 'b' * 64, 'q_root': str(qroot), 'run': 'r', 'evaluation': 'e', 'attempt': 'a',
        'output': str(output), 'probe_sha256': source_hash('probe_patient_simulator.py'),
        'adapter_sha256': source_hash('../development/patient_adapter.py')}
    path = tmp_path / 'config.json'; raw = json.dumps(config).encode(); path.write_bytes(raw)
    monkeypatch.setattr(go_chi_entry, '_identity', lambda _: ('b' * 64, {}))
    q = type('Q', (), {'close': lambda self: None})()
    monkeypatch.setattr(go_chi_local, 'acquire_existing_history', lambda _: q)
    class Journal:
        run = {'status': 'started'}
        def __init__(self, *args, **kwargs): pass
        def finish(self, status, error): self.run['status'] = status
        def close(self): pass
    monkeypatch.setattr(go_chi_journal, 'ChiJournal', Journal)
    monkeypatch.delenv('OPENCODE_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['probe', '--config', str(path), '--config-sha256', hashlib.sha256(raw).hexdigest()])
    with pytest.raises(SystemExit): probe.main()
    failure = json.loads((output / 'failure.json').read_text())
    assert failure == {'schema': 'chi-synthetic-patient-probe-result-v1', 'status': 'failed',
                       'safe_error_code': 'chi_patient_probe_failed', 'official_reward': None}
