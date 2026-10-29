import importlib.util
import sys
import types
import unittest
from pathlib import Path


class FakeHarness:
    async def exec_as_agent(self, environment, *, command, env):
        self.record = (command, env, dict(self._extra_env))
        return types.SimpleNamespace(return_code=self.exit_code)
    def populate_context_post_run(self, context):
        context.append(self.logs_dir)


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
        harness.logs_dir = Path("/tmp/logs")
        harness._extra_env = {"OPENCODE_API_KEY": "synthetic-key", "DEEPSEEK_API_KEY": "not-forwarded",
            "CHI_GO_BUNDLE_ROOT": "/opt/chi-go", "CHI_GO_STATE_ROOT": "/state", "CHI_GO_ROLE": "provider",
            "CHI_GO_EVALUATION_ID": "eval", "CHI_GO_TASK_ID": "task", "CHI_GO_ATTEMPT_ID": "attempt",
            "CHI_GO_RUN_ID": "run", "CHI_GO_BUNDLE_SHA256": "a" * 64, "CHI_GO_HISTORY_MODE": "external"}
        return harness

    async def test_command_environment_and_logs(self):
        harness = self.create(0)
        await harness.run("synthetic 'instruction'", None, None)
        command, env, extra = harness.record
        self.assertIn("/opt/chi-go/scripts/go_chi_entry.py live", command)
        self.assertIn("--mcp-url http://world:8020/mcp", command)
        self.assertIn("--role provider", command)
        self.assertEqual(env, {"OPENCODE_API_KEY": "synthetic-key"})
        self.assertEqual(extra, {})
        self.assertNotIn("not-forwarded", command)
        self.assertEqual(harness._extra_env["DEEPSEEK_API_KEY"], "not-forwarded")
        paths = []
        harness.populate_context_post_run(paths)
        self.assertEqual(paths, [Path("/tmp/logs/chi-run")])
        self.assertEqual(harness.logs_dir, Path("/tmp/logs"))

    async def test_failure_propagates_and_restores_extras(self):
        harness = self.create(2)
        with self.assertRaisesRegex(RuntimeError, "chi_runner_failed"):
            await harness.run("instruction", None, None)
        self.assertEqual(harness._extra_env["DEEPSEEK_API_KEY"], "not-forwarded")
