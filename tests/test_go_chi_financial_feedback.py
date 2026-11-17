import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chi_agent.accounting.journal import ChiJournal, acknowledge_unsettled, audit_or_rebind, inspect_history
from chi_agent.agent.runtime_policy import FEE_POLICY
from chi_agent.models.opencode_go_provider import GoFailure
from test_go_chi_inspect import event
from test_go_chi_journal import USAGE, settle


def fixture(root):
    identity = 'a' * 64
    j = ChiJournal(root, identity=identity, evaluation='e', task='t', attempt='a', run='r')
    j.reserve(b'{}', 'main'); j.record_diagnostic('chi_timeout', 1); j.finish('failed', 'chi_timeout'); j.close()
    provider = root.parent / 'synthetic-provider.json'; provider.write_text(json.dumps(event()))
    return dict(identity=identity, accounting_sha256=hashlib.sha256((root / 'chi-accounting.json').read_bytes()).hexdigest(),
                run='r', round_number=1, request_sha256=hashlib.sha256(b'{}').hexdigest(), provider_path=provider,
                provider_sha256=hashlib.sha256(provider.read_bytes()).hexdigest(), reason='user authorized continuation')


class FinancialFeedbackTests(unittest.TestCase):
    def test_entry_ack_uses_existing_local_q_and_checked_target(self):
        import contextlib
        import io
        import chi_agent.cli as entry
        from chi_agent.models.opencode_go_provider import GoJournal, source_identity
        with tempfile.TemporaryDirectory() as d:
            qroot = Path(d)/'q'
            q = GoJournal(qroot, 'synthetic-q', source_identity()); q.finish('failed', 'synthetic_failed', 0); q.close()
            root = qroot/'chi-evaluation'; root.mkdir(); args = fixture(root)
            output = io.StringIO()
            with patch.object(entry, '_identity', return_value=('b'*64, {})), contextlib.redirect_stdout(output):
                code = entry.main(['acknowledge-unsettled', '--bundle-sha256', 'c'*64, '--history-mode', 'local',
                    '--local-q-root', str(qroot), '--output-root', str(root), '--expected-old-identity', args['identity'],
                    '--expected-accounting-sha256', args['accounting_sha256'], '--target-run', args['run'],
                    '--target-round', '1', '--expected-request-sha256', args['request_sha256'],
                    '--provider-record', str(args['provider_path']), '--provider-record-sha256', args['provider_sha256'],
                    '--acknowledgement-reason', args['reason']])
            self.assertEqual(code, 0); self.assertEqual(json.loads(output.getvalue())['status'], 'acknowledged_unsettled')

    def test_old_policy_keeps_missing_cost_halt(self):
        with tempfile.TemporaryDirectory() as d:
            j = ChiJournal(Path(d), identity='a'*64, evaluation='e', task='t', attempt='a', run='r')
            usage = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}
            j.reserve(b'one', 'main')
            with self.assertRaisesRegex(GoFailure, 'billing_details_unknown'): settle(j, usage)
            j.finish('failed'); j.close()
            digest = hashlib.sha256((Path(d)/'chi-accounting.json').read_bytes()).hexdigest()
            self.assertEqual(inspect_history(Path(d), 'a'*64, digest)['usage']['billing_details_warnings'], 0)
            with self.assertRaisesRegex(GoFailure, 'chi_billing_halted'):
                ChiJournal(Path(d), identity='a'*64, evaluation='e', task='t', attempt='b', run='s')

    def test_non_go_and_invalid_source_do_not_warn(self):
        for source in ('balance', 'byok', 3):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as d:
                j = ChiJournal(Path(d), identity='a'*64, evaluation='e', task='t', attempt='a', run='r',
                               launch={'fee_policy': FEE_POLICY})
                usage = dict(USAGE); usage['opencode'] = dict(USAGE['opencode'], billing_source=source)
                j.reserve(b'one', 'main')
                with self.assertRaises(GoFailure): settle(j, usage)
                self.assertTrue(j.state['halted'] is not None or j.state['pending'] is not None)
                j.finish('failed'); j.close()

    def test_missing_cost_fields_warn_and_allow_next_request(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); j = ChiJournal(root, identity='a'*64, evaluation='e', task='t', attempt='a', run='r',
                                          launch={'fee_policy': FEE_POLICY})
            usage = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}
            j.reserve(b'one', 'main'); settle(j, usage)
            self.assertEqual(j.run['requests'][0]['billing_error'], 'billing_details_unknown')
            self.assertIsNone(j.state['halted']); self.assertFalse(j.usage_totals()['billing_complete'])
            j.reserve(b'two', 'main'); settle(j, USAGE)
            j.finish('failed'); j.close()
            nxt = ChiJournal(root, identity='a'*64, evaluation='e', task='t', attempt='b', run='s')
            self.assertFalse(nxt.usage_totals()['usd']['charged_usd']['complete'])
            nxt.finish('failed'); nxt.close()

    def test_positive_charge_without_source_still_halts(self):
        with tempfile.TemporaryDirectory() as d:
            j = ChiJournal(Path(d), identity='a'*64, evaluation='e', task='t', attempt='a', run='r',
                           launch={'fee_policy': FEE_POLICY})
            usage = {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5, 'cost': 1}
            j.reserve(b'one', 'main')
            with self.assertRaisesRegex(GoFailure, 'billing_source_unexpected'): settle(j, usage)
            self.assertEqual(j.run['requests'][0]['billing_error'], 'billing_details_unknown')
            self.assertEqual(j.state['halted'], 'billing_source_unexpected')
            j.finish('failed'); j.close()
            result = inspect_history(Path(d), 'a'*64, hashlib.sha256((Path(d)/'chi-accounting.json').read_bytes()).hexdigest())
            self.assertEqual(result['halted'], 'billing_source_unexpected')

    def test_invalid_billing_and_tokens_never_become_warning(self):
        values = [dict(USAGE, cost='bad'), dict(USAGE, cost=-1), dict(USAGE, cost=float('nan')),
                  dict(USAGE, total_tokens=99), dict(USAGE, completion_tokens=None)]
        for usage in values:
            with self.subTest(usage=usage), tempfile.TemporaryDirectory() as d:
                j = ChiJournal(Path(d), identity='a'*64, evaluation='e', task='t', attempt='a', run='r',
                               launch={'fee_policy': FEE_POLICY})
                j.reserve(b'one', 'main')
                with self.assertRaises(GoFailure): j.settle(usage)
                self.assertIsNotNone(j.state['pending']); self.assertEqual(j.run['requests'][0]['status'], 'pending')
                j.record_diagnostic('chi_timeout', 1); j.finish('failed'); j.close()

    def test_ack_preserves_failed_evidence_across_migration_and_b_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'chi'; root.mkdir(); args = fixture(root)
            before = (root/'chi-accounting.json').read_bytes()
            seal = (root/'run-seals/r.json').read_bytes()
            result = acknowledge_unsettled(root, **args)
            self.assertFalse(result['settled'])
            self.assertEqual((root/'unsettled-acknowledgements'/('0001-accounting-'+args['accounting_sha256']+'.json')).read_bytes(), before)
            self.assertEqual((root/'run-seals/r.json').read_bytes(), seal)
            state = root/'chi-accounting.json'; digest = hashlib.sha256(state.read_bytes()).hexdigest()
            report = inspect_history(root, 'a'*64, digest)
            self.assertIsNone(report['pending']); self.assertEqual(len(report['acknowledged_unsettled']), 1)
            self.assertFalse(report['usage']['billing_complete'])
            audit_or_rebind(root, 'a'*64, digest, 'b'*64, 'new source')
            with self.assertRaisesRegex(GoFailure, 'chi_b_receipt_missing'):
                ChiJournal(root, identity='b'*64, evaluation='e', task='clinical', attempt='c', run='c', require_b=True)
            j = ChiJournal(root, identity='b'*64, evaluation='e', task='t', attempt='b', run='s')
            self.assertEqual(j.usage_totals()['unsettled_requests'][0]['run'], 'r')
            j.finish('failed'); j.close()
            digest = hashlib.sha256((root/'chi-accounting.json').read_bytes()).hexdigest()
            audit_or_rebind(root, 'b'*64, digest, 'c'*64, 'another source')
            digest = hashlib.sha256((root/'chi-accounting.json').read_bytes()).hexdigest()
            self.assertEqual(len(inspect_history(root, 'c'*64, digest)['acknowledged_unsettled']), 1)
            with self.assertRaises(GoFailure): acknowledge_unsettled(root, **args)

    def test_invalid_target_and_interrupted_ack_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'chi'; root.mkdir(); args = fixture(root)
            with self.assertRaises(GoFailure): acknowledge_unsettled(root, **dict(args, request_sha256='f'*64))
            self.assertFalse((root/'acknowledgement.pending').exists())
            with patch('chi_agent.accounting.journal._atomic', side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError): acknowledge_unsettled(root, **args)
            self.assertTrue((root/'acknowledgement.pending').exists())
            with self.assertRaisesRegex(GoFailure, 'chi_history_invalid'):
                inspect_history(root, args['identity'], args['accounting_sha256'])

    def test_ack_requires_failed_timeout_correct_provider_and_unheld_lock(self):
        import fcntl
        for scenario in ('running', 'wrong_diagnostic', 'wrong_provider', 'wrong_round', 'locked'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as d:
                root = Path(d)/'chi'; root.mkdir()
                if scenario in ('running', 'wrong_diagnostic'):
                    j = ChiJournal(root, identity='a'*64, evaluation='e', task='t', attempt='a', run='r')
                    j.reserve(b'{}', 'main'); j.record_diagnostic('chi_timeout' if scenario == 'running' else 'chi_cancelled', 1)
                    if scenario != 'running': j.finish('failed', 'chi_cancelled')
                    j.close()
                    provider = root.parent/'provider.json'; provider.write_text(json.dumps(event()))
                    args = dict(identity='a'*64, accounting_sha256=hashlib.sha256((root/'chi-accounting.json').read_bytes()).hexdigest(),
                                run='r', round_number=1, request_sha256=hashlib.sha256(b'{}').hexdigest(), provider_path=provider,
                                provider_sha256=hashlib.sha256(provider.read_bytes()).hexdigest(), reason='user decision')
                else: args = fixture(root)
                if scenario == 'wrong_provider':
                    doc = event(); doc['event']['requestHeaders']['content-length'] = '3'
                    args['provider_path'].write_text(json.dumps(doc))
                    args['provider_sha256'] = hashlib.sha256(args['provider_path'].read_bytes()).hexdigest()
                if scenario == 'wrong_round': args['round_number'] = 2
                lock = (root/'.lock').open('r+') if scenario == 'locked' else None
                try:
                    if lock: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises((GoFailure, BlockingIOError)):
                        acknowledge_unsettled(root, **args)
                    self.assertFalse((root/'acknowledgement.pending').exists())
                finally:
                    if lock: lock.close()

    def test_ack_partial_writes_remain_blocked(self):
        from chi_agent.accounting.journal import _write_exclusive as real_write
        for kind in ('accounting', 'provider', 'event'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root = Path(d)/'chi'; root.mkdir(); args = fixture(root)
                def fail_at(path, data):
                    if f'-{kind}-' in path.name: raise OSError('synthetic write failure')
                    return real_write(path, data)
                with patch('chi_agent.accounting.journal._write_exclusive', side_effect=fail_at):
                    with self.assertRaises(OSError): acknowledge_unsettled(root, **args)
                self.assertTrue((root/'acknowledgement.pending').exists())
                with self.assertRaisesRegex(GoFailure, 'chi_history_invalid'):
                    inspect_history(root, args['identity'], args['accounting_sha256'])

    def test_new_pending_remains_blocked_and_cannot_use_legacy_ack(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'chi'; root.mkdir(); args = fixture(root); acknowledge_unsettled(root, **args)
            j = ChiJournal(root, identity='a'*64, evaluation='e', task='t', attempt='b', run='new',
                           launch={'fee_policy': FEE_POLICY})
            dispatch = {'version': 'chi-go-dispatch-v1', 'purpose': 'main', 'session_sha256': 'b'*64,
                        'started_utc_ms': 1700000000000, 'body_bytes': 2}
            j.reserve(b'{}', 'main', dispatch=dispatch); j.record_diagnostic('chi_timeout', 1); j.finish('failed'); j.close()
            digest = hashlib.sha256((root/'chi-accounting.json').read_bytes()).hexdigest()
            report = inspect_history(root, 'a'*64, digest)
            self.assertEqual(report['pending'], {'run': 'new', 'round': 1})
            self.assertEqual([x['run'] for x in report['acknowledged_unsettled']], ['r'])
            with self.assertRaisesRegex(GoFailure, 'chi_usage_unknown'):
                ChiJournal(root, identity='a'*64, evaluation='e', task='t', attempt='c', run='next')
            with self.assertRaisesRegex(GoFailure, 'chi_ack_target_invalid'):
                acknowledge_unsettled(root, **dict(args, accounting_sha256=digest, run='new'))

    def test_missing_or_tampered_ack_file_blocks(self):
        for kind in ('accounting', 'event', 'provider'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root = Path(d)/'chi'; root.mkdir(); args = fixture(root); acknowledge_unsettled(root, **args)
                next((root/'unsettled-acknowledgements').glob(f'0001-{kind}-*.json')).write_text('{}')
                digest = hashlib.sha256((root/'chi-accounting.json').read_bytes()).hexdigest()
                with self.assertRaisesRegex(GoFailure, 'chi_history_invalid'):
                    inspect_history(root, args['identity'], digest)

    def test_rehashed_ack_snapshot_schema_and_pending_prefix_rejected(self):
        for case in ('schema', 'account_prior_history', 'extra_key', 'extra_unknown'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                root = Path(d)/'chi'; root.mkdir(); args = fixture(root); acknowledge_unsettled(root, **args)
                directory = root/'unsettled-acknowledgements'
                account_file = next(directory.glob('0001-accounting-*.json'))
                event_file = next(directory.glob('0001-event-*.json'))
                snapshot = json.loads(account_file.read_bytes()); record = json.loads(event_file.read_bytes())
                state_file = root/'chi-accounting.json'; state = json.loads(state_file.read_bytes())
                if case == 'schema': snapshot['schema'] = 'wrong'
                elif case == 'account_prior_history': snapshot['account_prior_history'] = 'zero'
                elif case == 'extra_key': snapshot['unexpected'] = True
                else:
                    extra = {'run': 'other', 'requests': [{'status': 'unknown'}]}
                    snapshot['attempts'].append(extra); state['attempts'].append(extra)
                account_raw = json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()
                record['accounting_sha256'] = hashlib.sha256(account_raw).hexdigest()
                account_file.unlink()
                (directory/f"0001-accounting-{record['accounting_sha256']}.json").write_bytes(account_raw)
                event_raw = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
                event_hash = hashlib.sha256(event_raw).hexdigest(); event_file.unlink()
                (directory/f'0001-event-{event_hash}.json').write_bytes(event_raw)
                state['acknowledgements'][0]['event_sha256'] = event_hash
                state_file.write_text(json.dumps(state))
                with self.assertRaisesRegex(GoFailure, 'chi_history_invalid'):
                    inspect_history(root, args['identity'], hashlib.sha256(state_file.read_bytes()).hexdigest())

    def test_orphan_ack_directory_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'chi'; root.mkdir(); args = fixture(root)
            (root/'unsettled-acknowledgements').mkdir()
            with self.assertRaisesRegex(GoFailure, 'chi_history_invalid'):
                inspect_history(root, args['identity'], args['accounting_sha256'])
