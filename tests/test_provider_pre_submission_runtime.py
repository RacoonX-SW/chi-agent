"""Synthetic provider pre-submission branches through the Go SDK and MCP bridge."""
import asyncio
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from chi_agent.accounting.journal import ChiJournal, inspect_history
from chi_agent.agent.runtime import run_chi


@pytest.mark.parametrize('action', ['submit_pa', 'gather_more_evidence', 'do_not_submit'])
def test_provider_v3_branches_through_go_transport(tmp_path, action):
    asyncio.run(_exercise(tmp_path, action))


def test_malformed_successful_submit_is_not_redispatched(tmp_path):
    asyncio.run(_exercise(tmp_path, 'submit_pa', submit_outcome='malformed'))


def test_submit_error_with_unknown_effect_is_not_redispatched(tmp_path):
    asyncio.run(_exercise(tmp_path, 'submit_pa', submit_outcome='tool_error'))


def test_submission_requires_rebuilding_bundle_after_form_write(tmp_path):
    asyncio.run(_exercise(tmp_path, 'submit_pa', form_changed=True))


async def _exercise(tmp_path, action, submit_outcome='success', form_changed=False):
    verified = submit_outcome == 'success'
    patient = {'id':'P1', 'dob':'1970-01-01', 'sex':'male'}
    order = {'id':'O1', 'patient_id':'P1', 'procedure_code':'12345', 'site_of_service':'office'}
    chart = {'patient':patient, 'orders':[order], 'summaries':['90 day treatment trial']}
    roster = {'items':[patient], 'total':1}
    status = {'value':'draft', 'bundle_id':None}
    events = []; wire = []
    class Server:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def list_tools(self):
            def tool(name, props, required):
                return SimpleNamespace(name=name, description='synthetic', inputSchema={'type':'object','properties':props,'required':required,'additionalProperties':False})
            strprops = lambda *keys: {key:{'type':'string'} for key in keys}
            return [tool('chart.search_patients', {}, []), tool('chart.get_patient_chart_by_patient', strprops('patient_id'), ['patient_id']),
                    tool('cases.create_from_order', strprops('patient_id','source_order_id','procedure_code','description','site_of_service'), ['patient_id','source_order_id','procedure_code','description','site_of_service']),
                    tool('auth.finalize_provider_determination', strprops('case_id','final_action'), ['case_id','final_action']),
                    tool('docs.create_submission_bundle', {'case_id':{'type':'string'}, 'document_ids':{'type':'array','items':{'type':'string'}}}, ['case_id','document_ids']),
                    tool('forms.save_form_response', strprops('case_id'), ['case_id']),
                    tool('auth.submit_authorization', strprops('case_id','channel','bundle_document_id'), ['case_id','channel','bundle_document_id']),
                    tool('cases.get_case', strprops('case_id'), ['case_id'])]
        async def call_tool(self, name, args):
            events.append((name, args))
            case = lambda: {'id':'C1','patient_id':'P1','service_request_id':'O1','status':status['value']}
            if name == 'chart.search_patients': value = roster
            elif name == 'chart.get_patient_chart_by_patient': value = chart
            elif name == 'cases.create_from_order': value = {'case':case(),'patient':patient,'service_request':order}
            elif name == 'auth.finalize_provider_determination':
                status['value'] = {'submit_pa':'ready_to_submit','gather_more_evidence':'docs_needed','do_not_submit':'closed'}[args['final_action']]
                value = {'case':case(), 'next_actions':[], 'message':'recorded'}
            elif name == 'docs.create_submission_bundle':
                status['bundle_id'] = 'B2' if status['bundle_id'] else 'B1'
                value = {'bundle_document':{'id':status['bundle_id'],'case_id':'C1','patient_id':'P1','kind':'submission_bundle'},'readiness':{'ready_to_submit':True,'missing_items':[],'warnings':[]}}
            elif name == 'forms.save_form_response': value = {'case':case()}
            elif name == 'auth.submit_authorization':
                if submit_outcome == 'tool_error':
                    from mcp.types import CallToolResult, TextContent
                    return CallToolResult(isError=True, content=[TextContent(type='text', text='synthetic response error')])
                status['value'] = 'submitted' if verified else 'draft'; value = {'case':case(),'intake_case':{'id':'I1'}}
            elif name == 'cases.get_case':
                packets = [{'case_id':'C1','status':'submitted','payload':{'bundle_document_id':status['bundle_id']}}] if status['value'] == 'submitted' else []
                value = {'case':case(),'patient':patient,'service_request':order,'submission_packets':packets}
            else: raise AssertionError(name)
            return SimpleNamespace(isError=False, structuredContent=value, content=[], model_dump=lambda **_: {'structuredContent':value,'content':[],'isError':False})
    create = {'patient_id':'P1','source_order_id':'O1','procedure_code':'12345','description':'test service','site_of_service':'office'}
    policy = tmp_path/'handbook'/'rule.txt'
    calls = [('search','chart__search_patients',{}), ('chart','chart__get_patient_chart_by_patient',{'patient_id':'P1'}),
             ('confirm','local-confirm-patient',{'patient_id':'P1','instruction_quote':'90 day treatment trial','chart_quote':'90 day treatment trial'}),
             ('bad_create','cases__create_from_order',create),
             ('location','local-state-update',{'provider_location':{'site_of_service':'office','source_call_id':'chart','quote':'office'}}),
             ('wrong_site','cases__create_from_order',dict(create, site_of_service='home')),
             ('wrong_service','cases__create_from_order',dict(create, procedure_code='67890')),
             ('create','cases__create_from_order',create),
             ('policy','local-fs-read',{'path':str(policy)}),
             ('early_bundle','docs__create_submission_bundle',{'case_id':'C1','document_ids':[]}),
             ('review','local-state-update',{'provider_review':{'case_id':'C1','action':action,'rationale':'The evidence was reviewed.', 'policy_source_call_id':'policy','policy_quote':'A policy requires evidence.', 'clinical_source_call_id':'chart','clinical_quote':'90 day treatment trial'}}),
             ('decision','auth__finalize_provider_determination',{'case_id':'C1','final_action':action})]
    if action == 'submit_pa':
        calls += [('bundle','docs__create_submission_bundle',{'case_id':'C1','document_ids':[]}),
                  ('before_submit','cases__get_case',{'case_id':'C1'})]
        if form_changed:
            calls += [('edit_form','forms__save_form_response',{'case_id':'C1'}),
                      ('stale_bundle','auth__submit_authorization',{'case_id':'C1','channel':'portal','bundle_document_id':'B1'}),
                      ('rebuild','docs__create_submission_bundle',{'case_id':'C1','document_ids':[]})]
        calls += [('submit','auth__submit_authorization',{'case_id':'C1','channel':'portal','bundle_document_id':'B2' if form_changed else 'B1'})]
    else:
        calls += [('blocked_bundle','docs__create_submission_bundle',{'case_id':'C1','document_ids':[]}),
                  ('blocked_submit','auth__submit_authorization',{'case_id':'C1','channel':'portal','bundle_document_id':'B1'})]
    if not verified:
        calls += [('submit_again','auth__submit_authorization',{'case_id':'C1','channel':'fax','bundle_document_id':'B1'})]
    calls += [('readback','cases__get_case',{'case_id':'C1'}), ('claim','local-claim_done',{})]
    main = iter(calls)
    async def reply(request):
        body = json.loads(request.content); wire.append(body)
        if 'response_format' in body:
            value = {'status':'unique_match','selected_patient_id':'P1','matches':['P1'],'mismatches':[],'unknown':[],
                     'evidence':[{'instruction_quote':'90 day treatment trial','chart_quote':'90 day treatment trial'}]}
            message = {'role':'assistant','content':json.dumps(value)}; finish = 'stop'
        else:
            call = next(main, None)
            if call is None: message = {'role':'assistant','content':'done'}; finish = 'stop'
            else:
                cid, name, args = call
                message = {'role':'assistant','content':None,'reasoning_content':'synthetic', 'tool_calls':[{'id':cid,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}; finish = 'tool_calls'
        return httpx.Response(200, request=request, json={'id':'synthetic','object':'chat.completion','created':0,'model':'deepseek-v4.1-flash','choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5,'cost':0,'opencode':{'billing_source':'go','list_cost':0.1,'allowance':0.1}}})
    instruction = tmp_path/'instruction'; instruction.write_text('90 day treatment trial')
    handbook = tmp_path/'handbook'; handbook.mkdir(); policy.write_text('A policy requires evidence.')
    workspace = tmp_path/'workspace'; workspace.mkdir()
    server = Server(); root = tmp_path/'state'
    journal = ChiJournal(root, identity='a'*64, evaluation='eval', task='provider', attempt='a', run='run', launch={'context_policy':'chi-context-v3','source_evidence_policy':'canonical-v1','role':'provider'})
    try:
        async def run():
            return await run_chi(journal,'synthetic-secret',role='provider',instruction='90 day treatment trial',mcp_url='http://synthetic.invalid/mcp',instruction_path=instruction,logs_dir=tmp_path/'logs',workspace_root=workspace,handbook_root=handbook,tool_references=[],lower=httpx.MockTransport(reply),server_factory=lambda _:server)
        if not verified:
            from chi_agent.models.opencode_go_provider import GoFailure
            with pytest.raises(GoFailure, match='chi_claim_required'):
                await run()
        else:
            await run()
        assert len([e for e in events if e[0]=='cases.create_from_order']) == 1
        assert len([e for e in events if e[0]=='docs.create_submission_bundle']) == ((2 if form_changed else 1) if action == 'submit_pa' else 0)
        assert len([e for e in events if e[0]=='auth.submit_authorization']) == (1 if action == 'submit_pa' else 0)
        by_id = {m['tool_call_id']:m['content'] for body in wire for m in body['messages'] if m.get('role') == 'tool'}
        assert 'provider_location_evidence_required' in by_id['bad_create']
        assert 'provider_location_evidence_required' in by_id['wrong_site']
        assert 'provider_location_evidence_required' in by_id['wrong_service']
        assert 'provider_submit_decision_required' in by_id['early_bundle']
        if form_changed:
            assert 'provider_ready_bundle_required' in by_id['stale_bundle']
            assert [args['bundle_document_id'] for name, args in events if name == 'auth.submit_authorization'] == ['B2']
        if not verified:
            assert 'provider_submission_outcome_unverified' in by_id['submit_again']
            assert 'completion_blocked_unknown:' in by_id['claim']
        else:
            assert by_id['claim'] == 'task marked as done'
        stages = []
        for body in wire:
            for message in body['messages']:
                try:
                    anchor = json.loads(message.get('content') or '')
                except (TypeError, ValueError):
                    continue
                if type(anchor) is dict and anchor.get('schema') == 'chi-intent-anchor-v1':
                    stages.append(anchor['current_step'])
        assert 'verify_evidence' in stages
        if verified:
            assert 'verify_and_close' in stages
        if action == 'submit_pa' and verified:
            assert stages.index('verify_evidence') < stages.index('prepare_packet') < stages.index('submit_or_defer') < stages.index('verify_and_close')
        elif action != 'submit_pa':
            assert 'prepare_packet' not in stages and 'submit_or_defer' not in stages
        from chi_agent.cli import _read_run_log_checked, _is_completion
        run_log = tmp_path/'logs'/'run_log.txt'
        assert _read_run_log_checked(tmp_path/'logs') is not None
        original = json.loads(run_log.read_text())
        if verified:
            assert original['completion']['claim']['target'] == {'case_id': 'C1', 'patient_id': 'P1'}
        legacy = json.loads(json.dumps(original['completion']))
        legacy['completion_evidence'].pop('failed_terminal_objects')
        assert _is_completion(legacy)
        from chi_agent.agent.task_state import TaskState
        empty = TaskState(tmp_path/'empty-state', run='empty', role='provider', context_policy='chi-context-v3')
        blocked = empty.completion_report()
        assert blocked['required_readback'] == 'terminal_object'
        original['completion'] = blocked
        run_log.write_text(json.dumps(original))
        assert _read_run_log_checked(tmp_path/'logs') is not None
        journal.finish('complete' if verified else 'failed', error=None if verified else 'chi_claim_required'); journal._validate('a'*64)
    finally: journal.close()
    raw = (root/'chi-accounting.json').read_bytes()
    assert inspect_history(root,'a'*64,hashlib.sha256(raw).hexdigest())['status'] == 'inspected'


def test_candidate_order_reducer_preserves_location_and_procedure():
    from chi_agent.context.context_assembly import reduce_tool_result
    items = [{'id':f'O{i}', 'patient_id':'P1', 'procedure_code':'12345', 'site_of_service':'22', 'description':'service', 'private_field':'irrelevant'} for i in range(12)]
    reduced, _ = reduce_tool_result('chart.list_candidate_orders', json.dumps({'items':items,'total':12}))
    first = json.loads(reduced)['items'][0]
    assert first['site_of_service'] == '22' and first['procedure_code'] == '12345'
    assert 'private_field' not in first and len(json.loads(reduced)['items']) == 10


@pytest.mark.parametrize(('instruction', 'allowed'), [
    ('The study is scheduled at the office.', True),
    ('It is untrue that the study is scheduled at the office.', False),
    ('The study is scheduled at the office annex.', False),
    ('The study is scheduled at the office only if another site cannot be used.', False),
])
def test_location_quote_retains_the_full_sentence(tmp_path, instruction, allowed):
    from chi_agent.agent.task_state import TaskState

    binding = SimpleNamespace(bound='P1')
    state = TaskState(tmp_path / 'state', run='run', role='provider', binding=binding,
                      context_policy='chi-context-v3')
    state.provider_configure(lambda: None, {}, instruction, tmp_path / 'instruction', tmp_path, [])
    start = instruction.lower().index('the study')
    quote = instruction[start:instruction.index('office', start) + len('office')]
    state.propose({'provider_location': {'site_of_service': 'office', 'source_call_id': 'instruction',
                                         'quote': quote}})
    reason = state.provider_gate('cases.create_from_order', {'site_of_service': 'office', 'description': 'study'})
    assert reason is None if allowed else reason.startswith('provider_location_evidence_required')


def test_policy_version_uses_full_same_snapshot_across_pages(tmp_path):
    from chi_agent.tools.pdf_resource_reader import read_allowed_file
    from chi_agent.agent.task_state import TaskState
    path = tmp_path/'policy.txt'; path.write_bytes(b'A policy requires evidence.\r\nSecond line.\rThird line.')
    versions = []
    first = read_allowed_file(path, 1, 1, pdf_enabled=True, source_version=versions.append)
    second = read_allowed_file(path, 2, 1, pdf_enabled=True, source_version=versions.append)
    assert first == 'A policy requires evidence.\n' and second == 'Second line.\n'
    assert versions[0] == versions[1] == hashlib.sha256(path.read_bytes()).hexdigest()
    binding = SimpleNamespace(bound='P1', cases={}, documents={}, patient_documents={})
    state = TaskState(tmp_path/'state-policy', run='run', role='provider', binding=binding, context_policy='chi-context-v3')
    records = [{'id':'one','name':'local-fs-read','arguments':{'path':str(path),'offset':1,'limit':1},'result':first},
               {'id':'two','name':'local-fs-read','arguments':{'path':str(path),'offset':2,'limit':1},'result':second}]
    guard = SimpleNamespace(contract=SimpleNamespace(records=records), canonical_tools={'local-fs-read':'local-fs-read'}, full_results={'one':first,'two':second})
    state.provider_configure(lambda:guard, {'one':first,'two':second}, 'task', tmp_path/'instruction', tmp_path, [])
    state.provider_file_versions.update({'one':versions[0], 'two':versions[1]})
    for rec in records:
        state.observe(call_id=rec['id'],tool='local-fs-read',kind='local',arguments=rec['arguments'],result=rec['result'],scope='shared_public')
    source = state._provider_source('one','A policy requires evidence.','policy')
    assert state._provider_current(source)
    path.write_text('Modified policy.\nSecond line.\nThird line.')
    new_versions=[]
    third=read_allowed_file(path, 2, 1, pdf_enabled=True, source_version=new_versions.append)
    records.append({'id':'three','name':'local-fs-read','arguments':{'path':str(path),'offset':2,'limit':1},'result':third})
    guard.full_results['three'] = third; state.provider_file_versions['three'] = new_versions[0]
    state.observe(call_id='three',tool='local-fs-read',kind='local',arguments=records[-1]['arguments'],result=third,scope='shared_public')
    assert third == second and not state._provider_current(source)


@pytest.mark.parametrize(('text', 'quote', 'allowed'), [
    ('Pre-operative assessment; medically cleared; planned arthroscopic RCR (CPT 12345) at Example Memorial Hospital HOPD; ASC access attestation was completed citing equipment unavailable at Alternate Surgical Center.', 'planned arthroscopic RCR (CPT 12345) at Example Memorial Hospital HOPD', True),
    ('Pre-operative H&P and surgical planning; medically cleared for general anesthesia; planned repair (CPT 12345) at Example Memorial Hospital HOPD; ASC access attestation completed citing specialized equipment unavailability at Alternate Surgical Center.', 'planned repair (CPT 12345) at Example Memorial Hospital HOPD', True),
    ('Requesting HOPD authorization for CPT 12345 R shoulder arthroscopic repair based on: (1) complexity, and (2) equipment unavailable at accessible ASC (Alternate Surgical Center).', 'Requesting HOPD authorization for CPT 12345 R shoulder arthroscopic repair based on: (1) complexity, and (2) equipment unavailable at accessible ASC (Alternate Surgical Center)', True),
    ('Requesting HOPD authorization for CPT 12345 repair based on: (1) complexity and (2) equipment not available at accessible ASC (Other Facility).', 'Requesting HOPD authorization for CPT 12345 repair based on: (1) complexity and (2) equipment not available at accessible ASC (Other Facility)', True),
    ('**Planned Facility:** Example Memorial Hospital (HOPD), NPI 1234567890\n\n## Procedure Plan\n**Planned Procedure:** shoulder repair — CPT 12345\n**Laterality:** Right\n**Anesthesia:** General\n**Setting:** HOPD — see rationale below\n\n## Rationale\nDetails.', '**Planned Facility:** Example Memorial Hospital (HOPD), NPI 1234567890', True),
    ('**Planned Procedure:** arthroscopic repair CPT 12345\n**Planned Facility:** Example Hospital (HOPD)\n**Setting:** HOPD', 'Example Hospital (HOPD)', True),
    ('**Planned Procedure:** arthroscopic repair CPT 12345\n**Planned Facility:** Example Hospital (HOPD)\n**Setting:** HOPD', '**Planned Facility:** Example Hospital (HOPD)', True),
    ('Prior visit at Example Hospital HOPD; planned repair CPT 12345 at office.', 'Example Hospital HOPD', False),
    ('Planned repair CPT 67890 at Example Hospital HOPD.', 'Planned repair CPT 67890 at Example Hospital HOPD', False),
    ('Not planned repair CPT 12345 at Example Hospital HOPD.', 'planned repair CPT 12345 at Example Hospital HOPD', False),
    ('Planned repair CPT 12345 at Example Hospital HOPD if needed.', 'Planned repair CPT 12345 at Example Hospital HOPD', False),
    ('Planned repair CPT 12345 and CPT 67890 at Example Hospital HOPD.', 'Planned repair CPT 12345 and CPT 67890 at Example Hospital HOPD', False),
    ('This was cancelled; planned repair CPT 12345 at Example Hospital HOPD.', 'planned repair CPT 12345 at Example Hospital HOPD', False),
    ('Planned repair CPT 12345 at Example Hospital HOPD; only if cleared.', 'Planned repair CPT 12345 at Example Hospital HOPD', False),
    ('Planned repair CPT 12345 at Example Hospital HOPD; scheduled at the office.', 'Planned repair CPT 12345 at Example Hospital HOPD', False),
    ('Requesting HOPD authorization for CPT 12345 repair based on: only if cleared.', 'Requesting HOPD authorization for CPT 12345 repair based on: only if cleared', False),
    ('Requesting HOPD authorization for CPT 12345 repair, but the surgery is planned at an ASC.', 'Requesting HOPD authorization for CPT 12345 repair', False),
    ('Requesting HOPD authorization for CPT 12345 repair based on: HOPD unavailable.', 'Requesting HOPD authorization for CPT 12345 repair', False),
    ('Planned repair (CPT 12345) at Example Hospital hospital outpatient department.', 'Planned repair (CPT 12345) at Example Hospital hospital outpatient department', True),
    ('Requesting HOPD authorization for CPT 123456 repair.', 'Requesting HOPD authorization for CPT 123456 repair', False),
    ('**Planned Procedure:** repair CPT 12345\n**Planned Facility:** Example Hospital (HOPD)\n**Setting:** office', 'Example Hospital (HOPD)', False),
    ('**Planned Facility:** Example Hospital (HOPD), NPI 1234567890\n## Procedure Plan\n**Planned Procedure:** repair CPT 12345\n**Other Procedure:** repair CPT 67890\n**Setting:** HOPD', 'Example Hospital (HOPD)', False),
    ('**Planned Facility:** Example Hospital (HOPD), NPI 1234567890\n## Procedure Plan\n**Planned Procedure:** repair CPT 12345\n**Setting:** office', 'Example Hospital (HOPD)', False),
    ('**Planned Facility:** Example Hospital (HOPD), NPI 1234567890\n## Other section\n## Procedure Plan\n**Planned Procedure:** repair CPT 12345\n**Setting:** HOPD', 'Example Hospital (HOPD)', False),
])
def test_hopd_location_statement(text, quote, allowed):
    from chi_agent.agent.task_state import _provider_location_statement
    assert _provider_location_statement(text, quote, 'outpatient hospital', {'procedure_code':'12345', 'description':'arthroscopic repair'}) is allowed
