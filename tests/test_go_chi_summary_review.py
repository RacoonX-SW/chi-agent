import asyncio,copy,hashlib,json,tempfile,unittest
from pathlib import Path
import httpx
from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal,inspect_history
from go_chi_state import TaskState
from go_chi_context import DEFAULT_BUDGET
from opencode_go_provider import GoFailure
from request_budget import feedback

SECRET='independent-synthetic-secret'; SESSION='chi-'+'b'*32
MODEL='deepseek-v4.1-flash'; URL='https://opencode.ai/inference/go/openai/v1/chat/completions'
TOOLS=[{'type':'function','function':{'name':name,'description':'Synthetic audit '+name,'strict':False,
        'parameters':{'type':'object','properties':({'case_id':{'type':'string'},'value':{'type':'string'}} if name=='write' else {}),
                      'required':(['case_id','value'] if name=='write' else []),'additionalProperties':False}}} for name in ('read','write')]
USAGE={'prompt_tokens':10,'completion_tokens':3,'total_tokens':13,'cost':0,
       'opencode':{'billing_source':'go','list_cost':0.1,'allowance':0.1}}

def candidate(data):
    return {'schema':'chi-summary-candidate-v1','selection_sha256':data['selection_sha256'],
      'protected_sha256':data['protected_sha256'],'goal':'Complete original synthetic task',
      'facts':[{'text':'Earlier observations remain historical statements.','sources':[data['sources'][0]]}],
      'uncertainties':[],'actions':[],'gaps':[],'current_work':'Continue from recent results.','next_steps':['Read current state.']}
class Flow:
    def __init__(self,parent,mode,version='chi-input-summary-v1'):
        self.mode=mode;self.version=version;self.instruction='Audit synthetic case CASE-A; preserve uncertainty.'
        self.root=parent/'ledger';self.state=TaskState(parent/'task-state',run='r',role='payer')
        self.j=ChiJournal(self.root,identity='a'*64,evaluation='e',task='synthetic',attempt='a',run='r',
          launch={'role':'payer','input_summary':version,'instruction_sha256':hashlib.sha256(self.instruction.encode()).hexdigest()})
        self.messages=[];self.sent=[];self.views=[];self.summary_calls=0;self.main_calls=0;self.post=0
        self.originals=[];self.error=None
        self.guard=ChiGuard(self.j,SECRET,SESSION,httpx.MockTransport(self.answer),tools=TOOLS,
          system='Synthetic system',instruction=self.instruction,claimed=lambda:False,confirmation=lambda:None,
          canonical_tools={'read':'triage.get','write':'payer_intake_hub.save_auth_header'},
          summary_snapshot=lambda:(None,copy.deepcopy(self.state.data)),
          context_limit=dict(DEFAULT_BUDGET,max_estimated_tokens=100000 if version.endswith('v2') else 65000))
    def reply(self,req,message,finish='stop',usage=USAGE):
        value={'model':MODEL,'choices':[{'finish_reason':finish,'message':message}]}
        if usage is not None:value['usage']=usage
        return httpx.Response(200,request=req,json=value)
    async def answer(self,req):
        body=json.loads(req.content);self.sent.append(copy.deepcopy(body))
        if 'tools' not in body:
            self.summary_calls+=1
            self.assert_summary(body)
            data=json.loads(body['messages'][1]['content'])
            if self.mode=='unknown':return self.reply(req,{'role':'assistant','content':'unknown'},usage=None)
            if self.mode=='cancel':raise asyncio.CancelledError
            if self.mode=='changed':self.state.data['version']+=1
            if self.mode=='length':return self.reply(req,{'role':'assistant','content':'partial'},'length')
            output=candidate(data)
            if self.mode=='extra':output['pending']=None
            if self.mode=='hash':output['protected_sha256']='0'*64
            if self.mode=='ref':output['facts'][0]['sources']=[{'call_id':'not_observed','result_sha256':'0'*64}]
            if self.mode=='large':output['facts']=[{'text':'中'*1000,'sources':[data['sources'][0]]} for _ in range(16)]
            if self.mode=='not_reduced':
                output['facts']=[{'text':'x'*1000,'sources':[data['sources'][0]]} for _ in range(16)]
                output['uncertainties']=[{'text':'y'*1000,'sources':[data['sources'][0]]} for _ in range(8)]
            text='{invalid' if self.mode=='invalid' else '' if self.mode=='empty' else json.dumps(output)
            if self.mode=='duplicate':text='{"schema":"duplicate",'+text[1:]
            if self.mode=='tool':return self.reply(req,{'role':'assistant','content':text,'tool_calls':[self.call('read','forbidden')]},'tool_calls')
            return self.reply(req,{'role':'assistant','content':text})
        self.main_calls+=1
        if self.summary_calls:
            self.views.append(copy.deepcopy(body));self.post+=1
            if self.mode=='replay':
                return self.reply(req,{'role':'assistant','content':None,'tool_calls':[self.call('read','new_read'),self.call('write','replayed_write')]},'tool_calls')
            if self.post==2:return self.reply(req,{'role':'assistant','content':'done'})
        name='write' if self.main_calls==1 else 'read'
        return self.reply(req,{'role':'assistant','content':None,'reasoning_content':'synthetic reasoning',
           'tool_calls':[self.call(name,'call_'+str(self.main_calls))]},'tool_calls')
    def assert_summary(self,body):
        assert set(body)=={'model','messages','max_tokens','thinking','reasoning_effort'}
        assert body['max_tokens']==(8192 if self.version.endswith('v1') else 32768) and body['reasoning_effort']=='high'
        data=json.loads(body['messages'][1]['content'])
        schema=data['output_schema']
        assert schema['properties']['schema']['const']=='chi-summary-candidate-v1'
        assert schema['additionalProperties'] is False
        assert set(schema['required'])=={'schema','selection_sha256','protected_sha256','goal','facts','uncertainties','actions','gaps','current_work','next_steps'}
        assert schema['properties']['goal']['maxLength']==schema['properties']['current_work']['maxLength']==2000
        assert schema['properties']['next_steps']['maxItems']==8 and schema['properties']['next_steps']['items']['maxLength']==1000
        assert all(schema['properties'][key]['maxItems']==16 for key in ('facts','uncertainties','actions','gaps'))
        assert schema['$defs']['statement']['properties']['sources']['uniqueItems'] is True
        assert schema['$defs']['statement']['properties']['sources']['maxItems']==8
        assert schema['$defs']['reference']['additionalProperties'] is False
        assert data['instruction']==self.instruction
        assert data['protected']['task_state']['unknowns']==[]
        assert any(a['canonical_tool']=='payer_intake_hub.save_auth_header' for a in data['protected']['tool_actions'])
    def call(self,name,call_id):
        args={'case_id':'CASE-A','value':'reviewed'} if name=='write' else {}
        return {'id':call_id,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}
    async def run(self):
        for _ in range(12):
            used=sum(r['purpose']!='patient_simulator' for r in self.j.run['requests'])
            body={'model':MODEL,'max_tokens':8192,'thinking':{'type':'enabled'},'reasoning_effort':'high','tools':TOOLS,
              'messages':[{'role':'system','content':'Synthetic system'+feedback(used,False)[0]},
                          {'role':'user','content':self.instruction}]+copy.deepcopy(self.messages)}
            self.originals.append(copy.deepcopy(body))
            req=httpx.Request('POST',URL,headers={'Authorization':'Bearer '+SECRET,'User-Agent':'chi-agent','X-OpenCode-Session':SESSION},json=body)
            try:response=await self.guard.handle_async_request(req)
            except (GoFailure,asyncio.CancelledError) as exc:
                self.error='chi_cancelled' if isinstance(exc,asyncio.CancelledError) else exc.code;break
            msg=response.json()['choices'][0]['message']
            if response.json()['choices'][0]['finish_reason']=='stop':break
            self.messages.append(copy.deepcopy(msg))
            for call in msg['tool_calls']:
                args=json.loads(call['function']['arguments']);name=call['function']['name']
                canonical={'read':'triage.get','write':'payer_intake_hub.save_auth_header'}[name]
                text='saved' if name=='write' else ('中'*4500)
                self.j.start_tool(call['id'],canonical,args)
                self.guard.contract.record_result(call['id'],text)
                self.j.record_tool(call['id'],canonical,text)
                self.messages.append({'role':'tool','tool_call_id':call['id'],'content':text})
        return self
    def close_and_audit(self):
        self.j.finish('failed' if self.error else 'complete',self.error);self.j.close()
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        digest=hashlib.sha256((self.root/'chi-accounting.json').read_bytes()).hexdigest()
        result=inspect_history(self.root,'a'*64,digest)
        assert result['status']=='inspected'
        assert before=={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
class IndependentSummary(unittest.TestCase):
    def test_v2_wrong_wire_max_is_rejected_before_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            f = Flow(Path(d), 'valid', 'chi-input-summary-v2')
            body = {'model': MODEL, 'messages': [], 'max_tokens': 8192,
                    'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'}
            req = httpx.Request('POST', URL, headers={'Authorization':'Bearer '+SECRET,
                'User-Agent':'chi-agent', 'X-OpenCode-Session':SESSION}, json=body)
            f.guard._active_summary = {'kind':'summary', 'request':req, 'body_sha256':'0'*64}
            with self.assertRaises(GoFailure) as error:
                f.guard._validate(req, req.content)
            self.assertEqual(error.exception.code, 'chi_request_invalid')
            self.assertEqual(f.sent, [])
            self.assertIsNone(f.j.state['pending'])
            f.j.close()

    def test_valid_original_history_survives_and_checkpoint_reuses(self):
        with tempfile.TemporaryDirectory() as d:
            f=asyncio.run(Flow(Path(d),'valid').run())
            self.assertIsNone(f.error);self.assertEqual(f.summary_calls,1);self.assertEqual(len(f.views),2)
            self.assertEqual(len(f.j.run['requests']),f.main_calls+1)
            self.assertEqual(f.j.run['summary_events'][0]['status'],'installed')
            self.assertTrue(any(len(json.dumps(b,ensure_ascii=False).encode())+8192>65000 for b in f.originals))
            self.assertTrue(all(len(json.dumps(b,ensure_ascii=False).encode())+8192<=65000 for b in f.views))
            self.assertEqual(len(f.guard.contract.records),len(f.messages)//2)
            self.assertTrue(all(r['result'] is not None for r in f.guard.contract.records))
            f.close_and_audit()
    def test_rejected_candidates_never_send_a_projected_main(self):
        for version in ('chi-input-summary-v1', 'chi-input-summary-v2'):
          for mode in ('invalid','extra','empty','duplicate','hash','ref','large','not_reduced','length','tool','changed','unknown','cancel'):
            if version.endswith('v2') and mode == 'not_reduced':
                continue  # This longer selection is actually reduced by the same candidate.
            with self.subTest(version=version,mode=mode),tempfile.TemporaryDirectory() as d:
                f=asyncio.run(Flow(Path(d),mode,version).run())
                self.assertIsNotNone(f.error);self.assertEqual(f.summary_calls,1);self.assertEqual(f.views,[])
                self.assertNotEqual(f.j.run['summary_events'][0]['status'],'installed')
                self.assertEqual(f.j.state['pending'] is not None,mode in {'unknown','cancel'})
                if mode not in {'unknown','cancel'}:self.assertTrue(all(r['status']=='settled' for r in f.j.run['requests']))
                f.close_and_audit()
    def test_replayed_completed_write_rejects_whole_new_batch(self):
        with tempfile.TemporaryDirectory() as d:
            f=asyncio.run(Flow(Path(d),'replay').run())
            self.assertEqual(f.error,'chi_summary_replay');self.assertEqual(f.summary_calls,1)
            self.assertFalse(any(r['id'] in {'new_read','replayed_write'} for r in f.guard.contract.records))
            self.assertFalse(any(e['call_id'] in {'new_read','replayed_write'} for e in f.j.run['tool_events']))
            self.assertIsNone(f.j.state['pending']);f.close_and_audit()
if __name__=='__main__':unittest.main(verbosity=2)
