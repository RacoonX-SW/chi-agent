"""C: formal delivery/off-config consistency with real Harbor components.

No world, Trial, model request or network is started. The environment is a
synthetic object that records the exact commands the real harness would run.
"""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import chi_agent.delivery as delivery
import chi_agent.cli as go_chi_entry
from chi_agent.runtime_policy import RECOVERY_POLICY, SUMMARY_POLICY

HARBOR_AVAILABLE = importlib.util.find_spec("harbor") is not None
if HARBOR_AVAILABLE:
    from harbor.agents.factory import AgentFactory
    from harbor.models.agent.context import AgentContext
    from harbor.models.task.config import MCPServerConfig
    from chi_agent.harbor_adapter import GoChiHarness


class FakeEnvironment:
    """Minimal real-harness environment: records exec, never touches Docker."""

    def __init__(self, *, return_codes=(0, 0), stdout='{"status":"complete","official_reward":null}',
                 host_env=None, merge_env=None):
        self.return_codes = list(return_codes)
        self.stdout = stdout
        self._host_env = {} if host_env is None else host_env
        self._merge = {} if merge_env is None else merge_env
        self.calls = []

    def _merge_env(self, env):
        return dict(self._merge)

    async def exec(self, command, env=None):
        self.calls.append({"command": command, "env": dict(env or {})})
        index = len(self.calls) - 1
        code = self.return_codes[index] if index < len(self.return_codes) else self.return_codes[-1]
        return SimpleNamespace(return_code=code, stdout=self.stdout if code == 0 else "", stderr="")


def env_for(role, url):
    return {
        "OPENCODE_API_KEY": "synthetic",
        "CHI_GO_BUNDLE_ROOT": "/bundle",
        "CHI_GO_STATE_ROOT": "/state",
        "CHI_GO_ROLE": role,
        "CHI_GO_EVALUATION_ID": "e",
        "CHI_GO_TASK_ID": "t",
        "CHI_GO_ATTEMPT_ID": "a",
        "CHI_GO_RUN_ID": "r",
        "CHI_GO_BUNDLE_SHA256": "a" * 64,
        "CHI_GO_HISTORY_MODE": "external",
    }


class StaticDeliveryTests(unittest.TestCase):
    def test_delivery_plan_uses_one_forbidden_credential_set(self):
        self.assertIn("DEEPSEEK_API_KEY", delivery.FORBIDDEN_ENV)
        plan = {
            "schema": "chi-go-delivery-plan-v1", "role": "provider",
            "bundle": {"root": "/bundle", "sha256": "a" * 64},
            "dependencies": {"model_root": "/model", "pdf_root": "/pdf"},
            "vendor": {"root": "/vendor", "commit": "b" * 40},
            "resources": {"instruction": "/instruction.md", "handbook_root": "/handbook",
                          "tool_references": ["/tool.md"]},
            "mcp": {"url": "http://world:8020/mcp", "role": "provider"},
            "state": {"output_root": "/state", "logs_dir": "/logs"},
            "history": {"mode": "external", "q_root": None},
            "credentials": {"model_env": "OPENCODE_API_KEY",
                            "forbidden_env": sorted(delivery.FORBIDDEN_ENV)},
        }
        self.assertEqual(delivery.validate_plan(plan)["credentials"]["forbidden_env"],
                         sorted(delivery.FORBIDDEN_ENV))
        plan["credentials"]["forbidden_env"] = sorted(delivery.FORBIDDEN_ENV - {"DEEPSEEK_API_KEY"})
        with self.assertRaises(delivery.DeliveryError):
            delivery.validate_plan(plan)

    def test_formal_package_excludes_the_development_patient_simulator(self):
        from chi_agent.bundle import PACKAGE_FILES
        self.assertNotIn("scripts/dev_patient_adapter.py", PACKAGE_FILES)
        self.assertNotIn("scripts/dev_patient_broker.py", PACKAGE_FILES)
        self.assertNotIn("scripts/role_operator.py", PACKAGE_FILES)
        self.assertIn("scripts/go_chi_harness.py", PACKAGE_FILES)
        self.assertIn("scripts/chi_agent/delivery.py", PACKAGE_FILES)

    def test_summary_and_recovery_are_mutually_exclusive_and_off_by_default(self):
        parser = go_chi_entry._parser()
        base = ["live", "--bundle-sha256", "a" * 64]
        self.assertIsNone(parser.parse_args(base).input_summary)
        self.assertIsNone(parser.parse_args(base).output_recovery)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = go_chi_entry.main(base + ["--input-summary", "chi-input-summary-v1",
                                             "--output-recovery", "chi-output-recovery-v1"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stream.getvalue())["safe_error_code"],
                         "chi_summary_configuration_invalid")


@unittest.skipUnless(HARBOR_AVAILABLE, "Harbor controller overlay not installed")
class DeliveryConsistencyTests(unittest.IsolatedAsyncioTestCase):
    def agent(self, root, role, url, extra=None):
        values = env_for(role, url)
        if extra is not None:
            values.update(extra)
        agent = AgentFactory.create_agent_from_import_path(
            "chi_agent.harbor_adapter:GoChiHarness", root, extra_env=values,
            mcp_servers=[MCPServerConfig(name=role, url=url)])
        agent.logs_dir = root / "logs"
        agent.logs_dir.mkdir(parents=True, exist_ok=True)
        return agent

    def test_harness_uses_the_same_forbidden_credential_set(self):
        from chi_agent.harbor_adapter import FORBIDDEN_ENV
        self.assertIs(FORBIDDEN_ENV, delivery.FORBIDDEN_ENV)

    async def test_three_roles_assemble_the_real_entry_with_defaults_off(self):
        for role, port in (("provider", 8020), ("payer", 8100), ("cm", 8200)):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                url = f"http://world:{port}/mcp"
                agent = self.agent(root, role, url)
                environment = FakeEnvironment()
                await agent.run("Synthetic instruction", environment, AgentContext())
                self.assertEqual(len(environment.calls), 2)
                preflight, live = environment.calls
                self.assertIn("go_chi_entry.py preflight --bundle-sha256", preflight["command"])
                self.assertIn("go_chi_entry.py live", live["command"])
                self.assertIn("--role " + role, live["command"])
                self.assertIn("--output-root /state", live["command"])
                self.assertIn("--history-mode external", live["command"])
                self.assertNotIn("--input-summary", live["command"])
                self.assertNotIn("--output-recovery", live["command"])
                self.assertNotIn("CHI_DEV_", live["command"])
                self.assertNotIn("dev_patient", live["command"])
                self.assertEqual(live["env"], {"OPENCODE_API_KEY": "synthetic"})
                self.assertNotIn("synthetic", live["command"])
                self.assertTrue(agent._runner_succeeded)
                self.assertEqual(GoChiHarness.CLI_FLAGS, [])
                self.assertFalse(RECOVERY_POLICY["default_enabled"])
                self.assertFalse(SUMMARY_POLICY["default_enabled"])

    async def test_missing_supply_stops_at_the_named_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [
                ("role", {"CHI_GO_ROLE": "admin"}, "chi_harness_role_invalid"),
                ("port", {"CHI_GO_ROLE": "payer"}, "chi_harness_mcp_invalid"),
                ("bundle", {"CHI_GO_BUNDLE_SHA256": "not-a-sha"}, "chi_harness_identity_invalid"),
            ]
            for name, extra, code in cases:
                with self.subTest(case=name):
                    role = extra.get("CHI_GO_ROLE", "provider")
                    url = "http://world:8020/mcp"
                    agent = self.agent(root, role, url, extra)
                    with self.assertRaisesRegex(RuntimeError, code):
                        await agent.run("Synthetic instruction", FakeEnvironment(), AgentContext())
                    self.assertFalse(agent._runner_succeeded)

            agent = self.agent(root, "provider", "http://world:8020/mcp",
                               {"CHI_GO_BUNDLE_SHA256": "a" * 64})
            environment = FakeEnvironment(host_env={"DEEPSEEK_API_KEY": "host-only"})
            with self.assertRaisesRegex(RuntimeError, "chi_harness_environment_invalid"):
                await agent.run("Synthetic instruction", environment, AgentContext())
            self.assertEqual(environment.calls, [])

            agent = self.agent(root, "provider", "http://world:8020/mcp")
            environment = FakeEnvironment(merge_env={"DEEPSEEK_API_KEY": "x"})
            with self.assertRaisesRegex(RuntimeError, "chi_harness_environment_invalid"):
                await agent.run("Synthetic instruction", environment, AgentContext())
            self.assertEqual(environment.calls, [])

    async def test_missing_key_and_preflight_failure_never_start_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = env_for("provider", "http://world:8020/mcp")
            values.pop("OPENCODE_API_KEY")
            agent = AgentFactory.create_agent_from_import_path(
                "chi_agent.harbor_adapter:GoChiHarness", root, extra_env=values,
                mcp_servers=[MCPServerConfig(name="provider", url="http://world:8020/mcp")])
            agent.logs_dir = root / "logs"
            agent.logs_dir.mkdir()
            environment = FakeEnvironment()
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "chi_harness_key_missing"):
                    await agent.run("Synthetic instruction", environment, AgentContext())
            self.assertEqual(len(environment.calls), 1)
            self.assertIn("preflight", environment.calls[0]["command"])

            agent = self.agent(root, "provider", "http://world:8020/mcp")
            environment = FakeEnvironment(return_codes=(1, 0))
            with self.assertRaisesRegex(RuntimeError, "chi_harness_preflight_failed"):
                await agent.run("Synthetic instruction", environment, AgentContext())
            self.assertEqual(len(environment.calls), 1)

if __name__ == "__main__":
    unittest.main()
