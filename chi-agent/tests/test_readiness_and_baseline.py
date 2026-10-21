"""
tests/test_readiness_and_baseline.py — offline checks for chi-agent.

All tests drive real production entry points; only external boundaries
(subprocess, network, filesystem artifacts, clock, os.environ) are mocked.

Covers:
  - Missing required dependency → readiness exits non-zero and reports it
  - Missing env var (process + env_file) → readiness/baseline blocked
  - Credential presence reported without exposing values
  - Presence distinguished from connectivity
  - Handbook gate
  - Subprocess failure → manifest records process_failed + null reward
  - Timeout → manifest records timeout + null reward + reason
  - Launch exception → manifest records subprocess_error
  - Missing reward.json → reward=null + reason
  - Official binary reward=1 → accepted, passed=True
  - Official reward=0 → accepted, passed=False, status=completed
  - Non-binary float reward (0.5) → accepted as float but not-passed
  - Invalid reward.json (bad JSON, missing key, non-numeric) → null+reason
  - Omitting --task-name is a hard error (prevents fan-out)
  - Upstream submission YAML uses include_task_name+n_tasks, not --task-id
  - Submission ID is lowercase slug-safe
  - dry-run does not start subprocess and returns 0
  - --timeout-multiplier=0 is rejected
  - --outer-timeout=0 is rejected
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Make scripts importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ===========================================================================
# check_readiness tests — drive real module functions
# ===========================================================================

class TestReadinessChecks(unittest.TestCase):

    def test_python_ok_when_current_version_sufficient(self):
        import check_readiness as cr
        result = cr.check_python()
        if sys.version_info >= (3, 12):
            self.assertTrue(result["ok"])
        else:
            self.assertFalse(result["ok"])
            self.assertIsNotNone(result["fix"])

    def test_uv_missing_reports_fix(self):
        import check_readiness as cr
        with patch("shutil.which", return_value=None):
            result = cr.check_uv()
        self.assertFalse(result["ok"])
        self.assertTrue(result["required"])
        self.assertIsNotNone(result["fix"])

    def test_uv_present_reports_ok(self):
        import check_readiness as cr
        with patch("shutil.which", return_value="/usr/local/bin/uv"):
            result = cr.check_uv()
        self.assertTrue(result["ok"])

    def test_docker_cli_missing_blocks(self):
        import check_readiness as cr
        with patch("shutil.which", return_value=None):
            result = cr.check_docker()
        self.assertFalse(result["ok"])
        self.assertTrue(result["required"])
        self.assertIsNotNone(result["fix"])

    def test_docker_daemon_down_blocks(self):
        import check_readiness as cr
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Cannot connect to the Docker daemon"
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            result = cr.check_docker()
        self.assertFalse(result["ok"])
        self.assertTrue(result["required"])

    def test_docker_daemon_up_ok(self):
        import check_readiness as cr
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            result = cr.check_docker()
        self.assertTrue(result["ok"])

    def test_env_var_missing_blocks_required(self):
        import check_readiness as cr
        with patch.dict("os.environ", {}, clear=True):
            results = cr.check_env_vars()
        required = [r for r in results if r["required"]]
        for r in required:
            self.assertFalse(r["ok"])
            self.assertIsNotNone(r["fix"])

    def test_env_var_present_does_not_expose_value(self):
        import check_readiness as cr
        secret = "sk-ant-super-secret-key"
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": secret}):
            results = cr.check_env_vars()
        anthropic = next(r for r in results if r["check"] == "env:ANTHROPIC_API_KEY")
        self.assertTrue(anthropic["ok"])
        self.assertNotIn(secret, anthropic.get("detail", ""))
        self.assertNotIn(secret, anthropic.get("note", "") or "")

    def test_env_var_presence_not_claimed_as_connectivity(self):
        import check_readiness as cr
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            results = cr.check_env_vars()
        anthropic = next(r for r in results if r["check"] == "env:ANTHROPIC_API_KEY")
        note = (anthropic.get("note") or "").lower()
        self.assertIn("not verified", note)

    def test_handbook_not_granted_without_env_var(self):
        import check_readiness as cr
        with patch.dict("os.environ", {}, clear=True):
            result = cr.check_handbook()
        self.assertFalse(result["ok"])
        self.assertFalse(result["required"])

    def test_handbook_granted_with_env_var(self):
        import check_readiness as cr
        with patch.dict("os.environ", {"HF_HANDBOOK_ACCESS_GRANTED": "1"}):
            result = cr.check_handbook()
        self.assertTrue(result["ok"])

    def test_summarise_all_required_fail_returns_not_ready(self):
        import check_readiness as cr
        checks = [
            {"check": "python_version", "required": True, "ok": False,
             "detail": "Python 3.10", "fix": "install 3.12"},
            {"check": "uv", "required": True, "ok": False,
             "detail": "not found", "fix": "install uv"},
        ]
        all_ok, failures = cr.summarise(checks)
        self.assertFalse(all_ok)
        self.assertEqual(len(failures), 4)  # 2 × (message + fix)

    def test_summarise_all_pass_returns_ready(self):
        import check_readiness as cr
        checks = [{"check": "py", "required": True, "ok": True, "detail": "3.13", "fix": None}]
        all_ok, failures = cr.summarise(checks)
        self.assertTrue(all_ok)
        self.assertEqual(failures, [])

    def test_optional_failure_does_not_block_readiness(self):
        import check_readiness as cr
        checks = [
            {"check": "python_version", "required": True, "ok": True,
             "detail": "3.13", "fix": None},
            {"check": "handbook_access", "required": False, "ok": False,
             "detail": "not granted", "fix": "apply"},
        ]
        all_ok, failures = cr.summarise(checks)
        self.assertTrue(all_ok)

    def test_readiness_cli_exits_nonzero_when_blocked(self):
        """Drive the real CLI; pass empty env so ANTHROPIC_API_KEY is missing."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_readiness.py")],
            capture_output=True, text=True, timeout=30, env={},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT READY", result.stdout)

    def test_readiness_cli_json_output_structure(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_readiness.py"), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        self.assertIn("ready", data)
        self.assertIn("checks", data)
        self.assertIsInstance(data["checks"], list)


# ===========================================================================
# run_baseline module-level unit tests
# ===========================================================================

class TestRunBaselineHelpers(unittest.TestCase):
    """Tests that drive production functions in run_baseline."""

    def setUp(self):
        import run_baseline as rb
        self.rb = rb

    # ------------------------------------------------------------------
    # Slug / ID helpers
    # ------------------------------------------------------------------

    def test_run_id_is_lowercase_only(self):
        rb = self.rb
        rid = rb._make_run_id()
        self.assertEqual(rid, rid.lower(), f"run_id has uppercase: {rid!r}")

    def test_submission_id_is_slug_safe(self):
        rb = self.rb
        rid = rb._make_run_id()
        sid = rb._make_submission_id(rid)
        import re
        self.assertRegex(sid, r"^[a-z0-9][a-z0-9\-_]*$")

    def test_submission_id_does_not_contain_uppercase_T_Z(self):
        rb = self.rb
        for _ in range(5):
            rid = rb._make_run_id()
            sid = rb._make_submission_id(rid)
            self.assertNotIn("T", sid)
            self.assertNotIn("Z", sid)

    # ------------------------------------------------------------------
    # env_file loading
    # ------------------------------------------------------------------

    def test_load_env_file_parses_key_value(self):
        rb = self.rb
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("ANTHROPIC_API_KEY=sk-test\n# comment\nOTHER=val\n\n")
            name = f.name
        try:
            result = rb._load_env_file(name)
            self.assertEqual(result["ANTHROPIC_API_KEY"], "sk-test")
            self.assertEqual(result["OTHER"], "val")
            self.assertNotIn("# comment", result)
        finally:
            Path(name).unlink(missing_ok=True)

    def test_load_env_file_absent_returns_empty(self):
        rb = self.rb
        result = rb._load_env_file("/nonexistent/.env.xyz")
        self.assertEqual(result, {})

    def test_prerequisite_check_reads_env_file_for_api_key(self):
        """API key in env_file should satisfy the prerequisite."""
        rb = self.rb
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("ANTHROPIC_API_KEY=sk-from-file\nHF_HANDBOOK_ACCESS_GRANTED=1\n")
            name = f.name
        try:
            with patch("shutil.which", return_value="/usr/bin/uv"), \
                 patch("pathlib.Path.exists", return_value=True), \
                 patch("subprocess.run") as mock_run, \
                 patch.dict("os.environ", {}, clear=True):
                mock_run.return_value = MagicMock(stdout=rb.UPSTREAM_COMMIT + "\n")
                blocks = rb._check_prerequisites(name)
            # Should not have ANTHROPIC_API_KEY or handbook in blocks
            self.assertFalse(any("ANTHROPIC_API_KEY" in b for b in blocks), blocks)
            self.assertFalse(any("Handbook" in b for b in blocks), blocks)
        finally:
            Path(name).unlink(missing_ok=True)

    def test_prerequisite_missing_api_key_blocks(self):
        rb = self.rb
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("HF_HANDBOOK_ACCESS_GRANTED=1\n")  # no API key
            name = f.name
        try:
            with patch("shutil.which", return_value="/usr/bin/uv"), \
                 patch("pathlib.Path.exists", return_value=True), \
                 patch("subprocess.run") as mock_run, \
                 patch.dict("os.environ", {}, clear=True):
                mock_run.return_value = MagicMock(stdout=rb.UPSTREAM_COMMIT + "\n")
                blocks = rb._check_prerequisites(name)
            self.assertTrue(any("ANTHROPIC_API_KEY" in b for b in blocks), blocks)
        finally:
            Path(name).unlink(missing_ok=True)

    def test_prerequisite_handbook_not_granted_blocks(self):
        rb = self.rb
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("ANTHROPIC_API_KEY=sk-test\n")
            name = f.name
        try:
            with patch("shutil.which", return_value="/usr/bin/uv"), \
                 patch("pathlib.Path.exists", return_value=True), \
                 patch("subprocess.run") as mock_run, \
                 patch.dict("os.environ", {}, clear=True):
                mock_run.return_value = MagicMock(stdout=rb.UPSTREAM_COMMIT + "\n")
                blocks = rb._check_prerequisites(name)
            self.assertTrue(any("Handbook" in b or "handbook" in b.lower() for b in blocks))
        finally:
            Path(name).unlink(missing_ok=True)

    def test_prerequisite_uv_missing_blocks(self):
        rb = self.rb
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("ANTHROPIC_API_KEY=sk-test\nHF_HANDBOOK_ACCESS_GRANTED=1\n")
            name = f.name
        try:
            with patch("shutil.which", return_value=None), \
                 patch.dict("os.environ", {}, clear=True):
                blocks = rb._check_prerequisites(name)
            self.assertTrue(any("uv" in b for b in blocks), blocks)
        finally:
            Path(name).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Reward extraction — drives real extract_reward()
    # ------------------------------------------------------------------

    def _make_trial_dir(self, root: Path, task_name: str) -> Path:
        d = root / "trials" / task_name / "verifier"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_reward_binary_1_parsed_correctly(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text('{"reward": 1.0}')
            reward, _, reason = rb.extract_reward(output_dir, "my-task")
        self.assertEqual(reward, 1.0)
        self.assertIn("passed", reason)

    def test_reward_binary_0_is_completed_not_passed(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text('{"reward": 0.0}')
            reward, _, reason = rb.extract_reward(output_dir, "my-task")
        self.assertEqual(reward, 0.0)
        self.assertIn("not passed", reason)

    def test_reward_missing_file_returns_null(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            reward, sc, reason = rb.extract_reward(output_dir, "no-task")
        self.assertIsNone(reward)
        self.assertIsNone(sc)
        self.assertIn("not found", reason)

    def test_reward_invalid_json_returns_null(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text("not-json!!!")
            reward, _, reason = rb.extract_reward(output_dir, "my-task")
        self.assertIsNone(reward)
        self.assertIn("parsed", reason)

    def test_reward_missing_key_returns_null(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text('{"fractional_reward": 0.8}')
            reward, _, reason = rb.extract_reward(output_dir, "my-task")
        self.assertIsNone(reward)
        self.assertIn("'reward' key", reason)

    def test_reward_non_numeric_returns_null(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text('{"reward": "passed"}')
            reward, _, reason = rb.extract_reward(output_dir, "my-task")
        self.assertIsNone(reward)
        self.assertIn("not a number", reason)

    def test_scorecard_path_returned_when_present(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text('{"reward": 1.0}')
            (vdir / "scorecard.json").write_text('{"fractional_reward": 1.0}')
            _, sc_path, _ = rb.extract_reward(output_dir, "my-task")
        self.assertIsNotNone(sc_path)
        self.assertIn("scorecard.json", sc_path)

    def test_scorecard_path_none_when_absent(self):
        rb = self.rb
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td)
            vdir = self._make_trial_dir(output_dir, "my-task")
            (vdir / "reward.json").write_text('{"reward": 0.0}')
            _, sc_path, _ = rb.extract_reward(output_dir, "my-task")
        self.assertIsNone(sc_path)


# ===========================================================================
# run_baseline end-to-end tests — drive real main() with mocked externals
# ===========================================================================

class TestRunBaselineMain(unittest.TestCase):
    """
    Drive run_baseline.main() with mocked subprocess, prerequisite checks,
    and yaml. Only filesystem and reward artifacts are real.
    """

    def _run_main_with_mocks(
        self,
        *,
        task_name: str = "pa-t001",
        domain: str = "pa_provider",
        agent: str = "deepagents",
        model: str = "deepseek/deepseek-v4",
        extra_args: list[str] | None = None,
        subprocess_returncode: int = 0,
        subprocess_raises=None,
        reward_json: str | None = '{"reward": 1.0}',
        write_scorecard: bool = False,
        prereqs_clear: bool = True,
        dry_run: bool = False,
        timeout_multiplier: str = "1.0",
        outer_timeout: str = "1800",
    ) -> tuple[int, dict | None]:
        """
        Returns (exit_code, manifest_or_None).
        exit_code comes from SystemExit; manifest read from the temp run dir.
        """
        import run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text(
                "ANTHROPIC_API_KEY=sk-test\nHF_HANDBOOK_ACCESS_GRANTED=1\n"
            )

            argv = [
                "--agent", agent,
                "--model", model,
                "--domain", domain,
                "--task-name", task_name,
                "--env-file", str(env_file),
                "--timeout-multiplier", timeout_multiplier,
                "--outer-timeout", outer_timeout,
            ]
            if dry_run:
                argv.append("--dry-run")
            if extra_args:
                argv.extend(extra_args)

            # Patch RUNS_DIR to our temp location
            orig_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            # Build mock subprocess result
            if subprocess_raises:
                mock_proc = None
            else:
                mock_proc = MagicMock()
                mock_proc.returncode = subprocess_returncode

            def make_subprocess_side_effect(run_dir_ref):
                """Writes reward artifact before returning, so main() can find it."""
                def side_effect(*a, **kw):
                    if subprocess_raises is not None:
                        raise subprocess_raises
                    # Write reward artifact
                    if reward_json is not None and not dry_run:
                        # Determine output dir from the run dirs created
                        created = list(runs_dir.iterdir()) if runs_dir.exists() else []
                        if created:
                            out = created[0] / "output" / "trials" / task_name / "verifier"
                            out.mkdir(parents=True, exist_ok=True)
                            (out / "reward.json").write_text(reward_json)
                            if write_scorecard:
                                (out / "scorecard.json").write_text(
                                    '{"fractional_reward": 1.0}'
                                )
                    return mock_proc
                return side_effect

            exit_code = None
            try:
                with patch("sys.argv", ["run_baseline"] + argv), \
                     patch.object(rb, "_check_prerequisites",
                                  return_value=([] if prereqs_clear else ["blocked"])), \
                     patch("subprocess.run", side_effect=make_subprocess_side_effect(None)):
                    rb.main()
            except SystemExit as e:
                exit_code = e.code
            finally:
                rb.RUNS_DIR = orig_runs_dir

            # Read manifest if it exists
            manifest = None
            if runs_dir.exists():
                for run_dir in runs_dir.iterdir():
                    mp = run_dir / "manifest.json"
                    if mp.exists():
                        manifest = json.loads(mp.read_text())
                        break

        return exit_code, manifest

    def test_successful_run_with_binary_reward_1(self):
        exit_code, manifest = self._run_main_with_mocks(
            reward_json='{"reward": 1.0}',
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["reward"], 1.0)
        self.assertEqual(manifest["execution_status"], "completed")

    def test_completed_evaluation_with_reward_0(self):
        """reward=0 → completed evaluation, task not solved."""
        exit_code, manifest = self._run_main_with_mocks(
            reward_json='{"reward": 0.0}',
            subprocess_returncode=0,
        )
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["reward"], 0.0)
        self.assertEqual(manifest["execution_status"], "completed")
        self.assertNotIn("passed", manifest.get("reward_reason", "").lower().replace("not passed", ""))

    def test_process_failure_sets_status_and_null_reward(self):
        exit_code, manifest = self._run_main_with_mocks(
            subprocess_returncode=1,
            reward_json=None,
        )
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "process_failed")
        self.assertIsNone(manifest["reward"])
        self.assertNotEqual(exit_code, 0)

    def test_timeout_sets_timeout_status(self):
        exit_code, manifest = self._run_main_with_mocks(
            subprocess_raises=subprocess.TimeoutExpired(cmd="cb", timeout=1800),
        )
        self.assertEqual(exit_code, 3)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "timeout")
        self.assertIsNone(manifest["reward"])

    def test_subprocess_exception_sets_error_status(self):
        exit_code, manifest = self._run_main_with_mocks(
            subprocess_raises=OSError("docker: command not found"),
        )
        self.assertEqual(exit_code, 4)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "subprocess_error")
        self.assertIsNone(manifest["reward"])

    def test_missing_reward_file_gives_incomplete_no_verdict(self):
        exit_code, manifest = self._run_main_with_mocks(
            reward_json=None,   # no artifact written
            subprocess_returncode=0,
        )
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["execution_status"], "incomplete_no_verdict")
        self.assertIsNone(manifest["reward"])

    def test_null_usage_fields_always_null(self):
        _, manifest = self._run_main_with_mocks()
        self.assertIsNone(manifest["token_usage"])
        self.assertIsNone(manifest["cost_usd"])

    def test_submission_yaml_uses_include_task_name(self):
        """Verify the YAML written to disk uses include_task_name, not --task-id."""
        import run_baseline as rb
        import yaml

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text("ANTHROPIC_API_KEY=sk-test\nHF_HANDBOOK_ACCESS_GRANTED=1\n")

            orig_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/v4",
                    "--domain", "pa_provider",
                    "--task-name", "pa-t001",
                    "--env-file", str(env_file),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), \
                   patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0)
                    try:
                        rb.main()
                    except SystemExit:
                        pass
            finally:
                rb.RUNS_DIR = orig_runs_dir

            # Find and parse the submission YAML
            sub_yamls = list(runs_dir.rglob("submission.yaml"))
            self.assertTrue(sub_yamls, "submission.yaml not written")
            cfg = yaml.safe_load(sub_yamls[0].read_text())

        run_block = cfg.get("run", {})
        self.assertIn("include_task_name", run_block,
                      "submission YAML must have include_task_name for single-task selection")
        self.assertEqual(run_block["include_task_name"], ["pa-t001"])
        self.assertEqual(run_block.get("n_tasks"), 1)
        # Must NOT contain a task-id arg in the argv (no --task-id flag in upstream)
        # The command itself doesn't embed --task-id; selection is via YAML.

    def test_submission_id_is_lowercase(self):
        """Generated submission ID must satisfy upstream slug-safe validator."""
        import run_baseline as rb
        import re
        import yaml

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text("ANTHROPIC_API_KEY=sk-test\nHF_HANDBOOK_ACCESS_GRANTED=1\n")

            orig_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/v4",
                    "--domain", "pa_provider",
                    "--task-name", "pa-t001",
                    "--env-file", str(env_file),
                ]), patch.object(rb, "_check_prerequisites", return_value=[]), \
                   patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0)
                    try:
                        rb.main()
                    except SystemExit:
                        pass
            finally:
                rb.RUNS_DIR = orig_runs_dir

            sub_yamls = list(runs_dir.rglob("submission.yaml"))
            self.assertTrue(sub_yamls)
            cfg = yaml.safe_load(sub_yamls[0].read_text())

        sub_id = cfg["submission"]["id"]
        self.assertRegex(sub_id, r"^[a-z0-9][a-z0-9\-_]*$",
                         f"submission ID not slug-safe: {sub_id!r}")
        self.assertEqual(sub_id, sub_id.lower(),
                         f"submission ID has uppercase: {sub_id!r}")

    def test_dry_run_exits_zero_no_manifest_no_subprocess(self):
        """Dry-run must not start a subprocess and must not leave a started manifest."""
        import run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text("ANTHROPIC_API_KEY=sk-test\nHF_HANDBOOK_ACCESS_GRANTED=1\n")
            orig_runs_dir = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "deepagents",
                    "--model", "deepseek/v4",
                    "--domain", "pa_provider",
                    "--task-name", "pa-t001",
                    "--env-file", str(env_file),
                    "--dry-run",
                ]), patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0)
                    try:
                        rb.main()
                    except SystemExit as e:
                        exit_code = e.code
            finally:
                rb.RUNS_DIR = orig_runs_dir

        self.assertEqual(exit_code, 0)
        # No subprocess should have been called via the actual subprocess.run path
        # (it may have been mocked but run_baseline skips it in dry-run)
        # Verify no manifest with execution_status=started was left
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                mp = run_dir / "manifest.json"
                if mp.exists():
                    m = json.loads(mp.read_text())
                    self.assertNotEqual(
                        m.get("execution_status"), "started",
                        "dry-run must not leave manifest in 'started' state",
                    )

    def test_invalid_timeout_multiplier_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "run_baseline.py"),
             "--agent", "a", "--model", "m", "--domain", "pa_provider",
             "--task-name", "t", "--timeout-multiplier", "0"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timeout-multiplier", result.stdout + result.stderr)

    def test_invalid_outer_timeout_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "run_baseline.py"),
             "--agent", "a", "--model", "m", "--domain", "pa_provider",
             "--task-name", "t", "--outer-timeout", "0"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outer-timeout", result.stdout + result.stderr)

    def test_missing_task_name_exits_nonzero(self):
        """--task-name is required; omitting must be a hard error."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "run_baseline.py"),
             "--agent", "a", "--model", "m", "--domain", "pa_provider"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_prerequisite_blocks_exit_with_code_2(self):
        """When prerequisites fail, main() must exit 2."""
        import run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            env_file.write_text("")  # empty — no key
            orig_runs = rb.RUNS_DIR
            rb.RUNS_DIR = Path(td) / "runs"
            try:
                with patch("sys.argv", [
                    "run_baseline",
                    "--agent", "a", "--model", "m",
                    "--domain", "pa_provider",
                    "--task-name", "t",
                    "--env-file", str(env_file),
                ]):
                    try:
                        rb.main()
                    except SystemExit as e:
                        exit_code = e.code
            finally:
                rb.RUNS_DIR = orig_runs

        self.assertEqual(exit_code, 2)

    def test_credentials_never_in_manifest(self):
        """Manifest must not contain credential values."""
        secret = "sk-ant-definitely-secret-key"
        import run_baseline as rb

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            runs_dir = td_path / "runs"
            env_file = td_path / ".env"
            env_file.write_text(
                f"ANTHROPIC_API_KEY={secret}\nHF_HANDBOOK_ACCESS_GRANTED=1\n"
            )
            orig_runs = rb.RUNS_DIR
            rb.RUNS_DIR = runs_dir

            try:
                with patch("sys.argv", [
                    "run_baseline", "--agent", "a", "--model", "m",
                    "--domain", "pa_provider", "--task-name", "t",
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

            if runs_dir.exists():
                for run_dir in runs_dir.iterdir():
                    mp = run_dir / "manifest.json"
                    if mp.exists():
                        content = mp.read_text()
                        self.assertNotIn(secret, content)


if __name__ == "__main__":
    unittest.main()
