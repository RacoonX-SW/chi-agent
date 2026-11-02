import asyncio
import json

import httpx
import pytest

from go_chi_journal import ChiJournal, inspect_history
from go_chi_recovery import POLICY
from go_chi_runtime import run_chi
from opencode_go_provider import GoFailure
from test_go_chi_capabilities_runtime import Server, completion
from test_go_chi_recovery_journal import digest


def length(message):
    payload=completion()
    payload['choices'][0]['finish_reason']='length'
    payload['choices'][0]['message']={'role':'assistant', **message}
    return payload


def setup(tmp_path, role, name, payloads, hook=None):
    (tmp_path/'handbook').mkdir(); (tmp_path/'handbook'/'policy.md').write_text('synthetic policy')
    (tmp_path/'workspace'/'CASE-A'/role).mkdir(parents=True)
    instruction=tmp_path/'instruction';instruction.write_text('Synthetic task')
    j=ChiJournal(tmp_path/'state',identity='a'*64,evaluation='e',task='t',attempt='a',run='r',
                 launch={'output_recovery':POLICY, 'role':role})
    server=Server(tuple(name) if isinstance(name, list) else (name,)); seen=[]
    async def wire(req):
        seen.append(json.loads(req.content))
        if hook: hook(j, len(seen), req)
        item=payloads[len(seen)-1]
        if isinstance(item,BaseException): raise item
        return httpx.Response(200,request=req,json=item)
    async def execute():
        return await run_chi(j,'synthetic-secret',role=role,instruction='Synthetic task',
            mcp_url='http://synthetic.invalid/mcp',instruction_path=instruction,logs_dir=tmp_path/'logs',
            workspace_root=tmp_path/'workspace',handbook_root=tmp_path/'handbook',tool_references=[],
            lower=httpx.MockTransport(wire),server_factory=lambda _:server)
    return j,server,seen,execute


@pytest.mark.parametrize('role,name,model_name',[
    ('payer','triage.get','triage__get'),
    ('provider','chart.search_patients','chart__search_patients'),
    ('cm','cm_intake.list_referral_queue','cm_intake__list_referral_queue'),
])
@pytest.mark.parametrize('mode',['partial','regenerate'])
def test_real_sdk_recovery_tool_loop(tmp_path,role,name,model_name,mode):
    message={'reasoning_content':'partial reasoning'}
    if mode=='regenerate':
        message={'tool_calls':[{'id':'unfinished','type':'function',
                  'function':{'name':model_name,'arguments':'{'}}]}
    responses=[length(message),completion([('fresh',model_name,{})]),completion()]
    j,server,seen,execute=setup(tmp_path,role,name,responses)
    assert asyncio.run(execute())=='done'
    assert len(seen)==3 and server.calls==[(name,{})]
    if mode=='regenerate':
        assert all(not m.get('tool_calls') for m in seen[1]['messages'])
    else:
        assert seen[1]['messages'][-2]['reasoning_content']=='partial reasoning'
    assert any(m.get('tool_call_id')=='fresh' for m in seen[2]['messages'])
    assert any(m.get('reasoning_content')=='reason' for m in seen[2]['messages'] if m.get('role')=='assistant')
    summary=json.loads((tmp_path/'logs'/'run_log.txt').read_text())
    assert summary['physical_requests']=={'main':2,'confirmation':0,'continuation':1,'patient_simulator':0}
    assert summary['logical_model_steps']==2 and summary['recovery_permits_consumed']==1
    assert summary['journal_usage']['input_tokens_known']==9
    metrics=[json.loads(x) for x in (tmp_path/'logs'/'context.jsonl').read_text().splitlines()]
    assert [x['purpose'] for x in metrics]==['main','continuation','main']
    trace=[json.loads(x) for x in (tmp_path/'logs'/'wire-trace.jsonl').read_text().splitlines()]
    assert [x['purpose'] for x in trace]==['main','continuation','main']
    assert trace[1]['mode']==mode and trace[1]['parent_round']==1
    decisions=[json.loads(x) for x in (tmp_path/'logs'/'recovery-trace.jsonl').read_text().splitlines()]
    assert len(decisions)==1 and decisions[0]['mode']==mode and decisions[0]['result']=='settled'
    assert summary['journal_usage_scope']=='account_namespace'
    assert 'partial reasoning' not in json.dumps(trace) and 'synthetic-secret' not in json.dumps(trace)
    j.finish('complete');j.close()
    assert inspect_history(tmp_path/'state','a'*64,digest(tmp_path/'state'))['status']=='inspected'


def test_real_sdk_second_length_has_two_settled_and_failure_trace(tmp_path):
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[length({'content':'part'}),length({'content':'again'})])
    with pytest.raises(GoFailure,match='chi_output_truncated'): asyncio.run(execute())
    summary=json.loads((tmp_path/'logs'/'run_log.txt').read_text())
    trace=[json.loads(x) for x in (tmp_path/'logs'/'wire-trace.jsonl').read_text().splitlines()]
    assert len(seen)==2 and len(trace)==2 and summary['safe_error_code']=='chi_output_truncated'
    decisions=[json.loads(x) for x in (tmp_path/'logs'/'recovery-trace.jsonl').read_text().splitlines()]
    assert decisions[0]['result']=='failed' and decisions[0]['safe_stop_code']=='chi_output_truncated'
    assert all(x['status']=='settled' for x in j.run['requests']) and server.calls==[]
    j.finish('failed');j.close()


def test_provider_recovery_write_refused_without_binding(tmp_path):
    target=str(tmp_path/'workspace'/'CASE-A'/'provider'/'note.txt')
    payloads=[length({'content':'part'}), completion([('write','local-fs-write',{'path':target,'content':'x'})]), completion()]
    j,server,seen,execute=setup(tmp_path,'provider','chart.search_patients',payloads)
    assert asyncio.run(execute())=='done'
    assert not (tmp_path/'workspace'/'CASE-A'/'provider'/'note.txt').exists()
    assert any(e['call_id']=='write' and e['event']=='refused' for e in j.run['tool_events'])
    assert any('REFUSED' in str(m.get('content')) for m in seen[2]['messages'] if m.get('role')=='tool')
    j.finish('failed');j.close()


def test_sdk_completed_write_replay_rejects_entire_batch(tmp_path):
    write='cm_intake__open_case'; read='cm_intake__list_referral_queue'
    payloads=[completion([('old',write,{})]), length({'content':'part'}),
              completion([('new',write,{}),('sibling',read,{})])]
    j,server,seen,execute=setup(tmp_path,'cm',['cm_intake.open_case','cm_intake.list_referral_queue'],payloads)
    with pytest.raises(GoFailure,match='chi_recovery_replay'): asyncio.run(execute())
    assert len(seen)==3 and server.calls==[('cm_intake.open_case',{})]
    assert not any(e['call_id'] in {'new','sibling'} for e in j.run['tool_events'])
    j.finish('failed');j.close()


def test_sdk_duplicate_id_rejects_batch(tmp_path):
    payloads=[completion([('old','triage__get',{})]),length({'content':'part'}),
              completion([('old','triage__get',{}),('sibling','triage__get',{})])]
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',payloads)
    with pytest.raises(GoFailure,match='chi_tool_batch_invalid'): asyncio.run(execute())
    assert len(seen)==3 and server.calls==[('triage.get',{})]
    assert not any(e['call_id']=='sibling' for e in j.run['tool_events'])
    j.finish('failed');j.close()


def test_sdk_changed_state_stops_before_permit(tmp_path):
    def mutate(j, count, req):
        if count==1: j.run['claim_done']=True
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[length({'content':'part'})],hook=mutate)
    with pytest.raises(GoFailure,match='chi_recovery_invalid'): asyncio.run(execute())
    assert len(seen)==1 and j.run['recovery_events']==[] and server.calls==[]
    j.finish('failed');j.close()


def test_sdk_cancel_keeps_unknown_and_trace(tmp_path):
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError): asyncio.run(execute())
    trace=[json.loads(x) for x in (tmp_path/'logs'/'wire-trace.jsonl').read_text().splitlines()]
    summary=json.loads((tmp_path/'logs'/'run_log.txt').read_text())
    assert len(seen)==1 and len(trace)==1 and trace[0]['status']=='pending'
    assert summary['safe_error_code']=='chi_cancelled' and j.state['pending'] is not None
    j.finish('failed');j.close()


def test_sdk_wire_trace_failure_stops_after_settlement(tmp_path):
    from unittest.mock import patch
    from pathlib import Path
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[length({'content':'part'})])
    old=Path.open
    def fault(path,*args,**kwargs):
        if path.name=='wire-trace.jsonl' and args and args[0]=='a': raise OSError('synthetic')
        return old(path,*args,**kwargs)
    with patch.object(Path,'open',fault):
        with pytest.raises(GoFailure,match='chi_log_persistence_failed'): asyncio.run(execute())
    assert len(seen)==1 and j.run['requests'][0]['status']=='settled' and j.run['recovery_events']==[]
    summary=json.loads((tmp_path/'logs'/'run_log.txt').read_text())
    assert summary['physical_requests']['main']==1
    j.finish('failed');j.close()


@pytest.mark.parametrize('role,name',[('payer','triage.get'),('cm','cm_intake.list_referral_queue')])
def test_claim_then_recovery_cannot_mutate(tmp_path, role, name):
    target=str(tmp_path/'workspace'/'CASE-A'/role/'note.txt')
    responses=[completion([('claim','local-claim_done',{})]),length({'content':'part'}),
               completion([('write','local-fs-write',{'path':target,'content':'x'})]), completion()]
    j,server,seen,execute=setup(tmp_path,role,name,responses)
    with pytest.raises(GoFailure,match='chi_claim_violation'): asyncio.run(execute())
    assert len(seen)==4 and not (tmp_path/'workspace'/'CASE-A'/role/'note.txt').exists()
    assert any(e['call_id']=='write' and e['event']=='refused' for e in j.run['tool_events'])
    j.finish('failed');j.close()


def test_refused_write_is_not_treated_as_completed_replay(tmp_path):
    target=str(tmp_path/'workspace'/'CASE-A'/'provider'/'note.txt')
    args={'path':target,'content':'x'}
    responses=[completion([('first','local-fs-write',args)]),length({'content':'part'}),
               completion([('second','local-fs-write',args)]),completion()]
    j,server,seen,execute=setup(tmp_path,'provider','chart.search_patients',responses)
    assert asyncio.run(execute())=='done'
    assert len(seen)==4 and not (tmp_path/'workspace'/'CASE-A'/'provider'/'note.txt').exists()
    assert {e['call_id'] for e in j.run['tool_events'] if e['event']=='refused'}=={'first','second'}
    j.finish('failed');j.close()


def test_sdk_parent_wire_history_tamper_stops(tmp_path):
    def mutate(j, count, req):
        if count==1: req._content = b'{}'
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[length({'content':'part'})],hook=mutate)
    with pytest.raises(GoFailure,match='chi_recovery_history_changed'): asyncio.run(execute())
    assert len(seen)==1 and j.run['recovery_events']==[]
    j.finish('failed');j.close()


def test_sdk_cancel_after_permit_records_not_sent(tmp_path):
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[length({'content':'part'})])
    original=j.issue_recovery
    def issue(*args,**kwargs):
        index=original(*args,**kwargs)
        asyncio.current_task().cancel()
        return index
    j.issue_recovery=issue
    with pytest.raises(asyncio.CancelledError): asyncio.run(execute())
    rows=[json.loads(x) for x in (tmp_path/'logs'/'recovery-trace.jsonl').read_text().splitlines()]
    assert len(seen)==1 and len(rows)==1 and rows[0]['result']=='not_sent'
    assert rows[0]['decision']=='consumed' and rows[0]['safe_stop_code']=='chi_cancelled'
    j.finish('failed');j.close()


def test_cli_recovery_is_live_only_and_default_off(capsys):
    import go_chi_entry as entry
    args=entry._parser().parse_args(['coding-b','--bundle-sha256','a'*64])
    from go_chi_policy import RECOVERY_POLICY
    from go_chi_recovery import VIEW, INSTRUCTION_VERSION
    assert args.output_recovery is None and entry.CONFIG['output_recovery_policy']['default_enabled'] is False
    assert RECOVERY_POLICY['version']==POLICY and RECOVERY_POLICY['view_version']==VIEW
    assert RECOVERY_POLICY['instruction_version']==INSTRUCTION_VERSION
    assert entry.main(['coding-b','--bundle-sha256','a'*64,'--output-recovery',POLICY])==1
    assert 'chi_recovery_invalid' in capsys.readouterr().out


def test_later_limit_not_attributed_to_prior_recoveries(tmp_path):
    payloads=[length({'content':'part1'}),completion([('one','triage__get',{})]),
              length({'content':'part2'}),completion([('two','triage__get',{})]),length({'content':'part3'})]
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',payloads)
    with pytest.raises(GoFailure,match='chi_recovery_limit'): asyncio.run(execute())
    decisions=[json.loads(x) for x in (tmp_path/'logs'/'recovery-trace.jsonl').read_text().splitlines()]
    assert len(decisions)==2 and all(row['result']=='settled' and row['safe_stop_code'] is None for row in decisions)
    assert len(seen)==5 and len(server.calls)==2
    j.finish('failed');j.close()


def test_sdk_cancel_during_continuation_keeps_pending_and_own_stop_code(tmp_path):
    j,server,seen,execute=setup(tmp_path,'payer','triage.get',[length({'content':'part'}),asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError): asyncio.run(execute())
    rows=[json.loads(x) for x in (tmp_path/'logs'/'recovery-trace.jsonl').read_text().splitlines()]
    wires=[json.loads(x) for x in (tmp_path/'logs'/'wire-trace.jsonl').read_text().splitlines()]
    assert len(seen)==2 and len(rows)==1 and len(wires)==2
    assert rows[0]['result']=='pending' and rows[0]['safe_stop_code']=='chi_cancelled'
    assert j.state['pending']=={'run':'r','round':2}
    j.finish('failed');j.close()
