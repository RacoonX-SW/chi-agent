import os
import subprocess
import sys
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
        parsed = parser.parse_args(base + ["--input-summary", "chi-input-summary-v2"])
        self.assertEqual(parsed.input_summary, "chi-input-summary-v2")
        parsed = parser.parse_args(base + ["--output-recovery", "chi-output-recovery-v1"])
        self.assertEqual(parsed.output_recovery, "chi-output-recovery-v1")
        self.assertIsNone(parsed.input_summary)
        parsed = parser.parse_args(base)
        self.assertIsNone(parsed.input_summary)
        self.assertIsNone(parsed.output_recovery)

    FORMS = (
        ("--input-summary", "chi-input-summary-v1", "chi-input-summary-v1"),
        ("--input-summary", "chi-input-summary-v2", "chi-input-summary-v2"),
        ("--input-summary=chi-input-summary-v1", None, "chi-input-summary-v1"),
        ("--input-s", "chi-input-summary-v1", "chi-input-summary-v1"),
        ("--input-s=chi-input-summary-v1", None, "chi-input-summary-v1"),
        ("--output-recovery", "chi-output-recovery-v1", "chi-output-recovery-v1"),
        ("--output-recovery=chi-output-recovery-v1", None, "chi-output-recovery-v1"),
        ("--output-rec", "chi-output-recovery-v1", "chi-output-recovery-v1"),
        ("--output-rec=chi-output-recovery-v1", None, "chi-output-recovery-v1"),
    )

    def _base_args(self):
        return ["live", "--bundle-sha256", "a" * 64, "--evaluation-id", "e", "--task-id", "t",
                "--attempt-id", "a", "--run-id", "r", "--logs-dir", "/tmp/logs",
                "--role", "payer", "--instruction-file", "/tmp/instruction.md",
                "--mcp-url", "http://127.0.0.1:8100/mcp", "--history-mode", "external",
                "--output-root", "/tmp/state"]

    def test_argparse_forms_are_legal_and_resolved(self):
        parser = go_chi_entry._parser()
        for flag, value, expected in self.FORMS:
            with self.subTest(flag=flag):
                args = self._base_args() + ([flag] if value is None else [flag, value])
                parsed = parser.parse_args(args)
                self.assertEqual(parsed.input_summary or parsed.output_recovery, expected)
                self.assertEqual(role_runner.selected_validation_flags([flag] + ([value] if value else [])),
                                 {"--input-summary"} if "input" in expected else {"--output-recovery"})

    def test_shadow_rejects_every_legal_form(self):
        for flag, value, _expected in self.FORMS:
            with self.subTest(flag=flag), patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "shadow"}):
                argv = [flag] if value is None else [flag, value]
                with self.assertRaisesRegex(RuntimeError, "evidence_shadow_exclusive"):
                    role_runner.reject_shadow_with_validation_flags(["live"] + argv)

    def test_without_shadow_or_without_flags_is_allowed(self):
        with patch.dict(os.environ, {}, clear=True):
            role_runner.reject_shadow_with_validation_flags(["live", "--input-summary", "x"])
        with patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "off"}):
            role_runner.reject_shadow_with_validation_flags(["live", "--output-recovery", "x"])
        with patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "shadow"}):
            role_runner.reject_shadow_with_validation_flags(["live", "--role", "payer"])

    def test_actual_runner_script_stops_before_entry(self):
        env = dict(os.environ, CHI_DEV_EVIDENCE_SHADOW="shadow")
        completed = subprocess.run([sys.executable, "scripts/role_runner.py", "live",
                                    "--input-s=chi-input-summary-v1"],
                                   cwd=str(role_runner.Path(__file__).resolve().parents[1]),
                                   env=env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("evidence_shadow_exclusive", completed.stderr)

    def test_shadow_without_flags_is_allowed_by_this_guard(self):
        with patch.dict(os.environ, {"CHI_DEV_EVIDENCE_SHADOW": "shadow"}):
            role_runner.reject_shadow_with_validation_flags(["live", "--role", "payer"])


if __name__ == "__main__":
    unittest.main()
