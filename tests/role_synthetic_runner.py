"""Docker-only synthetic transport shim; never invokes a real provider."""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx

import chi_agent.cli as go_chi_entry
import chi_agent.opencode_go_provider as opencode_go_provider
import scripts.development.run_role_in_bundle as role_runner


def response(request, message, finish='stop'):
    return httpx.Response(200, request=request, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1,
        'model': 'deepseek-v4.1-flash', 'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5,
        'cost': 0, 'opencode': {'billing_source': 'go', 'list_cost': 0, 'allowance': 0}},
        'choices': [{'index': 0, 'finish_reason': finish, 'message': message}]})


def choose(field, text):
    match = re.search(r'"' + field + r'"\s*:\s*"([^"\\]+)"', text)
    if not match: raise ValueError('synthetic_field_missing_' + field)
    return match.group(1)


async def development(journal, secret, run_chi, kwargs):
    main_count = 0
    case = None
    async def main_reply(request):
        nonlocal main_count, case
        main_count += 1
        body = json.loads(request.content)
        tools = [m for m in body['messages'] if m.get('role') == 'tool']
        last = str(tools[-1]['content']) if tools else ''
        role = os.environ.get('SYNTHETIC_ROLE', 'cm')
        if role != 'cm':
            if main_count == 1:
                name, args = ('chart__search_patients' if role == 'provider' else 'payer_intake_hub__list_intake_queue'), {}
            elif main_count == 2 and role == 'payer':
                pdfs = sorted(p for p in Path('/logs/artifacts/workspaces').rglob('*.pdf') if p.parent.name == 'incoming_request')
                if len(pdfs) != 4: raise ValueError('synthetic_payer_pdfs_missing')
                name, args = 'local-fs-read', {'path': str(pdfs[0])}
            else:
                return response(request, {'role': 'assistant', 'content': 'Synthetic transport completed.'})
        elif main_count == 1: name, args = 'cm_intake__list_referral_queue', {}
        elif main_count == 2:
            name, args = 'cm_intake__open_case', {'referral_id': choose('referral_id', last), 'priority': 'standard', 'program': 'chronic_disease'}
        elif main_count == 3:
            case = choose('case_id', last)
            name, args = 'cm_chart__submit_chart_review', {'case_id': case, 'review': {}}
        elif main_count == 4: name, args = 'cm_outreach__start_outreach_call', {'case_id': case}
        elif main_count == 5: name, args = 'cm_outreach__send_message', {'session_id': choose('session_id', last), 'message': 'Hello from a synthetic test.'}
        else: return response(request, {'role': 'assistant', 'content': 'Synthetic transport completed.'})
        return response(request, {'role': 'assistant', 'content': None, 'reasoning_content': 'synthetic',
            'tool_calls': [{'id': f'call_{main_count}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}, 'tool_calls')

    async def patient_reply(request):
        if os.environ.get('SYNTHETIC_PATIENT_FAILURE') == '1':
            return httpx.Response(400, request=request, json={'error': 'synthetic failure',
                'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5,
                          'cost': 0, 'opencode': {'billing_source': 'go', 'list_cost': 0, 'allowance': 0}}})
        return response(request, {'role': 'assistant', 'content': 'Synthetic response. ###STOP###'})

    await kwargs['lower'].aclose()
    kwargs['lower'] = httpx.MockTransport(main_reply)
    original = role_runner.PatientBroker
    role_runner.PatientBroker = lambda j, s, cap, lock, lower: original(j, s, cap, lock, lambda: httpx.MockTransport(patient_reply))
    try:
        return await role_runner.development(journal, secret, run_chi, kwargs)
    finally:
        role_runner.PatientBroker = original


if __name__ == '__main__':
    if sys.argv[1] == 'coding-b':
        httpx.AsyncHTTPTransport = lambda *args, **kwargs: httpx.MockTransport(opencode_go_provider._offline_responder())
        raise SystemExit(go_chi_entry.main(sys.argv[1:]))
    raise SystemExit(go_chi_entry.main(sys.argv[1:], development=development))
