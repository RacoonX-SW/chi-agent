import asyncio
import contextvars
import hashlib
import json

import httpx
import pytest

import chi_agent.execution_policy as policies
import chi_agent.provider_transport as transport
import scripts.development.run_development_legacy as live
import chi_agent.model_runner_adapter as adapter
import chi_agent.patient_identity_binding as binding
from test_live_development import _adopt_synthetic_history


def prepared(tmp_path, handler):
    _adopt_synthetic_history(tmp_path, tmp_path)
    profile = live.load_profile()
    journal = live.RealDevelopmentJournal(tmp_path, "ceiling", profile=profile, policy=policies.load_real_development_policy())
    ledger = adapter.Ledger("synthetic")
    context = contextvars.ContextVar("synthetic-role", default=None)
    guard = transport.GuardedTransport(profile=profile, journal=journal, lower=httpx.MockTransport(handler),
             ledger=ledger, cap_cny=None, validate_response=lambda _payload: None,
             allowed_tool_names=set(), confirmation_context=context.get)
    return profile, journal, ledger, context, guard


def wire():
    evidence = '{"synthetic":"public"}'
    body = {"model": "deepseek-flash", "messages": [{"role": "system", "content": binding.PROMPT},
              {"role": "user", "content": evidence}], "max_tokens": 32768,
            "response_format": {"type": "json_object"}, "thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    return body, ("patient_confirmation", hashlib.sha256(evidence.encode()).hexdigest())


def request(body):
    return httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions", content=json.dumps(body).encode())


def test_raised_ceiling_requires_internal_context_and_exact_wire(tmp_path):
    profile, journal, _, context, guard = prepared(tmp_path, lambda req: httpx.Response(500, request=req))
    body, role = wire()
    with pytest.raises(transport.GuardFailure, match="output_limit"):
        guard._validate_request(request(body), request(body).content)
    forged = {**body, "purpose": "patient_confirmation"}
    with pytest.raises(transport.GuardFailure):
        guard._validate_request(request(forged), request(forged).content)
    token = context.set(role)
    try:
        assert guard._validate_request(request(body), request(body).content) == body
        for changed in ({**body, "tools": []}, {**body, "max_tokens": 8192}, {**body, "max_tokens": 32768.0},
                        {**body, "messages": [{"role": "system", "content": "forged"}, body["messages"][1]]},
                        {**body, "messages": [body["messages"][0], {"role": "user", "content": "forged"}]}):
            with pytest.raises(transport.GuardFailure):
                guard._validate_request(request(changed), request(changed).content)
    finally:
        context.reset(token)
        journal.close()


@pytest.mark.parametrize("failure", ["timeout", "cancel", "missing_usage"])
def test_confirmation_unknown_retains_valid_32768_pending(tmp_path, failure):
    def handler(req):
        if failure == "timeout": raise httpx.ReadTimeout("synthetic")
        if failure == "cancel": raise asyncio.CancelledError()
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": []}, request=req)
    profile, journal, ledger, context, guard = prepared(tmp_path, handler)
    body, role = wire()
    token = context.set(role)
    try:
        error_type = {"timeout": httpx.ReadTimeout, "cancel": asyncio.CancelledError,
                      "missing_usage": transport.GuardFailure}[failure]
        with pytest.raises(error_type):
            asyncio.run(guard.handle_async_request(request(body)))
        state = live._read_json(tmp_path / "accounting.json")
        assert state["pending"]["purpose"] == "patient_confirmation"
        assert state["pending"]["output_reserve_tokens"] == 32768
        assert state["pending"]["status"] == "unknown" and state["usage_complete"] is False
        assert live._validate_accounting_state(state, profile=profile, execution_identity=live._execution_identity(k=True)) is None
        assert ledger.error_code == {"timeout": "transport_timeout", "cancel": "transport_cancelled",
                                     "missing_usage": "usage_unknown"}[failure]
        with pytest.raises(transport.GuardFailure):
            asyncio.run(guard.handle_async_request(request(body)))
    finally:
        context.reset(token)
        journal.close()


def test_settlement_evidence_written_before_pending_clear(tmp_path, monkeypatch):
    profile, journal, _, _, _ = prepared(tmp_path, lambda req: httpx.Response(500, request=req))
    body, _ = wire()
    req = request(body)
    journal.reserve(profile, req, body, req.content, 32768, 1, purpose="patient_confirmation")
    pending = dict(journal.state["pending"])
    original = live._atomic_json
    def fail_run_write(path, value, **kwargs):
        if path == journal.run_path:
            raise OSError("synthetic crash")
        return original(path, value, **kwargs)
    monkeypatch.setattr(live, "_atomic_json", fail_run_write)
    with pytest.raises(OSError):
        journal.settle(profile.output_price / 1_000_000, 0, 1, response_metadata={
            "purpose": "patient_confirmation", "round": 1, "request_sha256": pending["request_sha256"],
            "finish_reason": "length", "content_present": False})
    assert live._read_json(journal.state_path)["pending"] == pending
    assert live._read_json(journal.state_path)["usage_complete"] is False
    journal.close()


def test_crash_after_journal_settlement_keeps_disk_pending(tmp_path, monkeypatch):
    profile, journal, _, _, _ = prepared(tmp_path, lambda req: httpx.Response(500, request=req))
    body, _ = wire()
    req = request(body)
    journal.reserve(profile, req, body, req.content, 32768, 1, purpose="patient_confirmation")
    pending = dict(journal.state["pending"])
    original = live._atomic_json
    def fail_state_write(path, value, **kwargs):
        if path == journal.state_path:
            raise OSError("synthetic crash")
        return original(path, value, **kwargs)
    monkeypatch.setattr(live, "_atomic_json", fail_state_write)
    with pytest.raises(OSError):
        journal.settle(profile.output_price / 1_000_000, 0, 1, response_metadata={
            "purpose": "patient_confirmation", "round": 1, "request_sha256": pending["request_sha256"],
            "finish_reason": "length", "content_present": False})
    saved = live._read_json(journal.run_path)["requests"][0]
    assert saved["status"] == "settled" and saved["output_tokens"] == 1
    assert saved["response_metadata"]["request_sha256"] == pending["request_sha256"]
    assert live._read_json(journal.state_path)["pending"] == pending
    journal.close()
