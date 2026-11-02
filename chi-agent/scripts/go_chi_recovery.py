"""Versioned, offline-only primitives for bounded output recovery.

Nothing in this module sends a request or grants a permit. Tool names here are
canonical local/MCP names, not model aliases; unlisted names fail closed.
"""
from __future__ import annotations

import hashlib
import json
import re

POLICY = 'chi-output-recovery-v1'
VIEW = 'chi-recovery-view-v1'
INSTRUCTION_VERSION = 'chi-recovery-instruction-v1'
PARTIAL = ('The previous response was interrupted by the output length limit. Continue the original task. '
           'Only accepted tool history establishes executed facts. If finishing, provide a complete standalone '
           'final answer. Do not treat the unfinished fragment as a completed action.')
REGENERATE = ('The previous response was interrupted by the output length limit. Its entire tool batch was not '
              'executed. Generate a complete next response from the accepted history. Do not replay completed '
              'actions recorded there.')
DIGEST = re.compile(r'^[0-9a-f]{64}$')

READ = frozenset('''local-fs-read local-fs-list local-fs-search local-task-state local-role-guidance
local-read-patient-observation local-completion-check local-evidence-sources local-evidence-excerpt
local-evidence-check chart.get_patient_chart_by_patient chart.list_candidate_orders chart.search_patients
cases.list_cases
forms.list_required_forms forms.validate_form p2p_session.get_context people.list_contacts
people.list_ordering_providers people.list_reviewer_contacts payer_intake_hub.list_intake_queue
payer_intake_hub.get_intake_case triage.get triage.calculate_sla
triage.check_gold_card determination.get_summary
p2p.list payer_letter_center.list payer_letter_center.get payer_letter_center.audit_completeness
cm_intake.list_referral_queue cm_intake.get_referral cm_chart.get_chart_data cm_outreach.get_transcript'''.split())
# Retrieval methods known to synchronize or materialize persisted records are mutations.
MUTATION = frozenset('''local-fs-write local-fs-edit local-confirm-patient local-claim_done local-state-update
cases.create_from_order inbox.list_messages inbox.read_message cases.get_case docs.get_document
docs.list_case_documents auth.check_status payer_intake_hub.list_documents review.get_nurse_review_data
review.get_md_review_data docs.create_submission_bundle docs.upload_evidence docs.upload_evidence_file
forms.save_form_response auth.file_appeal auth.file_external_appeal auth.finalize_provider_determination
auth.request_peer_to_peer auth.respond_to_peer_to_peer auth.respond_to_pend auth.submit_authorization
p2p_session.send_turn p2p_session.submit_summary payer_intake_hub.create_intake_case
payer_intake_hub.save_auth_header payer_intake_hub.save_diagnoses payer_intake_hub.save_requesting_provider
payer_intake_hub.add_line_item payer_intake_hub.update_line_item payer_intake_hub.remove_line_item
payer_intake_hub.confirm_decisions triage.set_disposition triage.route_case review.save_criteria_evaluation
review.submit_nurse_case_recommendation review.save_md_review review.submit_md_case_decision determination.finalize
p2p.offer_slots p2p.schedule p2p.record_outcome payer_letter_center.generate_approval
payer_letter_center.generate_partial_approval payer_letter_center.generate_denial payer_letter_center.generate_pend
payer_letter_center.generate_notification payer_letter_center.deliver payer_letter_center.reissue
cm_intake.open_case cm_intake.disenroll_case cm_chart.submit_chart_review cm_outreach.start_outreach_call
cm_outreach.send_message cm_outreach.end_outreach_call cm_assessment.start_assessment cm_assessment.save_section
cm_assessment.complete_assessment cm_care_plan.create_draft cm_care_plan.save_care_plan cm_care_plan.finalize'''.split())


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def classify(name):
    if name in READ: return 'read'
    if name in MUTATION: return 'mutation'
    raise ValueError('chi_recovery_tool_unclassified')


def mode_and_fragment(payload):
    """Validate the trusted, complete length response's recoverable shape."""
    if type(payload) is not dict or payload.get('model') != 'deepseek-v4.1-flash':
        raise ValueError('chi_response_invalid')
    choices = payload.get('choices')
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise ValueError('chi_response_invalid')
    choice = choices[0]
    msg = choice.get('message')
    if (choice.get('finish_reason') != 'length' or type(msg) is not dict or msg.get('role') != 'assistant'
            or msg.get('function_call') is not None or set(msg) - {'role', 'content', 'reasoning_content', 'tool_calls', 'function_call', 'refusal', 'annotations', 'audio'}
            or any(msg.get(k) is not None for k in ('refusal', 'annotations', 'audio'))
            or any(msg.get(k) is not None and type(msg[k]) is not str for k in ('content', 'reasoning_content'))):
        raise ValueError('chi_response_invalid')
    calls = msg.get('tool_calls')
    if calls is not None and type(calls) is not list: raise ValueError('chi_response_invalid')
    if calls:
        for call in calls:
            if (type(call) is not dict or set(call) not in ({'id', 'type', 'function'}, {'id', 'type', 'function', 'index'})
                    or type(call['id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', call['id'])
                    or call['type'] != 'function'
                    or ('index' in call and (type(call['index']) is not int or call['index'] < 0))):
                raise ValueError('chi_response_invalid')
            fn = call['function']
            if (type(fn) is not dict or set(fn) != {'name', 'arguments'}
                    or type(fn['name']) is not str or type(fn['arguments']) is not str):
                raise ValueError('chi_response_invalid')
        return 'regenerate', None
    fragment = {k: msg[k] for k in ('content', 'reasoning_content') if msg.get(k) is not None}
    if not any(fragment.values()): raise ValueError('chi_response_invalid')
    return 'partial', fragment


def derive_view(parent_body, response, *, old_used, claimed):
    """Derive a wire body from the persisted parent; no arbitrary history accepted.

    Guard remains responsible for proving SDK history against ToolContract.
    """
    import copy
    from request_budget import feedback
    if (type(parent_body) is not dict or type(parent_body.get('messages')) is not list
            or len(parent_body['messages']) < 2 or type(old_used) is not int or old_used < 0
            or type(claimed) is not bool):
        raise ValueError('chi_recovery_invalid')
    messages = parent_body['messages']
    if (type(messages[0]) is not dict or set(messages[0]) != {'role', 'content'}
            or messages[0]['role'] != 'system' or type(messages[0]['content']) is not str
            or type(messages[1]) is not dict or set(messages[1]) != {'role', 'content'}
            or messages[1]['role'] != 'user' or type(messages[1]['content']) is not str):
        raise ValueError('chi_recovery_invalid')
    pending = set()
    seen = set()
    for msg in messages[2:]:
        if type(msg) is not dict:
            raise ValueError('chi_recovery_invalid')
        if msg.get('role') == 'assistant':
            calls = msg.get('tool_calls')
            if pending or type(calls) is not list or not calls:
                raise ValueError('chi_recovery_invalid')
            for call in calls:
                if type(call) is not dict or type(call.get('id')) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', call['id']) or call['id'] in seen:
                    raise ValueError('chi_recovery_invalid')
                seen.add(call['id']); pending.add(call['id'])
        elif msg.get('role') == 'tool':
            if set(msg) != {'role', 'tool_call_id', 'content'} or msg['tool_call_id'] not in pending:
                raise ValueError('chi_recovery_invalid')
            pending.remove(msg['tool_call_id'])
        else:
            raise ValueError('chi_recovery_invalid')
    if pending: raise ValueError('chi_recovery_invalid')
    suffix = feedback(old_used, claimed)[0]
    if not messages[0]['content'].endswith(suffix): raise ValueError('chi_recovery_history_changed')
    result = copy.deepcopy(parent_body)
    system = result['messages'][0]['content']
    result['messages'][0]['content'] = system[:-len(suffix)] + feedback(old_used + 1, claimed)[0] if suffix else system + feedback(old_used + 1, claimed)[0]
    mode, fragment = mode_and_fragment(response)
    if mode == 'partial':
        result['messages'].append({'role': 'assistant', **fragment})
    result['messages'].append({'role': 'user', 'content': PARTIAL if mode == 'partial' else REGENERATE})
    return result


def validate_permit(doc, *, identity, run, parent_round, parent_request, parent_response, response_sha256, old_used, claimed):
    """Validate a permit against already verified, restricted wire evidence.

    The caller must independently verify journal identity, parent settlement,
    raw evidence hashes, no intervening request and the SDK ToolContract.
    """
    fields = {'schema', 'policy', 'identity', 'evaluation', 'task', 'attempt', 'run',
              'root_round', 'parent_round', 'parent_response_sha256', 'mode', 'chain_ordinal',
              'history_version', 'history_sha256', 'instruction_version', 'view_version', 'view_sha256',
              'continuation_round', 'decision', 'result', 'view_body'}
    if (type(doc) is not dict or set(doc) != fields or doc['schema'] != 'chi-recovery-permit-v1'
            or doc['policy'] != POLICY or doc['identity'] != identity
            or any(doc[k] != run[k] for k in ('evaluation', 'task', 'attempt', 'run'))
            or type(parent_round) is not int or parent_round < 1
            or type(doc['root_round']) is not int or doc['root_round'] != parent_round
            or type(doc['parent_round']) is not int or doc['parent_round'] != parent_round
            or doc['parent_response_sha256'] != response_sha256
            or type(response_sha256) is not str or not DIGEST.fullmatch(response_sha256)
            or type(doc['chain_ordinal']) is not int or doc['chain_ordinal'] != 1
            or doc['history_version'] != 'chi-tool-history-v1'
            or doc['instruction_version'] != INSTRUCTION_VERSION or doc['view_version'] != VIEW
            or doc['continuation_round'] is not None or doc['decision'] != 'issued'
            or doc['result'] != 'pending'):
        raise ValueError('chi_recovery_invalid')
    expected_mode, _ = mode_and_fragment(parent_response)
    view = derive_view(parent_request, parent_response, old_used=old_used, claimed=claimed)
    if (doc['mode'] != expected_mode or doc['history_sha256'] != canonical_sha(parent_request['messages'])
            or doc['view_sha256'] != canonical_sha(view) or canonical_sha(doc['view_body']) != canonical_sha(view)):
        raise ValueError('chi_recovery_history_changed')
