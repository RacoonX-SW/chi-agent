import importlib.util
import asyncio
import sys
import types
import unittest
import tempfile
import json
from pathlib import Path


class FakeHarness:
    def populate_context_post_run(self, context):
        context.append(self.logs_dir)


class FakeEnvironment:
    def __init__(self, harness):
        self.harness = harness

    def _merge_env(self, env):
        return None

    async def exec(self, *, command, env):
        if " preflight " in command:
            self.harness.preflight_env = env
            return types.SimpleNamespace(return_code=0)
        self.harness.record = (command, env, dict(self.harness._extra_env))
        return types.SimpleNamespace(return_code=self.harness.exit_code)


def adapter_class():
    name = "chi_bench.experiment.agents.openai_agents_harness"
    old = sys.modules.get(name)
    stub = types.ModuleType(name)
    stub.OpenAIAgentsHarness = FakeHarness
    sys.modules[name] = stub
    try:
        path = Path(__file__).parents[1] / "scripts" / "go_chi_harness.py"
        spec = importlib.util.spec_from_file_location("go_chi_harness_stub_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.GoChiHarness
    finally:
        if old is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old


class HarnessTests(unittest.IsolatedAsyncioTestCase):
    def create(self, exit_code):
        harness = adapter_class()()
        harness.exit_code = exit_code
        harness.mcp_servers = [types.SimpleNamespace(url="http://world:8020/mcp")]
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        harness.logs_dir = Path(directory.name)
        harness._extra_env = {"OPENCODE_API_KEY": "synthetic-key", "DEEPSEEK_API_KEY": "not-forwarded",
            "CHI_GO_BUNDLE_ROOT": "/opt/chi-go", "CHI_GO_STATE_ROOT": "/state", "CHI_GO_ROLE": "provider",
            "CHI_GO_EVALUATION_ID": "eval", "CHI_GO_TASK_ID": "task", "CHI_GO_ATTEMPT_ID": "attempt",
            "CHI_GO_RUN_ID": "run", "CHI_GO_BUNDLE_SHA256": "a" * 64, "CHI_GO_HISTORY_MODE": "external"}
        return harness

    async def test_command_environment_and_logs(self):
        harness = self.create(0)
        await harness.run("synthetic 'instruction'", FakeEnvironment(harness), None)
        command, env, extra = harness.record
        self.assertIn("/opt/chi-go/scripts/go_chi_entry.py live", command)
        self.assertIn("--mcp-url http://world:8020/mcp", command)
        self.assertIn("--role provider", command)
        self.assertEqual(env, {"OPENCODE_API_KEY": "synthetic-key"})
        self.assertEqual(extra, {})
        self.assertNotIn("not-forwarded", command)
        self.assertEqual(harness._extra_env["DEEPSEEK_API_KEY"], "not-forwarded")
        self.assertEqual(harness.extra_env, {})
        self.assertEqual(harness.preflight_env, {})
        with tempfile.TemporaryDirectory() as root:
            harness.logs_dir = Path(root)
            logs = harness.logs_dir / "chi-run"
            logs.mkdir()
            with self.assertRaisesRegex(RuntimeError, "chi_runner_logs_invalid"):
                harness.populate_context_post_run([])
            self.assertEqual(harness.logs_dir, Path(root))

    async def test_failure_propagates_and_restores_extras(self):
        harness = self.create(2)
        with self.assertRaisesRegex(RuntimeError, "chi_runner_failed"):
            await harness.run("instruction", FakeEnvironment(harness), None)
        self.assertEqual(harness._extra_env["DEEPSEEK_API_KEY"], "not-forwarded")

    async def test_invalid_role_endpoint_fails_before_exec(self):
        harness = self.create(0)
        harness._extra_env["CHI_GO_ROLE"] = "payer"
        with self.assertRaisesRegex(RuntimeError, "chi_harness_mcp_invalid"):
            await harness.run("instruction", FakeEnvironment(harness), None)
        self.assertFalse(hasattr(harness, "record"))

    async def test_missing_return_code_and_safe_summary(self):
        harness = self.create(None)
        with self.assertRaisesRegex(RuntimeError, "chi_runner_failed"):
            await harness.run("instruction", FakeEnvironment(harness), None)
        summary = json.loads((harness.logs_dir / "chi-exec-summary.json").read_text())
        self.assertIsNone(summary["return_code"])
        self.assertEqual(summary["status"], "failed")

    async def test_safe_code_never_copies_the_secret(self):
        harness = self.create(1)
        harness._extra_env["OPENCODE_API_KEY"] = "chi_secret"
        class Environment(FakeEnvironment):
            async def exec(self, *, command, env):
                if " preflight " in command:
                    return types.SimpleNamespace(return_code=0)
                return types.SimpleNamespace(return_code=1, stderr="chi_secret", stdout=json.dumps({
                    "status": "blocked", "safe_error_code": "chi_secret"}))
        with self.assertRaisesRegex(RuntimeError, "chi_runner_failed"):
            await harness.run("instruction", Environment(harness), None)
        summary = (harness.logs_dir / "chi-exec-summary.json").read_text()
        self.assertNotIn("chi_secret", summary)
        self.assertNotIn("safe_error_code", json.loads(summary))

    async def test_cancellation_and_timeout_restore_environment(self):
        for error in (asyncio.CancelledError(), TimeoutError()):
            harness = self.create(0)
            class Environment(FakeEnvironment):
                async def exec(self, *, command, env):
                    if " preflight " in command:
                        return types.SimpleNamespace(return_code=0)
                    raise error
            with self.assertRaises(type(error)):
                await harness.run("instruction", Environment(harness), None)
            self.assertEqual(harness._extra_env["DEEPSEEK_API_KEY"], "not-forwarded")
            summary = json.loads((harness.logs_dir / "chi-exec-summary.json").read_text())
            self.assertEqual(summary["status"], "exec_exception")
