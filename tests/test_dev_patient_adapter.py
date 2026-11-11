import asyncio
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import httpx

HAVE_ANTHROPIC = importlib.util.find_spec("anthropic") is not None
if HAVE_ANTHROPIC:
    from chi_bench.conversation.message import STOP_SIGNAL
    from chi_bench.conversation.persona import build_system_prompt
    from chi_bench.conversation.patient_simulator import PatientSimulator
    from chi_bench.conversation.session import ConversationSession
    from dev_patient_adapter import adapter_class
    from dev_patient_bootstrap import install
else:
    STOP_SIGNAL = build_system_prompt = PatientSimulator = ConversationSession = None
    adapter_class = install = None


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_official_prompt_role_flip_and_stop_without_anthropic():
    asyncio.run(_test_adapter())


async def _test_adapter():
    captured = []
    async def broker(session, messages):
        captured.append((session, messages))
        return {'content': 'Goodbye ' + STOP_SIGNAL, 'token_usage': 4}
    scenario = {'reason_for_call': 'appointment'}
    cls = adapter_class(broker)
    instance = cls(scenario=scenario, clinical_context='', patient_profile='Synthetic persona')
    now = datetime.now(timezone.utc)
    session = ConversationSession(session_id='ses', case_id='case', patient_name='test',
                                  reason_for_call='appointment', created_at=now)
    session.add_care_manager_message('Hello', now)
    session.add_patient_message('Hi', now)
    session.add_care_manager_message('Bye', now)
    answer = await instance.generate_response(session)
    assert captured[0][1] == [{'role': 'system', 'content': build_system_prompt(scenario=scenario,
        clinical_context='', persona_contract_text='Synthetic persona')}, {'role': 'user', 'content': 'Hello'},
        {'role': 'assistant', 'content': 'Hi'}, {'role': 'user', 'content': 'Bye'}]
    assert answer.content == 'Goodbye' and answer.stopped and answer.token_usage == 4


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_bootstrap_is_explicit_and_reversible():
    from chi_bench.conversation import patient_simulator
    assert patient_simulator.PatientSimulator is PatientSimulator
    restore = install(broker_url='http://broker:8000/patient', capability='synthetic-capability', run_id='r')
    assert patient_simulator.PatientSimulator is not PatientSimulator
    restore()
    assert patient_simulator.PatientSimulator is PatientSimulator


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_synthetic_probe_stops_without_second_call():
    asyncio.run(_test_probe())


@unittest.skipUnless(HAVE_ANTHROPIC, "anthropic is not installed")
def test_world_cb_installs_before_same_process_serve():
    import os
    import runpy
    import sys
    from types import ModuleType
    from unittest.mock import patch
    from chi_bench.conversation import patient_simulator
    calls = []
    fake = ModuleType('chi_bench.cli')
    fake.app = lambda args: calls.append((args, patient_simulator.PatientSimulator is not PatientSimulator))
    with tempfile.TemporaryDirectory() as d:
        cap = Path(d) / 'cap'; cap.write_text('c' * 32)
        env = {'CHI_DEV_PATIENT_SIMULATOR': 'go-v1', 'CHI_DEV_CAPABILITY_FILE': str(cap),
               'CHI_DEV_RUN_ID': 'r', 'CHI_DEV_BROKER_URL': 'http://broker:8000/patient'}
        script = Path(__file__).resolve().parents[1] / 'scripts/dev_patient_cb'
        argv = [str(script), 'serve', '--host', '0.0.0.0', '--port', '8023', '--no-frontend']
        try:
            with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {'chi_bench.cli': fake}), patch.object(sys, 'argv', argv):
                runpy.run_path(str(script), run_name='__main__')
            assert calls == [(argv[1:], True)]
        finally:
            patient_simulator.PatientSimulator = PatientSimulator


async def _test_probe():
    from dev_patient_probe import _run
    from go_chi_journal import ChiJournal
    with tempfile.TemporaryDirectory() as d:
        journal = ChiJournal(Path(d), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r',
                             kind='patient_probe', launch={'aux_contract': 'patient-simulator-v1'})
        calls = []
        async def answer(req):
            calls.append(req)
            return httpx.Response(200, request=req, json={'id': 'test', 'object': 'chat.completion', 'created': 1,
                'model': 'deepseek-v4.1-flash', 'usage': {'prompt_tokens': 1, 'completion_tokens': 1,
                'total_tokens': 2, 'cost': 0, 'opencode': {'billing_source': 'go', 'list_cost': 0, 'allowance': 0}},
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'Bye ' + STOP_SIGNAL}}]})
        result = await _run(journal, 'synthetic-secret', lower=httpx.MockTransport(answer))
        assert len(calls) == 1 and result['responses'] == 1 and result['session']['termination_reason'] == 'patient_ended'
        journal.finish('complete'); journal.close()
