"""D: bounded, safe diagnostic preservation and fallback at the entry boundary."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import chi_agent.cli as go_chi_entry
from chi_agent.models.opencode_go_provider import GoFailure


def rich_log():
    completion = {
        "schema": "chi-completion-v3",
        "verification": "blocked",
        "business_effect": "not_verified",
        "reason": "completion_readback_required:call_w1",
        "target": {"case_id": "CASE-A", "patient_id": None},
        "claim": None,
        "claim_policy": "optional_final_text",
        "latest_business_status": None,
        "last_business_mutation": {"call_id": "call_w1", "tool": "triage.set_disposition",
                                   "seq": 1, "event": "returned"},
        "last_file_mutation": None,
        "last_mutation_call_id": "call_w1",
        "required_readback": "business_status",
        "unresolved_file_deliveries": [],
        "open_unknowns": [],
        "claim_violation": False,
        "stagnation": None,
        "remaining_limitations": ["final_text_without_claim_not_blocked"],
        "note": "mechanical/source check only; not a clinical or official verdict",
    }
    return {
        "schema": "chi-go-run-log-v2",
        "status": "incomplete",
        "safe_error_code": "chi_timeout",
        "safe_cause": {"schema": "chi-safe-cause-v1", "stage": "transport", "reason": "timeout"},
        "provider_requests": 3,
        "physical_requests": {"main": 2, "confirmation": 1},
        "tool_events": 4,
        "completion": completion,
        "context_requests": 2,
        "context_max_chars": 100,
        "context_max_estimated_tokens": 25,
        "journal_usage": {
            "input_tokens_known": 10, "output_tokens_known": 5,
            "usd": {"charged_usd": {"known": "0", "complete": True},
                    "list_cost_usd": {"known": "0.1", "complete": True},
                    "allowance_usd": {"known": "0.1", "complete": True}},
            "account_prior_history": "unknown", "billing_details_warnings": 0,
            "billing_complete": True, "unsettled_requests": [],
        },
        "current_run_agent_usage": {"input_tokens_known": 10, "output_tokens_known": 5,
                                    "complete": True},
        "recovery_limits": {"per_chain": 1, "per_run": 2, "shared_requests": 50},
        "task_state_target": {"case_id": "CASE-A", "patient_id": None},
        "task_state_claim": None,
        "task_state_claim_violation": False,
        "task_state_open_unknowns": [],
        "task_state_version": 1,
        "guidance_version": "chi-role-guidance-v3",
        "guidance_sha256": "a" * 64,
        "task_state_sha256": "b" * 64,
        "context_budget": "chi-context-budget-v2",
        "capabilities": "f0-f3-v1",
        "journal_usage_scope": "account_namespace",
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

    def test_structured_fields_reject_unknown_keys_bad_types_and_unknown_codes(self):
        import copy
        base = rich_log()
        cases = {
            "physical-injected": {**base, "physical_requests": {"main": 1,
                                                                 "injected": "synthetic-secret-marker"}},
            "completion-injected": {**base, "completion": {**copy.deepcopy(base["completion"]),
                                                            "injected": "synthetic-secret-marker"}},
            "safe-code": {**base, "safe_error_code": "synthetic_secret_marker"},
            "unknown-code": {**base, "safe_error_code": "chi_made_up"},
            "known-non-error-literal": {**base, "safe_error_code": "chi_bench"},
            "target-injected": {**base, "task_state_target": {
                "case_id": "CASE-A", "patient_id": None, "injected": "x"}},
            "claim-injected": {**base, "task_state_claim": {
                "version": 1, "target": {"case_id": "CASE-A", "patient_id": None},
                "verified_status_call_id": None, "at_utc_ms": 1,
                "kind": "model_claim", "injected": "x"}},
            "journal-old-shape": {**base, "journal_usage": {"input_tokens": 10}},
            "bool-count": {**base, "provider_requests": True},
            "negative-count": {**base, "tool_events": -1},
            "missing-core": {"schema": "chi-go-run-log-v2", "status": "incomplete"},
        }
        for name, value in cases.items():
            with self.subTest(case=name):
                path = self.logs / "run_log.txt"
                if path.exists() or path.is_symlink():
                    path.unlink()
                path.write_text(json.dumps(value), encoding="utf-8")
                self.assertIsNone(go_chi_entry._read_run_log(self.logs))
                self.assertTrue(go_chi_entry._failure_run_log(self.logs, error="chi_entry_failed"))
                updated = json.loads(path.read_text())
                self.assertTrue(updated["log_fallback"])
                self.assertNotIn("synthetic", json.dumps(updated))
                self.assertNotIn("injected", json.dumps(updated))

    def test_nested_wrong_types_fall_back_without_raising(self):
        import copy
        base = rich_log()
        cases = {
            "verification-list": ("verification", []),
            "verification-dict": ("verification", {}),
            "verification-none": ("verification", None),
            "business-effect-list": ("business_effect", []),
            "business-effect-dict": ("business_effect", {}),
            "required-readback-list": ("required_readback", []),
            "required-readback-dict": ("required_readback", {}),
            "required-readback-int": ("required_readback", 1),
            "limitations-object": ("remaining_limitations", [{}]),
            "limitations-int": ("remaining_limitations", [1]),
            "limitations-string": ("remaining_limitations", "x"),
            "limitations-none": ("remaining_limitations", None),
        }
        for name, (field, value) in cases.items():
            with self.subTest(case=name):
                log = {**base, "completion": copy.deepcopy(base["completion"])}
                log["completion"][field] = value
                path = self.logs / "run_log.txt"
                if path.exists() or path.is_symlink():
                    path.unlink()
                path.write_text(json.dumps(log), encoding="utf-8")
                self.assertIsNone(go_chi_entry._read_run_log(self.logs))
                self.assertTrue(go_chi_entry._failure_run_log(self.logs, error="chi_entry_failed"))
                updated = json.loads(path.read_text())
                self.assertTrue(updated["log_fallback"])
                self.assertNotIn("synthetic", json.dumps(updated))

    def test_nested_reference_and_status_types_fall_back(self):
        import copy
        base = rich_log()
        cases = {
            "reference-event-list": ("last_business_mutation", "event", []),
            "reference-event-dict": ("last_business_mutation", "event", {}),
            "status-kind-list": ("latest_business_status", "source_kind", []),
            "status-event-dict": ("latest_business_status", "source_event", {}),
            "unresolved-event-list": ("unresolved_file_deliveries", "event", []),
        }
        for name, (field, key, value) in cases.items():
            with self.subTest(case=name):
                log = {**base, "completion": copy.deepcopy(base["completion"])}
                if field == "unresolved_file_deliveries":
                    log["completion"][field] = [{"call_id": "c", "tool": "local-fs-write",
                                                  "resource": "/workspace/CASE-A/payer/a",
                                                  key: value}]
                elif field == "latest_business_status":
                    log["completion"][field] = {
                        "text": "observed", "source_call_id": "c", "source_seq": 1,
                        "source_tool": "triage.get", "source_kind": "business_status",
                        "source_scope": "case:CASE-A", "source_event": "returned",
                    }
                    log["completion"][field][key] = value
                else:
                    log["completion"][field] = {
                        "call_id": "c", "tool": "triage.set_disposition",
                        "seq": 1, "event": "returned",
                    }
                    log["completion"][field][key] = value
                path = self.logs / "run_log.txt"
                if path.exists() or path.is_symlink():
                    path.unlink()
                path.write_text(json.dumps(log), encoding="utf-8")
                self.assertIsNone(go_chi_entry._read_run_log(self.logs))
                self.assertTrue(go_chi_entry._failure_run_log(self.logs, error="chi_entry_failed"))

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

    def test_entry_error_boundary_survives_nested_invalid_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, logs = root / "out", root / "logs"
            stream = io.StringIO()

            def fake_run(coro):
                coro.close()
                value = rich_log()
                value["completion"]["verification"] = []
                (logs / "run_log.txt").write_text(json.dumps(value), encoding="utf-8")
                raise GoFailure("chi_timeout")

            argv = ["coding-b", "--bundle-sha256", "a" * 64, "--evaluation-id", "e",
                    "--task-id", "synthetic-coding-b", "--attempt-id", "a", "--run-id", "r",
                    "--output-root", str(output), "--logs-dir", str(logs), "--history-mode", "external"]
            with mock.patch.dict(os.environ, {"OPENCODE_API_KEY": "synthetic"}), \
                    mock.patch.object(go_chi_entry, "_identity", return_value=("a" * 64, {})), \
                    mock.patch.object(go_chi_entry.asyncio, "run", side_effect=fake_run), \
                    contextlib.redirect_stdout(stream):
                code = go_chi_entry.main(argv)
            self.assertEqual(code, 1)
            result = json.loads(stream.getvalue())
            self.assertEqual(result["safe_error_code"], "chi_timeout")
            value = json.loads((logs / "run_log.txt").read_text())
            self.assertTrue(value["log_fallback"])
            self.assertEqual(value["safe_error_code"], "chi_timeout")
            self.assertEqual(value["first_error_code"], "chi_timeout")

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
