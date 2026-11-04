"""D: bounded, safe diagnostic preservation and fallback at the entry boundary."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import go_chi_entry
from opencode_go_provider import GoFailure


def rich_log():
    return {
        "schema": "chi-go-run-log-v2",
        "status": "incomplete",
        "safe_error_code": "chi_timeout",
        "safe_cause": {"schema": "chi-safe-cause-v1", "stage": "transport", "reason": "timeout"},
        "provider_requests": 3,
        "tool_events": 4,
        "completion": {"schema": "chi-completion-v2", "verification": "blocked"},
        "context_requests": 2,
        "journal_usage": {"input_tokens": 10},
        "task_state_target": {"case_id": "CASE-A", "patient_id": None},
        "final_output_claimed": False,
        "official_reward": None,
    }


class DiagnosticPreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.logs = Path(self.temp.name) / "logs"
        self.logs.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_failure_preserves_valid_runtime_fields_and_separates_layers(self):
        (self.logs / "run_log.txt").write_text(json.dumps(rich_log()), encoding="utf-8")
        self.assertTrue(go_chi_entry._failure_run_log(
            self.logs, error="chi_runner_failed", journal_error="chi_persistence_failed"))
        value = json.loads((self.logs / "run_log.txt").read_text())
        self.assertEqual(value["status"], "incomplete")
        self.assertEqual(value["safe_error_code"], "chi_timeout")
        self.assertEqual(value["first_error_code"], "chi_timeout")
        self.assertEqual(value["outer_error_code"], "chi_runner_failed")
        self.assertEqual(value["journal_error_code"], "chi_persistence_failed")
        self.assertEqual(value["safe_cause"]["reason"], "timeout")
        self.assertEqual(value["completion"]["verification"], "blocked")
        self.assertEqual(value["context_requests"], 2)
        self.assertFalse(value["log_fallback"])

    def test_cleanup_layer_is_added_without_overwriting_first_error(self):
        (self.logs / "run_log.txt").write_text(json.dumps(rich_log()), encoding="utf-8")
        go_chi_entry._cleanup_run_log(self.logs, "chi_cleanup_failed")
        value = json.loads((self.logs / "run_log.txt").read_text())
        self.assertEqual(value["safe_error_code"], "chi_timeout")
        self.assertEqual(value["cleanup_error_code"], "chi_cleanup_failed")
        self.assertEqual(value["status"], "incomplete")

    def test_invalid_unknown_or_oversize_log_falls_back_without_merging_text(self):
        cases = {
            "broken": b"{not-json",
            "unknown-schema": json.dumps({**rich_log(), "schema": "chi-go-run-log-v1"}).encode(),
            "extra-key": json.dumps({**rich_log(), "secret": "do-not-copy"}).encode(),
            "oversize": b"{" + b" " * (go_chi_entry.MAX_RUN_LOG_BYTES + 1) + b"}",
            "bad-cause": json.dumps({**rich_log(), "safe_cause": {"schema": "x"}}).encode(),
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                path = self.logs / "run_log.txt"
                if path.exists() or path.is_symlink():
                    path.unlink()
                path.write_bytes(raw)
                self.assertIsNone(go_chi_entry._read_run_log(self.logs))
                self.assertTrue(go_chi_entry._failure_run_log(self.logs, error="chi_entry_failed"))
                value = json.loads(path.read_text())
                self.assertTrue(value["log_fallback"])
                self.assertEqual(value["log_fallback_reason"], "invalid_or_missing_runtime_log")
                self.assertNotIn("do-not-copy", json.dumps(value))
                self.assertEqual(set(value) - go_chi_entry._RUN_LOG_KEYS, set())

    def test_symlinked_log_is_not_followed(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text(json.dumps(rich_log()), encoding="utf-8")
        (self.logs / "run_log.txt").symlink_to(outside)
        before = outside.read_text()
        self.assertIsNone(go_chi_entry._read_run_log(self.logs))
        self.assertFalse(go_chi_entry._failure_run_log(self.logs, error="chi_entry_failed"))
        self.assertEqual(outside.read_text(), before)


class EntryFailurePathTests(unittest.TestCase):
    def test_entry_preserves_runtime_log_when_outer_path_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, logs = root / "out", root / "logs"

            def fake_run(coro):
                coro.close()
                (logs / "run_log.txt").write_text(json.dumps(rich_log()), encoding="utf-8")
                raise GoFailure("chi_timeout")

            argv = ["coding-b", "--bundle-sha256", "a" * 64, "--evaluation-id", "e",
                    "--task-id", "synthetic-coding-b", "--attempt-id", "a", "--run-id", "r",
                    "--output-root", str(output), "--logs-dir", str(logs), "--history-mode", "external"]
            with mock.patch.dict(os.environ, {"OPENCODE_API_KEY": "synthetic"}), \
                    mock.patch.object(go_chi_entry, "_identity", return_value=("a" * 64, {})), \
                    mock.patch.object(go_chi_entry.asyncio, "run", side_effect=fake_run):
                code = go_chi_entry.main(argv)
            self.assertEqual(code, 1)
            value = json.loads((logs / "run_log.txt").read_text())
            self.assertEqual(value["completion"]["verification"], "blocked")
            self.assertEqual(value["context_requests"], 2)
            self.assertEqual(value["safe_error_code"], "chi_timeout")
            self.assertFalse(value["log_fallback"])
            self.assertTrue((logs / "run_error.json").is_file())

    def test_cleanup_failure_is_visible_without_losing_success_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, logs = root / "out", root / "logs"

            def fake_run(coro):
                coro.close()
                return "done"

            argv = ["coding-b", "--bundle-sha256", "a" * 64, "--evaluation-id", "e",
                    "--task-id", "synthetic-coding-b", "--attempt-id", "a", "--run-id", "r",
                    "--output-root", str(output), "--logs-dir", str(logs), "--history-mode", "external"]
            with mock.patch.dict(os.environ, {"OPENCODE_API_KEY": "synthetic"}), \
                    mock.patch.object(go_chi_entry, "_identity", return_value=("a" * 64, {})), \
                    mock.patch.object(go_chi_entry.asyncio, "run", side_effect=fake_run), \
                    mock.patch.object(go_chi_entry.ChiJournal, "close", side_effect=RuntimeError("cleanup")):
                code = go_chi_entry.main(argv)
            self.assertEqual(code, 1)
            value = json.loads((logs / "run_log.txt").read_text())
            self.assertEqual(value["status"], "incomplete")
            self.assertEqual(value["safe_error_code"], "chi_cleanup_failed")
            self.assertEqual(value["cleanup_error_code"], "chi_cleanup_failed")
            self.assertEqual(value["provider_requests"], 0)


if __name__ == "__main__":
    unittest.main()
