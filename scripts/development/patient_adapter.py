"""Opt-in development adapter; never included in an evaluation bundle."""
from __future__ import annotations

import time

from chi_bench.conversation.persona import build_system_prompt
from chi_bench.conversation.patient_simulator import PatientSimulator, SimulatorResponse


def adapter_class(call_broker):
    """Construct a class for explicit injection in a dedicated development world."""
    class DevelopmentPatientSimulator:
        def __init__(self, *, scenario, clinical_context, patient_profile=None, persona_config=None, model=None, voice=False):
            if patient_profile is None or model is not None:
                raise ValueError('development_patient_configuration_invalid')
            self.prompt = build_system_prompt(scenario=scenario, clinical_context=clinical_context,
                persona_config=persona_config, persona_contract_text=patient_profile, voice=voice)

        async def generate_response(self, session):
            messages = [{'role': 'system', 'content': self.prompt}]
            messages.extend({'role': msg.flipped_api_role, 'content': msg.content} for msg in session.messages)
            start = time.monotonic()
            result = await call_broker(session.session_id, messages)
            if (type(result) is not dict or set(result) != {'content', 'token_usage'}
                    or type(result['content']) is not str or not result['content'].strip()
                    or type(result['token_usage']) is not int or result['token_usage'] < 0):
                raise ValueError('development_patient_response_invalid')
            raw = result['content']
            stopped = PatientSimulator.detect_stop_signal(raw)
            content = PatientSimulator.strip_stop_signal(raw) if stopped else raw
            return SimulatorResponse(content=content, stopped=stopped, token_usage=result['token_usage'],
                                     generation_time_seconds=time.monotonic() - start)

    return DevelopmentPatientSimulator
