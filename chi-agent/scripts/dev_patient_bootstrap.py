"""Explicit opt-in for a disposable development world only."""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from dev_patient_adapter import adapter_class


def install(*, broker_url, capability, run_id):
    parsed = urlsplit(broker_url)
    if (parsed.scheme != 'http' or not parsed.hostname or parsed.path != '/patient' or parsed.query
            or parsed.fragment or parsed.username or parsed.password or not capability or not run_id):
        raise ValueError('development_patient_bootstrap_invalid')
    from chi_bench.conversation import patient_simulator
    original = patient_simulator.PatientSimulator

    async def call(session, messages):
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                transport=httpx.AsyncHTTPTransport(retries=0), timeout=httpx.Timeout(430, connect=10)) as client:
            response = await client.post(broker_url, headers={'x-chi-capability': capability},
                json={'run': run_id, 'session': session, 'messages': messages})
            response.raise_for_status()
            return response.json()

    patient_simulator.PatientSimulator = adapter_class(call)
    return lambda: setattr(patient_simulator, 'PatientSimulator', original)
