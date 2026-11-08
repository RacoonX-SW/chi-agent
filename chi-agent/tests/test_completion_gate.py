import tempfile
import unittest
from pathlib import Path

from go_chi_state import CONTEXT_POLICY_V3, TaskState


class CompletionGateTests(unittest.TestCase):
    def _state(self, directory):
        return TaskState(Path(directory) / "state", run="r", role="payer",
                         context_policy=CONTEXT_POLICY_V3)

    def _observe(self, state, call_id, tool, result="{}", event="returned"):
        state.observe(call_id=call_id, tool=tool, kind="mcp",
                      arguments={"case_id": "CASE-A"}, result=result,
                      event=event, scope="case:CASE-A")

    def test_missing_steps_block_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            allowed, reason = state.can_claim()
            self.assertFalse(allowed)
            self.assertTrue(reason.startswith("completion_missing_step:"))

    def test_terminal_and_readback_allow_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            self._observe(state, "c1", "payer_intake_hub.get_intake_case")
            self._observe(state, "c2", "triage.get")
            self._observe(state, "c3", "review.get_nurse_review_data")
            self._observe(state, "c4", "review.submit_nurse_case_recommendation")
            self._observe(state, "c5", "determination.get_summary")
            state.propose({"latest_business_status": {
                "text": "nurse recommendation submitted", "source_call_id": "c5"}})
            allowed, reason = state.can_claim()
            self.assertTrue(allowed, reason)
            self.assertEqual(state.record_claim()["status"], "recorded")

    def test_fake_claim_without_terminal_object_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            self._observe(state, "c1", "payer_intake_hub.get_intake_case")
            self._observe(state, "c2", "triage.get")
            self._observe(state, "c3", "review.get_nurse_review_data")
            state.propose({"latest_business_status": {
                "text": "reviewed", "source_call_id": "c1"}})
            allowed, reason = state.can_claim()
            self.assertFalse(allowed)
            self.assertEqual(reason, "completion_terminal_object_missing")

    def test_mutation_without_readback_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            self._observe(state, "c1", "payer_intake_hub.get_intake_case")
            self._observe(state, "c2", "triage.get")
            self._observe(state, "c3", "review.get_nurse_review_data")
            self._observe(state, "c4", "review.submit_nurse_case_recommendation")
            allowed, reason = state.can_claim()
            self.assertFalse(allowed)
            self.assertTrue(reason.startswith("completion_readback_required:"))

    def test_completion_report_marks_mandatory_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(directory)
            report = state.completion_report()
            self.assertEqual(report["schema"], "chi-completion-v5")
            self.assertEqual(report["claim_policy"], "mandatory_claim")
            self.assertIn("completion_evidence", report)


if __name__ == "__main__":
    unittest.main()
