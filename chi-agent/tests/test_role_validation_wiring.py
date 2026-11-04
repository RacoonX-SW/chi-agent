import os
import unittest
from unittest.mock import patch

import go_chi_entry
import role_runner


class ValidationWiringTests(unittest.TestCase):
    def test_runner_reexports_the_package_entry(self):
        self.assertIs(role_runner.main, go_chi_entry.main)

    def test_entry_parser_accepts_the_two_flags(self):
        parser = go_chi_entry._parser()
        base = ["live", "--bundle-sha256", "a" * 64, "--evaluation-id", "e", "--task-id", "t",
                "--attempt-id", "a", "--run-id", "r", "--logs-dir", "/tmp/logs",
                "--role", "payer", "--instruction-file", "/tmp/instruction.md",
                "--mcp-url", "http://127.0.0.1:8100/mcp", "--history-mode", "external",
                "--output-root", "/tmp/state"]
        parsed = parser.parse_args(base + ["--input-summary", "chi-input-summary-v1"])
        self.assertEqual(parsed.input_summary, "chi-input-summary-v1")
        self.assertIsNone(parsed.output_recovery)
        parsed = parser.parse_args(base + ["--output-recovery", "chi-output-recovery-v1"])
        self.assertEqual(parsed.output_recovery, "chi-output-recovery-v1")
        self.assertIsNone(parsed.input_summary)
        parsed = parser.parse_args(base)
        self.assertIsNone(parsed.input_summary)
        self.assertIsNone(parsed.output_recovery)

    def test_shadow_rejects_validation_flags_at_the_runner_seam(self):
        for flag in ("--input-summary", "--output-recovery"):
            with self.subTest(flag=flag):
                with patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "shadow"}):
                    with self.assertRaisesRegex(RuntimeError, "evidence_shadow_exclusive"):
                        role_runner.reject_shadow_with_validation_flags(["live", flag, "x"])
        with patch.dict(os.environ, {}, clear=True):
            role_runner.reject_shadow_with_validation_flags(["live", "--input-summary", "x"])
        with patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "off"}):
            role_runner.reject_shadow_with_validation_flags(["live", "--output-recovery", "x"])

    def test_shadow_without_flags_is_allowed_by_this_guard(self):
        with patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "shadow"}):
            role_runner.reject_shadow_with_validation_flags(["live", "--role", "payer"])


if __name__ == "__main__":
    unittest.main()
