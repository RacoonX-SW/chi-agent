"""Lifecycle-boundary tests for the offline C rehearsal controller."""

from __future__ import annotations

import json
import io
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import c_run_control as control


class RecordingBackend:
    def __init__(self, *, outcome=None, create_error=None, cleanup_error=False, handle=None):
        self.calls = []
        self.outcome = outcome or control.BackendResult(0, {"input_tokens": 4, "output_tokens": 2}, 0.0000432, "fixture-v1")
        self.create_error = create_error
        self.cleanup_error = cleanup_error
        self.handle = handle
        self.lock = threading.Lock()

    def create_world(self, spec):
        with self.lock:
            self.calls.append("create")
        if self.create_error:
            raise self.create_error
        return self.handle or control.OwnedHandle("world-owned", True, spec.run_id)

    def run_once(self, handle, spec):
        with self.lock:
            self.calls.append("run")
        return self.outcome

    def cleanup(self, handle):
        with self.lock:
            self.calls.append("cleanup")
        if self.cleanup_error:
            raise RuntimeError("secret detail must not be persisted")


class TestCRunControl(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "runs" / "c-control"
        self.spec = control.RunSpec("c-test-1", "openai-agents", "deepseek-flash")
        self.budget = control.BudgetEvidence(
            0.25, "synthetic-fixture-v1", 1.0, 1.0, "synthetic-price-v1", 7.2, "synthetic-fx-v1"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def read_manifest(self, run_id):
        return json.loads((self.root / "runs" / run_id / "manifest.json").read_text())

    def test_plan_is_read_only_and_marks_limits_unverified(self):
        result = control.plan(self.spec, self.budget)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["requested_limits"]["enforcement_status"], "configured_unverified")
        self.assertEqual(result["experiment_config"]["include_task_name"], [control.TASK_ID])
        self.assertEqual(result["experiment_config"]["n_tasks"], 1)
        self.assertFalse(self.root.exists())

    def test_invalid_bool_and_out_of_range_limits_reject_before_backend(self):
        for changes in ({"max_rounds": True}, {"max_rounds": 31}, {"max_output_tokens": 8193},
                        {"timeout_seconds": 901}, {"attempts": 2}, {"attempts": 1.0},
                        {"concurrency": 2}, {"concurrency": 1.0}, {"retries": 1}, {"retries": 0.0}):
            with self.subTest(changes=changes):
                bad = control.RunSpec("bad-case", "openai-agents", "deepseek-flash", **changes)
                with self.assertRaises(control.ControlError):
                    control.plan(bad)

    def test_success_claims_before_single_runner_and_cleans_owned_world(self):
        backend = RecordingBackend()
        result = control.rehearse(self.spec, root=self.root, backend=backend, budget=self.budget)
        self.assertEqual(backend.calls, ["create", "run", "cleanup"])
        self.assertEqual(result["status"], "rehearsal_completed")
        self.assertEqual(result["provenance"], "synthetic_rehearsal")
        self.assertEqual(result["cleanup"]["status"], "succeeded")
        self.assertIsNone(result["real_provider_usage"])
        self.assertIsNone(result["real_provider_cost_cny"])
        self.assertIsNone(result["official_reward"])
        self.assertEqual(result["task_success"], "unknown")
        self.assertEqual(result["synthetic_accounting"]["status"], "complete")
        self.assertAlmostEqual(result["synthetic_accounting"]["synthetic_total_cost_cny"], 0.2500432)
        self.assertEqual(result["real_shared_budget"]["status"], "unknown")
        claim = json.loads(Path(result["claim_path"]).read_text())
        self.assertEqual(claim["namespace"], "synthetic")
        self.assertEqual(claim["status"], "rehearsal_completed")
        self.assertIn("synthetic-price", result["synthetic_budget"]["pricing_version"])

    def test_second_run_id_cannot_replay_campaign_scope(self):
        first_backend = RecordingBackend()
        control.rehearse(self.spec, root=self.root, backend=first_backend, budget=self.budget)
        claim_before = next((self.root / "claims" / "synthetic").glob("*.json")).read_bytes()
        second_backend = RecordingBackend()
        second = control.rehearse(
            control.RunSpec("c-test-2", "openai-agents", "deepseek-flash"),
            root=self.root,
            backend=second_backend,
            budget=self.budget,
        )
        self.assertEqual(second["status"], "claim_conflict")
        self.assertEqual(second_backend.calls, [])
        self.assertEqual(next((self.root / "claims" / "synthetic").glob("*.json")).read_bytes(), claim_before)

    def test_malformed_existing_claim_fails_closed_without_backend_call(self):
        claims_dir = self.root / "claims" / "synthetic"
        claims_dir.mkdir(parents=True)
        claim = claims_dir / f"{control._scope_key('synthetic')}.json"
        claim.write_text("", encoding="utf-8")
        backend = RecordingBackend()
        result = control.rehearse(self.spec, root=self.root, backend=backend, budget=self.budget)
        self.assertEqual(result["status"], "claim_conflict")
        self.assertEqual(backend.calls, [])
        self.assertEqual(claim.read_text(encoding="utf-8"), "")

    def test_concurrent_claim_has_one_backend_winner(self):
        backend = RecordingBackend()
        barrier = threading.Barrier(2)

        def invoke(run_id):
            barrier.wait()
            return control.rehearse(
                control.RunSpec(run_id, "openai-agents", "deepseek-flash"),
                root=self.root,
                backend=backend,
                budget=self.budget,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, ("c-race-a", "c-race-b")))
        self.assertEqual(sum(item["status"] == "rehearsal_completed" for item in results), 1)
        self.assertEqual(sum(item["status"] == "claim_conflict" for item in results), 1)
        self.assertEqual(backend.calls.count("create"), 1)
        self.assertEqual(backend.calls.count("run"), 1)

    def test_unknown_budget_blocks_before_claim_or_backend(self):
        backend = RecordingBackend()
        result = control.rehearse(
            self.spec,
            root=self.root,
            backend=backend,
            budget=control.BudgetEvidence(None, None, None, None, None, None, None),
        )
        self.assertEqual(result["status"], "preflight_blocked")
        self.assertFalse(result["attempt_claimed"])
        self.assertEqual(backend.calls, [])
        self.assertFalse((self.root / "claims").exists())

    def test_budget_sources_must_be_nonblank_strings_before_claim(self):
        invalid_budgets = (
            control.BudgetEvidence(0.25, None, 1.0, 1.0, "price-v1", 7.2, "fx-v1"),
            control.BudgetEvidence(0.25, "  ", 1.0, 1.0, "price-v1", 7.2, "fx-v1"),
            control.BudgetEvidence(0.25, True, 1.0, 1.0, "price-v1", 7.2, "fx-v1"),
            control.BudgetEvidence(0.25, "b-v1", 1.0, 1.0, " ", 7.2, "fx-v1"),
            control.BudgetEvidence(0.25, "b-v1", 1.0, 1.0, "price-v1", 7.2, {}),
        )
        for index, budget in enumerate(invalid_budgets):
            backend = RecordingBackend()
            result = control.rehearse(
                control.RunSpec(f"c-bad-budget-{index}", "openai-agents", "deepseek-flash"),
                root=self.root / f"budget-{index}", backend=backend, budget=budget,
            )
            self.assertEqual(result["status"], "preflight_blocked")
            self.assertEqual(backend.calls, [])

    def test_result_over_shared_cap_is_recorded_but_not_completed(self):
        backend = RecordingBackend(outcome=control.BackendResult(
            0, {"input_tokens": 1_000_000, "output_tokens": 1_000_000}, 14.4, "fixture-v1"
        ))
        result = control.rehearse(self.spec, root=self.root, backend=backend, budget=self.budget)
        self.assertEqual(result["status"], "budget_exceeded")
        self.assertEqual(result["synthetic_accounting"]["budget_status"], "exceeded")
        self.assertEqual(result["synthetic_accounting"]["synthetic_total_cost_cny"], 14.65)
        self.assertEqual(backend.calls, ["create", "run", "cleanup"])

    def test_partial_create_timeout_and_runner_rejection_keep_claim_and_cleanup_evidence(self):
        cases = [
            ("c-partial", control.SyntheticBackend("partial-create"), "world_creation_failed", ["create_world", "cleanup"]),
            ("c-timeout", control.SyntheticBackend("timeout"), "timeout", ["create_world", "run_once", "cleanup"]),
            ("c-reject", control.SyntheticBackend("runner-rejection"), "runner_rejected", ["create_world", "run_once", "cleanup"]),
        ]
        for run_id, backend, expected_status, expected_calls in cases:
            with self.subTest(run_id=run_id):
                case_root = self.root / f"isolated-{run_id}"
                result = control.rehearse(
                    control.RunSpec(run_id, "openai-agents", "deepseek-flash"),
                    root=case_root,
                    backend=backend,
                    budget=self.budget,
                )
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(backend.calls, expected_calls)
                self.assertTrue(Path(result["claim_path"]).is_file())
                if run_id == "c-partial":
                    self.assertEqual(result["resource_ids_owned"], ["synthetic-c-partial"])

    def test_cleanup_failure_is_separate_and_foreign_handle_is_never_removed(self):
        cleanup_backend = RecordingBackend(cleanup_error=True)
        result = control.rehearse(self.spec, root=self.root, backend=cleanup_backend, budget=self.budget)
        self.assertEqual(result["status"], "cleanup_failed")
        self.assertEqual(result["cleanup_error"]["error_type"], "RuntimeError")
        self.assertNotIn("secret detail", (self.root / "runs" / self.spec.run_id / "manifest.json").read_text())

        foreign_backend = RecordingBackend(handle=control.OwnedHandle(
            "synthetic-a-different-run", True, "a-different-run"
        ))
        foreign_root = self.root / "foreign"
        foreign = control.rehearse(
            control.RunSpec("c-foreign", "openai-agents", "deepseek-flash"),
            root=foreign_root,
            backend=foreign_backend,
            budget=self.budget,
        )
        self.assertEqual(foreign_backend.calls, ["create"])
        self.assertEqual(foreign["cleanup"]["status"], "resource_state_unknown")
        self.assertEqual(foreign["status"], "world_creation_failed")

        unknown_backend = RecordingBackend(create_error=control.OwnedHandleError())
        unknown_root = self.root / "unknown-resource"
        unknown = control.rehearse(
            control.RunSpec("c-unknown-resource", "openai-agents", "deepseek-flash"),
            root=unknown_root,
            backend=unknown_backend,
            budget=self.budget,
        )
        self.assertEqual(unknown_backend.calls, ["create"])
        self.assertEqual(unknown["cleanup"]["status"], "resource_state_unknown")
        self.assertEqual(unknown["resource_ids_owned"], [])

    def test_malformed_handle_is_terminal_and_not_cleaned(self):
        backend = RecordingBackend(handle={"resource_id": "world", "owned": True})
        result = control.rehearse(
            control.RunSpec("c-malformed-handle", "openai-agents", "deepseek-flash"),
            root=self.root, backend=backend, budget=self.budget,
        )
        self.assertEqual(backend.calls, ["create"])
        self.assertEqual(result["status"], "world_creation_failed")
        self.assertEqual(result["cleanup"]["status"], "resource_state_unknown")
        self.assertTrue((self.root / "runs" / "c-malformed-handle" / "manifest.json").is_file())

    def test_missing_usage_never_becomes_successful_accounting(self):
        result = control.rehearse(
            control.RunSpec("c-missing-usage", "openai-agents", "deepseek-flash"),
            root=self.root,
            scenario="missing-usage",
            budget=self.budget,
        )
        self.assertEqual(result["status"], "accounting_unknown")
        self.assertIsNone(result["synthetic_result"]["usage"])
        self.assertEqual(result["synthetic_result"]["known_prefix_usage"], {"input_tokens": 0, "output_tokens": 0})
        self.assertIsNone(result["synthetic_accounting"]["synthetic_total_cost_cny"])
        self.assertEqual(result["synthetic_accounting"]["synthetic_known_prefix_cost_cny"], 0.25)

    def test_unrecognized_usage_fields_are_not_persisted(self):
        backend = RecordingBackend(outcome=control.BackendResult(
            0,
            {"input_tokens": 10, "output_tokens": 5, "unexpected_field": "marker-not-allowed"},
            0.000108, "fixture-v1",
            {"input_tokens": 10, "output_tokens": 5, "extra": "marker-not-allowed"},
        ))
        result = control.rehearse(
            control.RunSpec("c-extra-usage", "openai-agents", "deepseek-flash"),
            root=self.root, backend=backend, budget=self.budget,
        )
        manifest_text = (self.root / "runs" / "c-extra-usage" / "manifest.json").read_text()
        self.assertEqual(result["status"], "accounting_unknown")
        self.assertNotIn("marker-not-allowed", manifest_text)
        self.assertIsNone(result["synthetic_result"]["usage"])
        self.assertIsNone(result["synthetic_result"]["known_prefix_usage"])

    def test_cleanup_runs_when_cleanup_started_evidence_write_fails(self):
        backend = RecordingBackend()
        original_write = control._atomic_json

        def fail_cleanup_started(path, payload):
            if payload.get("cleanup") == {"attempted": True, "status": "started"}:
                raise OSError("evidence marker-not-allowed")
            return original_write(path, payload)

        with patch.object(control, "_atomic_json", side_effect=fail_cleanup_started):
            result = control.rehearse(self.spec, root=self.root, backend=backend, budget=self.budget)
        self.assertEqual(backend.calls, ["create", "run", "cleanup"])
        self.assertEqual(result["status"], "evidence_write_failed")
        self.assertEqual(result["cleanup"]["status"], "succeeded")
        self.assertFalse(result["evidence_complete"])
        self.assertIn("OSError", (self.root / "runs" / self.spec.run_id / "manifest.json").read_text())
        self.assertNotIn("marker-not-allowed", (self.root / "runs" / self.spec.run_id / "manifest.json").read_text())
        self.assertTrue(Path(result["claim_path"]).is_file())

    def test_duplicate_run_id_preserves_existing_manifest(self):
        control.rehearse(self.spec, root=self.root, budget=self.budget)
        manifest_path = self.root / "runs" / self.spec.run_id / "manifest.json"
        before = manifest_path.read_bytes()
        with self.assertRaises(control.ControlError):
            control.rehearse(self.spec, root=self.root, budget=self.budget)
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_symlink_output_root_is_rejected(self):
        outside = Path(self.tempdir.name) / "outside"
        outside.mkdir()
        link = Path(self.tempdir.name) / "linked-runs"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(control.ControlError):
            control.rehearse(self.spec, root=link, budget=self.budget)
        self.assertEqual(list(outside.iterdir()), [])

    def test_live_is_refused_without_output_root_or_claim(self):
        self.assertEqual(
            control.main(["live", "--run-id", "c-live", "--agent", "openai-agents", "--model", "deepseek-flash"]),
            2,
        )
        self.assertFalse(self.root.exists())

    def test_cli_exit_codes_do_not_call_blocked_or_conflict_completed(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch.object(control, "rehearse", return_value={"status": "preflight_blocked"}):
                self.assertEqual(control.main(["rehearse", "--run-id", "c-blocked", "--agent", "openai-agents", "--model", "deepseek-flash"]), 1)
            with patch.object(control, "rehearse", return_value={"status": "claim_conflict"}):
                self.assertEqual(control.main(["rehearse", "--run-id", "c-conflict", "--agent", "openai-agents", "--model", "deepseek-flash"]), 1)
            with patch.object(control, "rehearse", return_value={"status": "rehearsal_completed"}):
                self.assertEqual(control.main(["rehearse", "--run-id", "c-done", "--agent", "openai-agents", "--model", "deepseek-flash"]), 0)


if __name__ == "__main__":
    unittest.main()
