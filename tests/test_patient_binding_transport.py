import asyncio
import datetime
import json
from decimal import Decimal

import httpx
import pytest

import chi_agent.provider_profile as profiles
import chi_agent.provider_transport as transport
import chi_agent.model_runner_adapter as adapter


def request():
    body = {"model": "deepseek-flash", "max_tokens": 128, "reasoning_effort": "high",
            "thinking": {"type": "enabled"}, "messages": []}
    return httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions", content=json.dumps(body).encode())


@pytest.mark.parametrize("mode", ["observer", "cancel", "cancel_read"])
def test_reserved_request_failure_preserves_unknown(tmp_path, mode):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise asyncio.CancelledError()
            yield b""
    class Lower(httpx.AsyncBaseTransport):
        calls = 0
        async def handle_async_request(self, req):
            self.calls += 1
            if mode == "cancel":
                raise asyncio.CancelledError()
            return httpx.Response(200, stream=Stream(), request=req)
    lower = Lower()
    journal = transport.SyntheticJournal(tmp_path, "synthetic")
    ledger = adapter.Ledger("synthetic")
    def observe(_body):
        if mode == "observer": raise RuntimeError("synthetic")
    guard = transport.GuardedTransport(profile=profiles.load_profile(today=datetime.date(2026, 10, 26)),
        journal=journal, lower=lower, ledger=ledger, cap_cny=Decimal("5"),
        validate_response=lambda _payload: None, allowed_tool_names=set(), observe_request=observe)
    with pytest.raises(RuntimeError if mode == "observer" else asyncio.CancelledError):
        asyncio.run(guard.handle_async_request(request()))
    assert journal.state["pending"]["status"] == "unknown"
    assert journal.state["usage_complete"] is False
    assert lower.calls == (0 if mode == "observer" else 1)
    with pytest.raises(transport.GuardFailure):
        asyncio.run(guard.handle_async_request(request()))
    assert lower.calls == (0 if mode == "observer" else 1)
    journal.close()


def test_cancel_after_usage_settlement_keeps_known_usage(tmp_path):
    class Lower(httpx.AsyncBaseTransport):
        async def handle_async_request(self, req):
            return httpx.Response(200, json={"usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                                          "total_tokens": 15}}, request=req)
    journal = transport.SyntheticJournal(tmp_path, "settled")
    ledger = adapter.Ledger("synthetic")
    def cancel(_payload): raise asyncio.CancelledError()
    guard = transport.GuardedTransport(profile=profiles.load_profile(today=datetime.date(2026, 10, 26)),
        journal=journal, lower=Lower(), ledger=ledger, cap_cny=Decimal("5"),
        validate_response=cancel, allowed_tool_names=set())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(guard.handle_async_request(request()))
    assert journal.state["pending"] is None
    assert journal.state["usage_complete"] is True
    assert journal.run_doc["requests"][0]["status"] == "settled"
    journal.close()
