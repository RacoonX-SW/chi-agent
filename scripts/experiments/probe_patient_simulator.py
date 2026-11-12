"""Explicit, standalone two-turn synthetic patient probe; never in a bundle."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args()
    raw = args.config.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.config_sha256 or len(raw) > 16384:
        raise ValueError('probe_config_invalid')
    c = json.loads(raw)
    if (type(c) is not dict or set(c) != {'schema', 'bundle', 'bundle_sha256', 'runtime_identity', 'q_root',
            'run', 'evaluation', 'attempt', 'output', 'probe_sha256', 'adapter_sha256'}
            or c['schema'] != 'chi-synthetic-patient-probe-v1'
            or any(type(c[k]) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', c[k])
                   for k in ('run', 'evaluation', 'attempt'))):
        raise ValueError('probe_config_invalid')
    probe = Path(__file__).resolve()
    adapter = probe.parents[1] / 'development/patient_adapter.py'
    for path, key in [(probe, 'probe_sha256'), (adapter, 'adapter_sha256')]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != c[key]: raise ValueError('probe_source_invalid')
    bundle = Path(c['bundle'])
    if not bundle.is_absolute(): raise ValueError('probe_bundle_invalid')
    sys.path.insert(0, str(bundle / 'scripts'))
    from chi_agent.cli import _identity
    from chi_agent.local_history import acquire_existing_history
    from chi_agent.journal import ChiJournal
    from chi_agent.runtime_policy import FEE_POLICY
    from chi_agent.evaluation_bundle import _check_components
    identity, _ = _identity(c['bundle_sha256'])
    if identity != c['runtime_identity']: raise ValueError('probe_identity_invalid')
    qroot = _check_components(Path(c['q_root']), 'probe_root_invalid', final_may_be_missing=False)
    output = _check_components(Path(c['output']), 'probe_output_invalid')
    if not qroot.is_absolute() or not output.is_absolute() or output.exists() or not output.parent.is_dir():
        raise ValueError('probe_output_invalid')
    if output == qroot or qroot in output.parents or output in qroot.parents or output == bundle or bundle in output.parents:
        raise ValueError('probe_output_overlap')
    output.mkdir(mode=0o700)
    q = None
    journal = None
    try:
        q = acquire_existing_history(qroot)
        journal = ChiJournal(qroot / 'chi-evaluation', identity=identity, evaluation=c['evaluation'],
            task='synthetic-patient-probe', attempt=c['attempt'], run=c['run'], kind='patient_probe', require_b=True,
            launch={'kind': 'patient_probe', 'aux_contract': 'patient-simulator-v1', 'fee_policy': FEE_POLICY,
                    'probe_config_sha256': args.config_sha256})
        secret = os.environ.get('OPENCODE_API_KEY')
        if not secret: raise ValueError('probe_credential_missing')
        result = asyncio.run(_run(journal, secret))
        (output / 'result.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
        journal.finish('complete')
        (output / 'completion.json').write_text(json.dumps({'status': 'complete', 'official_reward': None}) + '\n')
    except BaseException as exc:
        if journal is not None and journal.run['status'] == 'started':
            try: journal.finish('failed', 'chi_patient_probe_failed')
            except Exception: pass
        code = getattr(exc, 'code', 'chi_patient_probe_failed')
        if type(code) is not str or not re.fullmatch(r'[a-z0-9_]{1,64}', code): code = 'chi_patient_probe_failed'
        (output / 'failure.json').write_text(json.dumps({'schema': 'chi-synthetic-patient-probe-result-v1',
            'status': 'failed', 'safe_error_code': code, 'official_reward': None}, sort_keys=True) + '\n')
        raise SystemExit(code) from None
    finally:
        if journal is not None: journal.close()
        if q is not None: q.close()


async def _run(journal, secret, *, lower=None):
    import httpx
    from openai import AsyncOpenAI
    from chi_bench.conversation.session import ConversationSession
    from scripts.development.patient_adapter import adapter_class
    from chi_agent.auxiliary_transport import AuxiliaryTransport
    session_header = 'chi-' + uuid.uuid4().hex
    transport = AuxiliaryTransport(journal, secret, session_header, lower or httpx.AsyncHTTPTransport(retries=0, verify=True),
                                   asyncio.Lock(), lambda: None)
    client = AsyncOpenAI(api_key=secret, base_url='https://opencode.ai/inference/go/openai/v1', max_retries=0,
        default_headers={'User-Agent': 'chi-agent', 'X-OpenCode-Session': session_header},
        http_client=httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False))
    async def call(_session, messages):
        response = await client.chat.completions.create(model='deepseek-v4.1-flash', messages=messages,
            max_tokens=8192, reasoning_effort='high', extra_body={'thinking': {'type': 'enabled'}})
        return {'content': response.choices[0].message.content,
                'token_usage': response.usage.prompt_tokens + response.usage.completion_tokens}
    try:
        simulator = adapter_class(call)(scenario={'reason_for_call': 'Arrange a fictional appointment'},
            clinical_context='', patient_profile='You are a fictional person arranging an appointment. No clinical information is involved.')
        now = datetime.now(timezone.utc)
        session = ConversationSession(session_id='synthetic-session', case_id='synthetic-case', patient_name='Fictional',
                                      reason_for_call='appointment', created_at=now)
        for message in ('Hello, would you prefer a morning appointment?', 'Would Tuesday work for you?'):
            session.add_care_manager_message(message, datetime.now(timezone.utc))
            response = await simulator.generate_response(session)
            session.add_patient_message(response.content, datetime.now(timezone.utc), token_usage=response.token_usage,
                                        generation_time_seconds=response.generation_time_seconds)
            if response.stopped:
                session.terminate('patient_ended')
                break
        return {'schema': 'chi-synthetic-patient-probe-result-v1', 'status': 'responses_received',
                'responses': len(journal.run['requests']), 'official_reward': None,
                'condition': 'development-go-patient-simulator', 'session': session.model_dump(mode='json')}
    finally:
        await client.close()


if __name__ == '__main__':
    main()
