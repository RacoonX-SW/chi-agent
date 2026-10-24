"""Focused production behavior tests for D0 budget gating and reward identity."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import run_baseline as rb


class TestBudgetDecision(unittest.TestCase):
    def evaluate(self, *, cumulative=4.0, **overrides):
        values = {
            "budget_cny": 5.0,
            "max_rounds": 30,
            "max_tokens_per_request": 1000,
            "rounds_used": 4,
            "cumulative_cost_cny": cumulative,
            "input_price_usd_per_million": 100.0,
            "output_price_usd_per_million": 100.0,
            "max_input_tokens_per_request": 1000,
            "usd_to_cny": 2.0,
            "pricing_version": "synthetic-test-v1",
            "fx_rate_source": "synthetic-test-rate",
        }
        values.update(overrides)
        return rb.evaluate_budget(**values)

    def test_accumulated_cost_and_max_request_reserve_fit(self):
        status, reason = self.evaluate(cumulative=4.0)
        self.assertEqual(status, "within_budget")
        self.assertIn("0.4", reason)

    def test_accumulated_cost_plus_reserve_exceeding_budget_stops(self):
        status, reason = self.evaluate(cumulative=4.8)
        self.assertEqual(status, "stopped_insufficient_budget")
        self.assertIn("above cap", reason)

    def test_usage_already_over_budget_stops(self):
        status, reason = self.evaluate(cumulative=5.1)
        self.assertEqual(status, "stopped_budget_exhausted")
        self.assertIn("already exceeds", reason)

    def test_exhausted_round_limit_stops_before_reserving(self):
        status, reason = self.evaluate(rounds_used=30)
        self.assertEqual(status, "stopped_round_limit")
        self.assertIn("30/30", reason)

    def test_missing_cumulative_usage_or_input_limit_is_unknown(self):
        self.assertEqual(self.evaluate(cumulative=None)[0], "unverified_unknown_usage")
        self.assertEqual(self.evaluate(max_input_tokens_per_request=None)[0], "unverified_unknown_usage")

    def test_missing_price_version_and_conversion_stop(self):
        self.assertEqual(self.evaluate(input_price_usd_per_million=None)[0], "unverified_unknown_pricing")
        self.assertEqual(self.evaluate(pricing_version=None)[0], "unverified_unknown_pricing")
        self.assertEqual(self.evaluate(usd_to_cny=None)[0], "unverified_unknown_conversion")
        self.assertEqual(self.evaluate(fx_rate_source=None)[0], "unverified_unknown_conversion")

    def test_nonfinite_negative_and_boolean_cost_inputs_never_pass(self):
        self.assertNotEqual(self.evaluate(input_price_usd_per_million=float("inf"))[0], "within_budget")
        self.assertNotEqual(self.evaluate(output_price_usd_per_million=-1)[0], "within_budget")
        self.assertNotEqual(self.evaluate(cumulative=True)[0], "within_budget")
        self.assertNotEqual(self.evaluate(usd_to_cny=float("nan"))[0], "within_budget")

    def test_real_entrypoint_blocks_before_uv_without_accounting_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            env_file = Path(td) / "empty.env"
            env_file.write_text("")
            original_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir
            calls = []

            def fake_run(argv, **kwargs):
                calls.append(argv)
                result = MagicMock(returncode=0, stdout="synthetic-git-sha\n")
                return result

            try:
                with patch("sys.argv", [
                    "run_baseline", "--agent", "deepagents", "--model", "synthetic/model",
                    "--task-name", "task-1", "--mode", "scored", "--env-file", str(env_file),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), patch("subprocess.run", side_effect=fake_run):
                    with self.assertRaises(SystemExit) as exit_info:
                        rb.main()
            finally:
                rb.RUNS_DIR = original_runs_dir

            self.assertEqual(exit_info.exception.code, 2)
            self.assertFalse(any(argv and argv[0] == "uv" for argv in calls))
            manifests = list(runs_dir.glob("*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["execution_status"], "blocked_before_execution")
            self.assertEqual(manifest["budget_status"], "unverified_unknown_usage")
            self.assertIsNotNone(manifest["finished_at"])
            self.assertIn("Budget gate", manifest["blocked_prerequisites"][-1])


class TestRewardIdentity(unittest.TestCase):
    def write_reward(self, root: Path, rel: str, reward: str, config: dict | None = None) -> Path:
        trial = root / rel
        verifier = trial / "verifier"
        verifier.mkdir(parents=True)
        if config is not None:
            (trial / "config.json").write_text(json.dumps(config))
        reward_path = verifier / "reward.json"
        reward_path.write_text('{"reward": ' + reward + '}')
        return reward_path

    def test_explicit_other_task_metadata_cannot_be_overridden_by_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_reward(root, "task-1__ABC", "1", {"task": {"path": "/synthetic/another-task"}})
            reward, _, reason, actual_path = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertIsNone(actual_path)
            self.assertIn("explicitly identifies a different task", reason)

    def test_conflicting_or_corrupt_metadata_is_not_recovered_from_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_reward(root, "task-1__ABC", "1", {"task": {"path": "/synthetic/another-task", "id": "task-1"}})
            reward, _, reason, _ = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertIn("explicitly identifies a different task", reason)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trial = root / "task-1__ABC"
            self.write_reward(root, "task-1__ABC", "1")
            (trial / "config.json").write_text("not-json")
            reward, _, reason, _ = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertIn("invalid config.json task metadata", reason)

    def test_missing_metadata_uses_exact_or_double_underscore_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_reward(root, "task-1_other", "1")
            reward, _, reason, _ = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertIn("No reward belongs", reason)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            expected = self.write_reward(root, "task-1__ABC", "0")
            reward, _, _, actual_path = rb.extract_reward(root, "task-1")
            self.assertEqual(reward, 0.0)
            self.assertEqual(actual_path, str(expected))

    def test_ambiguous_metadata_free_trials_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_reward(root, "task-1", "0")
            self.write_reward(root, "task-1__ABC", "1")
            reward, _, reason, actual_path = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertIsNone(actual_path)
            self.assertIn("Ambiguous", reason)

    def test_giant_integer_is_invalid_result_not_exception(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reward_path = self.write_reward(root, "task-1", str(10**400))
            reward, _, reason, actual_path = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertEqual(actual_path, str(reward_path))
            self.assertIn("cannot be represented", reason)

    def test_integer_exceeding_json_parser_limit_is_invalid_result(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            verifier = root / "task-1" / "verifier"
            verifier.mkdir(parents=True)
            reward_path = verifier / "reward.json"
            reward_path.write_text('{"reward": ' + ("9" * 5000) + '}')
            reward, _, reason, actual_path = rb.extract_reward(root, "task-1")
            self.assertIsNone(reward)
            self.assertEqual(actual_path, str(reward_path))
            self.assertIn("could not be parsed", reason)

    def test_giant_integer_result_collection_finishes_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runs_dir = root / "runs"
            env_file = root / "test.env"
            env_file.write_text("ANTHROPIC_API_KEY=synthetic\n")
            original_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            def fake_run(argv, **kwargs):
                if argv and argv[0] == "git":
                    return MagicMock(returncode=0, stdout="synthetic-git-sha\n")
                run_dir = next(runs_dir.iterdir())
                self.write_reward(run_dir / "output" / "trials", "task-1", str(10**400))
                return MagicMock(returncode=0, stdout="")

            try:
                with patch("sys.argv", [
                    "run_baseline", "--agent", "deepagents", "--model", "synthetic/model",
                    "--task-name", "task-1", "--mode", "scored", "--env-file", str(env_file),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), \
                     patch.object(rb, "evaluate_budget", side_effect=[("within_budget", "synthetic evidence"), ("unverified_unknown_usage", "usage unavailable")]), \
                     patch("subprocess.run", side_effect=fake_run):
                    with self.assertRaises(SystemExit) as exit_info:
                        rb.main()
            finally:
                rb.RUNS_DIR = original_runs_dir

            self.assertEqual(exit_info.exception.code, 0)
            manifest_path = next(runs_dir.glob("*/manifest.json"))
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["execution_status"], "incomplete_no_verdict")
            self.assertIsNone(manifest["reward"])
            self.assertIsNotNone(manifest["finished_at"])
            self.assertIn("cannot be represented", manifest["reward_reason"])


if __name__ == "__main__":
    unittest.main()
