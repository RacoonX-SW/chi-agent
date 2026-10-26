"""Offline-only regression for the isolated real-development adapters."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import httpx

import live_development as live

# The isolated runner's container sets this explicitly. The fake container
# executes in-process, so mirror that one import path for the end-to-end mock.
sys.path.insert(0, str(live.ROOT / "vendor" / "chi-bench" / "src"))


def _completion(*, calls=None, text=None, input_tokens=7, output_tokens=3):
    message = {"role": "assistant", "content": text, "reasoning_content": "mock reasoning"}
    if calls is not None:
        message["tool_calls"] = calls
    usage = {"prompt_tokens": input_tokens, "completion_tokens": output_tokens,
             "total_tokens": input_tokens + output_tokens}
    return {"model": "deepseek-flash", "choices": [{"index": 0, "message": message,
             "finish_reason": "tool_calls" if calls is not None else "stop"}], "usage": usage}


def _call(call_id, name, args):
    return {"id": call_id, "type": "function", "function": {"name": name,
            "arguments": json.dumps(args, separators=(",", ":"))}}


class FakeWire:
    def __init__(self, kind: str):
        self.kind = kind
        self.requests = []
        if kind == "b-smoke":
            self.responses = [
                _completion(calls=[_call("call_lookup", "smoke_lookup", {"query": "CHI-Bench"})]),
                _completion(calls=[_call("call_transform", "smoke_transform", {"value": "lookup-result:CHI-Bench"})]),
                _completion(text="The lookup and dependent transformation both completed."),
            ]
        else:
            self.responses = [
                _completion(calls=[
                    _call("call_case", "cases__lookup_case", {"case_id": "case-17"}),
                    _call("call_docs", "cases__list_case_documents", {"case_id": "case-17"}),
                ]),
                _completion(text="I reviewed the available case materials and completed the requested work."),
            ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if not self.responses:
            raise AssertionError("unexpected additional provider request")
        return httpx.Response(200, json=self.responses.pop(0), request=request)


class FakeMCP:
    name = "mock-official-task-mcp"
    use_structured_content = False

    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def _get_failure_error_function(self, function):
        return function

    def _get_needs_approval_for_tool(self, _tool, _agent):
        return False

    async def list_tools(self, *_args, **_kwargs):
        from mcp.types import Tool
        schema = lambda: {"type": "object", "properties": {"case_id": {"type": "string"}},
                          "required": ["case_id"], "additionalProperties": False}
        return [Tool(name="cases.lookup_case", description="Lookup case", inputSchema=schema()),
                Tool(name="cases.list_case_documents", description="List documents", inputSchema=schema())]

    async def call_tool(self, name, arguments, **_kwargs):
        from mcp.types import CallToolResult, TextContent
        self.calls.append({"name": name, "arguments": arguments})
        return CallToolResult(content=[TextContent(type="text", text=f"mock result for {name}")])


class FakeImage:
    def __init__(self, image_id):
        self.id = image_id


class FakeNetwork:
    def __init__(self, name):
        self.name = name
        self.id = f"net-{name}"

    def connect(self, _container):
        return None


class FakeContainer:
    def __init__(self, name, command, environment, volumes, options, *, test_root, mode):
        self.name = name
        self.id = f"container-{name}"
        self.command = command
        self.environment = environment
        self.volumes = volumes
        self.options = options
        self.test_root = test_root
        self.mode = mode
        self.exit_code = 0
        self.started = False
        self.error = None

    def start(self):
        self.started = True
        if self.mode == "runner":
            args = self.command
            kind = args[args.index("--kind") + 1]
            run_id = args[args.index("--run-id") + 1]
            output_root = self.test_root
            run_dir = output_root / run_id
            if kind == "c-once":
                projection_source = next(Path(source) for source, options in self.volumes.items()
                                         if options.get("bind") == "/participant/projection")
                instruction = projection_source / "instruction.md"
            else:
                instruction = run_dir / "b-smoke-instruction.md"
            worker_args = Namespace(kind=kind, run_id=run_id, budget_root=output_root,
                                    logs_dir=run_dir / "runner-logs", instruction_file=instruction,
                                    mcp_url=args[args.index("--mcp-url") + 1])
            try:
                with patch.dict(os.environ, self.environment):
                    self.exit_code = asyncio.run(live._worker_run(worker_args))
            except BaseException as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                self.exit_code = 1

    def wait(self, timeout=None):
        return {"StatusCode": self.exit_code}

    def remove(self, force=False):
        return None

    def logs(self, **_kwargs):
        return b"mock world logs\n"


class FakeCollection:
    def __init__(self, test_root):
        self.test_root = test_root
        self.created = []

    def get(self, name):
        if name.startswith("chi-agent-real-runner-"):
            exc = RuntimeError("not found")
            exc.status_code = 404
            raise exc
        fixed_ids = {
            "chi-agent-a-control:latest": "sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3",
            "chi-agent-dev:latest": "sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3",
            "chi-agent-a-world:py312-review-20261025-01": "sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50",
        }
        return FakeImage(fixed_ids.get(name, f"image-{name}"))

    def create(self, *args, **kwargs):
        name = kwargs.get("name", "mock-network")
        obj = FakeContainer(name, kwargs.get("command", []), kwargs.get("environment", {}),
                            kwargs.get("volumes", {}), kwargs, test_root=self.test_root,
                            mode="runner" if name.startswith("chi-agent-real-runner-") else "world")
        self.created.append(obj)
        return obj


class FakeDocker:
    def __init__(self, test_root):
        self.test_root = test_root
        self.images = FakeCollection(test_root)
        self.volumes = FakeCollection(test_root)
        self.containers = FakeCollection(test_root)
        self.networks = self

    def create(self, name, **_kwargs):
        return FakeNetwork(name)

    def close(self):
        return None


class LiveDevelopmentTests(unittest.TestCase):
    def test_missing_mock_credentials_and_unsupported_response_stop_without_reading_host_env(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(live, "ROOT", Path(temp)), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(live.LiveFailure) as missing:
                    live._model_key()
                self.assertEqual(missing.exception.code, "provider_credential_missing")
        profile = live.load_profile()
        with self.assertRaises(live.LiveFailure) as unsupported:
            live._validate_live_response({"model": "other-model"}, None, profile, {}, set(), None, {})
        self.assertEqual(unsupported.exception.code, "response_model_mismatch")

    def test_unknown_real_usage_blocks_restart_and_one_c_claim_cannot_replay(self):
        from b_execution_policy import load_local_policy
        from b_provider_profile import load_profile

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile, policy = load_profile(), load_local_policy()
            live.initialize_real_accounting(root, prior_source="mock-test-reviewed-zero")
            journal = live.RealDevelopmentJournal(root, "mock-unknown", profile=profile, policy=policy)
            body = {"model": profile.model}
            request = httpx.Request("POST", profile.endpoint + "/v1/chat/completions", content=b"mock")
            journal.reserve(profile, request, body, b"mock", 1024, 1)
            journal.mark_unknown("transport_timeout")
            journal.close()
            self.assertEqual(live._budget_preflight(root)["status"], "unknown")
            with self.assertRaises(live.LiveFailure) as blocked:
                live.RealDevelopmentJournal(root, "mock-restart", profile=profile, policy=policy)
            self.assertEqual(blocked.exception.code, "real_accounting_pending_unknown")

            claim_root = Path(temp) / "claim-campaign"
            claim = live._claim_c_once(claim_root, "first-c-attempt", {
                "execution_identity": {"mock": True}, "profile_sha256": profile.sha256,
            })
            with self.assertRaises(live.LiveFailure) as replay:
                live._claim_c_once(claim_root, "second-c-attempt", {
                    "execution_identity": {"mock": True}, "profile_sha256": profile.sha256,
                })
            self.assertEqual(replay.exception.code, "real_c_attempt_already_claimed")
            self.assertEqual(json.loads(claim.read_text())["run_id"], "first-c-attempt")

    def test_real_only_text_block_tool_history_is_strict_and_legacy_default_stays_closed(self):
        from types import SimpleNamespace
        from b_provider_profile import load_profile
        from b_provider_transport import GuardedTransport, GuardFailure

        body = {
            "model": "deepseek-flash", "max_tokens": 128, "reasoning_effort": "high",
            "thinking": {"type": "enabled"}, "tool_choice": "auto",
            "tools": [{"type": "function", "function": {"name": "cases__lookup_case"}}],
            "messages": [
                {"role": "system", "content": "system"}, {"role": "user", "content": "user"},
                {"role": "assistant", "content": None, "reasoning_content": "reasoning",
                 "tool_calls": [{"id": "call_1", "type": "function",
                                 "function": {"name": "cases__lookup_case", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_1",
                 "content": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]},
            ],
        }

        def guard_for(enabled):
            guard = object.__new__(GuardedTransport)
            guard.profile = load_profile()
            guard.ledger = SimpleNamespace(error_code=None, rounds=0)
            guard.max_rounds = 30
            guard.allowed_tool_names = {"cases__lookup_case"}
            guard.allow_text_blocks_in_tool_history = enabled
            return guard

        request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions",
                                content=json.dumps(body).encode())
        self.assertEqual(guard_for(True)._validate_request(request, request.content), body)
        with self.assertRaises(GuardFailure):
            guard_for(False)._validate_request(request, request.content)
        for invalid in (
            [{"type": "text", "text": "ok"}, {"type": "image_url", "image_url": "bad"}],
            [{"type": "text", "text": "ok", "extra": "reject"}],
            [{"type": "text", "text": 7}],
            [],
        ):
            malformed = json.loads(json.dumps(body))
            malformed["messages"][-1]["content"] = invalid
            bad_request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions",
                                        content=json.dumps(malformed).encode())
            with self.subTest(invalid=invalid), self.assertRaises(GuardFailure):
                guard_for(True)._validate_request(bad_request, bad_request.content)

    def test_real_runner_paths_use_only_mock_http_and_complete_b_then_c(self):
        evidence_root = live.ROOT / "runs" / "real-b-c" / "impl"
        evidence_root.mkdir(parents=True, exist_ok=True)
        test_root = Path(tempfile.mkdtemp(prefix="mock-e2e-", dir=evidence_root))
        (test_root / "runs" / "a-environment").mkdir(parents=True)
        (test_root / "projection-output").mkdir()
        run_b, run_c = "mock-b-smoke", "mock-c-once"
        identity = live._execution_identity()
        live.initialize_real_accounting(test_root, prior_source="mock-only-test-prior-zero",
                                        execution_identity=identity)
        wire_by_kind = {"b-smoke": FakeWire("b-smoke"), "c-once": FakeWire("c-once")}
        transport_factories = []
        mcp_calls = []
        current_kind = {"value": "b-smoke"}
        request_debug = []

        def fake_transport_factory(**_kwargs):
            transport_factories.append(current_kind["value"])
            return httpx.MockTransport(wire_by_kind[current_kind["value"]])

        fake_docker = FakeDocker(test_root)
        fake_mcp_factory = lambda *args, **kwargs: FakeMCP(mcp_calls)

        from b_provider_transport import GuardedTransport
        original_validate_request = GuardedTransport._validate_request

        def capture_guard_shape(transport, request, raw):
            try:
                return original_validate_request(transport, request, raw)
            except Exception:
                try:
                    body = json.loads(raw)
                    request_debug.append([
                        {"role": item.get("role"), "name": item.get("name"),
                         "tool_call_id": item.get("tool_call_id"),
                         "content_type": type(item.get("content")).__name__,
                         "content_shape": ([type(part).__name__ for part in item.get("content", [])]
                                           if isinstance(item.get("content"), list) else None),
                         "calls": [{"id": call.get("id"),
                                    "name": call.get("function", {}).get("name")}
                                   for call in item.get("tool_calls", [])]}
                        for item in body.get("messages", []) if isinstance(item, dict)
                    ])
                except Exception:
                    request_debug.append(["shape_unavailable"])
                raise
        monkeypatches = [
            patch.object(live, "_model_key", return_value="mock-secret-never-real"),
            patch("httpx.AsyncHTTPTransport", side_effect=fake_transport_factory),
            patch("a_environment._docker", return_value=fake_docker),
            patch("a_environment._daemon_path", side_effect=lambda _root, path: str(path)),
            patch("a_environment._check_resource_slots", return_value=None),
            patch("a_environment.wait_world", return_value=0.0),
            patch("a_environment.cleanup", return_value={"container_removed": True, "network_removed": True}),
            patch("a_environment._capture_logs", return_value=True),
            patch.object(live, "_official_world_run_dir",
                         side_effect=lambda run_id: test_root / "runs" / "a-environment" / run_id),
            patch.object(live, "_projection_run_dir",
                         side_effect=lambda run_id: test_root / "projection-output" / run_id),
            patch.object(GuardedTransport, "_validate_request", capture_guard_shape),
        ]
        for item in monkeypatches:
            item.start()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "mock-secret-never-real"}):
            try:
                result_b = live._orchestrate("b-smoke", run_b, test_root,
                                             _test_context=live._MOCK_ORCHESTRATION_TEST)
                self.assertEqual(result_b["status"], "smoke_completed",
                                 msg=f"result={result_b}; transport_factories={transport_factories}; "
                                     f"mock runner error: {fake_docker.containers.created[-1].error}")
                self.assertEqual(len(wire_by_kind["b-smoke"].requests), 3)
                runner_b = fake_docker.containers.created[-1]
                self.assertTrue(runner_b.options["read_only"])
                self.assertEqual(runner_b.options["cap_drop"], ["ALL"])
                self.assertEqual(runner_b.options["security_opt"], ["no-new-privileges:true"])
                self.assertEqual(runner_b.volumes["chi-h-root-model-deps-20261027-v1"]["mode"], "ro")
                self.assertNotIn("/var/run/docker.sock", " ".join(runner_b.volumes))
                self.assertFalse(any(".env" in mount for mount in runner_b.volumes))
                current_kind["value"] = "c-once"
                with patch("agents.mcp.MCPServerStreamableHttp", side_effect=fake_mcp_factory):
                    result_c = live._orchestrate("c-once", run_c, test_root,
                                                 _test_context=live._MOCK_ORCHESTRATION_TEST)
                self.assertEqual(result_c["status"], "completed_ungraded",
                                 msg=f"mock C request shapes: {request_debug}")
                self.assertIsNone(result_c["official_reward"])
                self.assertEqual(len(wire_by_kind["c-once"].requests), 2)
                self.assertEqual([item["name"] for item in mcp_calls],
                                 ["cases.lookup_case", "cases.list_case_documents"])
                runner_c = fake_docker.containers.created[-1]
                world_c = fake_docker.containers.created[-2]
                self.assertTrue(runner_c.options["read_only"])
                self.assertNotIn("DEEPSEEK_API_KEY", world_c.environment)
                self.assertIn("/logs/artifacts/workspaces", runner_c.volumes.values().__str__())
                claim = json.loads((test_root / live.CLAIM_FILE).read_text())
                self.assertFalse(claim["replay_allowed"])
                self.assertEqual(claim["terminal_status"], "completed_ungraded")
                run_doc = json.loads((test_root / "runs" / f"{run_c}.json").read_text())
                self.assertEqual([item["state"] for item in run_doc["tool_dispatches"]], ["returned", "returned"])
                self.assertIsNone(run_doc["official_reward"])
                self.assertFalse(any("mock-secret-never-real" in p.read_text(errors="ignore")
                                     for p in (test_root / run_b).rglob("*") if p.is_file()))
                summary = {"result_b": result_b, "result_c": result_c,
                           "mock_provider_requests": {key: len(value.requests) for key, value in wire_by_kind.items()},
                           "mock_mcp_calls": mcp_calls, "credentials": "mock only", "official_reward": None}
                (test_root / "mock-e2e-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            finally:
                for p in reversed(monkeypatches):
                    p.stop()


if __name__ == "__main__":
    unittest.main()
