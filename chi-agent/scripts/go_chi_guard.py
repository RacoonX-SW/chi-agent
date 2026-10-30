"""Transport boundary for Go CHI; requires a separately wired trusted runtime."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time

import httpx

from go_chi_contract import ToolContract, ContractFailure
from opencode_go_provider import (GoFailure, _contains_secret, _unique,
                                  SYSTEM as B_SYSTEM, INSTRUCTION as B_INSTRUCTION,
                                  SCHEMAS as B_SCHEMAS, DESCRIPTIONS as B_DESCRIPTIONS)
from b_provider_transport import GuardedTransport
from go_chi_policy import TIME_POLICY


class ChiGuard(httpx.AsyncBaseTransport):
    """Zero-retry transport with a shared request ledger and fixed route.

    The caller must populate the contract from the selected MCP and trusted local
    tools before the first request, record the actual tool results, and provide
    confirmation context only after verifying patient selection evidence.
    """
    def __init__(self, journal, secret, session, lower, *, tools, system, instruction,
                 claimed, confirmation, before_batch=None, observed_request=None, run_started=None,
                 billing_lock=None, fatal_getter=None):
        if (type(secret) is not str or not secret.strip() or type(session) is not str
                or not re.fullmatch(r"chi-[0-9a-f]{32}", session)
                or type(system) is not str or type(instruction) is not str
                or not callable(claimed) or not callable(confirmation)):
            raise GoFailure("chi_guard_invalid")
        if before_batch is not None and not callable(before_batch):
            raise GoFailure("chi_guard_invalid")
        if observed_request is not None and not callable(observed_request):
            raise GoFailure("chi_guard_invalid")
        self.journal, self.secret, self.session, self.lower = journal, secret, session, lower
        self.contract = ToolContract(tools)
        self.system, self.instruction = system, instruction
        self.claimed, self.confirmation = claimed, confirmation
        self.before_batch = before_batch
        self.observed_request = observed_request
        self.error = None
        self.billing_lock = billing_lock or asyncio.Lock()
        self.fatal_getter = fatal_getter or (lambda: None)
        self.run_started = time.monotonic() if run_started is None else run_started
        if journal.run["kind"] == "coding_b":
            expected = [{"type": "function", "function": {"name": name, "description": B_DESCRIPTIONS[name],
                        "parameters": B_SCHEMAS[name], "strict": False}} for name in ("inspect_code", "verify_patch")]
            if system != B_SYSTEM or instruction != B_INSTRUCTION or not self.contract.definitions_match(expected):
                raise GoFailure("chi_b_contract_invalid")

    def _validate(self, request, raw):
        if self.fatal_getter():
            raise GoFailure(self.fatal_getter())
        if self.error is not None:
            raise GoFailure(self.error)
        url = request.url
        if (request.method != "POST" or url.scheme != "https" or url.host != "opencode.ai"
                or url.port is not None or url.path != "/inference/go/openai/v1/chat/completions"
                or url.query or url.fragment or url.userinfo or len(raw) > 8 * 1024 * 1024):
            raise GoFailure("chi_route_invalid")
        if (request.headers.get_list("authorization") != ["Bearer " + self.secret]
                or request.headers.get_list("user-agent") != ["chi-agent"]
                or request.headers.get_list("x-opencode-session") != [self.session]):
            raise GoFailure("chi_headers_invalid")
        used = sum(item['purpose'] != 'patient_simulator' for item in self.journal.run['requests'])
        if used >= (6 if self.journal.run["kind"] == "coding_b" else 50):
            raise GoFailure("chi_request_limit")
        try:
            body = json.loads(raw, object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            context = self.confirmation()
            coding_b = self.journal.run["kind"] == "coding_b"
            if coding_b and context is not None:
                raise ValueError
            purpose = "confirmation" if context is not None else "main"
            keys = {"model", "messages", "max_tokens", "reasoning_effort", "thinking"}
            keys |= {"response_format"} if context is not None else {"tools"}
            if (type(body) is not dict or set(body) != keys or body["model"] != "deepseek-v4.1-flash"
                    or type(body["max_tokens"]) is not int or body["max_tokens"] != (1024 if coding_b else 32768 if context is not None else 8192)
                    or body["thinking"] != {"type": "enabled"} or body["reasoning_effort"] != "high"
                    or _contains_secret(body, self.secret, self.session)):
                raise ValueError
            if context is not None:
                if (type(context) is not tuple or len(context) != 2 or any(type(x) is not str for x in context)
                        or body["response_format"] != {"type": "json_object"}
                        or body["messages"] != [{"role": "system", "content": context[0]},
                                                 {"role": "user", "content": context[1]}]):
                    raise ValueError
            else:
                if not self.contract.definitions_match(body["tools"]):
                    raise ValueError
                self.contract.validate_history(body["messages"], system=self.system, instruction=self.instruction,
                                               used=used, claimed=self.claimed(),
                                               coding_probe=coding_b)
                if self.observed_request is not None:
                    self.observed_request(body["messages"], used)
            return purpose
        except Exception:
            raise GoFailure("chi_request_invalid") from None

    def _response(self, payload, purpose):
        if type(payload) is not dict or payload.get("model") != "deepseek-v4.1-flash":
            raise GoFailure("chi_response_invalid")
        choices = payload.get("choices")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise GoFailure("chi_response_invalid")
        choice = choices[0]
        msg = choice.get("message")
        if type(msg) is not dict or msg.get("role") != "assistant" or msg.get("function_call") is not None:
            raise GoFailure("chi_response_invalid")
        if choice.get("finish_reason") == "length":
            if purpose != "confirmation":
                raise GoFailure("chi_output_truncated")
            if (msg.get("tool_calls") not in (None, []) or
                    msg.get("content") is not None and type(msg.get("content")) is not str or
                    msg.get("reasoning_content") is not None and type(msg.get("reasoning_content")) is not str):
                raise GoFailure("chi_response_invalid")
            return
        if choice.get("finish_reason") == "stop":
            if (not isinstance(msg.get("content"), str) or not msg["content"].strip()
                    or msg.get("tool_calls") not in (None, [])
                    or msg.get("reasoning_content") is not None and not isinstance(msg["reasoning_content"], str)):
                raise GoFailure("chi_response_invalid")
            if self.journal.run["kind"] == "coding_b":
                records = self.contract.records
                if (len(records) != 2 or records[0]["name"] != "inspect_code"
                        or records[0]["result"] != "def add(a, b):\n    return a - b\n"
                        or records[1]["name"] != "verify_patch" or records[1]["result"] != "verification:pass"):
                    raise GoFailure("chi_b_incomplete")
        elif purpose == "main" and choice.get("finish_reason") == "tool_calls":
            # Store exactly the assistant representation required for subsequent history.
            clean = {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls")}
            try:
                reasoning = msg.get("reasoning_content")
                if reasoning is not None:
                    if type(reasoning) is not str:
                        raise ContractFailure("chi_reasoning_invalid")
                    clean["reasoning_content"] = reasoning
                if self.journal.run["kind"] == "coding_b":
                    calls = clean["tool_calls"]
                    records = self.contract.records
                    if (type(calls) is not list or len(calls) != 1 or type(calls[0]) is not dict
                            or type(calls[0].get("function")) is not dict):
                        raise ContractFailure("chi_b_batch_invalid")
                    name = calls[0]["function"].get("name")
                    if not ((not records and name == "inspect_code") or
                            (len(records) == 1 and records[0]["name"] == "inspect_code"
                             and records[0]["result"] == "def add(a, b):\n    return a - b\n"
                             and name == "verify_patch")):
                        raise ContractFailure("chi_b_order_invalid")
                parsed = self.contract.accept_batch(clean)
                if self.before_batch is not None:
                    self.before_batch(parsed)
            except ContractFailure:
                raise GoFailure("chi_tool_batch_invalid") from None
        else:
            raise GoFailure("chi_response_invalid")

    async def handle_async_request(self, request):
        async with self.billing_lock:
            return await self._handle_serialized(request)

    async def _handle_serialized(self, request):
        try:
            raw = request.content
            purpose = self._validate(request, raw)
            limit = TIME_POLICY['b_admission_seconds' if self.journal.run['kind'] == 'coding_b' else 'chi_admission_seconds']
            if time.monotonic() - self.run_started >= limit:
                raise GoFailure('chi_run_time_limit')
            dispatch = {'version': 'chi-go-dispatch-v1', 'purpose': purpose,
                        'session_sha256': hashlib.sha256(self.session.encode()).hexdigest(),
                        'started_utc_ms': time.time_ns() // 1000000, 'body_bytes': len(raw)}
            self.journal.reserve(raw, purpose, secrets=(self.secret, self.session), dispatch=dispatch)
        except Exception as exc:
            self.error = exc.code if isinstance(exc, GoFailure) else "chi_persistence_failed"
            raise GoFailure(self.error) from None
        start = time.monotonic()
        persistence_failed = False
        try:
            request.extensions['timeout'] = {'connect': TIME_POLICY['connect_seconds'],
                'read': TIME_POLICY['confirmation_read_seconds' if purpose == 'confirmation' else 'main_read_seconds'],
                'write': TIME_POLICY['write_seconds'], 'pool': TIME_POLICY['pool_seconds']}
            async with asyncio.timeout(TIME_POLICY['confirmation_io_seconds' if purpose == 'confirmation' else 'main_io_seconds']):
                response = await self.lower.handle_async_request(request)
                raw_response = await response.aread()
            payload = None
            if len(raw_response) <= 4 * 1024 * 1024:
                try:
                    payload = json.loads(raw_response, object_pairs_hook=_unique,
                                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except Exception:
                    pass
            known = False
            try:
                GuardedTransport._usage(payload)
                known = True
            except Exception:
                pass
            try:
                self.journal.record_response(raw_response, response.status_code, int((time.monotonic() - start) * 1000),
                                             secrets=(self.secret, self.session))
            except Exception:
                persistence_failed = True
                if known:
                    try: self.journal.settle(payload["usage"])
                    except Exception: pass
                raise GoFailure("chi_evidence_persistence_failed") from None
            if known:
                try:
                    self.journal.settle(payload["usage"])
                except GoFailure:
                    raise
                except Exception:
                    persistence_failed = True
                    raise GoFailure("chi_persistence_failed") from None
            if response.status_code != 200:
                raise GoFailure("chi_http_error")
            if len(raw_response) > 4 * 1024 * 1024:
                raise GoFailure("chi_response_too_large")
            if type(payload) is not dict:
                raise GoFailure("chi_response_json_invalid")
            if not known:
                raise GoFailure("chi_usage_unknown")
            if _contains_secret(payload, self.secret, self.session):
                raise GoFailure("chi_secret_in_body")
            if (payload["usage"]["prompt_tokens"] > 1048576
                    or payload["usage"]["completion_tokens"] > (1024 if self.journal.run["kind"] == "coding_b" else 32768 if purpose == "confirmation" else 8192)):
                raise GoFailure("chi_usage_over_limit")
            self._response(payload, purpose)
            try:
                self.journal.record_diagnostic("ok", int((time.monotonic() - start) * 1000))
            except Exception:
                persistence_failed = True
                raise GoFailure("chi_evidence_persistence_failed") from None
            return response
        except BaseException as exc:
            self.error = ("chi_cancelled" if isinstance(exc, asyncio.CancelledError) else
                          exc.code if isinstance(exc, GoFailure) else
                          "chi_timeout" if isinstance(exc, (httpx.TimeoutException, TimeoutError)) else
                          "chi_transport_error" if isinstance(exc, httpx.RequestError) else "chi_transport_unknown")
            if not persistence_failed:
                try:
                    self.journal.record_diagnostic(self.error, int((time.monotonic() - start) * 1000))
                except Exception:
                    self.error = "chi_evidence_persistence_failed"
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise GoFailure(self.error) from None

    async def aclose(self):
        await self.lower.aclose()
