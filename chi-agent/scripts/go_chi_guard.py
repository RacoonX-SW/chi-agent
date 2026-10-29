"""Transport boundary for Go CHI; requires a separately wired trusted runtime."""
from __future__ import annotations

import asyncio
import json
import re

import httpx

from go_chi_contract import ToolContract, ContractFailure
from opencode_go_provider import (GoFailure, _contains_secret, _unique,
                                  SYSTEM as B_SYSTEM, INSTRUCTION as B_INSTRUCTION,
                                  SCHEMAS as B_SCHEMAS, DESCRIPTIONS as B_DESCRIPTIONS)
from b_provider_transport import GuardedTransport


class ChiGuard(httpx.AsyncBaseTransport):
    """Zero-retry transport with a shared request ledger and fixed route.

    The caller must populate the contract from the selected MCP and trusted local
    tools before the first request, record the actual tool results, and provide
    confirmation context only after verifying patient selection evidence.
    """
    def __init__(self, journal, secret, session, lower, *, tools, system, instruction,
                 claimed, confirmation, before_batch=None, observed_request=None):
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
        if journal.run["kind"] == "coding_b":
            expected = [{"type": "function", "function": {"name": name, "description": B_DESCRIPTIONS[name],
                        "parameters": B_SCHEMAS[name], "strict": False}} for name in ("inspect_code", "verify_patch")]
            if system != B_SYSTEM or instruction != B_INSTRUCTION or not self.contract.definitions_match(expected):
                raise GoFailure("chi_b_contract_invalid")

    def _validate(self, request, raw):
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
                                               used=len(self.journal.run["requests"]), claimed=self.claimed(),
                                               coding_probe=coding_b)
                if self.observed_request is not None:
                    self.observed_request(body["messages"], len(self.journal.run["requests"]))
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
            clean = {"role": "assistant", "content": msg.get("content"),
                     "reasoning_content": msg.get("reasoning_content"), "tool_calls": msg.get("tool_calls")}
            try:
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
        try:
            raw = request.content
            purpose = self._validate(request, raw)
            self.journal.reserve(raw, purpose)
        except Exception as exc:
            self.error = exc.code if isinstance(exc, GoFailure) else "chi_persistence_failed"
            raise GoFailure(self.error) from None
        try:
            response = await self.lower.handle_async_request(request)
            if response.status_code != 200:
                raise GoFailure("chi_http_error")
            raw_response = await response.aread()
            if len(raw_response) > 4 * 1024 * 1024:
                raise GoFailure("chi_usage_unknown")
            payload = json.loads(raw_response, object_pairs_hook=_unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(payload) is not dict or type(payload.get("usage")) is not dict:
                raise GoFailure("chi_usage_unknown")
            try:
                GuardedTransport._usage(payload)
            except Exception:
                raise GoFailure("chi_usage_unknown") from None
            self.journal.settle(payload["usage"])
            if _contains_secret(payload, self.secret, self.session):
                raise GoFailure("chi_secret_in_body")
            if (payload["usage"]["prompt_tokens"] > 1048576
                    or payload["usage"]["completion_tokens"] > (1024 if self.journal.run["kind"] == "coding_b" else 32768 if purpose == "confirmation" else 8192)):
                raise GoFailure("chi_usage_over_limit")
            self._response(payload, purpose)
            return response
        except BaseException as exc:
            self.error = exc.code if isinstance(exc, GoFailure) else "chi_transport_unknown"
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise GoFailure(self.error) from None

    async def aclose(self):
        await self.lower.aclose()
