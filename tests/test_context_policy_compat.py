import tempfile
import unittest
from pathlib import Path

import go_chi_entry
from go_chi_journal import ChiJournal
from opencode_go_provider import GoFailure


class ContextPolicyCompatibilityTests(unittest.TestCase):
    def test_v3_rejects_output_recovery_and_input_summary(self):
        for field, value in (("output_recovery", "chi-output-recovery-v1"),
                             ("input_summary", "chi-input-summary-v1")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(GoFailure) as caught:
                    ChiJournal(Path(directory), identity="a" * 64, evaluation="e",
                               task="t", attempt="a", run="r",
                               launch={"context_policy": "chi-context-v3", field: value})
                self.assertEqual(caught.exception.code, "chi_context_policy_incompatible")

    def test_v2_recovery_still_constructs(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e",
                                 task="t", attempt="a", run="r",
                                 launch={"output_recovery": "chi-output-recovery-v1"})
            journal.finish("failed")
            journal.close()

    def test_entry_rejects_v3_recovery_before_identity(self):
        self.assertEqual(go_chi_entry.main([
            "live", "--bundle-sha256", "a" * 64,
            "--output-recovery", "chi-output-recovery-v1"]), 1)
        self.assertEqual(go_chi_entry.main([
            "live", "--bundle-sha256", "a" * 64,
            "--input-summary", "chi-input-summary-v1"]), 1)


if __name__ == "__main__":
    unittest.main()
