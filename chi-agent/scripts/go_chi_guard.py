"""Transport boundary for Go CHI; requires a separately wired trusted runtime."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import time

import httpx

from go_chi_context import DEFAULT_BUDGET, budget_pressure, check_budget, measure_request
from go_chi_assembly import project_messages
from go_chi_contract import ToolContract, ContractFailure
from go_chi_diagnostics import build_cause, cause_for_code
from opencode_go_provider import (GoFailure, _contains_secret, _unique,
                                  SYSTEM as B_SYSTEM, INSTRUCTION as B_INSTRUCTION,
                                  SCHEMAS as B_SCHEMAS, DESCRIPTIONS as B_DESCRIPTIONS)
from b_provider_transport import GuardedTransport
from go_chi_policy import TIME_POLICY, SUMMARY_VERSIONS, output_limit


class ChiGuard(httpx.AsyncBaseTransport):
    """Zero-retry transport with a shared request ledger and fixed route.

    The caller must populate the contract from the selected MCP and trusted local
    tools before the first request, record the actual tool results, and provide
    confirmation context only after verifying patient selection evidence.
    """
    def __init__(self, journal, secret, session, lower, *, tools, system, instruction,
                 claimed, confirmation, before_batch=None, observed_request=None, run_started=None,
                 billing_lock=None, fatal_getter=None, context_recorder=None, context_limit=DEFAULT_BUDGET,
                 recovery_blocker=None, canonical_tools=None, wire_recorder=None, summary_snapshot=None,
                 main_max_tokens=8192, anchor_getter=None):
        if (type(secret) is not str or not secret.strip() or type(session) is not str
                or not re.fullmatch(r"chi-[0-9a-f]{32}", session)
                or type(system) is not str or type(instruction) is not str
                or not callable(claimed) or not callable(confirmation)):
            raise GoFailure("chi_guard_invalid")
        if before_batch is not None and not callable(before_batch):
            raise GoFailure("chi_guard_invalid")
        if observed_request is not None and not callable(observed_request):
            raise GoFailure("chi_guard_invalid")
        if context_recorder is not None and not callable(context_recorder):
            raise GoFailure("chi_guard_invalid")
        if context_limit is not None and type(context_limit) is not dict:
            raise GoFailure("chi_guard_invalid")
        if type(main_max_tokens) is not int or not 1024 <= main_max_tokens <= 32768:
            raise GoFailure("chi_guard_invalid")
        if wire_recorder is not None and not callable(wire_recorder):
            raise GoFailure("chi_guard_invalid")
        self.wire_recorder = wire_recorder
        if anchor_getter is not None and not callable(anchor_getter):
            raise GoFailure("chi_guard_invalid")
        self.anchor_getter = anchor_getter or (lambda: None)
        if recovery_blocker is not None and not callable(recovery_blocker):
            raise GoFailure("chi_guard_invalid")
        if canonical_tools is not None and (type(canonical_tools) is not dict or
                any(type(k) is not str or type(v) is not str for k, v in canonical_tools.items())):
            raise GoFailure("chi_guard_invalid")
        self.recovery_blocker = recovery_blocker or (lambda: None)
        self.canonical_tools = dict(canonical_tools or {})
        self._active_permit = None
        self._active_summary = None
        self._active_projection = None
        self.context_policy = journal.run['launch'].get('context_policy')
        self.summary_snapshot = summary_snapshot
        if journal.run['launch'].get('input_summary') is not None:
            if (journal.run['launch'].get('input_summary') not in SUMMARY_VERSIONS
                    or journal.run['kind'] != 'chi' or journal.run['launch'].get('output_recovery') is not None
                    or not callable(summary_snapshot)):
                raise GoFailure('chi_summary_configuration_invalid')
        self._control_lock = asyncio.Lock()
        self.journal, self.secret, self.session, self.lower = journal, secret, session, lower
        self.context_recorder, self.context_limit = context_recorder, context_limit
        self.main_max_tokens = main_max_tokens
        self.contract = ToolContract(tools)
        self.system, self.instruction = system, instruction
        self.claimed, self.confirmation = claimed, confirmation
        self.before_batch = before_batch
        self.observed_request = observed_request
        self.error = None
        self.safe_cause = None
        self.billing_lock = billing_lock or asyncio.Lock()
        self.fatal_getter = fatal_getter or (lambda: None)
        self.run_started = time.monotonic() if run_started is None else run_started
        if journal.run["kind"] == "coding_b":
            expected = [{"type": "function", "function": {"name": name, "description": B_DESCRIPTIONS[name],
                        "parameters": B_SCHEMAS[name], "strict": False}} for name in ("inspect_code", "verify_patch")]
            if system != B_SYSTEM or instruction != B_INSTRUCTION or not self.contract.definitions_match(expected):
                raise GoFailure("chi_b_contract_invalid")

    def _expected_max_tokens(self, purpose):
        if self.journal.run['kind'] == 'chi' and purpose in {'main', 'continuation'}:
            return self.main_max_tokens
        return output_limit(self.journal.run['kind'], purpose, self.journal.run['launch'].get('input_summary'))

    def _validate(self, request, raw, *, source_only=False):
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
            failure = GoFailure("chi_request_limit")
            failure.cause = cause_for_code("chi_request_limit")
            raise failure
        try:
            body = json.loads(raw, object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            context = self.confirmation()
            coding_b = self.journal.run["kind"] == "coding_b"
            if coding_b and context is not None:
                raise ValueError
            active = self._active_permit
            summary = self._active_summary
            if summary is not None and request is not summary['request']:
                raise GoFailure('chi_summary_source_changed')
            continuation = active is not None and request is active["request"]
            if active is not None and not continuation:
                raise GoFailure("chi_recovery_invalid")
            if continuation and context is not None:
                raise GoFailure("chi_recovery_invalid")
            purpose = ('summary' if summary is not None and summary['kind'] == 'summary' else
                       'continuation' if continuation else 'confirmation' if context is not None else 'main')
            keys = {"model", "messages", "max_tokens", "reasoning_effort", "thinking"}
            keys |= {"response_format"} if context is not None else set() if purpose == 'summary' else {"tools"}
            if (type(body) is not dict or set(body) != keys or body["model"] != "deepseek-v4.1-flash"
                    or type(body["max_tokens"]) is not int or body["max_tokens"] != self._expected_max_tokens(purpose)
                    or body["thinking"] != {"type": "enabled"} or body["reasoning_effort"] != "high"
                    or _contains_secret(body, self.secret, self.session)):
                raise ValueError
            if purpose == 'summary':
                from go_chi_recovery import canonical_sha
                if context is not None or canonical_sha(body) != summary['body_sha256']:
                    raise GoFailure('chi_summary_source_changed')
            elif context is not None:
                if (type(context) is not tuple or len(context) != 2 or any(type(x) is not str for x in context)
                        or body["response_format"] != {"type": "json_object"}
                        or body["messages"] != [{"role": "system", "content": context[0]},
                                                 {"role": "user", "content": context[1]}]):
                    raise ValueError
            else:
                if not self.contract.definitions_match(body["tools"]):
                    raise ValueError
                projection = self._active_projection
                projected = projection is not None and raw == projection["wire_raw"]
                source_body = projection["source_body"] if projected else body
                messages = source_body["messages"]
                source_used = used
                if summary is not None and summary['kind'] == 'main':
                    from go_chi_recovery import canonical_sha
                    if canonical_sha(body) != summary['body_sha256']:
                        raise GoFailure('chi_summary_source_changed')
                    messages = summary['source_body']['messages']
                    source_used = summary['source_used']
                if continuation:
                    from go_chi_recovery import canonical_sha
                    if (hashlib.sha256(raw).hexdigest() != active["body_sha256"]
                            or canonical_sha(body) != active["view_sha256"]):
                        raise GoFailure("chi_recovery_history_changed")
                    messages = messages[:active["history_length"]]
                try:
                    self.contract.validate_history(messages, system=self.system, instruction=self.instruction,
                                                   used=source_used, claimed=self.claimed(),
                                                   coding_probe=coding_b)
                except ContractFailure:
                    failure = GoFailure("chi_request_invalid")
                    failure.cause = build_cause("request", "history_invalid")
                    raise failure from None
                if self.observed_request is not None and not source_only:
                    observed = (source_body['messages'][:2] + source_body['messages'][3:]
                                if summary is not None and summary['kind'] == 'main' else messages)
                    self.observed_request(observed, used)
            metric = measure_request(body, raw, self.context_limit)
            blocked = check_budget(metric, self.context_limit)
            if blocked is not None and not source_only:
                failure = GoFailure(blocked)
                failure.cause = build_cause("request", "budget_exceeded")
                raise failure
            if self.context_recorder is not None and not source_only:
                self.context_recorder(metric, purpose)
            return purpose
        except GoFailure:
            raise
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
        if purpose == 'summary' and (choice.get('finish_reason') != 'stop'
                or msg.get('tool_calls') not in (None, []) or type(msg.get('content')) is not str
                or not msg['content'].strip()):
            raise GoFailure('chi_summary_invalid')
        if choice.get("finish_reason") == "length":
            if purpose == 'summary':
                raise GoFailure('chi_summary_invalid')
            if purpose == "main" and self.journal.run["kind"] == "chi" and self.journal.run["launch"].get("output_recovery") == "chi-output-recovery-v1":
                from go_chi_recovery import mode_and_fragment
                try: mode_and_fragment(payload)
                except ValueError: raise GoFailure("chi_response_invalid") from None
                return True
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
        elif purpose in {"main", "continuation"} and choice.get("finish_reason") == "tool_calls":
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
                if purpose == "continuation" or (purpose == 'main' and self._active_summary is not None):
                    from go_chi_recovery import canonical_sha, classify
                    parsed = copy.deepcopy(self.contract).accept_batch(clean)
                    completed = set()
                    dispatched = {event['call_id'] for event in self.journal.run['tool_events']
                                  if event.get('event') in {'returned', 'returned_error'}}
                    for record in self.contract.records:
                        canonical = self.canonical_tools.get(record["name"])
                        try:
                            effect = classify(canonical)
                        except (TypeError, ValueError):
                            raise GoFailure('chi_summary_replay' if purpose == 'main' else 'chi_recovery_tool_unclassified') from None
                        if record["id"] in dispatched and record["result"] is not None and effect == "mutation":
                            completed.add(canonical_sha({"name": canonical, "arguments": record["arguments"]}))
                    for call in parsed:
                        canonical = self.canonical_tools.get(call["name"])
                        try:
                            effect = classify(canonical)
                        except (TypeError, ValueError):
                            raise GoFailure('chi_summary_replay' if purpose == 'main' else 'chi_recovery_tool_unclassified') from None
                        if effect == "mutation" and canonical_sha({"name": canonical, "arguments": call["arguments"]}) in completed:
                            raise GoFailure('chi_summary_replay' if purpose == 'main' else 'chi_recovery_replay')
                parsed = self.contract.accept_batch(clean, recover_schema=True)
                if self.before_batch is not None:
                    self.before_batch(parsed)
            except ContractFailure as failure:
                error = GoFailure("chi_tool_batch_invalid")
                error.cause = getattr(failure, "cause", None)
                raise error from None
        else:
            raise GoFailure("chi_response_invalid")

    def _contract_snapshot(self):
        from go_chi_recovery import canonical_sha
        return canonical_sha({"definitions": self.contract.definitions, "records": self.contract.records,
                              "batches": self.contract.batches, "seen": sorted(self.contract.seen),
                              "refusals": self.contract.refusals})

    def _recovery_check(self, snapshot, raw_hash, request, used, claimed, *, issued=False):
        fatal = self.fatal_getter()
        if fatal: raise GoFailure(fatal)
        if self.error is not None: raise GoFailure(self.error)
        task = asyncio.current_task()
        if task is not None and task.cancelling(): raise asyncio.CancelledError
        if self.recovery_blocker(): raise GoFailure("chi_recovery_invalid")
        if (self.journal.state["pending"] is not None or self.journal.state["halted"] is not None
                or any(event.get("event") == "failed" for event in self.journal.run["tool_events"])
                or any(record["result"] is None for record in self.contract.records)):
            raise GoFailure("chi_recovery_invalid")
        if (self._contract_snapshot() != snapshot or hashlib.sha256(request.content).hexdigest() != raw_hash
                or self.claimed() != claimed):
            raise GoFailure("chi_recovery_history_changed")
        if time.monotonic() - self.run_started >= TIME_POLICY['chi_admission_seconds']:
            raise GoFailure("chi_run_time_limit")
        if sum(x['purpose'] != 'patient_simulator' for x in self.journal.run['requests']) != used + 1:
            raise GoFailure("chi_recovery_history_changed")
        if used + 1 >= 50 or len(self.journal.run['recovery_events']) > (2 if issued else 1):
            raise GoFailure("chi_recovery_limit")

    def _summary_protected(self):
        from go_chi_summary import protected_snapshot
        binding, state = self.summary_snapshot()
        return protected_snapshot(journal=self.journal, contract=self.contract, canonical_tools=self.canonical_tools,
                                  role=self.journal.run['launch']['role'], instruction=self.instruction,
                                  system=self.system, patient_binding=binding, task_state=state)

    def _summary_check(self, *, request, raw_hash, contract_hash, protected_hash, used):
        from go_chi_summary import canonical_sha
        if self.fatal_getter(): raise GoFailure(self.fatal_getter())
        if self.error is not None: raise GoFailure(self.error)
        task = asyncio.current_task()
        if task is not None and task.cancelling(): raise asyncio.CancelledError
        if (self.recovery_blocker() or self.journal.state['pending'] is not None
                or self.journal.state['halted'] is not None
                or hashlib.sha256(request.content).hexdigest() != raw_hash
                or self._contract_snapshot() != contract_hash
                or sum(item['purpose'] != 'patient_simulator' for item in self.journal.run['requests']) != used
                or canonical_sha(self._summary_protected()) != protected_hash):
            raise GoFailure('chi_summary_source_changed')
        if time.monotonic() - self.run_started >= TIME_POLICY['chi_admission_seconds']:
            raise GoFailure('chi_run_time_limit')

    async def _handle_input_summary(self, request):
        from go_chi_summary import canonical_sha, select_closed, summary_request, NOTICE
        if self.journal.run['launch'].get('input_summary') not in SUMMARY_VERSIONS or self.confirmation() is not None:
            return False, None
        try:
            async with self.billing_lock:
                self._validate(request, request.content, source_only=True)
                body = json.loads(request.content, object_pairs_hook=_unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                metric = measure_request(body, request.content, self.context_limit)
                blocked = check_budget(metric, self.context_limit)
                if blocked not in (None, 'chi_context_budget_exceeded'):
                    raise GoFailure(blocked)
                used = sum(item['purpose'] != 'patient_simulator' for item in self.journal.run['requests'])
                events = self.journal.run['summary_events']
                if not events:
                    trigger = (blocked is not None or budget_pressure(metric, self.context_limit))
                    if not trigger:
                        return False, None
                    selection = select_closed(body['messages'])
                    if selection is None:
                        if blocked: raise GoFailure(blocked)
                        return False, None
                    if used >= 49:
                        raise GoFailure('chi_summary_limit')
                elif len(events) != 1 or events[0]['status'] != 'installed':
                    raise GoFailure('chi_summary_unavailable')
                protected = self._summary_protected()
                snapshot = self._contract_snapshot()
                raw_hash = hashlib.sha256(request.content).hexdigest()
                protected_hash = canonical_sha(protected)
                self._summary_check(request=request, raw_hash=raw_hash, contract_hash=snapshot,
                                    protected_hash=protected_hash, used=used)
                if not events:
                    candidate_request = summary_request(body, selection, protected, self.journal.run['launch']['input_summary'])
                    summary_raw = json.dumps(candidate_request, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                    minimal = copy.deepcopy(body)
                    minimal['messages'] = body['messages'][:2] + [{'role': 'user', 'content': json.dumps(
                        {'schema': 'chi-summary-context-v1', 'notice': NOTICE, 'protected': protected},
                        ensure_ascii=False, separators=(',', ':'))}] + body['messages'][selection['end']:]
                    minimal_raw = json.dumps(minimal, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                    for probe, wire in ((candidate_request, summary_raw), (minimal, minimal_raw)):
                        failure = check_budget(measure_request(probe, wire, self.context_limit), self.context_limit)
                        if failure: raise GoFailure(failure)
                    permit, generated = self.journal.select_summary(body, protected, self.canonical_tools,
                        source_raw=request.content, secrets=(self.secret, self.session))
                    if canonical_sha(generated) != canonical_sha(candidate_request):
                        raise GoFailure('chi_summary_source_changed')
                else:
                    permit = None
            if permit is not None:
                headers = httpx.Headers(request.headers)
                if 'content-length' in headers: del headers['content-length']
                summary_wire = httpx.Request(request.method, request.url, headers=headers, content=summary_raw,
                                             extensions=dict(request.extensions))
                self._active_summary = {'kind': 'summary', 'request': summary_wire, 'index': permit,
                                        'body_sha256': canonical_sha(candidate_request)}
                async with self.billing_lock:
                    self._summary_check(request=request, raw_hash=raw_hash, contract_hash=snapshot,
                                        protected_hash=protected_hash, used=used)
                    await self._handle_serialized(summary_wire)
                self._active_summary = None
                used_after = used + 1
                self._summary_check(request=request, raw_hash=raw_hash, contract_hash=snapshot,
                                    protected_hash=protected_hash, used=used_after)
                self.journal.install_summary(self._summary_protected(), context_limit=self.context_limit,
                                             secrets=(self.secret, self.session))
            else:
                used_after = used
            async with self.billing_lock:
                self._summary_check(request=request, raw_hash=raw_hash, contract_hash=snapshot,
                                    protected_hash=protected_hash, used=used_after)
                projection, wire = self.journal.project_summary(body, request.content, self._summary_protected(),
                    source_used=used, context_limit=self.context_limit, secrets=(self.secret, self.session))
                headers = httpx.Headers(request.headers)
                if 'content-length' in headers: del headers['content-length']
                follow = httpx.Request(request.method, request.url, headers=headers, content=wire,
                                       extensions=dict(request.extensions))
                self._active_summary = {'kind': 'main', 'request': follow, 'index': projection,
                                        'body_sha256': canonical_sha(json.loads(wire)),
                                        'source_body': body, 'source_used': used}
                self._summary_check(request=request, raw_hash=raw_hash, contract_hash=snapshot,
                                    protected_hash=protected_hash, used=used_after)
                response, _ = await self._handle_serialized(follow)
            return True, response
        except BaseException as exc:
            fatal = self.fatal_getter()
            self.error = (fatal if fatal else self.error if self.error else
                          'chi_cancelled' if isinstance(exc, asyncio.CancelledError) else
                          exc.code if isinstance(exc, GoFailure) else 'chi_summary_invalid')
            if isinstance(exc, asyncio.CancelledError): raise
            raise GoFailure(self.error) from None
        finally:
            self._active_summary = None

    async def handle_async_request(self, request):
        from go_chi_recovery import canonical_sha, derive_view
        async with self._control_lock:
            handled, summary_response = await self._handle_input_summary(request)
            if handled:
                return summary_response
            projection_request = request
            self._active_projection = None
            if (self.context_policy == "chi-context-v3"
                    and self.confirmation() is None
                    and self.journal.run['launch'].get('output_recovery') is None
                    and self.journal.run['launch'].get('input_summary') is None):
                try:
                    source_body = json.loads(request.content, object_pairs_hook=_unique,
                                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    metric = measure_request(source_body, request.content, self.context_limit)
                    limit = self.context_limit.get('max_input_tokens') if type(self.context_limit) is dict else None
                    anchor = self.anchor_getter()
                    pressure = (type(limit) is int and metric.get('estimated_tokens_upper', 0) >= int(0.4 * limit))
                    if anchor is not None or pressure:
                        records = {record['id']: record for record in self.contract.records}
                        events = {}
                        for event in self.journal.run['tool_events']:
                            if event.get('event') in {'returned', 'returned_error', 'refused', 'failed'}:
                                events[event['call_id']] = event['event']
                        projected, report = project_messages(
                            source_body['messages'], records=records, events=events,
                            canonical_tools=self.canonical_tools, anchor=anchor)
                        if report['saved_bytes'] > 0 or anchor is not None:
                            wire_body = dict(source_body)
                            wire_body['messages'] = projected
                            wire_raw = json.dumps(wire_body, ensure_ascii=False,
                                                  separators=(',', ':'), allow_nan=False).encode()
                            headers = httpx.Headers(request.headers)
                            if 'content-length' in headers:
                                del headers['content-length']
                            projection_request = httpx.Request(
                                request.method, request.url, headers=headers, content=wire_raw,
                                extensions=dict(request.extensions))
                            self._active_projection = {
                                'source_body': source_body, 'wire_raw': wire_raw,
                                'report': report, 'request': projection_request,
                            }
                except (ValueError, KeyError, TypeError):
                    self._active_projection = None
                    projection_request = request
            snapshot = self._contract_snapshot()
            raw_hash = hashlib.sha256(request.content).hexdigest()
            used = sum(x['purpose'] != 'patient_simulator' for x in self.journal.run['requests'])
            claimed = self.claimed()
            async with self.billing_lock:
                response, candidate = await self._handle_serialized(projection_request)
            if candidate is None:
                return response
            try:
                self._recovery_check(snapshot, raw_hash, request, used, claimed)
                original = json.loads(request.content, object_pairs_hook=_unique,
                                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                self.contract.validate_history(original["messages"], system=self.system, instruction=self.instruction,
                                               used=used, claimed=claimed)
                view = derive_view(original, candidate, old_used=used, claimed=claimed)
                wire = json.dumps(view, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
                blocked = check_budget(measure_request(view, wire, self.context_limit), self.context_limit)
                if blocked: raise GoFailure(blocked)
                self._recovery_check(snapshot, raw_hash, request, used, claimed)
                permit = self.journal.issue_recovery(view, secrets=(self.secret, self.session))
                headers = httpx.Headers(request.headers)
                if "content-length" in headers: del headers["content-length"]
                follow = httpx.Request(request.method, request.url, headers=headers, content=wire,
                                       extensions=dict(request.extensions))
                self._active_permit = {"index": permit, "request": follow,
                    "body_sha256": hashlib.sha256(wire).hexdigest(), "view_sha256": canonical_sha(view),
                    "history_length": len(original["messages"])}
                async with self.billing_lock:
                    self._recovery_check(snapshot, raw_hash, request, used, claimed, issued=True)
                    final, _ = await self._handle_serialized(follow)
                return final
            except BaseException as exc:
                fatal = self.fatal_getter()
                self.error = (fatal if fatal else self.error if self.error else
                              "chi_cancelled" if isinstance(exc, asyncio.CancelledError) else
                              exc.code if isinstance(exc, GoFailure) else "chi_recovery_invalid")
                if isinstance(exc, asyncio.CancelledError): raise
                raise GoFailure(self.error) from None
            finally:
                self._active_permit = None
                self._active_projection = None

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
            self.journal.reserve(raw, purpose, secrets=(self.secret, self.session), dispatch=dispatch,
                                 recovery_permit=self._active_permit["index"] if purpose == "continuation" else None,
                                 summary_permit=self._active_summary['index'] if purpose == 'summary' else None,
                                 summary_projection=(self._active_summary['index'] if purpose == 'main'
                                                     and self._active_summary is not None else None),
                                 context_projection=(self._active_projection["report"]
                                                     if self._active_projection is not None and purpose == 'main'
                                                     else None))
        except Exception as exc:
            self.error = exc.code if isinstance(exc, GoFailure) else "chi_persistence_failed"
            self.safe_cause = getattr(exc, "cause", None) or cause_for_code(self.error)
            raise GoFailure(self.error) from None
        start = time.monotonic()
        persistence_failed = False
        dispatched = False
        try:
            request.extensions['timeout'] = {'connect': TIME_POLICY['connect_seconds'],
                'read': TIME_POLICY['confirmation_read_seconds' if purpose == 'confirmation' else 'main_read_seconds'],
                'write': TIME_POLICY['write_seconds'], 'pool': TIME_POLICY['pool_seconds']}
            async with asyncio.timeout(TIME_POLICY['confirmation_io_seconds' if purpose == 'confirmation' else 'main_io_seconds']):
                dispatched = True
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
                    or payload["usage"]["completion_tokens"] > self._expected_max_tokens(purpose)):
                raise GoFailure("chi_usage_over_limit")
            recoverable = self._response(payload, purpose)
            self.safe_cause = None
            try:
                self.journal.record_diagnostic("ok", int((time.monotonic() - start) * 1000))
            except Exception:
                persistence_failed = True
                raise GoFailure("chi_evidence_persistence_failed") from None
            return response, payload if recoverable else None
        except BaseException as exc:
            self.error = ("chi_cancelled" if isinstance(exc, asyncio.CancelledError) else
                          exc.code if isinstance(exc, GoFailure) else
                          "chi_timeout" if isinstance(exc, (httpx.TimeoutException, TimeoutError)) else
                          "chi_transport_error" if isinstance(exc, httpx.RequestError) else "chi_transport_unknown")
            self.safe_cause = getattr(exc, "cause", None) or cause_for_code(self.error)
            if not persistence_failed:
                try:
                    self.journal.record_diagnostic(self.error, int((time.monotonic() - start) * 1000),
                                                   cause=self.safe_cause)
                except Exception:
                    self.error = "chi_evidence_persistence_failed"
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise GoFailure(self.error) from None
        finally:
            if dispatched and self.wire_recorder is not None:
                original_error = __import__("sys").exc_info()[1]
                try:
                    self.wire_recorder(self.journal.run["requests"][-1])
                except Exception:
                    self.error = self.error or "chi_log_persistence_failed"
                    if not isinstance(original_error, asyncio.CancelledError):
                        raise GoFailure(self.error) from None

    async def aclose(self):
        await self.lower.aclose()
