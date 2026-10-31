"""Development-only capability gate and Go SDK patient response broker."""
from __future__ import annotations

import asyncio
import hmac
import json
import re
import uuid

import httpx
from openai import AsyncOpenAI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from go_chi_auxiliary import AuxiliaryTransport


class PatientBroker:
    def __init__(self, journal, secret, capability, billing_lock, lower_factory):
        if (not isinstance(capability, str) or len(capability) < 32 or not isinstance(secret, str)
                or not secret or not callable(lower_factory)):
            raise ValueError('broker_configuration_invalid')
        self.journal, self.secret, self.capability = journal, secret, capability
        self.billing_lock, self.lower_factory = billing_lock, lower_factory
        self.parent = None
        self.used = set()
        self.sessions = {}
        self.fatal = None
        self.busy = False

    def begin(self, call_id, tool, args):
        if (self.parent is not None or self.fatal or tool != 'cm_outreach.send_message' or type(args) is not dict
                or type(args.get('session_id')) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', args['session_id'])
                or type(call_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', call_id)
                or call_id in self.used):
            raise ValueError('broker_parent_invalid')
        self.parent = (call_id, args['session_id'])

    def end(self, call_id):
        if self.parent is None or self.parent[0] != call_id or self.busy:
            self.fatal = 'chi_aux_parent_invalid'
            raise ValueError('broker_parent_invalid')
        self.used.add(call_id)
        self.parent = None

    def _client(self, patient_session):
        if patient_session not in self.sessions:
            session = 'chi-' + uuid.uuid4().hex
            transport = AuxiliaryTransport(self.journal, self.secret, session, self.lower_factory(), self.billing_lock,
                lambda: self.parent[0] if self.parent else None)
            client = AsyncOpenAI(api_key=self.secret, base_url='https://opencode.ai/inference/go/openai/v1', max_retries=0,
                default_headers={'User-Agent': 'chi-agent', 'X-OpenCode-Session': session},
                http_client=httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False))
            self.sessions[patient_session] = (client, transport)
        return self.sessions[patient_session]

    async def respond(self, capability, run, patient_session, messages):
        parent = self.parent[0] if self.parent else None
        if (not isinstance(capability, str) or not hmac.compare_digest(capability, self.capability)
                or self.fatal or self.busy or run != self.journal.run_id or self.parent != (parent, patient_session)
                or parent in self.used or type(messages) is not list or not messages
                or len(json.dumps(messages, ensure_ascii=True).encode()) > 8 * 1024 * 1024):
            raise ValueError('broker_request_invalid')
        self.busy = True
        self.used.add(parent)
        client, transport = self._client(patient_session)
        try:
            result = await client.chat.completions.create(model='deepseek-v4.1-flash', messages=messages,
                max_tokens=8192, reasoning_effort='high', extra_body={'thinking': {'type': 'enabled'}})
            return {'content': result.choices[0].message.content,
                    'token_usage': result.usage.prompt_tokens + result.usage.completion_tokens}
        except BaseException:
            self.fatal = transport.error or 'chi_aux_failed'
            raise
        finally:
            self.busy = False

    async def close(self):
        for client, _ in self.sessions.values(): await client.close()

    def app(self):
        async def post(request: Request):
            supplied = request.headers.get('x-chi-capability')
            authorized = isinstance(supplied, str) and hmac.compare_digest(supplied, self.capability)
            try:
                if request.headers.get('content-type') != 'application/json': raise ValueError
                length = request.headers.get('content-length')
                if not length or not length.isdigit() or int(length) > 8 * 1024 * 1024: raise ValueError
                raw = await request.body()
                if len(raw) > 8 * 1024 * 1024: raise ValueError
                obj = json.loads(raw)
                if len(raw) != int(length) or type(obj) is not dict or set(obj) != {'run', 'session', 'messages'}: raise ValueError
                result = await self.respond(supplied, obj['run'], obj['session'], obj['messages'])
                return JSONResponse(result)
            except Exception:
                if authorized:
                    self.fatal = self.fatal or 'chi_aux_broker_invalid'
                return JSONResponse({'error': 'patient_broker_unavailable'}, status_code=400)
        return Starlette(routes=[Route('/patient', post, methods=['POST'])])
