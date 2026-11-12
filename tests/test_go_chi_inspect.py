import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from chi_agent.provider_inspection import inspect_provider
from chi_agent.journal import ChiJournal, inspect_history, audit_or_rebind
from chi_agent.opencode_go_provider import GoFailure


def event():
    session = 'chi-' + 'a' * 32
    return {'event': {'id': 'synthetic', 'requestID': 'synthetic', 'category': 'inference',
        'model': 'deepseek-v4.1-flash', 'requestedModel': 'deepseek-v4.1-flash', 'provider': 'opencode',
        'product': 'go', 'protocol': 'openai-chat', 'method': 'POST', 'path': '/inference/go/openai/v1/chat/completions',
        'stream': False, 'statusCode': 200, 'outcome': 'succeeded', 'startedAt': 1700000000000,
        'finishedAt': 1700000088000, 'durationMs': 88000, 'firstTokenAt': 1700000087000,
        'lastTokenAt': 1700000087000, 'timeToFirstTokenMs': 87000, 'inputTokens': 100, 'outputTokens': 20,
        'reasoningTokens': 10, 'cacheReadTokens': 0, 'cacheWriteTokens': 0, 'cost': 0.0001,
        'reasoningEffort': 'high', 'reasoningMode': 'effort', 'attemptCount': 1,
        'attempts': [{'provider': 'opencode', 'model': 'deepseek-v4.1-flash', 'statusCode': 200, 'durationMs': 87000}],
        'sessionID': session, 'requestHeaders': {'content-length': '2', 'user-agent': 'chi-agent', 'x-opencode-session': session},
        'userAgent': 'chi-agent', 'userID': 'private'}}


class InspectionTests(unittest.TestCase):
    def test_invalid_dispatch_body_size_does_not_reserve(self):
        for raw in (b'', b'x' * (8 * 1024 * 1024 + 1)):
            with self.subTest(size=len(raw)), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
                dispatch = {'version': 'chi-go-dispatch-v1', 'purpose': 'main', 'session_sha256': 'b' * 64,
                            'started_utc_ms': 1700000000000, 'body_bytes': len(raw)}
                with self.assertRaisesRegex(GoFailure, 'chi_reservation_invalid'):
                    j.reserve(raw, 'main', dispatch=dispatch)
                self.assertEqual(j.run['requests'], [])
                self.assertIsNone(j.state['pending'])
                self.assertFalse((root / 'tool-inflight').exists())
                j.finish('failed'); j.close()

    def test_halted_history_can_be_inspected_but_not_rebound(self):
        from tests.test_go_chi_journal import USAGE, settle
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); identity = 'a' * 64
            j = ChiJournal(root, identity=identity, evaluation='e', task='t', attempt='a', run='r')
            usage = dict(USAGE, cost=1)
            j.reserve(b'{}', 'main')
            with self.assertRaises(GoFailure): settle(j, usage)
            j.finish('failed', 'billing_source_unexpected'); j.close()
            state = root / 'chi-accounting.json'; digest = hashlib.sha256(state.read_bytes()).hexdigest()
            result = inspect_history(root, identity, digest)
            self.assertEqual(result['halted'], 'billing_source_unexpected')
            self.assertEqual(result['missing'], [])
            self.assertFalse(result['execution_allowed'])
            with self.assertRaisesRegex(GoFailure, 'chi_migration_history_unsettled'):
                audit_or_rebind(root, identity, digest)

    def test_halt_reports_exact_missing_allowance_or_source(self):
        from tests.test_go_chi_journal import USAGE, settle
        for missing in ('allowance', 'billing_source'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as d:
                root = Path(d); identity = 'a' * 64
                j = ChiJournal(root, identity=identity, evaluation='e', task='t', attempt='a', run='r')
                usage = dict(USAGE); usage['opencode'] = dict(USAGE['opencode']); del usage['opencode'][missing]
                j.reserve(b'{}', 'main')
                with self.assertRaises(GoFailure): settle(j, usage)
                j.finish('failed', 'billing_details_unknown'); j.close()
                state = root / 'chi-accounting.json'; before = state.read_bytes()
                result = inspect_history(root, identity, hashlib.sha256(before).hexdigest())
                self.assertIsNone(result['pending'])
                self.assertEqual(result['halted'], 'billing_details_unknown')
                self.assertEqual(result['missing'], ['allowance_usd' if missing == 'allowance' else 'billing_source'])
                self.assertEqual(state.read_bytes(), before)

    def test_dispatch_tampering_is_rejected(self):
        from chi_agent.journal import _seal
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); identity = 'a' * 64
            j = ChiJournal(root, identity=identity, evaluation='e', task='t', attempt='a', run='r')
            dispatch = {'version': 'chi-go-dispatch-v1', 'purpose': 'main', 'session_sha256': 'b' * 64,
                        'started_utc_ms': 1700000000000, 'body_bytes': 2}
            j.reserve(b'{}', 'main', dispatch=dispatch); j.record_diagnostic('chi_timeout', 1)
            j.finish('failed', 'chi_timeout'); j.close()
            evidence = root / 'wire-evidence/r/001-request.json'
            doc = json.loads(evidence.read_text()); doc['dispatch']['body_bytes'] = 3
            raw = (json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
            evidence.write_bytes(raw)
            state = root / 'chi-accounting.json'; data = json.loads(state.read_text())
            data['attempts'][0]['requests'][0]['request_evidence_sha256'] = hashlib.sha256(raw).hexdigest()
            state.write_text(json.dumps(data))
            (root / 'run-seals/r.json').write_text(json.dumps(_seal(data['attempts'][0], identity)))
            with self.assertRaisesRegex(GoFailure, 'chi_history_invalid'):
                inspect_history(root, identity, hashlib.sha256(state.read_bytes()).hexdigest())

    def test_pending_history_and_provider_are_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); identity = 'a' * 64
            j = ChiJournal(root, identity=identity, evaluation='e', task='t', attempt='a', run='r')
            j.reserve(b'{}', 'main'); j.record_diagnostic('chi_timeout', 1); j.finish('failed', 'chi_timeout'); j.close()
            state = root / 'chi-accounting.json'; before = state.read_bytes(); digest = hashlib.sha256(before).hexdigest()
            result = inspect_history(root, identity, digest)
            self.assertEqual(result['pending'], {'run': 'r', 'round': 1})
            self.assertEqual(result['pending_request']['body_bytes'], 2)
            self.assertFalse(result['execution_allowed']); self.assertIn('dispatch_metadata', result['missing'])
            with self.assertRaisesRegex(GoFailure, 'chi_migration_history_unsettled'):
                audit_or_rebind(root, identity, digest)
            record = root / 'console.json'; record.write_text(json.dumps(event()))
            inspection = inspect_provider(record, hashlib.sha256(record.read_bytes()).hexdigest(), result['pending_request'])
            self.assertEqual(inspection['correlation']['status'], 'unavailable')
            self.assertEqual(inspection['console_cost'], '0.0001')
            self.assertFalse(inspection['execution_allowed'])
            self.assertNotIn('private', json.dumps(inspection))
            self.assertEqual(state.read_bytes(), before)
            mismatch = event(); mismatch['event']['requestHeaders']['content-length'] = '3'
            record.write_text(json.dumps(mismatch))
            with self.assertRaisesRegex(GoFailure, 'chi_provider_record_invalid'):
                inspect_provider(record, hashlib.sha256(record.read_bytes()).hexdigest(), result['pending_request'])

    def test_non_streaming_console_without_first_token_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "record.json"
            doc = event()
            doc["event"]["stream"] = False
            doc["event"]["firstTokenAt"] = None
            doc["event"]["timeToFirstTokenMs"] = None
            path.write_text(json.dumps(doc), encoding="utf-8")
            inspection = inspect_provider(path, hashlib.sha256(path.read_bytes()).hexdigest(), None)
            self.assertEqual(inspection["status"], "inspected")
            self.assertEqual(inspection["request_id"], "synthetic")

    def test_bad_console_values_or_hash_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'record.json'
            for key, value in [('model', 'other'), ('stream', 'yes'), ('outputTokens', -1), ('attemptCount', 2), ('requestID', 'other')]:
                doc = event(); doc['event'][key] = value; path.write_text(json.dumps(doc))
                with self.subTest(key=key), self.assertRaisesRegex(GoFailure, 'chi_provider_record_invalid'):
                    inspect_provider(path, hashlib.sha256(path.read_bytes()).hexdigest(), None)
            path.write_text(json.dumps(event()))
            with self.assertRaisesRegex(GoFailure, 'chi_provider_record_invalid'):
                inspect_provider(path, 'f' * 64, None)

    def test_dispatch_correlation_is_not_unique_proof(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'record.json'; path.write_text(json.dumps(event()))
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            pending = {'purpose': 'main', 'kind': 'chi', 'dispatch': {'session_sha256': hashlib.sha256(('chi-' + 'a' * 32).encode()).hexdigest(),
                       'body_bytes': 2, 'started_utc_ms': 1700000000000}}
            result = inspect_provider(path, sha, pending)
            self.assertEqual(result['correlation']['status'], 'consistent')
            self.assertFalse(result['correlation']['unique_match'])
            pending['dispatch']['body_bytes'] = 3
            self.assertEqual(inspect_provider(path, sha, pending)['correlation']['status'], 'mismatch')
