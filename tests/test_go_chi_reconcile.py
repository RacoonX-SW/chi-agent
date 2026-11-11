import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from chi_agent.journal import ChiJournal, inspect_history, reconcile_provider_timeout
from chi_agent.opencode_go_provider import GoFailure


def provider_event(session, body_bytes, started_at):
    return {"event": {
        "id": "req-1", "requestID": "req-1", "category": "inference",
        "model": "deepseek-v4.1-flash", "requestedModel": "deepseek-v4.1-flash",
        "provider": "opencode", "product": "go", "protocol": "openai-chat",
        "method": "POST", "path": "/inference/go/openai/v1/chat/completions",
        "stream": True, "statusCode": 200, "outcome": "succeeded",
        "startedAt": started_at, "finishedAt": started_at + 88000, "durationMs": 88000,
        "firstTokenAt": started_at + 1000, "lastTokenAt": started_at + 87000,
        "timeToFirstTokenMs": 1000, "inputTokens": 369422, "outputTokens": 8192,
        "reasoningTokens": 8192, "cacheReadTokens": 0, "cacheWriteTokens": 0,
        "cost": 0.0603285, "reasoningEffort": "high", "reasoningMode": "effort",
        "attemptCount": 1,
        "attempts": [{"provider": "opencode", "model": "deepseek-v4.1-flash",
                      "statusCode": 200, "durationMs": 87000}],
        "sessionID": session, "requestHeaders": {
            "content-length": str(body_bytes), "user-agent": "chi-agent",
            "x-opencode-session": session},
        "userAgent": "chi-agent", "userID": "private",
    }}


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"
        self.root.mkdir()
        self.session = "chi-" + "a" * 32
        self.body = b'{"synthetic":true}'
        self.dispatch = {"version": "chi-go-dispatch-v1", "purpose": "main",
                         "session_sha256": hashlib.sha256(self.session.encode()).hexdigest(),
                         "started_utc_ms": 1700000000000, "body_bytes": len(self.body)}
        self.identity = "b" * 64
        journal = ChiJournal(self.root, identity=self.identity, evaluation="eval", task="task",
                             attempt="attempt", run="run", kind="chi", launch={})
        journal.reserve(self.body, "main", dispatch=self.dispatch)
        journal.record_diagnostic("chi_timeout", 60000)
        journal.finish("failed", "chi_timeout")
        self.request = journal.run["requests"][0]
        journal.close()
        self.accounting = (self.root / "chi-accounting.json").read_bytes()
        self.seal = (self.root / "run-seals" / "run.json").read_bytes()
        self.provider = Path(self.temp.name) / "provider.json"
        self.provider.write_text(json.dumps(provider_event(self.session, len(self.body),
                                                            self.dispatch["started_utc_ms"] + 1000)),
                                 encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def reconcile(self):
        return reconcile_provider_timeout(
            self.root, identity=self.identity,
            accounting_sha256=hashlib.sha256(self.accounting).hexdigest(),
            run="run", round_number=1, request_sha256=self.request["request_sha256"],
            provider_path=self.provider,
            provider_sha256=hashlib.sha256(self.provider.read_bytes()).hexdigest(),
            reason="provider console 200 after client read timeout")

    def test_reconcile_clears_admission_without_rewriting_request_or_seal(self):
        result = self.reconcile()
        self.assertEqual(result["status"], "reconciled_provider_timeout")
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["request_retry_allowed"])
        self.assertTrue(result["admission_cleared"])
        self.assertFalse(result["settled"])
        state = json.loads((self.root / "chi-accounting.json").read_text())
        self.assertIsNone(state["pending"])
        self.assertEqual(len(state["reconciliations"]), 1)
        self.assertEqual(state["attempts"][0]["requests"][0]["status"], "pending")
        self.assertEqual((self.root / "run-seals" / "run.json").read_bytes(), self.seal)
        files = sorted(path.name for path in (self.root / "reconciliations").iterdir())
        self.assertEqual(len(files), 3)
        self.assertTrue(any("-event-" in name for name in files))
        self.assertTrue(any("-accounting-" in name for name in files))
        self.assertTrue(any("-provider-" in name for name in files))
        current = (self.root / "chi-accounting.json").read_bytes()
        inspection = inspect_history(self.root, self.identity, hashlib.sha256(current).hexdigest())
        self.assertFalse(inspection["execution_allowed"])
        self.assertEqual(inspection["reconciled_provider_timeouts"][0]["provider_request_id"], "req-1")
        self.assertEqual(inspection["reconciled_provider_timeouts"][0]["tokens"],
                         {"input_tokens": 369422, "output_tokens": 8192})
        # Reopening validates the reconciled history and allows a new attempt.
        reopened = ChiJournal(self.root, identity=self.identity, evaluation="eval", task="task2",
                              attempt="attempt2", run="run2", kind="chi", launch={})
        reopened.finish("complete"); reopened.close()

    def test_duplicate_reconcile_is_rejected(self):
        self.reconcile()
        current = (self.root / "chi-accounting.json").read_bytes()
        with self.assertRaises(GoFailure) as caught:
            reconcile_provider_timeout(
                self.root, identity=self.identity,
                accounting_sha256=hashlib.sha256(current).hexdigest(),
                run="run", round_number=1, request_sha256=self.request["request_sha256"],
                provider_path=self.provider,
                provider_sha256=hashlib.sha256(self.provider.read_bytes()).hexdigest(),
                reason="duplicate")
        self.assertEqual(caught.exception.code, "chi_reconcile_target_invalid")

    def test_leftover_marker_blocks_validation(self):
        self.reconcile()
        (self.root / "reconciliation.pending").write_text("in progress\n", encoding="utf-8")
        with self.assertRaises(GoFailure) as caught:
            ChiJournal(self.root, identity=self.identity, evaluation="eval", task="task2",
                       attempt="attempt2", run="run2", kind="chi", launch={})
        self.assertEqual(caught.exception.code, "chi_history_invalid")

    def test_provider_mismatch_is_rejected_without_state_change(self):
        bad = json.loads(self.provider.read_text())
        bad["event"]["sessionID"] = "chi-" + "c" * 32
        bad["event"]["requestHeaders"]["x-opencode-session"] = bad["event"]["sessionID"]
        self.provider.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaises(GoFailure) as caught:
            self.reconcile()
        self.assertEqual(caught.exception.code, "chi_reconcile_provider_mismatch")
        self.assertEqual((self.root / "chi-accounting.json").read_bytes(), self.accounting)
        self.assertIsNone(json.loads((self.root / "chi-accounting.json").read_text())["reconciliations"]
                          if "reconciliations" in json.loads((self.root / "chi-accounting.json").read_text()) else None)


if __name__ == "__main__":
    unittest.main()
