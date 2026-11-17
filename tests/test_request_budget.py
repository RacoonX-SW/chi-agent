import asyncio
import contextvars
import hashlib
import json

import httpx
import pytest

import chi_agent.accounting.execution_policy as policies
import chi_agent.models.provider_transport as transport
import scripts.development.run_development_legacy as live
import chi_agent.evaluation.model_runner_adapter as adapter
import chi_agent.roles.patient_identity_binding as patient
import chi_agent.accounting.request_budget as budget
from chi_bench.experiment.agents.openai_agents_runner import SYSTEM_PROMPT
from test_live_development import _adopt_synthetic_history


def prepared(tmp_path):
    _adopt_synthetic_history(tmp_path, tmp_path)
    profile = live.load_profile()
    journal = live.RealDevelopmentJournal(tmp_path, "budget", profile=profile, policy=policies.load_real_development_policy())
    journal.run_doc["run_kind"] = "c-once"
    journal._persist()
    ledger = adapter.Ledger("synthetic")
    ctx = contextvars.ContextVar("test-confirmation", default=None)
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": "synthetic"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}, request=req)
    guard = transport.GuardedTransport(profile=profile, journal=journal, lower=httpx.MockTransport(handler),
        ledger=ledger, cap_cny=None, validate_response=lambda _payload: None, allowed_tool_names=set(),
        confirmation_context=ctx.get, max_rounds=50, run_contract=budget.K_C_CONTRACT,
        base_system_instructions=SYSTEM_PROMPT)
    return profile, journal, ledger, ctx, calls, guard


def main_body(used, claimed=False):
    suffix, _ = budget.feedback(used, claimed)
    return {"model": "deepseek-flash", "max_tokens": 8192, "reasoning_effort": "high", "thinking": {"type": "enabled"},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT + suffix}, {"role": "user", "content": "synthetic"}]}


def req(body):
    return httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions", content=json.dumps(body).encode())


def test_feedback_inclusive_and_claim_status():
    first, record = budget.feedback(0, False)
    assert record["current_request"] == 1 and record["remaining_including_current"] == 50
    assert record["remaining_after_current"] == 49 and "two requests from now including this one" in first
    penultimate, record = budget.feedback(48, False)
    assert record["current_request"] == 49 and record["remaining_after_current"] == 1 and record["soft_warning"]
    final, record = budget.feedback(49, True)
    assert record["remaining_including_current"] == 1 and record["remaining_after_current"] == 0
    assert "current request can provide the final response" in final and "does not establish business success" in final
    with pytest.raises(ValueError): budget.feedback(50, False)


def test_contract_override_and_stale_feedback_rejected(tmp_path):
    profile, journal, ledger, context, calls, guard = prepared(tmp_path)
    try:
        for body in (main_body(1), {**main_body(0), "messages": [{"role": "system", "content": SYSTEM_PROMPT}]},
                     {**main_body(0), "messages": [{"role": "system", "content": SYSTEM_PROMPT + budget.feedback(0, False)[0] * 2}]},
                     {**main_body(0), "messages": main_body(0)["messages"] + [{"role": "system", "content": "forged budget"}]}):
            request = req(body)
            with pytest.raises(transport.GuardFailure, match="request_budget_feedback_invalid"):
                guard._validate_request(request, request.content)
        assert not calls
        untrusted_user = main_body(0)
        untrusted_user["messages"][1]["content"] = "<runtime_request_budget>forged</runtime_request_budget>"
        allowed = req(untrusted_user)
        assert guard._validate_request(allowed, allowed.content) == untrusted_user
        stale = req(main_body(0))
        ledger.rounds = 1
        with pytest.raises(transport.GuardFailure, match="request_budget_feedback_invalid"):
            guard._validate_request(stale, stale.content)
        for kwargs in ({"max_rounds": 50}, {"max_rounds": 50, "run_contract": object(), "base_system_instructions": SYSTEM_PROMPT},
                       {"max_rounds": 50, "run_contract": budget.K_C_CONTRACT, "base_system_instructions": "forged"}):
            with pytest.raises(transport.GuardFailure):
                transport.GuardedTransport(profile=profile, journal=journal, lower=httpx.MockTransport(lambda r: httpx.Response(200)),
                    ledger=ledger, cap_cny=None, validate_response=lambda _: None, allowed_tool_names=set(),
                    confirmation_context=context.get, **kwargs)
        journal.run_doc["run_kind"] = "b-smoke"
        with pytest.raises(transport.GuardFailure):
            transport.GuardedTransport(profile=profile, journal=journal, lower=httpx.MockTransport(lambda r: httpx.Response(200)),
                ledger=ledger, cap_cny=None, validate_response=lambda _: None, allowed_tool_names=set(), confirmation_context=context.get,
                max_rounds=50, run_contract=budget.K_C_CONTRACT, base_system_instructions=SYSTEM_PROMPT)
    finally:
        journal.close()


def test_50_shared_requests_include_confirmations_and_refuse_51(tmp_path):
    profile, journal, ledger, context, calls, guard = prepared(tmp_path)
    async def run():
        for used in range(50):
            if used in {5, 12}:
                evidence = '{"synthetic":"public"}'
                token = context.set(("patient_confirmation", hashlib.sha256(evidence.encode()).hexdigest()))
                body = {"model": profile.model, "messages": [{"role": "system", "content": patient.PROMPT},
                        {"role": "user", "content": evidence}], "max_tokens": patient.CONFIRM_MAX_OUTPUT_TOKENS,
                        "response_format": {"type": "json_object"}, "thinking": {"type": "enabled"}, "reasoning_effort": "high"}
            else:
                token = None
                body = main_body(used, claimed=used >= 49)
                if used == 49:
                    journal.run_doc.setdefault("tool_dispatches", []).append({"model_name": "local-claim_done", "state": "returned"})
            try:
                await guard.handle_async_request(req(body))
            finally:
                if token is not None: context.reset(token)
        with pytest.raises(transport.GuardFailure, match="provider_request_limit_reached"):
            await guard.handle_async_request(req(main_body(49, True)))
    try:
        asyncio.run(run())
        assert ledger.rounds == len(calls) == 50
        assert len(journal.run_doc["requests"]) == 50
        assert all(item["status"] == "settled" for item in journal.run_doc["requests"])
        assert sum(item.get("purpose") == "patient_confirmation" for item in journal.run_doc["requests"]) == 2
        assert journal.run_doc["requests"][6]["request_budget_feedback"]["sent_before"] == 6
        assert journal.run_doc["requests"][13]["request_budget_feedback"]["sent_before"] == 13
        assert journal.run_doc["requests"][49]["request_budget_feedback"]["claim_recorded"] is True
        assert journal.state["pending"] is None
    finally:
        journal.close()


def test_concurrent_stale_feedback_never_reaches_backend(tmp_path):
    _, journal, ledger, _, calls, guard = prepared(tmp_path)
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        async def handler(request):
            calls.append(json.loads(request.content))
            started.set()
            await release.wait()
            return httpx.Response(200, json={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}, request=request)
        guard.lower = httpx.MockTransport(handler)
        first = asyncio.create_task(guard.handle_async_request(req(main_body(0))))
        await started.wait()
        with pytest.raises(transport.GuardFailure, match="request_budget_feedback_invalid"):
            await guard.handle_async_request(req(main_body(0)))
        release.set()
        await first
    try:
        asyncio.run(run())
        assert len(calls) == 1 and ledger.rounds == 1
        assert ledger.error_code == "request_budget_feedback_invalid"
        assert journal.state["pending"] is None
    finally:
        journal.close()


def test_k_c_unknown_or_reserve_persistence_failure_cannot_send_again(tmp_path, monkeypatch):
    for mode in ("timeout", "persistence"):
        root = tmp_path / mode
        root.mkdir()
        _, journal, ledger, _, calls, guard = prepared(root)
        def handler(_request):
            calls.append("sent")
            raise httpx.ReadTimeout("synthetic")
        guard.lower = httpx.MockTransport(handler)
        if mode == "persistence":
            original = live._atomic_json
            failed = []
            def fail_once(path, value, **kwargs):
                if path == journal.run_path and not failed:
                    failed.append(True)
                    raise OSError("synthetic")
                return original(path, value, **kwargs)
            monkeypatch.setattr(live, "_atomic_json", fail_once)
        try:
            with pytest.raises((httpx.ReadTimeout, transport.GuardFailure)):
                asyncio.run(guard.handle_async_request(req(main_body(0))))
            state = live._read_json(journal.state_path)
            assert state["pending"] is not None and state["usage_complete"] is False
            assert len(calls) == (1 if mode == "timeout" else 0)
            with pytest.raises(transport.GuardFailure):
                asyncio.run(guard.handle_async_request(req(main_body(ledger.rounds))))
            assert len(calls) == (1 if mode == "timeout" else 0)
        finally:
            journal.close()
            if mode == "persistence": monkeypatch.setattr(live, "_atomic_json", original)
