"""Independent, offline C4 policy checks; expected limits are literal contracts."""
import asyncio
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

import go_chi_entry as entry
from go_chi_auxiliary import AuxiliaryTransport
from go_chi_bundle import PACKAGE_FILES, build_bundle, validate_bundle
from go_chi_context import DEFAULT_BUDGET
from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal
from go_chi_policy import RECOVERY_POLICY, TIME_POLICY
from opencode_go_provider import GoFailure, SYSTEM, INSTRUCTION, SCHEMAS, DESCRIPTIONS
from request_budget import feedback

URL = 'https://opencode.ai/inference/go/openai/v1/chat/completions'
SECRET = 'synthetic-secret'
SESSION = 'chi-' + 'a' * 32
HEADERS = {'Authorization': 'Bearer ' + SECRET, 'User-Agent': 'chi-agent', 'X-OpenCode-Session': SESSION}
TOOLS = [{'type':'function','function':{'name':'read','description':'Read','strict':False,
          'parameters':{'type':'object','properties':{},'additionalProperties':False}}}]
BTOOLS = [{'type':'function','function':{'name':name,'description':DESCRIPTIONS[name],
           'parameters':SCHEMAS[name],'strict':False}} for name in ('inspect_code','verify_patch')]


def usage(output=2):
    return {'prompt_tokens':3,'completion_tokens':output,'total_tokens':3+output,'cost':0,
            'opencode':{'billing_source':'go','list_cost':0.1,'allowance':0.1}}


def request(body):
    return httpx.Request('POST', URL, headers=HEADERS, json=body)


def payload(role, max_tokens, *, prompt='instruction'):
    data={'model':'deepseek-v4.1-flash','max_tokens':max_tokens,'thinking':{'type':'enabled'},
          'reasoning_effort':'high'}
    if role=='confirmation':
        data.update(messages=[{'role':'system','content':'prompt'}, {'role':'user','content':prompt}],
                    response_format={'type':'json_object'})
    else:
        system = SYSTEM if role == 'coding_b' else 'system' + feedback(0,False)[0]
        data.update(messages=[{'role':'system','content':system},
                              {'role':'user','content':INSTRUCTION if role=='coding_b' else prompt}],
                    tools=BTOOLS if role=='coding_b' else TOOLS)
    return data


def source_copy(target):
    target.mkdir()
    for path in set(PACKAGE_FILES.values()):
        destination=target/path; destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(entry.ROOT/path,destination)


@pytest.mark.parametrize('mutation', ['valid','limit','bool','extra','time','recovery','nested_extra'])
def test_real_bundle_identity_rejects_profile_drift(tmp_path, monkeypatch, mutation):
    source=tmp_path/'source'; source_copy(source)
    profile=source/'profiles/go-chi-entry.json'
    value=json.loads(profile.read_text())
    if mutation=='limit': value['chi_max_requests']=51
    elif mutation=='bool': value['automatic_retries']=False
    elif mutation=='extra': value['unknown_field']=0
    elif mutation=='time': value['time_policy']['main_read_seconds']=241
    elif mutation=='recovery': value['output_recovery_policy']['default_enabled']=0
    elif mutation=='nested_extra': value['output_recovery_policy']['extra']=1
    profile.write_text(json.dumps(value))
    package=tmp_path/'package'; built=build_bundle(package,source_root=source)
    assert validate_bundle(package).manifest_sha256==built.manifest_sha256
    monkeypatch.setattr(entry,'ROOT',package)
    if mutation=='valid':
        identity, details=entry._identity(built.manifest_sha256)
        assert len(identity)==64 and details['bundle_manifest_sha256']==built.manifest_sha256
    else:
        with pytest.raises(GoFailure,match='chi_config_invalid'):
            entry._identity(built.manifest_sha256)


@pytest.mark.parametrize('role,limit',[('main',8192),('confirmation',32768),('coding_b',1024)])
@pytest.mark.parametrize('offset',[0,-1,1,'bool','float','str'])
def test_guard_request_wire_limit_and_journal(tmp_path,role,limit,offset):
    async def run():
        kind='coding_b' if role=='coding_b' else 'chi'
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r',kind=kind)
        sent=[]
        async def answer(req):
            sent.append(req)
            finish='length' if role=='coding_b' else 'stop'
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash','usage':usage(),
                'choices':[{'finish_reason':finish,'message':{'role':'assistant','content':'done'}}]})
        guard=ChiGuard(j,SECRET,SESSION,httpx.MockTransport(answer),tools=BTOOLS if role=='coding_b' else TOOLS,
                       system=SYSTEM if role=='coding_b' else 'system',
                       instruction=INSTRUCTION if role=='coding_b' else 'instruction',
                       claimed=lambda:False,confirmation=(lambda:('prompt','instruction')) if role=='confirmation' else lambda:None)
        n=(True if offset=='bool' else float(limit) if offset=='float' else str(limit) if offset=='str' else limit+offset)
        if offset==0 and role!='coding_b': await guard.handle_async_request(request(payload(role,n)))
        elif offset==0:
            with pytest.raises(GoFailure,match='chi_output_truncated'):
                await guard.handle_async_request(request(payload(role,n)))
        else:
            with pytest.raises(GoFailure,match='chi_request_invalid'):
                await guard.handle_async_request(request(payload(role,n)))
        assert len(sent)==(1 if offset==0 else 0)
        if sent:
            assert j.run['requests'][0]['max_tokens']==limit
            assert j.run['requests'][0]['purpose']==('main' if role=='coding_b' else role)
        j.finish('failed');j.close()
    asyncio.run(run())


@pytest.mark.parametrize('role,limit',[('main',8192),('confirmation',32768),('coding_b',1024)])
@pytest.mark.parametrize('over',[False,True])
def test_returned_usage_cap_settles_before_decision(tmp_path,role,limit,over):
    async def run():
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r',
                     kind='coding_b' if role=='coding_b' else 'chi')
        sent=[]
        async def answer(req):
            sent.append(req)
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash','usage':usage(limit+int(over)),
                'choices':[{'finish_reason':'length' if role=='coding_b' else 'stop',
                            'message':{'role':'assistant','content':'done'}}]})
        guard=ChiGuard(j,SECRET,SESSION,httpx.MockTransport(answer),tools=BTOOLS if role=='coding_b' else TOOLS,
            system=SYSTEM if role=='coding_b' else 'system',instruction=INSTRUCTION if role=='coding_b' else 'instruction',
            claimed=lambda:False,confirmation=(lambda:('prompt','instruction')) if role=='confirmation' else lambda:None)
        if over:
            with pytest.raises(GoFailure,match='chi_usage_over_limit'):
                await guard.handle_async_request(request(payload(role,limit)))
        elif role=='coding_b':
            with pytest.raises(GoFailure,match='chi_output_truncated'):
                await guard.handle_async_request(request(payload(role,limit)))
        else:
            await guard.handle_async_request(request(payload(role,limit)))
        assert len(sent)==1 and j.run['requests'][0]['status']=='settled'
        assert j.run['requests'][0]['usage']['output_tokens']==limit+int(over)
        assert j.state['pending'] is None
        j.finish('failed');j.close()
    asyncio.run(run())


def test_time_policy_literal_contract():
    assert TIME_POLICY=={'connect_seconds':30,'main_read_seconds':240,'confirmation_read_seconds':360,
        'write_seconds':60,'pool_seconds':60,'main_io_seconds':300,'confirmation_io_seconds':420,
        'b_admission_seconds':180,'chi_admission_seconds':1800,'b_operator_seconds':360,
        'chi_operator_seconds':1380,'operator_max_seconds':3600}
    assert DEFAULT_BUDGET['max_chars']==3500000 and DEFAULT_BUDGET['max_estimated_tokens']==1000000
    assert DEFAULT_BUDGET['output_reserve_tokens']==8192
    assert RECOVERY_POLICY=={'version':'chi-output-recovery-v1','default_enabled':False,
        'max_per_chain':1,'max_per_run':2,'max_output_tokens':8192,'shared_max_requests':50,
        'instruction_version':'chi-recovery-instruction-v1','view_version':'chi-recovery-view-v1'}
    profile=json.loads((entry.ROOT/'profiles/opencode-go-deepseek.json').read_text())
    assert profile['documented_context_tokens']==1048576


@pytest.mark.parametrize('role,limit,reserve',[('main',8192,8192),('confirmation',32768,32768)])
@pytest.mark.parametrize('over',[False,True])
def test_real_wire_chinese_context_boundary(tmp_path,role,limit,reserve,over):
    async def run():
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r')
        sent=[];metrics=[]
        async def answer(req):
            sent.append(req)
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash','usage':usage(),
                'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'done'}}]})
        initial=payload(role,limit,prompt='')
        base=len(request(initial).content)
        count=(1000000-reserve-base)//3 + int(over)
        prompt='病'*count
        data=payload(role,limit,prompt=prompt)
        raw=request(data).content
        assert (len(raw)+reserve>1000000)==over
        guard=ChiGuard(j,SECRET,SESSION,httpx.MockTransport(answer),tools=TOOLS,system='system',instruction=prompt,
            claimed=lambda:False,confirmation=(lambda:('prompt',prompt)) if role=='confirmation' else lambda:None,
            context_recorder=lambda m,p:metrics.append((m,p)))
        if over:
            with pytest.raises(GoFailure,match='chi_context_budget_exceeded'): await guard.handle_async_request(request(data))
        else:
            await guard.handle_async_request(request(data))
            assert metrics[0][0]['raw_bytes']==len(raw) and metrics[0][0]['effective_output_reserve_tokens']==reserve
        assert len(sent)==int(not over)
        j.finish('failed');j.close()
    asyncio.run(run())


@pytest.mark.parametrize('value,code',[(8192,None),(8192.0,'chi_context_budget_invalid'),
                                         ('8192','chi_aux_request_invalid'),(True,'chi_aux_request_invalid')])
def test_patient_probe_wire_type_and_full_chain(tmp_path,value,code):
    async def run():
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r',kind='patient_probe',
                     launch={'aux_contract':'patient-simulator-v1'})
        sent=[]
        async def answer(req):
            sent.append(req)
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash','usage':usage(),
                'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'done'}}]})
        guard=AuxiliaryTransport(j,SECRET,SESSION,httpx.MockTransport(answer),asyncio.Lock(),lambda:None)
        data={'model':'deepseek-v4.1-flash','max_tokens':value,'thinking':{'type':'enabled'},
              'reasoning_effort':'high','messages':[{'role':'system','content':'synthetic'}]}
        if code:
            with pytest.raises(GoFailure,match=code): await guard.handle_async_request(request(data))
        else:
            await guard.handle_async_request(request(data))
        assert len(sent)==int(code is None) and len(j.run['requests'])==int(code is None)
        if code is None: assert j.run['requests'][0]['max_tokens']==8192
        j.finish('failed');j.close()
    asyncio.run(run())


@pytest.mark.parametrize('role,read,wall',[('main',240,300),('confirmation',360,420),('patient',360,420)])
def test_actual_transport_timeout_by_purpose(tmp_path,role,read,wall):
    async def run():
        is_patient=role=='patient'
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r',
            kind='patient_probe' if is_patient else 'chi',
            launch={'aux_contract':'patient-simulator-v1'} if is_patient else None)
        timeouts=[];walls=[]
        async def answer(req):
            timeouts.append(req.extensions['timeout'])
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash','usage':usage(),
                'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'done'}}]})
        if is_patient:
            guard=AuxiliaryTransport(j,SECRET,SESSION,httpx.MockTransport(answer),asyncio.Lock(),lambda:None)
            data={'model':'deepseek-v4.1-flash','max_tokens':8192,'thinking':{'type':'enabled'},
                  'reasoning_effort':'high','messages':[{'role':'system','content':'synthetic'}]}
        else:
            guard=ChiGuard(j,SECRET,SESSION,httpx.MockTransport(answer),tools=TOOLS,system='system',
                instruction='instruction',claimed=lambda:False,
                confirmation=(lambda:('prompt','instruction')) if role=='confirmation' else lambda:None)
            data=payload(role,32768 if role=='confirmation' else 8192)
        original=asyncio.timeout
        def spy(value):
            walls.append(value)
            return original(value)
        with patch('asyncio.timeout',side_effect=spy):
            await guard.handle_async_request(request(data))
        assert timeouts==[{'connect':10,'read':read,'write':60,'pool':60}]
        assert walls==[wall]
        j.finish('failed');j.close()
    asyncio.run(run())


def test_mixed_confirmation_continuation_and_ten_patients_keep_shared_limit(tmp_path):
    async def run():
        from go_chi_recovery import derive_view
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r',
                     launch={'role':'cm','aux_contract':'patient-simulator-v1',
                             'output_recovery':'chi-output-recovery-v1'})
        calls=[]; active=[None]
        async def answer(req):
            calls.append(req)
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash','usage':usage(),
                'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'done'}}]})
        patient=AuxiliaryTransport(j,SECRET,SESSION,httpx.MockTransport(answer),asyncio.Lock(),lambda:active[0])
        patient_body={'model':'deepseek-v4.1-flash','max_tokens':8192,'thinking':{'type':'enabled'},
                      'reasoning_effort':'high','messages':[{'role':'system','content':'synthetic'}]}
        for i in range(10):
            active[0]=f'patient{i}'
            j.start_tool(active[0],'cm_outreach.send_message',{'session_id':'synthetic'})
            await patient.handle_async_request(request(patient_body))
            j.record_tool(active[0],'cm_outreach.send_message','ok')
        active[0]='extra'
        j.start_tool('extra','cm_outreach.send_message',{'session_id':'synthetic'})
        with pytest.raises(GoFailure,match='chi_aux_request_limit'):
            await patient.handle_async_request(request(patient_body))
        j.record_tool('extra','cm_outreach.send_message','refused')
        def settle(purpose,raw=b'{}',**kwargs):
            j.reserve(raw,purpose,**kwargs)
            j.record_response(json.dumps({'usage':usage()}).encode(),200,1)
            j.settle(usage());j.record_diagnostic('ok',1)
        settle('confirmation');settle('confirmation')
        with pytest.raises(GoFailure,match='chi_confirmation_limit'): j.reserve(b'{}','confirmation')
        parent=payload('main',8192)
        parent['messages'][0]['content']='system'+feedback(2,False)[0]
        response={'model':'deepseek-v4.1-flash','usage':usage(),
                  'choices':[{'finish_reason':'length','message':{'role':'assistant','content':'partial'}}]}
        j.reserve(json.dumps(parent).encode(),'main')
        j.record_response(json.dumps(response).encode(),200,1);j.settle(usage());j.record_diagnostic('ok',1)
        view=derive_view(parent,response,old_used=2,claimed=False)
        permit=j.issue_recovery(view)
        settle('continuation',json.dumps(view).encode(),recovery_permit=permit)
        for _ in range(46): settle('main')
        assert len(j.run['requests'])==60 and len(calls)==10
        assert sum(x['purpose']!='patient_simulator' for x in j.run['requests'])==50
        with pytest.raises(GoFailure,match='chi_request_limit'): j.reserve(b'{}','main')
        j.finish('failed');j.close()
        reopened=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='b',run='s')
        reopened.finish('failed');reopened.close()
    asyncio.run(run())


@pytest.mark.parametrize('override',[
    {'thinking':{'type':'disabled'}},
    {'reasoning_effort':'medium'},
    {'reasoning_effort':True},
    {'max_retries':1},
])
def test_guard_rejects_reasoning_or_retry_drift_before_dispatch(tmp_path,override):
    async def run():
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r')
        sent=[]
        async def answer(req):
            sent.append(req)
            raise AssertionError('must not dispatch')
        guard=ChiGuard(j,SECRET,SESSION,httpx.MockTransport(answer),tools=TOOLS,system='system',
                       instruction='instruction',claimed=lambda:False,confirmation=lambda:None)
        data=payload('main',8192);data.update(override)
        with pytest.raises(GoFailure,match='chi_request_invalid'):
            await guard.handle_async_request(request(data))
        assert sent==[] and j.run['requests']==[]
        j.finish('failed');j.close()
    asyncio.run(run())


def test_legacy_adapter_limits_are_separate_from_go_profile():
    import model_runner_adapter as legacy
    profile=json.loads((entry.ROOT/'profiles/opencode-go-deepseek.json').read_text())
    assert (legacy.MAX_ROUNDS,legacy.MAX_OUTPUT_TOKENS)==(3,128)
    assert (profile['max_requests'],profile['max_output_tokens'])==(6,1024)
    assert profile['thinking']=={'type':'enabled'} and profile['reasoning_effort']=='high'
    assert type(profile['automatic_retries']) is int and profile['automatic_retries']==0
    assert profile['context_evidence']=='documentation_only_not_measured'


@pytest.mark.parametrize('over',[False,True])
def test_continuation_usage_cap_and_timeout_are_main_limits(tmp_path,over):
    async def run():
        j=ChiJournal(tmp_path,identity='a'*64,evaluation='e',task='t',attempt='a',run='r',
                     launch={'output_recovery':'chi-output-recovery-v1'})
        sent=[];walls=[]
        async def answer(req):
            sent.append(req)
            is_first=len(sent)==1
            return httpx.Response(200,request=req,json={'model':'deepseek-v4.1-flash',
                'usage':usage(2 if is_first else 8192+int(over)),
                'choices':[{'finish_reason':'length' if is_first else 'stop',
                            'message':{'role':'assistant','content':'part' if is_first else 'done'}}]})
        guard=ChiGuard(j,SECRET,SESSION,httpx.MockTransport(answer),tools=TOOLS,system='system',
            instruction='instruction',claimed=lambda:False,confirmation=lambda:None,
            canonical_tools={'read':'local-fs-read'})
        original=asyncio.timeout
        def spy(value):
            walls.append(value)
            return original(value)
        with patch('asyncio.timeout',side_effect=spy):
            if over:
                with pytest.raises(GoFailure,match='chi_usage_over_limit'):
                    await guard.handle_async_request(request(payload('main',8192)))
            else:
                await guard.handle_async_request(request(payload('main',8192)))
        assert len(sent)==2 and walls==[300,300]
        assert [req.extensions['timeout']['read'] for req in sent]==[240,240]
        assert j.run['requests'][1]['purpose']=='continuation'
        assert j.run['requests'][1]['max_tokens']==8192
        assert j.run['requests'][1]['usage']['output_tokens']==8192+int(over)
        assert j.run['requests'][1]['status']=='settled'
        j.finish('failed');j.close()
    asyncio.run(run())
