import asyncio,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import go_chi_journal as journal_module
from go_chi_journal import ChiJournal,inspect_history
from opencode_go_provider import GoFailure
from test_go_chi_summary_review import Flow

class PersistenceMatrix(unittest.TestCase):
    def test_checkpoint_boundaries_are_sticky_and_never_retry(self):
      for version in ('chi-input-summary-v1', 'chi-input-summary-v2'):
        for kind in ('summary-selection','summary-candidate','summary-checkpoint','summary-projection'):
            with self.subTest(version=version,kind=kind),tempfile.TemporaryDirectory() as d:
                f=Flow(Path(d),'valid',version);original=journal_module.write_evidence;hits=[]
                def fail(root,run,number,selected,value):
                    if selected==kind:
                        hits.append(selected);raise OSError('synthetic fsync/write failure')
                    return original(root,run,number,selected,value)
                with patch.object(journal_module,'write_evidence',side_effect=fail):asyncio.run(f.run())
                self.assertEqual(hits,[kind]);self.assertEqual(f.error,'chi_summary_persistence_failed')
                self.assertEqual(f.summary_calls,0 if kind=='summary-selection' else 1)
                self.assertEqual(f.views,[]);self.assertIsNone(f.j.state['pending'])
                before=len(f.j.run['requests'])
                with self.assertRaises(GoFailure) as error:f.j.reserve(b'{}','main')
                self.assertEqual(error.exception.code,'chi_summary_persistence_failed')
                self.assertEqual(len(f.j.run['requests']),before)
                f.j.finish('failed',f.error);f.j.close()
                digest=hashlib.sha256((f.root/'chi-accounting.json').read_bytes()).hexdigest()
                try:
                    value=inspect_history(f.root,'a'*64,digest);status=value['status']
                    self.assertIs(value['execution_allowed'],False)
                except GoFailure as exc:status=exc.code
                print(json.dumps({'fault':kind,'summary_calls':f.summary_calls,'requests':before,'inspection':status,
                    'event_status':f.j.run['summary_events'][0]['status'] if f.j.run['summary_events'] else None}))
if __name__=='__main__':unittest.main(verbosity=2)
