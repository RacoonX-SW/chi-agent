import asyncio,copy,hashlib,json,shutil,tempfile,unittest
from pathlib import Path
from go_chi_journal import inspect_history
from go_chi_summary import validate_saved_source
from opencode_go_provider import GoFailure
from request_budget import feedback
from test_go_chi_summary_review import Flow

class ReaderMatrix(unittest.TestCase):
    def test_strict_keys_types_links_and_source_facts(self):
        with tempfile.TemporaryDirectory() as d:
            f=asyncio.run(Flow(Path(d),'valid').run());assert f.error is None
            f.close_and_audit()
            state=json.loads((f.root/'chi-accounting.json').read_text());run=state['attempts'][0]
            number=run['summary_events'][0]['summary_round']
            selected=json.loads((f.root/'wire-evidence'/'r'/f'{number:03d}-summary-selection.json').read_text())
            prefix=copy.deepcopy(run);prefix['requests']=prefix['requests'][:number-1]
            options=dict(root=f.root,run=prefix,identity='a'*64,used=selected['source_used'],
              claimed=selected['claimed'],canonical_tools=selected['canonical_tools'])
            validate_saved_source(body=selected['source_body'],protected=selected['protected'],**options)
            for mode in ('task','old_result','claim'):
                with self.subTest(source=mode):
                    body=copy.deepcopy(selected['source_body']);protected=copy.deepcopy(selected['protected']);kwargs=dict(options)
                    if mode=='task':
                        body['messages'][1]['content']='forged task'
                        protected['instruction_sha256']=hashlib.sha256(b'forged task').hexdigest()
                    elif mode=='old_result':
                        body['messages'][3]['content']='forged old result'
                        protected['tool_actions'][0]['result_sha256']=hashlib.sha256(b'forged old result').hexdigest()
                    else:
                        kwargs['claimed']=True;protected['claim_done']=True;protected['task_state']=None
                        body['messages'][0]['content']='Synthetic system'+feedback(selected['source_used'],True)[0]
                    with self.assertRaises(ValueError):validate_saved_source(body=body,protected=protected,**kwargs)
            for mode in ('run_extra','event_extra','round_bool','projection_bool','missing_link','unknown_status'):
                with self.subTest(stored=mode),tempfile.TemporaryDirectory() as t:
                    target=Path(t)/'state';shutil.copytree(f.root,target)
                    bad=copy.deepcopy(state);r=bad['attempts'][0];e=r['summary_events'][0]
                    if mode=='run_extra':r['summary_unvalidated']=True
                    elif mode=='event_extra':e['extra']=True
                    elif mode=='round_bool':e['summary_round']=True
                    elif mode=='projection_bool':e['projections'][0]['round']=True
                    elif mode=='missing_link':e['projections'].pop()
                    else:e['status']='unrecognized'
                    path=target/'chi-accounting.json';path.write_text(json.dumps(bad,ensure_ascii=False))
                    before={str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
                    with self.assertRaises(GoFailure):inspect_history(target,'a'*64,hashlib.sha256(path.read_bytes()).hexdigest())
                    assert before=={str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
if __name__=='__main__':unittest.main(verbosity=2)
