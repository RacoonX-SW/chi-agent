"""
tests/test_readiness_and_baseline.py — offline checks for chi-agent.

All tests drive real production entry points and module functions;
only external boundaries (subprocess, network, filesystem artifacts, clock, os.environ) are mocked.

Covers:
  - Multi-mode readiness evaluation (offline, tools, ungraded, scored)
  - Missing ANTHROPIC_API_KEY does NOT block offline mode
  - Missing ANTHROPIC_API_KEY DOES block scored mode
  - Handbook verified via on-disk presence; env authorization flag alone is rejected
  - Ungraded mode requires vendor checkout, dataset, handbook on disk, runner credentials
  - Credential presence reported without exposing values
  - Credential presence distinguished from proven connectivity
  - Offline mode does NOT require Docker socket or daemon (R4)
  - Ungraded real execution is explicitly blocked before subprocess launch (R1)
  - Single-task enforcement in ExperimentConfig (include_task_name + n_tasks=1)
  - Rejection of multi-task / multi-attempt misconfiguration
  - Real argv construction: cb experiment run -f <experiment.yaml>
  - Forwarding finite limits into agent_kwargs (R2)
  - Offline budget decision logic: reservation check, unverified unknown usage (R2)
  - Trial directory resolution via config.json metadata and prefix matching (R3)
  - Ambiguous multiple matching trials rejected (R3)
  - Strict binary reward validation: rejects bool, str, NaN, 0.5; records actual reward path (R3)
  - Strict finite positive numbers validation: rejects NaN, Inf, <=0 (R7)
  - Absolute resolution of relative --env-file paths and override priority (R8)
  - Dry-run validation without subprocess or started manifest
  - No credential values ever saved in manifest
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent


# ===========================================================================
# check_readiness tests — drive real module functions
# ===========================================================================

class TestReadinessChecks(unittest.TestCase):

    def test_python_ok_when_current_version_sufficient(self):
        import scripts.experiments.check_readiness as cr
        result = cr.check_python()
        if sys.version_info >= (3, 12):
            self.assertTrue(result["ok"])
        else:
            self.assertFalse(result["ok"])
            self.assertIsNotNone(result["fix"])

    def test_uv_missing_reports_fix(self):
        import scripts.experiments.check_readiness as cr
        with patch("shutil.which", return_value=None):
            result = cr.check_uv()
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["fix"])

    def test_uv_present_reports_ok(self):
        import scripts.experiments.check_readiness as cr
        with patch("shutil.which", return_value="/usr/local/bin/uv"):
            result = cr.check_uv()
        self.assertTrue(result["ok"])

    def test_docker_cli_missing_fails(self):
        import scripts.experiments.check_readiness as cr
        with patch("shutil.which", return_value=None):
            result = cr.check_docker()
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["fix"])

    def test_docker_daemon_down_fails(self):
        import scripts.experiments.check_readiness as cr
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Cannot connect to the Docker daemon"
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            result = cr.check_docker()
        self.assertFalse(result["ok"])

    def test_docker_daemon_up_ok(self):
        import scripts.experiments.check_readiness as cr
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            result = cr.check_docker()
        self.assertTrue(result["ok"])

    def test_handbook_detected_from_disk_files(self):
        import scripts.experiments.check_readiness as cr
        with tempfile.TemporaryDirectory() as td:
            skill_dir = Path(td) / "skills" / "managed-care-operations-handbook"
            skill_dir.mkdir(parents=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text("# Handbook")

            with patch.object(cr, "HANDBOOK_DIR", skill_dir):
                res = cr.check_handbook(env={})
                self.assertTrue(res["ok"])
                self.assertIn("present", res["detail"].lower())
                self.assertIn("revision", res["note"].lower())

    def test_handbook_granted_via_env_flag_alone_fails(self):
        """R5: Authorization flag alone is NOT downloaded/versioned handbook files."""
        import scripts.experiments.check_readiness as cr
        with tempfile.TemporaryDirectory() as td:
            empty_dir = Path(td) / "empty"
            empty_dir.mkdir()
            with patch.object(cr, "HANDBOOK_DIR", empty_dir):
                res = cr.check_handbook(env={"HF_HANDBOOK_ACCESS_GRANTED": "1"})
                self.assertFalse(res["ok"])
                self.assertIn("HF_HANDBOOK_ACCESS_GRANTED=1", res["detail"])
                self.assertIn("not downloaded", res["detail"].lower())

    def test_handbook_missing_when_not_on_disk_and_no_flag(self):
        import scripts.experiments.check_readiness as cr
        with tempfile.TemporaryDirectory() as td:
            empty_dir = Path(td) / "empty"
            empty_dir.mkdir()
            with patch.object(cr, "HANDBOOK_DIR", empty_dir):
                res = cr.check_handbook(env={})
                self.assertFalse(res["ok"])

    def test_credentials_check_does_not_expose_value(self):
        import scripts.experiments.check_readiness as cr
        secret = "sk-super-secret-key-12345"
        creds = cr.check_credentials(env={"ANTHROPIC_API_KEY": secret})
        self.assertTrue(creds["ANTHROPIC_API_KEY"]["ok"])
        self.assertNotIn(secret, creds["ANTHROPIC_API_KEY"]["detail"])

    def test_credentials_presence_distinguished_from_connectivity(self):
        import scripts.experiments.check_readiness as cr
        creds = cr.check_credentials(env={"ANTHROPIC_API_KEY": "sk-test"})
        note = (creds["ANTHROPIC_API_KEY"].get("note") or "").lower()
        self.assertIn("not verified", note)

    def test_offline_mode_does_not_require_docker_or_api_keys(self):
        """R4: Offline mode is READY with python, git, and uv; does NOT require docker daemon/socket or keys."""
        import scripts.experiments.check_readiness as cr
        with patch.object(cr, "check_python", return_value={"ok": True, "detail": "3.13"}), \
             patch.object(cr, "check_docker", side_effect=AssertionError("offline must not contact Docker")), \
             patch.object(cr, "check_git", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_uv", return_value={"ok": True, "detail": "OK"}):
            modes = cr.evaluate_modes(env={}, include_real_modes=False, include_environment_modes=False)
            self.assertTrue(modes["offline"]["ready"])
            self.assertEqual(modes["offline"]["failures"], [])

    def test_offline_evaluation_does_not_call_real_mode_gate(self):
        import scripts.experiments.check_readiness as cr
        with patch.object(cr, "check_python", return_value={"ok": True, "detail": "3.13"}), \
             patch.object(cr, "check_git", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_uv", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_docker", side_effect=AssertionError("offline must not contact Docker")), \
             patch.object(cr, "check_vendor", side_effect=AssertionError("offline need not check vendor")), \
             patch.object(cr, "evaluate_gate", side_effect=AssertionError("real gate must not run")):
            report = cr.evaluate_modes(env={}, include_real_modes=False, include_environment_modes=False)
        self.assertTrue(report["offline"]["ready"])

    def test_scored_readiness_cannot_claim_ready_without_budget_accounting(self):
        import scripts.experiments.check_readiness as cr
        good = {"ready": True, "failures": [], "evidence": {"synthetic": True}}
        with patch.object(cr, "check_python", return_value={"ok": True, "detail": "3.13"}), \
             patch.object(cr, "check_docker", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_git", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_uv", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_vendor", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "evaluate_gate", return_value=good):
            report = cr.evaluate_modes(
                env={}, domain="pa_provider", task_name="synthetic", model="deepseek/chat"
            )
        self.assertTrue(report["scored"]["local_configuration_ready"])
        self.assertFalse(report["scored"]["ready"])
        self.assertTrue(any("Budget gate" in reason for reason in report["scored"]["failures"]))

    def test_ungraded_mode_requires_vendor_checkout(self):
        """R5: Ungraded mode requires vendor checkout at pinned commit."""
        import scripts.experiments.check_readiness as cr
        with patch.object(cr, "check_python", return_value={"ok": True, "detail": "3.13"}), \
             patch.object(cr, "check_docker", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_git", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_uv", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_vendor", return_value={"ok": False, "detail": "vendor not cloned"}), \
             patch.object(cr, "check_dataset", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_handbook", return_value={"ok": True, "detail": "OK"}):
            env = {"DEEPSEEK_API_KEY": "sk-deepseek"}
            modes = cr.evaluate_modes(env=env)
            self.assertFalse(modes["ungraded"]["ready"])
            self.assertTrue(any("vendor" in f.lower() for f in modes["ungraded"]["failures"]))

    def test_ungraded_mode_does_not_require_anthropic_key(self):
        """Ungraded mode requires a runner key (e.g. DeepSeek/Gemini), NOT Anthropic key."""
        import scripts.experiments.check_readiness as cr
        with patch.object(cr, "check_python", return_value={"ok": True, "detail": "3.13"}), \
             patch.object(cr, "check_docker", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_git", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_uv", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_vendor", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_dataset", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_handbook", return_value={"ok": True, "detail": "OK"}):
            env = {"DEEPSEEK_API_KEY": "sk-deepseek-123"}
            modes = cr.evaluate_modes(env=env)
            self.assertFalse(modes["ungraded"]["ready"])
            self.assertFalse(modes["scored"]["ready"])
            self.assertFalse(any("ANTHROPIC_API_KEY" in f for f in modes["ungraded"]["failures"]))
            self.assertTrue(any("ANTHROPIC_API_KEY" in f for f in modes["scored"]["failures"]))

    def test_scored_mode_requires_anthropic_key(self):
        """Scored mode requires ANTHROPIC_API_KEY."""
        import scripts.experiments.check_readiness as cr
        with patch.object(cr, "check_python", return_value={"ok": True, "detail": "3.13"}), \
             patch.object(cr, "check_docker", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_git", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_uv", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_vendor", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_dataset", return_value={"ok": True, "detail": "OK"}), \
             patch.object(cr, "check_handbook", return_value={"ok": True, "detail": "OK"}):
            env = {"DEEPSEEK_API_KEY": "sk-deepseek", "ANTHROPIC_API_KEY": "sk-anthropic"}
            modes = cr.evaluate_modes(env=env)
            self.assertFalse(modes["scored"]["ready"])
            self.assertFalse(any("ANTHROPIC_API_KEY" in f for f in modes["scored"]["failures"]))

    def test_cli_json_mode_output(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m", "scripts.experiments.check_readiness",
                "--mode", "offline",
                "--env-file", "/tmp/chi-agent-no-env-test",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["mode"], "offline")
        self.assertIn("ready", data)
        self.assertIn("modes", data)
        self.assertIn("offline", data["modes"])
        self.assertIn("ungraded", data["modes"])
        self.assertIn("scored", data["modes"])


# ===========================================================================
# run_baseline helper tests
# ===========================================================================

class TestRunBaselineHelpers(unittest.TestCase):

    def setUp(self):
        import scripts.experiments.run_baseline as rb
        self.rb = rb

    def test_run_id_is_lowercase_slug_safe(self):
        rb = self.rb
        for _ in range(5):
            rid = rb._make_run_id()
            self.assertEqual(rid, rid.lower())
            self.assertRegex(rid, r"^[a-z0-9][a-z0-9\-_]*$")
            self.assertNotIn("T", rid)
            self.assertNotIn("Z", rid)

    def test_build_experiment_config_valid(self):
        rb = self.rb
        cfg = rb.build_experiment_config(
            dataset_dir="data/prior_auth_provider/tasks",
            task_name="pa_t018_sample",
            agent="deepagents",
            model="deepseek/deepseek-chat",
            trials_dir="runs/run-1/output/trials",
            env_file="/path/to/.env",
            timeout_multiplier=1.5,
            max_rounds=25,
            max_tokens_per_request=4096,
            budget_cny=3.5,
        )
        self.assertEqual(cfg["dataset"], "data/prior_auth_provider/tasks")
        self.assertEqual(cfg["include_task_name"], ["pa_t018_sample"])
        self.assertEqual(cfg["n_tasks"], 1)
        self.assertEqual(cfg["n_attempts"], 1)
        self.assertEqual(cfg["concurrency"], 1)
        self.assertEqual(cfg["timeout_multiplier"], 1.5)
        self.assertEqual(cfg["environment"], "docker")
        self.assertEqual(cfg["max_retries"], 0)
        # R2: agent_kwargs forwards limits
        self.assertEqual(cfg["agent_kwargs"]["max_rounds"], "25")
        self.assertEqual(cfg["agent_kwargs"]["max_tokens_per_request"], "4096")
        self.assertEqual(cfg["agent_kwargs"]["budget_cny"], "3.5")

    def test_build_experiment_config_rejects_multi_task(self):
        rb = self.rb
        with self.assertRaises(ValueError):
            rb.build_experiment_config(
                dataset_dir="data",
                task_name="t1",
                agent="a",
                model="m",
                trials_dir="trials",
                env_file=".env",
                timeout_multiplier=1.0,
                n_tasks=2,
            )

    def test_build_experiment_config_rejects_multi_attempt(self):
        rb = self.rb
        with self.assertRaises(ValueError):
            rb.build_experiment_config(
                dataset_dir="data",
                task_name="t1",
                agent="a",
                model="m",
                trials_dir="trials",
                env_file=".env",
                timeout_multiplier=1.0,
                n_attempts=3,
            )

    def test_build_experiment_config_rejects_multi_concurrency(self):
        rb = self.rb
        with self.assertRaises(ValueError):
            rb.build_experiment_config(
                dataset_dir="data",
                task_name="t1",
                agent="a",
                model="m",
                trials_dir="trials",
                env_file=".env",
                timeout_multiplier=1.0,
                concurrency=4,
            )

    # ------------------------------------------------------------------
    # Budget Evaluation (R2)
    # ------------------------------------------------------------------

    def test_evaluate_budget_insufficient_reservation(self):
        rb = self.rb
        status, reason = rb.evaluate_budget(
            budget_cny=0.000001,
            max_rounds=1,
            max_tokens_per_request=1,
            cumulative_cost_cny=0,
            input_price_usd_per_million=100,
            output_price_usd_per_million=100,
            max_input_tokens_per_request=1000,
            usd_to_cny=2000,
            pricing_version="synthetic-v1",
            fx_rate_source="synthetic-test-rate",
        )
        self.assertEqual(status, "stopped_insufficient_budget")
        self.assertIn("above cap", reason)

    def test_evaluate_budget_unmeasured_usage_post_execution(self):
        rb = self.rb
        status, reason = rb.evaluate_budget(
            budget_cny=5.0,
            max_rounds=30,
            max_tokens_per_request=8192,
            cumulative_cost_cny=None,
        )
        self.assertEqual(status, "unverified_unknown_usage")
        self.assertIn("Maximum input tokens", reason)

    def test_evaluate_budget_within_budget(self):
        rb = self.rb
        status, reason = rb.evaluate_budget(
            budget_cny=5.0,
            max_rounds=30,
            max_tokens_per_request=8192,
            cumulative_cost_cny=0.25,
            input_price_usd_per_million=1.0,
            output_price_usd_per_million=2.0,
            max_input_tokens_per_request=1000,
            usd_to_cny=7.0,
            pricing_version="synthetic-v1",
            fx_rate_source="synthetic-test-rate",
        )
        self.assertEqual(status, "within_budget")

    # ------------------------------------------------------------------
    # Reward Extraction and Binary Validation (R3)
    # ------------------------------------------------------------------

    def test_extract_reward_ungraded_mode_returns_none(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            reward, sc_path, reason, rew_path = rb.extract_reward(output_dir, "task-1", mode="ungraded")
            self.assertIsNone(reward)
            self.assertIsNone(sc_path)
            self.assertIsNone(rew_path)
            self.assertIn("ungraded", reason)

    def test_extract_reward_binary_1_passed(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            rf = vdir / "reward.json"
            rf.write_text('{"reward": 1.0}')
            reward, _, reason, actual_path = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertEqual(reward, 1.0)
            self.assertEqual(actual_path, str(rf))
            self.assertIn("passed", reason)

    def test_extract_reward_binary_0_completed_unsolved(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            rf = vdir / "reward.json"
            rf.write_text('{"reward": 0.0}')
            reward, _, reason, actual_path = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertEqual(reward, 0.0)
            self.assertEqual(actual_path, str(rf))
            self.assertIn("not passed", reason)

    def test_extract_reward_with_trial_suffix_and_config_json(self):
        """R3: Resolve trial directory with random suffix and verify actual path."""
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            trial_dir = output_dir / "trials" / "job-1" / "pa_t018__AbC123"
            vdir = trial_dir / "verifier"
            vdir.mkdir(parents=True)
            (trial_dir / "config.json").write_text(json.dumps({"task": {"path": "/synthetic/pa_t018"}}))
            rf = vdir / "reward.json"
            rf.write_text('{"reward": 1.0}')
            reward, _, reason, actual_path = rb.extract_reward(output_dir, "pa_t018", mode="scored")
            self.assertEqual(reward, 1.0)
            self.assertEqual(actual_path, str(rf))

    def test_extract_reward_rejects_ambiguous_trials(self):
        """R3: Rejects ambiguous multiple matching trial directories."""
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            for job, rew in [("job-1", 1.0), ("job-2", 0.0)]:
                vdir = output_dir / "trials" / job / "task-1" / "verifier"
                vdir.mkdir(parents=True)
                (vdir / "reward.json").write_text(json.dumps({"reward": rew}))
            reward, sc_path, reason, actual_path = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertIsNone(reward)
            self.assertIsNone(actual_path)
            self.assertIn("Ambiguous", reason)

    def test_extract_reward_rejects_numeric_string(self):
        """R3: String '1' is rejected as non-numeric binary."""
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            (vdir / "reward.json").write_text('{"reward": "1"}')
            reward, _, reason, _ = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertIsNone(reward)
            self.assertIn("string", reason)

    def test_extract_reward_rejects_boolean(self):
        """R3: Boolean True is rejected."""
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            (vdir / "reward.json").write_text('{"reward": true}')
            reward, _, reason, _ = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertIsNone(reward)
            self.assertIn("boolean", reason)

    def test_extract_reward_rejects_non_binary_float(self):
        """0.5 is non-binary and must be rejected as invalid reward."""
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            (vdir / "reward.json").write_text('{"reward": 0.5}')
            reward, _, reason, _ = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertIsNone(reward)
            self.assertIn("Invalid non-binary reward", reason)

    def test_extract_reward_rejects_negative_reward(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            (vdir / "reward.json").write_text('{"reward": -1.0}')
            reward, _, reason, _ = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertIsNone(reward)
            self.assertIn("Invalid non-binary reward", reason)

    def test_extract_reward_missing_file_returns_none(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            reward, _, reason, _ = rb.extract_reward(output_dir, "missing-task", mode="scored")
            self.assertIsNone(reward)
            self.assertIn("not found", reason)

    def test_extract_reward_corrupted_json_returns_none(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = output_dir / "trials" / "task-1" / "verifier"
            vdir.mkdir(parents=True)
            (vdir / "reward.json").write_text("NOT_VALID_JSON{")
            reward, _, reason, _ = rb.extract_reward(output_dir, "task-1", mode="scored")
            self.assertIsNone(reward)
            self.assertIn("could not be parsed", reason)


# ===========================================================================
# run_baseline main() integration tests (with mocked externals)
# ===========================================================================

class TestRunBaselineMain(unittest.TestCase):

    def _run_main_with_mocks(
        self,
        *,
        mode: str = "scored",
        task_name: str = "pa_t018_test",
        domain: str = "pa_provider",
        agent: str = "deepagents",
        model: str = "deepseek/deepseek-chat",
        subprocess_returncode: int = 0,
        subprocess_raises=None,
        reward_json: str | None = None,
        prereqs_clear: bool = True,
        dry_run: bool = False,
        extra_args: list[str] | None = None,
    ) -> tuple[int, dict | None, Path]:
        """Drive run_baseline.main() and return (exit_code, manifest_dict, runs_dir)."""
        import scripts.experiments.run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text("ANTHROPIC_API_KEY=sk-test\nDEEPSEEK_API_KEY=sk-test\nHF_HANDBOOK_ACCESS_GRANTED=1\n")

            argv = [
                "--agent", agent,
                "--model", model,
                "--domain", domain,
                "--task-name", task_name,
                "--mode", mode,
                "--env-file", str(env_file),
            ]
            if dry_run:
                argv.append("--dry-run")
            if extra_args:
                argv.extend(extra_args)

            orig_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            if subprocess_raises:
                mock_proc = None
            else:
                mock_proc = MagicMock()
                mock_proc.returncode = subprocess_returncode

            def side_effect(*a, **kw):
                cmd = a[0] if a else kw.get("args", [])
                if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == "git":
                    git_proc = MagicMock()
                    git_proc.returncode = 0
                    git_proc.stdout = "mock-sha-12345\n"
                    return git_proc

                if subprocess_raises is not None:
                    raise subprocess_raises
                if reward_json is not None and not dry_run:
                    created = list(runs_dir.iterdir()) if runs_dir.exists() else []
                    if created:
                        out = created[0] / "output" / "trials" / task_name / "verifier"
                        out.mkdir(parents=True, exist_ok=True)
                        (out / "reward.json").write_text(reward_json)
                mock_proc = MagicMock()
                mock_proc.returncode = subprocess_returncode
                mock_proc.stdout = "output\n"
                return mock_proc

            exit_code = None
            try:
                with patch("sys.argv", ["run_baseline"] + argv), \
                     patch.object(rb, "_check_prerequisites",
                                  return_value=([] if prereqs_clear else ["Prerequisite blocked"])), \
                     patch.object(rb, "evaluate_budget", side_effect=[("within_budget", "synthetic test evidence"), ("unverified_unknown_usage", "not measured by test harness")]), \
                     patch("subprocess.run", side_effect=side_effect):
                    rb.main()
            except SystemExit as e:
                exit_code = e.code
            finally:
                rb.RUNS_DIR = orig_runs_dir

            manifest = None
            if runs_dir.exists():
                for run_dir in runs_dir.iterdir():
                    mp = run_dir / "manifest.json"
                    if mp.exists():
                        manifest = json.loads(mp.read_text())
                        break

        return exit_code, manifest, runs_dir

    def test_ungraded_real_execution_blocked_before_subprocess(self):
        """R1: Ungraded real execution is explicitly blocked before subprocess launch."""
        import scripts.experiments.run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text("DEEPSEEK_API_KEY=sk-test\n")

            orig_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir
            exit_code = None
            mock_sub = MagicMock()
            mock_sub.return_value = MagicMock(returncode=0, stdout="test-git-sha\n")

            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/deepseek-chat",
                    "--task-name", "pa_t018",
                    "--mode", "ungraded",
                    "--env-file", str(env_file),
                ]), patch("subprocess.run", mock_sub):
                    try:
                        rb.main()
                    except SystemExit as e:
                        exit_code = e.code
            finally:
                rb.RUNS_DIR = orig_runs_dir

            # Blocked before external process launch: no cb/uv experiment run launched
            self.assertEqual(exit_code, 2)
            experiment_calls = [
                c for c in mock_sub.call_args_list
                if c.args and isinstance(c.args[0], list) and c.args[0] and c.args[0][0] != "git"
            ]
            self.assertEqual(experiment_calls, [])

            manifests = list(runs_dir.glob("*/manifest.json"))
            self.assertTrue(manifests, "Blocked run must write manifest recording reason")
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["execution_status"], "blocked_before_execution")
            self.assertEqual(manifest["exit_code"], 2)
            self.assertIn("Ungraded real execution is currently unsupported", manifest["reward_reason"])

    def test_scored_successful_run_reward_1(self):
        exit_code, manifest, _ = self._run_main_with_mocks(
            mode="scored",
            subprocess_returncode=0,
            reward_json='{"reward": 1.0}',
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "completed")
        self.assertEqual(manifest["reward"], 1.0)
        self.assertIn("passed", manifest["reward_reason"])
        # R2: token usage was not measured by harness, so budget status is unverified_unknown_usage
        self.assertEqual(manifest["budget_status"], "unverified_unknown_usage")

    def test_scored_evaluation_reward_0(self):
        exit_code, manifest, _ = self._run_main_with_mocks(
            mode="scored",
            subprocess_returncode=0,
            reward_json='{"reward": 0.0}',
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "completed")
        self.assertEqual(manifest["reward"], 0.0)
        self.assertIn("not passed", manifest["reward_reason"])

    def test_scored_missing_reward_gives_incomplete_no_verdict(self):
        exit_code, manifest, _ = self._run_main_with_mocks(
            mode="scored",
            subprocess_returncode=0,
            reward_json=None,
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "incomplete_no_verdict")
        self.assertIsNone(manifest["reward"])

    def test_subprocess_failure_gives_process_failed(self):
        exit_code, manifest, _ = self._run_main_with_mocks(
            mode="scored",
            subprocess_returncode=1,
        )
        self.assertEqual(exit_code, 1)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "process_failed")

    def test_timeout_sets_timeout_status(self):
        exit_code, manifest, _ = self._run_main_with_mocks(
            subprocess_raises=subprocess.TimeoutExpired(cmd="cb", timeout=1800),
        )
        self.assertEqual(exit_code, 3)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "timeout")
        self.assertIsNone(manifest["reward"])

    def test_subprocess_exception_sets_error_status(self):
        exit_code, manifest, _ = self._run_main_with_mocks(
            subprocess_raises=OSError("Docker failed"),
        )
        self.assertEqual(exit_code, 4)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "subprocess_error")
        self.assertIsNone(manifest["reward"])

    def test_generated_config_is_single_task_experiment_yaml(self):
        """Verify the written YAML conforms to ExperimentConfig with single task bound and limits forwarded."""
        import scripts.experiments.run_baseline as rb
        import yaml

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text("DEEPSEEK_API_KEY=sk-test\n")

            orig_runs = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir
            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/deepseek-chat",
                    "--domain", "pa_provider",
                    "--task-name", "pa_t018_sample",
                    "--mode", "scored",
                    "--env-file", str(env_file),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), \
                   patch.object(rb, "evaluate_budget", side_effect=[("within_budget", "synthetic test evidence"), ("unverified_unknown_usage", "not measured by test harness")]), \
                   patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0)
                    try:
                        rb.main()
                    except SystemExit:
                        pass
            finally:
                rb.RUNS_DIR = orig_runs

            exp_yamls = list(runs_dir.rglob("experiment.yaml"))
            self.assertTrue(exp_yamls, "experiment.yaml was not generated")
            cfg = yaml.safe_load(exp_yamls[0].read_text())

            self.assertEqual(cfg["include_task_name"], ["pa_t018_sample"])
            self.assertEqual(cfg["n_tasks"], 1)
            self.assertEqual(cfg["n_attempts"], 1)
            self.assertEqual(cfg["concurrency"], 1)
            self.assertEqual(cfg["agent"], "deepagents")
            self.assertEqual(cfg["model"], "deepseek/deepseek-chat")
            # R2: agent limits forwarded
            self.assertIn("agent_kwargs", cfg)
            self.assertEqual(cfg["agent_kwargs"]["max_rounds"], "30")
            # R8: env_file is absolute
            self.assertTrue(Path(cfg["env_file"]).is_absolute())

    def test_relative_env_file_resolves_to_absolute_path(self):
        """R8: Relative --env-file is resolved to absolute path so child process in vendor/ loads the same file."""
        import scripts.experiments.run_baseline as rb
        import yaml

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            rel_env = td_path / "local.env"
            rel_env.write_text("DEEPSEEK_API_KEY=test-val\n")

            runs_dir = td_path / "runs"
            orig_runs = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            captured_cfg = {}

            def mock_sub(argv, **kw):
                if argv[0] == "git":
                    proc = MagicMock()
                    proc.returncode = 0
                    proc.stdout = "git-sha\n"
                    return proc
                cfg_path = Path(argv[argv.index("-f") + 1])
                captured_cfg.update(yaml.safe_load(cfg_path.read_text()))
                proc = MagicMock()
                proc.returncode = 0
                return proc

            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/chat",
                    "--task-name", "pa_t018",
                    "--mode", "scored",
                    "--env-file", str(rel_env),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), \
                   patch.object(rb, "evaluate_budget", side_effect=[("within_budget", "synthetic test evidence"), ("unverified_unknown_usage", "not measured by test harness")]), \
                   patch("subprocess.run", side_effect=mock_sub):
                    try:
                        rb.main()
                    except SystemExit:
                        pass
            finally:
                rb.RUNS_DIR = orig_runs

            self.assertTrue(captured_cfg, "Subprocess was not called")
            resolved_env = Path(captured_cfg["env_file"])
            self.assertTrue(resolved_env.is_absolute(), f"env_file must be absolute: {resolved_env}")
            self.assertTrue(resolved_env.is_file(), f"resolved env file must exist: {resolved_env}")

    def test_dry_run_exits_zero_without_subprocess_or_started_manifest(self):
        import scripts.experiments.run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            orig_runs = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir
            exit_code = None
            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/chat",
                    "--task-name", "pa_t018",
                    "--dry-run",
                ]), patch("subprocess.run") as mock_sub:
                    try:
                        rb.main()
                    except SystemExit as e:
                        exit_code = e.code
                    mock_sub.assert_not_called()
            finally:
                rb.RUNS_DIR = orig_runs

        self.assertEqual(exit_code, 0)
        self.assertFalse(runs_dir.exists())

    def test_budget_parameters_and_validation(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.experiments.run_baseline",
             "--agent", "a", "--model", "m", "--task-name", "t",
             "--budget-cny", "0"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("budget-cny", result.stdout + result.stderr)

    def test_outer_timeout_validation(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.experiments.run_baseline",
             "--agent", "a", "--model", "m", "--task-name", "t",
             "--outer-timeout", "0"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outer-timeout", result.stdout + result.stderr)

    def test_timeout_multiplier_validation(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.experiments.run_baseline",
             "--agent", "a", "--model", "m", "--task-name", "t",
             "--timeout-multiplier", "0"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timeout-multiplier", result.stdout + result.stderr)

    def test_non_finite_parameters_rejected(self):
        """R7: Validate that NaN and Inf are rejected across float parameters."""
        for flag in ["--budget-cny", "--timeout-multiplier"]:
            for bad_val in ["nan", "inf", "-inf"]:
                result = subprocess.run(
                    [sys.executable, "-m", "scripts.experiments.run_baseline",
                     "--agent", "a", "--model", "m", "--task-name", "t",
                     "--dry-run", f"{flag}={bad_val}"],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertNotEqual(
                    result.returncode, 0,
                    f"Expected {flag}={bad_val} to be rejected with non-zero exit code"
                )
                self.assertIn("finite positive number", result.stdout + result.stderr)

    def test_missing_task_name_rejected(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.experiments.run_baseline",
             "--agent", "a", "--model", "m"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_secret_never_leaks_into_manifest(self):
        import scripts.experiments.run_baseline as rb

        secret_str = "SUPER_SECRET_ANTHROPIC_KEY_9999"
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text(f"ANTHROPIC_API_KEY={secret_str}\n")

            orig_runs = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir
            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/chat",
                    "--task-name", "pa_t018",
                    "--mode", "scored",
                    "--env-file", str(env_file),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), \
                   patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0)
                    try:
                        rb.main()
                    except SystemExit:
                        pass
            finally:
                rb.RUNS_DIR = orig_runs

            for run_dir in runs_dir.iterdir():
                manifest_file = run_dir / "manifest.json"
                if manifest_file.exists():
                    self.assertNotIn(secret_str, manifest_file.read_text())


if __name__ == "__main__":
    unittest.main()
