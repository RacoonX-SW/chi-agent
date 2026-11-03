"""Default-disabled accounting transport for a development patient simulator."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

import httpx

from go_chi_context import DEFAULT_BUDGET, check_budget, measure_request
from go_chi_diagnostics import cause_for_code
from b_provider_transport import GuardedTransport
from opencode_go_provider import GoFailure, _contains_secret, _unique


class AuxiliaryTransport(httpx.AsyncBaseTransport):
    """One journal owner and one billing lock shared with the main guard."""
    def __init__(self, journal, secret, session, lower, lock, parent_getter, *, context_limit=DEFAULT_BUDGET, context_recorder=None, wire_recorder=None):
        self.journal, self.secret, self.session = journal, secret, session
        self.lower, self.lock, self.parent_getter = lower, lock, parent_getter
        self.error = None
        self.context_limit, self.context_recorder = context_limit, context_recorder
        self.wire_recorder = wire_recorder

    async def handle_async_request(self, request):
        async with self.lock:
            if self.error:
                raise GoFailure(self.error)
            start = time.monotonic()
            reserved = False
            dispatched = False
            try:
                raw = request.content
                url = request.url
                if (request.method != 'POST' or url.scheme != 'https' or url.host != 'opencode.ai'
                        or url.path != '/inference/go/openai/v1/chat/completions' or url.port is not None
                        or url.query or url.fragment or url.userinfo or len(raw) > 8 * 1024 * 1024
                        or request.headers.get_list('authorization') != ['Bearer ' + self.secret]
                        or request.headers.get_list('user-agent') != ['chi-agent']
                        or request.headers.get_list('x-opencode-session') != [self.session]):
                    raise GoFailure('chi_aux_route_invalid')
                body = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if (type(body) is not dict or set(body) != {'model', 'messages', 'max_tokens', 'reasoning_effort', 'thinking'}
                        or body['model'] != 'deepseek-v4.1-flash' or body['max_tokens'] != 8192
                        or body['reasoning_effort'] != 'high' or body['thinking'] != {'type': 'enabled'}
                        or type(body['messages']) is not list or not body['messages']
                        or any(type(m) is not dict or set(m) != {'role', 'content'}
                               or m['role'] not in {'system', 'user', 'assistant'} or type(m['content']) is not str
                               for m in body['messages']) or body['messages'][0]['role'] != 'system'
                        or any(m['role'] == 'system' for m in body['messages'][1:])
                        or _contains_secret(body, self.secret, self.session)):
                    raise GoFailure('chi_aux_request_invalid')
                metric = measure_request(body, raw)
                blocked = check_budget(metric, self.context_limit)
                if blocked is not None: raise GoFailure(blocked)
                if self.context_recorder is not None: self.context_recorder(metric, "patient_simulator")
                parent = self.parent_getter()
                dispatch = {'version': 'chi-go-dispatch-v1', 'purpose': 'patient_simulator',
                            'session_sha256': hashlib.sha256(self.session.encode()).hexdigest(),
                            'started_utc_ms': time.time_ns() // 1000000, 'body_bytes': len(raw)}
                self.journal.reserve(raw, 'patient_simulator', secrets=(self.secret, self.session),
                                     dispatch=dispatch, parent_call_id=parent)
                reserved = True
                request.extensions['timeout'] = {'connect': 10, 'read': 360, 'write': 60, 'pool': 60}
                async with asyncio.timeout(420):
                    dispatched = True
                    response = await self.lower.handle_async_request(request)
                    payload_bytes = await response.aread()
                payload = None
                if len(payload_bytes) <= 4 * 1024 * 1024:
                    try: payload = json.loads(payload_bytes, object_pairs_hook=_unique)
                    except Exception: pass
                try:
                    incoming, outgoing = GuardedTransport._usage(payload)
                    known = True
                except Exception:
                    known = False
                self.journal.record_response(payload_bytes, response.status_code, int((time.monotonic() - start) * 1000),
                                             secrets=(self.secret, self.session))
                if known: self.journal.settle(payload['usage'])
                if not known: raise GoFailure('chi_usage_unknown')
                if response.status_code != 200 or outgoing > 8192 or incoming > 1048576 or _contains_secret(payload, self.secret, self.session):
                    raise GoFailure('chi_aux_response_invalid')
                choices = payload.get('choices')
                if (payload.get('model') != 'deepseek-v4.1-flash' or type(choices) is not list or len(choices) != 1
                        or type(choices[0]) is not dict or choices[0].get('finish_reason') != 'stop'):
                    raise GoFailure('chi_aux_response_invalid')
                msg = choices[0].get('message')
                if (type(msg) is not dict or msg.get('role') != 'assistant' or not isinstance(msg.get('content'), str)
                        or not msg['content'].strip() or msg.get('tool_calls') not in (None, []) or msg.get('function_call') is not None):
                    raise GoFailure('chi_aux_response_invalid')
                self.journal.record_diagnostic('ok', int((time.monotonic() - start) * 1000))
                return response
            except BaseException as exc:
                self.error = exc.code if isinstance(exc, GoFailure) else 'chi_aux_cancelled' if isinstance(exc, asyncio.CancelledError) else 'chi_aux_transport_error'
                if reserved:
                    try: self.journal.record_diagnostic(self.error, int((time.monotonic() - start) * 1000),
                                                        cause=cause_for_code(self.error))
                    except Exception: self.error = 'chi_evidence_persistence_failed'
                if isinstance(exc, asyncio.CancelledError): raise
                raise GoFailure(self.error) from None
            finally:
                if dispatched and self.wire_recorder is not None:
                    original_error = __import__("sys").exc_info()[1]
                    try: self.wire_recorder(self.journal.run["requests"][-1])
                    except Exception:
                        self.error = self.error or 'chi_log_persistence_failed'
                        if not isinstance(original_error, asyncio.CancelledError):
                            raise GoFailure(self.error) from None

    async def aclose(self):
        await self.lower.aclose()
