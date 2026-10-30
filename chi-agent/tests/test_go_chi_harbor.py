"""Real Harbor controller component checks; no model requests or world runs."""
import tempfile
import unittest
import importlib.util
import hashlib
import json
from unittest.mock import patch
from pathlib import Path

HARBOR_AVAILABLE = importlib.util.find_spec("harbor") is not None
if HARBOR_AVAILABLE:
    from harbor.agents.factory import AgentFactory
    from harbor.agents.installed.base import BaseInstalledAgent
    from harbor.models.agent.context import AgentContext
    from harbor.models.task.config import EnvironmentConfig, MCPServerConfig
    from harbor.models.trial.paths import TrialPaths
    from harbor.models.trajectories.trajectory import Trajectory
    from chi_bench.experiment.docker_env import ChiBenchDockerEnvironment


@unittest.skipUnless(HARBOR_AVAILABLE, "Harbor controller overlay not installed")
class RealHarborTests(unittest.IsolatedAsyncioTestCase):
    def logs_fixture(self, root):
        agent = AgentFactory.create_agent_from_import_path("go_chi_harness:GoChiHarness", root)
        agent._runner_succeeded = True
        agent._instruction_sha256 = hashlib.sha256(b"synthetic instruction").hexdigest()
        logs = root / "chi-run"
        logs.mkdir()
        result = {"input_tokens": 6, "output_tokens": 4, "cached_tokens": None, "cost_usd": None,
                  "turns": 2, "final_output": "done", "model": "deepseek-v4.1-flash", "error": None}
        trace = [{"role": "system", "content": "system"}, {"role": "user", "content": "synthetic instruction"},
                 {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "name": "read", "arguments": {}}]},
                 {"role": "tool", "content": "result", "tool_call_id": "call_1"},
                 {"role": "assistant", "content": "done", "usage": {"input_tokens": 3, "output_tokens": 2}}]
        (logs / "run_result.json").write_text(json.dumps(result))
        (logs / "run_log.txt").write_text(json.dumps({"status": "complete", "safe_error_code": None}))
        (logs / "run_output.txt").write_text("done")
        (logs / "trace.jsonl").write_text("".join(json.dumps(row) + "\n" for row in trace))
        return agent, logs, result, trace

    def test_real_trajectory_uses_settled_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            agent, logs, result, _ = self.logs_fixture(Path(directory))
            context = AgentContext()
            agent.populate_context_post_run(context)
            trajectory = Trajectory.model_validate_json((logs / "trajectory.json").read_text())
            self.assertEqual((context.n_input_tokens, context.n_output_tokens), (6, 4))
            self.assertEqual((trajectory.final_metrics.total_prompt_tokens,
                              trajectory.final_metrics.total_completion_tokens), (6, 4))
            self.assertIsNone(trajectory.final_metrics.total_cached_tokens)
            self.assertIsNone(trajectory.final_metrics.total_cost_usd)
            self.assertEqual(result["input_tokens"], context.n_input_tokens)
            self.assertEqual(result["output_tokens"], context.n_output_tokens)

    def test_rejects_corrupt_or_incomplete_logs(self):
        for case in ("empty-row", "no-assistant", "bad-metrics", "negative", "zero-turns", "cached-bool",
                     "wrong-instruction", "wrong-output", "duplicate-key", "nan", "symlink", "missing"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                agent, logs, result, trace = self.logs_fixture(Path(directory))
                if case == "empty-row": trace[2] = {}
                if case == "no-assistant": trace = trace[:2]
                if case == "wrong-instruction": trace[1]["content"] = "other"
                if case == "wrong-output": trace[-1]["content"] = "other"
                if case in {"empty-row", "no-assistant", "wrong-instruction", "wrong-output"}:
                    (logs / "trace.jsonl").write_text("".join(json.dumps(row) + "\n" for row in trace))
                if case == "bad-metrics":
                    result["input_tokens"] = True
                    (logs / "run_result.json").write_text(json.dumps(result))
                if case in {"negative", "zero-turns", "cached-bool"}:
                    result[{"negative": "output_tokens", "zero-turns": "turns", "cached-bool": "cached_tokens"}[case]] = {
                        "negative": -1, "zero-turns": 0, "cached-bool": True}[case]
                    (logs / "run_result.json").write_text(json.dumps(result))
                if case == "duplicate-key":
                    (logs / "run_result.json").write_text('{"input_tokens": 1, "input_tokens": 2}')
                if case == "nan":
                    (logs / "run_result.json").write_text(json.dumps({**result, "input_tokens": float("nan")}))
                if case == "symlink":
                    (logs / "run_output.txt").unlink()
                    (logs / "run_output.txt").symlink_to(logs / "run_log.txt")
                if case == "missing": (logs / "trace.jsonl").unlink()
                with self.assertRaisesRegex(RuntimeError, "chi_runner_logs_invalid"):
                    agent.populate_context_post_run(AgentContext())

    def test_parent_missing_trajectory_is_rejected(self):
        from chi_bench.experiment.agents.openai_agents_harness import OpenAIAgentsHarness
        with tempfile.TemporaryDirectory() as directory:
            agent, _, _, _ = self.logs_fixture(Path(directory))
            with patch.object(OpenAIAgentsHarness, "populate_context_post_run", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "chi_runner_trajectory_invalid"):
                    agent.populate_context_post_run(AgentContext())

    def test_preexisting_trajectory_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            agent, logs, _, _ = self.logs_fixture(Path(directory))
            (logs / "trajectory.json").symlink_to(logs / "run_result.json")
            with self.assertRaisesRegex(RuntimeError, "chi_runner_trajectory_invalid"):
                agent.populate_context_post_run(AgentContext())

    async def test_factory_and_real_scoped_environment(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            extra = {"OPENCODE_API_KEY": "synthetic", "DEEPSEEK_API_KEY": "synthetic-other",
                     "CHI_GO_BUNDLE_ROOT": "/bundle", "CHI_GO_STATE_ROOT": "/state",
                     "CHI_GO_ROLE": "provider", "CHI_GO_EVALUATION_ID": "e", "CHI_GO_TASK_ID": "t",
                     "CHI_GO_ATTEMPT_ID": "a", "CHI_GO_RUN_ID": "r", "CHI_GO_BUNDLE_SHA256": "a" * 64,
                     "CHI_GO_HISTORY_MODE": "external"}
            agent = AgentFactory.create_agent_from_import_path(
                "go_chi_harness:GoChiHarness", path, extra_env=extra,
                mcp_servers=[MCPServerConfig(name="provider", url="http://world:8020/mcp")])
            self.assertIsInstance(agent, BaseInstalledAgent)
            context = AgentContext()
            env = ChiBenchDockerEnvironment(environment_dir=path, environment_name="synthetic",
                session_id="synthetic", trial_paths=TrialPaths(trial_dir=path / "trial"),
                task_env_config=EnvironmentConfig(), host_env={})
            with env.scoped_exec_env(agent.extra_env):
                self.assertEqual(env._merge_env({"OPENCODE_API_KEY": "synthetic"}),
                                 {"OPENCODE_API_KEY": "synthetic"})
            with env.scoped_exec_env(extra):
                self.assertIn("DEEPSEEK_API_KEY", env._merge_env(None))
                with self.assertRaisesRegex(RuntimeError, "chi_harness_environment_invalid"):
                    await agent.run("Synthetic instruction", env, context)
            self.assertTrue(context.is_empty())
