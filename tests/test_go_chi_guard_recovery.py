import asyncio
import copy
import json
from unittest.mock import patch

import httpx
import pytest

from chi_agent.request_guard import ChiGuard
from chi_agent.journal import ChiJournal, inspect_history
from chi_agent.output_recovery import POLICY
from chi_agent.opencode_go_provider import GoFailure
from test_go_chi_guard import SECRET, SESSION, TOOLS, USAGE, body, request
from test_go_chi_recovery_journal import digest


def response(message, reason='length', usage=USAGE):
    return {'model': 'deepseek-v4.1-flash', 'usage': usage,
            'choices': [{'finish_reason': reason, 'message': {'role': 'assistant', **message}}]}


def run_test(coro): return asyncio.run(coro)


def setup(root, payloads, *, enabled=True, tools=TOOLS, mapping=None, **kwargs):
    j = ChiJournal(root, identity='a'*64, evaluation='e', task='t', attempt='a', run='r',
                   launch={'output_recovery': POLICY} if enabled else {})
    sent = []
    async def answer(req):
        sent.append(json.loads(req.content))
        item = payloads[len(sent)-1]
        if isinstance(item, BaseException): raise item
        return httpx.Response(200, request=req, json=item)
    g = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=tools, system='system',
                 instruction='instruction', claimed=lambda: False, confirmation=lambda: None,
                 canonical_tools=mapping or {'read': 'local-fs-read'}, **kwargs)
    return j, g, sent


@pytest.mark.parametrize('fragment', [{'content': 'part'}, {'reasoning_content': 'thought'}])
def test_partial_recovers_and_counts(tmp_path, fragment):
    async def run():
        metrics=[]
        j,g,sent=setup(tmp_path, [response(fragment), response({'content': 'done'}, 'stop')],
                       context_recorder=lambda metric,purpose: metrics.append((metric,purpose)))
        result=await g.handle_async_request(request(body()))
        assert result.json()['choices'][0]['message']['content']=='done'
        assert len(sent)==2 and sent[1]['messages'][-2]=={'role':'assistant', **fragment}
        assert [x['purpose'] for x in j.run['requests']]==['main','continuation']
        assert [x[1] for x in metrics]==['main','continuation']
        assert j.run['recovery_events'][0]['continuation_round']==2
        j.finish('complete'); j.close()
        assert inspect_history(tmp_path, 'a'*64, digest(tmp_path))['status']=='inspected'
    run_test(run())


def test_off_length_stops(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'})],enabled=False)
        with pytest.raises(GoFailure,match='chi_output_truncated'): await g.handle_async_request(request(body()))
        assert len(sent)==1 and j.run['requests'][0]['status']=='settled'
        j.finish('failed');j.close()
    run_test(run())


def test_regenerate_then_valid_tool_batch(tmp_path):
    async def run():
        half={'id':'bad','type':'function','function':{'name':'read','arguments':'{'}}
        good={'id':'new','type':'function','function':{'name':'read','arguments':'{}'}}
        complete={'id':'first','type':'function','function':{'name':'read','arguments':'{}'}}
        j,g,sent=setup(tmp_path,[response({'tool_calls':[complete,half]}), response({'tool_calls':[good]},'tool_calls')])
        await g.handle_async_request(request(body()))
        assert len(sent)==2 and all('tool_calls' not in msg for msg in sent[1]['messages'])
        assert [r['id'] for r in g.contract.records]==['new'] and 'bad' not in g.contract.seen and 'first' not in g.contract.seen
        g.contract.record_result('new','ok'); j.finish('failed'); j.close()
    run_test(run())


def test_second_length_stops_without_third(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'}),response({'content':'again'})])
        with pytest.raises(GoFailure,match='chi_output_truncated'): await g.handle_async_request(request(body()))
        assert len(sent)==2 and all(x['status']=='settled' for x in j.run['requests'])
        j.finish('failed');j.close()
    run_test(run())


@pytest.mark.parametrize('failure', ['unknown','duplicate_id','replay'])
def test_recovery_batch_rejected_atomically(tmp_path,failure):
    async def run():
        defs=copy.deepcopy(TOOLS); defs.append(copy.deepcopy(defs[0])); defs[1]['function']['name']='write'
        mapping={'read':'local-fs-read','write':'local-fs-write'}
        calls=[{'id':'new1','type':'function','function':{'name':'write','arguments':'{}'}},
               {'id':'new2','type':'function','function':{'name':'read','arguments':'{}'}}]
        j,g,sent=setup(tmp_path,[response({'content':'part'}),response({'tool_calls':calls},'tool_calls')],
                       tools=defs,mapping=mapping if failure!='unknown' else {'read':'local-fs-read'})
        data=body();data['tools']=defs
        if failure in ('duplicate_id','replay'):
            previous={'role':'assistant','content':None,'tool_calls':[{'id':'old','type':'function',
                       'function':{'name':'write','arguments':'{}'}}]}
            g.contract.accept_batch(previous);g.contract.record_result('old','ok')
            j.start_tool('old','local-fs-write',{});j.record_tool('old','local-fs-write','ok')
            data['messages'] += [previous,{'role':'tool','tool_call_id':'old','content':'ok'}]
        if failure=='duplicate_id': calls[0]['id']='old'
        code={'unknown':'chi_recovery_tool_unclassified','duplicate_id':'chi_tool_batch_invalid',
              'replay':'chi_recovery_replay'}[failure]
        with pytest.raises(GoFailure,match=code): await g.handle_async_request(request(data))
        assert len(sent)==2 and all(record['id']=='old' for record in g.contract.records)
        assert 'new2' not in g.contract.seen
        j.finish('failed');j.close()
    run_test(run())


def test_blocker_stops_before_permit(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'})],recovery_blocker=lambda: True)
        with pytest.raises(GoFailure,match='chi_recovery_invalid'): await g.handle_async_request(request(body()))
        assert len(sent)==1 and j.run['recovery_events']==[]
        j.finish('failed');j.close()
    run_test(run())


@pytest.mark.parametrize('case', ['network','timeout','usage','secret','oversized','cancel'])
def test_fatal_main_never_continues(tmp_path,case):
    async def run():
        if case=='network': item=httpx.ConnectError('synthetic')
        elif case=='timeout': item=httpx.ReadTimeout('synthetic')
        elif case=='cancel': item=asyncio.CancelledError()
        elif case=='usage': item=response({'content':'part'},usage={'prompt_tokens':1})
        elif case=='secret': item=response({'content':SECRET})
        else: item=response({'content':'x'*(4*1024*1024+1)})
        j,g,sent=setup(tmp_path,[item])
        expected={'network':'chi_transport_error','timeout':'chi_timeout','usage':'chi_usage_unknown',
                  'secret':'chi_secret_in_body','oversized':'chi_response_too_large','cancel':'chi_cancelled'}[case]
        exc_type=asyncio.CancelledError if case=='cancel' else GoFailure
        with pytest.raises(exc_type): await g.handle_async_request(request(body()))
        assert g.error==expected and len(sent)==1 and j.run['recovery_events']==[]
        if case in {'network','timeout','usage','oversized','cancel'}: assert j.state['pending'] is not None
        j.finish('failed');j.close()
    run_test(run())


def test_mutated_contract_history_blocks_before_permit(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'})])
        async def mutate(req):
            sent.append(req); g.contract.refusals['alien']='changed'
            return httpx.Response(200,request=req,json=response({'content':'part'}))
        g.lower=httpx.MockTransport(mutate)
        with pytest.raises(GoFailure,match='chi_recovery_history_changed'):
            await g.handle_async_request(request(body()))
        assert len(sent)==1 and j.run['recovery_events']==[]
        j.finish('failed');j.close()
    run_test(run())


def test_budget_exceeded_before_issue(tmp_path):
    async def run():
        from chi_agent.context_budget import DEFAULT_BUDGET, measure_request
        raw=request(body()).content
        original=measure_request(body(),raw)
        limit=dict(DEFAULT_BUDGET,max_estimated_tokens=original['estimated_tokens']+8192+10)
        j,g,sent=setup(tmp_path,[response({'content':'part'*100})],context_limit=limit)
        with pytest.raises(GoFailure,match='chi_context_budget_exceeded'):
            await g.handle_async_request(request(body()))
        assert len(sent)==1 and j.run['recovery_events']==[]
        j.finish('failed');j.close()
    run_test(run())


def test_block_after_issued_keeps_consumed_permit(tmp_path):
    async def run():
        n=[0]
        def blocker():
            n[0]+=1
            return n[0]>=3
        j,g,sent=setup(tmp_path,[response({'content':'part'})],recovery_blocker=blocker)
        with pytest.raises(GoFailure,match='chi_recovery_invalid'): await g.handle_async_request(request(body()))
        assert len(sent)==1 and len(j.run['recovery_events'])==1
        assert j.run['recovery_events'][0]['continuation_round'] is None
        j.finish('failed');j.close()
        assert inspect_history(tmp_path, 'a'*64, digest(tmp_path))['status']=='inspected'
    run_test(run())


@pytest.mark.parametrize('point', ['issue','reserve','response','settle','diagnostic'])
def test_fault_boundaries_do_not_trigger_another_send(tmp_path,point):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'}),response({'content':'done'},'stop')])
        if point=='issue': target='issue_recovery'; fail_at=1
        elif point=='reserve': target='reserve'; fail_at=2
        elif point=='response': target='record_response'; fail_at=2
        elif point=='settle': target='settle'; fail_at=2
        else: target='record_diagnostic'; fail_at=2
        original=getattr(j,target); seen=[0]
        def fault(*args,**kwargs):
            seen[0]+=1
            if seen[0]==fail_at: raise OSError('synthetic fault')
            return original(*args,**kwargs)
        with patch.object(j,target,side_effect=fault):
            with pytest.raises(GoFailure): await g.handle_async_request(request(body()))
        assert len(sent)==(1 if point in {'issue','reserve'} else 2)
        assert g.error is not None
        j.close()
    run_test(run())


def test_cancel_while_waiting_for_second_lock_preserves_permit(tmp_path):
    async def run():
        lock=asyncio.Lock()
        j,g,sent=setup(tmp_path,[response({'content':'part'})],billing_lock=lock)
        original=j.issue_recovery
        def issue(*args,**kwargs):
            result=original(*args,**kwargs)
            asyncio.current_task().cancel()
            return result
        j.issue_recovery=issue
        task = asyncio.create_task(g.handle_async_request(request(body())))
        with pytest.raises(asyncio.CancelledError): await task
        assert g.error=='chi_cancelled' and len(sent)==1 and len(j.run['recovery_events'])==1
        assert j.run['recovery_events'][0]['continuation_round'] is None
        j.finish('failed');j.close()
    run_test(run())


def test_two_independent_chains_then_third_stops(tmp_path):
    async def run():
        payloads = [response({'content':'part'}), response({'content':'done'},'stop'),
                    response({'content':'part'}), response({'content':'done'},'stop'),
                    response({'content':'part'})]
        j,g,sent=setup(tmp_path,payloads)
        await g.handle_async_request(request(body(0)))
        await g.handle_async_request(request(body(2)))
        with pytest.raises(GoFailure,match='chi_recovery_limit'):
            await g.handle_async_request(request(body(4)))
        assert len(sent)==5 and len(j.run['recovery_events'])==2
        j.finish('failed'); j.close()
    run_test(run())


def test_shared_fiftieth_request_no_continuation(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'})])
        for _ in range(49):
            j.reserve(b'{}','main'); j.record_response(json.dumps({'usage':USAGE}).encode(),200,1)
            j.settle(USAGE); j.record_diagnostic('ok',1)
        with pytest.raises(GoFailure,match='chi_recovery_limit'):
            await g.handle_async_request(request(body(49)))
        assert len(sent)==1 and len(j.run['requests'])==50 and j.run['recovery_events']==[]
        j.finish('failed'); j.close()
    run_test(run())


def test_repeated_read_allowed(tmp_path):
    async def run():
        prior={'role':'assistant','content':None,'tool_calls':[{'id':'old','type':'function',
                'function':{'name':'read','arguments':'{}'}}]}
        call={'id':'new','type':'function','function':{'name':'read','arguments':'{}'}}
        j,g,sent=setup(tmp_path,[response({'content':'part'}),response({'tool_calls':[call]},'tool_calls')])
        g.contract.accept_batch(prior); g.contract.record_result('old','ok')
        data=body(); data['messages'] += [prior,{'role':'tool','tool_call_id':'old','content':'ok'}]
        await g.handle_async_request(request(data))
        assert [r['id'] for r in g.contract.records]==['old','new']
        g.contract.record_result('new','ok');j.finish('failed');j.close()
    run_test(run())


def test_admission_expiry_after_main_prevents_recovery(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'content':'part'})])
        async def expire(req):
            sent.append(req); g.run_started -= 10000
            return httpx.Response(200,request=req,json=response({'content':'part'}))
        g.lower=httpx.MockTransport(expire)
        with pytest.raises(GoFailure,match='chi_run_time_limit'):
            await g.handle_async_request(request(body()))
        assert len(sent)==1 and j.run['recovery_events']==[]
        j.finish('failed');j.close()
    run_test(run())


def test_invalid_original_tool_container_is_not_recovered(tmp_path):
    async def run():
        j,g,sent=setup(tmp_path,[response({'tool_calls':[{'id':'incomplete'}]})])
        with pytest.raises(GoFailure,match='chi_response_invalid'):
            await g.handle_async_request(request(body()))
        assert len(sent)==1 and j.run['recovery_events']==[] and g.contract.records==[]
        j.finish('failed');j.close()
    run_test(run())
