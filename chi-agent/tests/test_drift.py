import hashlib
import tempfile
import unittest
from pathlib import Path

from go_chi_journal import ChiJournal, inspect_history
from go_chi_state import CONTEXT_POLICY_V3, TaskState


class DriftTests(unittest.TestCase):
    def _state(self, directory):
        return TaskState(Path(directory) / "state", run="r", role="payer",
                         context_policy=CONTEXT_POLICY_V3)

    def test_unread_write_is_hard(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            result = state.drift_check("local-fs-write", "local",
                                       {"path": "/workspace/CASE-A/payer/out.txt"})
            self.assertEqual(result, "HARD:unread_write")

    def test_repeat_read_is_soft_then_hard(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            args = {"case_id": "CASE-A"}
            state.observe(call_id="c1", tool="payer_intake_hub.get_intake_case",
                          kind="mcp", arguments=args, result="{}",
                          event="returned", scope="case:CASE-A")
            first = state.drift_check("payer_intake_hub.get_intake_case", "mcp", args)
            second = state.drift_check("payer_intake_hub.get_intake_case", "mcp", args)
            third = state.drift_check("payer_intake_hub.get_intake_case", "mcp", args)
            self.assertEqual(first, "SOFT:repeat_call:1")
            self.assertEqual(second, "SOFT:repeat_call:2")
            self.assertEqual(third, "HARD:repeat_call")

    def test_legacy_state_has_no_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TaskState(Path(directory) / "state", run="r", role="payer")
            self.assertIsNone(state.drift_check("local-fs-write", "local",
                                                {"path": "/workspace/CASE-A/payer/out.txt"}))

    def test_drift_record_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            state.drift_check("local-fs-write", "local",
                              {"path": "/workspace/CASE-A/payer/out.txt"})
            state.drift_record("unread_write", "c1", "hard", "stopped")
            self.assertEqual(state.data["drift"]["events"][-1]["rule"], "unread_write")

    def test_journal_drift_event_is_inspectable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity="a" * 64, evaluation="e", task="t",
                                 attempt="a", run="r",
                                 launch={"context_policy": CONTEXT_POLICY_V3})
            journal.record_drift("repeat_call", "c1", 1, severity="soft", outcome="refused")
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            report = inspect_history(root, "a" * 64, hashlib.sha256(raw).hexdigest())
            self.assertEqual(report["status"], "inspected")


if __name__ == "__main__":
    unittest.main()
