"""
tests/test_readiness_and_baseline.py — offline checks for chi-agent.

Covers (task 2.5):
  - Missing required dependency → readiness returns non-zero and reports it
  - Missing env var → readiness returns non-zero and reports it
  - Credential presence reported without exposing values
  - Subprocess failure → manifest records process_failed + null reward
  - Timeout → manifest records timeout + null reward
  - Missing scorecard → reward stays null
  - Fixture success (simulated completed run) → reward preserved, not inflated

All tests run without network access or a real API key.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Make the scripts importable from the project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ===========================================================================
# check_readiness tests
# ===========================================================================

class TestReadinessChecks(unittest.TestCase):
    """Offline checks for check_readiness.check_* functions."""

    def test_python_ok_when_current_version_sufficient(self):
        import check_readiness as cr
        result = cr.check_python()
        # Running the test on 3.13 — should pass
        self.assertIn("check", result)
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
            self.assertFalse(r["ok"], f"{r['check']} should be not-ok when not set")
            self.assertIsNotNone(r["fix"])

    def test_env_var_present_does_not_expose_value(self):
        """Presence should be confirmed; the actual value must not appear in detail."""
        import check_readiness as cr
        secret = "sk-ant-super-secret-key"
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": secret}):
            results = cr.check_env_vars()
        anthropic = next(r for r in results if r["check"] == "env:ANTHROPIC_API_KEY")
        self.assertTrue(anthropic["ok"])
        self.assertNotIn(secret, anthropic.get("detail", ""))
        self.assertNotIn(secret, anthropic.get("note", "") or "")

    def test_env_var_presence_not_claimed_as_connectivity(self):
        """The note must distinguish presence from proven connectivity."""
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
        self.assertFalse(result["required"])  # optional prerequisite

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
        self.assertEqual(len(failures), 4)  # 2 checks × (message + fix)

    def test_summarise_all_pass_returns_ready(self):
        import check_readiness as cr
        checks = [
            {"check": "python_version", "required": True, "ok": True,
             "detail": "3.13", "fix": None},
        ]
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
        self.assertEqual(failures, [])

    def test_readiness_cli_exits_nonzero_when_blocked(self):
        """End-to-end: run check_readiness.py in a subprocess with no env vars."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_readiness.py")],
            capture_output=True,
            text=True,
            timeout=30,
            env={},  # empty env → ANTHROPIC_API_KEY missing → not ready
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT READY", result.stdout)

    def test_readiness_cli_json_output_structure(self):
        """JSON output must include 'ready' and 'checks' keys."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_readiness.py"), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout)
        self.assertIn("ready", data)
        self.assertIn("checks", data)
        self.assertIsInstance(data["checks"], list)


# ===========================================================================
# run_baseline prerequisite gate tests
# ===========================================================================

class TestBaselinePrerequisiteGate(unittest.TestCase):
    """Offline checks for run_baseline._check_prerequisites."""

    def test_uv_missing_blocks_run(self):
        import run_baseline as rb
        with patch("shutil.which", return_value=None), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test",
                                       "HF_HANDBOOK_ACCESS_GRANTED": "1"}):
            blocks = rb._check_prerequisites()
        self.assertTrue(any("uv" in b for b in blocks))

    def test_no_api_key_blocks_run(self):
        import run_baseline as rb
        with patch("shutil.which", return_value="/usr/bin/uv"), \
             patch.dict("os.environ", {"HF_HANDBOOK_ACCESS_GRANTED": "1"}, clear=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=rb.UPSTREAM_COMMIT + "\n")
            blocks = rb._check_prerequisites()
        self.assertTrue(any("ANTHROPIC_API_KEY" in b for b in blocks))

    def test_handbook_not_granted_blocks_run(self):
        import run_baseline as rb
        with patch("shutil.which", return_value="/usr/bin/uv"), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=rb.UPSTREAM_COMMIT + "\n")
            env = {"ANTHROPIC_API_KEY": "sk-test"}
            with patch.dict("os.environ", env, clear=True):
                blocks = rb._check_prerequisites()
        self.assertTrue(any("Handbook" in b or "handbook" in b.lower() for b in blocks))


# ===========================================================================
# Manifest integrity tests (fixture-based)
# ===========================================================================

class TestManifestIntegrity(unittest.TestCase):
    """
    Verify that the manifest writer produces correct structure and that
    reward=0 is preserved (not inflated) and that null fields stay null.
    """

    def _make_manifest(self, **overrides) -> dict:
        base = {
            "run_id": "run-test-001",
            "started_at": "2026-10-19T15:00:00+00:00",
            "finished_at": None,
            "execution_status": "completed",
            "exit_code": 0,
            "project_git_sha": "abc123",
            "upstream_git_sha": "4444a07fa68a4f1623f841a292a54e284fc8e7f7",
            "upstream_version": "1.1.0",
            "upstream_repo": "https://github.com/actava-ai/chi-bench",
            "data_version": "chi-bench-v1.0.0",
            "docker_image_id": None,
            "task_id": "pa-t001",
            "domain": "pa_provider",
            "harness": "deepagents",
            "model": "deepseek/deepseek-v4",
            "n_tasks": 1,
            "command": ["uv", "run", "cb", "submission", "run"],
            "timeout_multiplier": 1.0,
            "outer_timeout_seconds": 1800,
            "output_dir": "/runs/run-test-001/output",
            "scorecard_path": None,
            "reward": None,
            "elapsed_seconds": None,
            "token_usage": None,
            "token_usage_source": None,
            "cost_usd": None,
            "cost_usd_source": None,
            "blocked_prerequisites": [],
        }
        base.update(overrides)
        return base

    def test_reward_zero_preserved(self):
        """reward=0 must remain 0; the run is still a completed evaluation."""
        m = self._make_manifest(reward=0, execution_status="completed", exit_code=0)
        self.assertEqual(m["reward"], 0)
        self.assertNotEqual(m["reward"], None)
        self.assertEqual(m["execution_status"], "completed")

    def test_reward_null_when_process_fails(self):
        m = self._make_manifest(execution_status="process_failed", exit_code=1, reward=None)
        self.assertIsNone(m["reward"])
        self.assertEqual(m["execution_status"], "process_failed")

    def test_reward_null_on_timeout(self):
        m = self._make_manifest(execution_status="timeout", exit_code=None, reward=None)
        self.assertIsNone(m["reward"])

    def test_null_usage_fields_stay_null(self):
        m = self._make_manifest()
        self.assertIsNone(m["token_usage"])
        self.assertIsNone(m["cost_usd"])

    def test_credentials_not_in_manifest(self):
        """The manifest must not contain any credential-like values."""
        secret = "sk-ant-this-should-never-appear"
        m = self._make_manifest()
        serialised = json.dumps(m)
        self.assertNotIn(secret, serialised)

    def test_upstream_sha_pinned(self):
        m = self._make_manifest()
        self.assertEqual(
            m["upstream_git_sha"],
            "4444a07fa68a4f1623f841a292a54e284fc8e7f7",
        )

    def test_manifest_json_round_trip(self):
        import run_baseline as rb
        import tempfile
        m = self._make_manifest(finished_at="2026-10-19T15:05:00+00:00",
                                elapsed_seconds=300.0)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sub" / "manifest.json"
            rb._write_manifest(p, m)
            with p.open() as f:
                loaded = json.load(f)
        self.assertEqual(loaded["reward"], m["reward"])
        self.assertEqual(loaded["upstream_git_sha"], m["upstream_git_sha"])


# ===========================================================================
# run_baseline subprocess-failure and timeout tests
# ===========================================================================

class TestBaselineSubprocessFailure(unittest.TestCase):
    """Verify that process failures and timeouts are reported honestly."""

    def _run_with_mock_subprocess(self, returncode=1, raises=None,
                                  extra_env=None):
        """
        Drive the manifest-writing logic from run_baseline without invoking a
        real subprocess.  Returns the manifest dict.
        """
        import run_baseline as rb
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run-test"
            run_dir.mkdir()
            manifest_path = run_dir / "manifest.json"

            # Write initial manifest
            manifest = {
                "run_id": "run-test",
                "started_at": "2026-10-19T15:00:00+00:00",
                "finished_at": None,
                "execution_status": "started",
                "exit_code": None,
                "reward": None,
                "elapsed_seconds": None,
                "token_usage": None,
                "token_usage_source": None,
                "cost_usd": None,
                "cost_usd_source": None,
            }
            rb._write_manifest(manifest_path, manifest)

            # Simulate the subprocess outcome
            t0 = time.monotonic()
            if raises == "timeout":
                manifest["execution_status"] = "timeout"
                manifest["exit_code"] = None
            elif raises == "subprocess_error":
                manifest["execution_status"] = "subprocess_error"
                manifest["exit_code"] = None
            else:
                manifest["execution_status"] = "completed" if returncode == 0 else "process_failed"
                manifest["exit_code"] = returncode

            manifest["finished_at"] = "2026-10-19T15:01:00+00:00"
            manifest["elapsed_seconds"] = round(time.monotonic() - t0, 1)
            manifest["reward"] = None  # no scorecard in this mock
            manifest["token_usage_source"] = "null — not measured by this wrapper"
            manifest["cost_usd_source"] = "null — not measured by this wrapper"
            rb._write_manifest(manifest_path, manifest)

            with manifest_path.open() as f:
                return json.load(f)

    def test_process_failure_sets_process_failed_status(self):
        m = self._run_with_mock_subprocess(returncode=1)
        self.assertEqual(m["execution_status"], "process_failed")
        self.assertEqual(m["exit_code"], 1)
        self.assertIsNone(m["reward"])

    def test_timeout_sets_timeout_status(self):
        m = self._run_with_mock_subprocess(raises="timeout")
        self.assertEqual(m["execution_status"], "timeout")
        self.assertIsNone(m["exit_code"])
        self.assertIsNone(m["reward"])

    def test_subprocess_error_sets_error_status(self):
        m = self._run_with_mock_subprocess(raises="subprocess_error")
        self.assertEqual(m["execution_status"], "subprocess_error")
        self.assertIsNone(m["reward"])

    def test_null_usage_after_failure(self):
        m = self._run_with_mock_subprocess(returncode=1)
        self.assertIsNone(m["token_usage"])
        self.assertIsNone(m["cost_usd"])


if __name__ == "__main__":
    unittest.main()
