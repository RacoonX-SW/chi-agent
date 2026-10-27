"""Offline-only regression for the isolated real-development adapters."""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import httpx

import live_development as live


def test_capture_review_input_bounded_and_fail_closed(tmp_path):
    class World:
        id = "synthetic-world"
        class Client:
            class API:
                timeout = 30
            api = API()
        client = Client()

        def exec_run(self, command, demux=False):
            assert "127.0.0.1:8023/export" in command[-1]
            return 0, b'{"world_id":"synthetic-world","audit_logs": []}'

        def get_archive(self, path):
            assert path in (f"/opt/chi-bench/tasks/{live.TASK_ID}/fixtures/expectations.json",
                            "/opt/chi-bench/worlds/synthetic-world.json")
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                data = (b'{"verifier_contract":"contract_v5"}' if path.endswith("expectations.json")
                        else b'{"patients":[],"documents":[]}')
                info = tarfile.TarInfo(Path(path).name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            return [buf.getvalue()], {}

    result = live._capture_review_input(World(), tmp_path, "synthetic", {"source": "synthetic"})
    assert result["status"] == "ready"
    manifest = json.loads((tmp_path / "synthetic" / "manifest.json").read_text())
    assert manifest["world_id"] == "synthetic-world"
    assert manifest["shared_world_id"] == "synthetic-world"
    assert manifest["official_reward"] is None
    assert live._capture_review_input(World(), tmp_path, "synthetic", {})["status"] == "unavailable"

    class Failed(World):
        def exec_run(self, command, demux=False):
            return 1, b"sensitive error"

    result = live._capture_review_input(Failed(), tmp_path / "failed", "synthetic", {})
    assert result == {"status": "unavailable", "safe_error_code": "review_input_capture_failed"}

    class BadArchive(World):
        def get_archive(self, path):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                info = tarfile.TarInfo("expectations.json")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            return [buf.getvalue()], {}

    assert live._capture_review_input(BadArchive(), tmp_path / "bad", "synthetic", {})["status"] == "unavailable"

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
        self.removed = False

    def connect(self, _container):
        return None

    def remove(self):
        self.removed = True


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
                                    mcp_url=args[args.index("--mcp-url") + 1],
                                    k_development="--k-development" in args,
                                    _test_context=live._MOCK_ORCHESTRATION_TEST)
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
        self.fail_network_create = False
        self.network_remove_attempts = []

    def create(self, name, **_kwargs):
        if self.fail_network_create:
            self.unknown_network_name = name
            raise OSError("synthetic create outcome unknown")
        return FakeNetwork(name)

    def close(self):
        return None


class LiveDevelopmentTests(unittest.TestCase):
    def test_live_guard_replays_empty_reasoning_on_both_tool_rounds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            live.initialize_real_accounting(root, prior_source="synthetic")
            instruction = root / "instruction.md"
            instruction.write_text("Use both smoke tools in order.")
            wire = FakeWire("b-smoke")
            for response in wire.responses[:2]:
                response["choices"][0]["message"].update(content="", reasoning_content="")
            args = Namespace(kind="b-smoke", run_id="synthetic-b", budget_root=root,
                             logs_dir=root / "logs", instruction_file=instruction,
                             mcp_url="http://127.0.0.1:9/unused", _test_context=live._MOCK_ORCHESTRATION_TEST)
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic"}), patch(
                    "httpx.AsyncHTTPTransport", side_effect=lambda **kw: httpx.MockTransport(wire)):
                self.assertEqual(asyncio.run(live._worker_run(args)), 0)
            assistants = [m for m in wire.requests[2]["messages"] if m.get("role") == "assistant" and m.get("tool_calls")]
            self.assertEqual([m["tool_calls"][0]["id"] for m in assistants], ["call_lookup", "call_transform"])
            self.assertEqual([m["reasoning_content"] for m in assistants], ["", ""])
            run = json.loads((root / "runs" / "synthetic-b.json").read_text())
            self.assertEqual(len(run["requests"]), 3)
            self.assertTrue(all(request["status"] == "settled" for request in run["requests"]))

    def test_live_guard_rejects_missing_or_invalid_reasoning_without_retry(self):
        for value in (None, 7, "absent"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                live.initialize_real_accounting(root, prior_source="synthetic")
                instruction = root / "instruction.md"
                instruction.write_text("Use smoke tools.")
                wire = FakeWire("b-smoke")
                message = wire.responses[0]["choices"][0]["message"]
                if value == "absent":
                    del message["reasoning_content"]
                else:
                    message["reasoning_content"] = value
                args = Namespace(kind="b-smoke", run_id="synthetic-b", budget_root=root,
                                 logs_dir=root / "logs", instruction_file=instruction,
                                 mcp_url="http://127.0.0.1:9/unused", _test_context=live._MOCK_ORCHESTRATION_TEST)
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic"}), patch(
                        "httpx.AsyncHTTPTransport", side_effect=lambda **kw: httpx.MockTransport(wire)):
                    self.assertNotEqual(asyncio.run(live._worker_run(args)), 0)
                self.assertEqual(len(wire.requests), 1)
                run = json.loads((root / "runs" / "synthetic-b.json").read_text())
                self.assertEqual(run["primary_error_code"], "response_invalid")
                self.assertEqual(run["requests"][0]["status"], "settled")

    def test_j_identity_binds_utf8_reader_without_pdf_dependency(self):
        import hashlib
        from types import SimpleNamespace
        identity = live._execution_identity()
        source = live.ROOT / "scripts" / "pdf_resource_reader.py"
        self.assertEqual(identity["application_files_sha256"]["scripts/pdf_resource_reader.py"],
                         hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertNotIn("pdf_dependency", identity)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            target = workspace / "case-1" / "provider" / "text.txt"
            target.parent.mkdir(parents=True)
            target.write_text("一\n二\n", encoding="utf-8")
            ledger = SimpleNamespace(pending_calls=[])
            class Journal:
                policy = SimpleNamespace(scope="local_development")
                def start_dispatch(self, **kwargs): pass
                def finish_dispatch(self, **kwargs): pass
                def record_effect(self, effect): pass
            with patch.object(live, "WORKSPACE_CONTAINER_ROOT", workspace):
                tool = next(t for t in live._live_tools("c-once", root, root, Journal(), {}, ledger)
                            if t.name == "local-fs-read")
                args = {"path": str(target), "offset": 2, "limit": 1}
                ledger.pending_calls.append({"tool": tool.name, "arguments": args, "call_id": "test"})
                self.assertEqual(asyncio.run(tool.on_invoke_tool(None, json.dumps(args))), "二\n")

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

    def test_unknown_usage_keeps_known_prefix_and_never_reports_zero_total(self):
        from decimal import Decimal
        from b_execution_policy import load_local_policy
        from b_provider_profile import load_profile

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile, policy = load_profile(), load_local_policy()
            live.initialize_real_accounting(root, prior_source="offline-unknown-prefix-fixture")
            journal = live.RealDevelopmentJournal(root, "mock-prefix-unknown", profile=profile, policy=policy)
            request = httpx.Request("POST", profile.endpoint + "/v1/chat/completions", content=b"mock")
            body = {"model": profile.model}
            journal.reserve(profile, request, body, b"settled-prefix", 1024, 1)
            journal.settle(Decimal("0.000038"), 7, 3)
            journal.reserve(profile, request, body, b"unknown-request", 1024, 2)
            journal.mark_unknown("transport_timeout")
            journal.finalize(status="incomplete", primary_error="transport_timeout")
            journal.finalize(status="incomplete", primary_error="transport_timeout")
            doc = json.loads(journal.run_path.read_text())
            self.assertIsNone(doc["real_usage"])
            self.assertIsNone(doc["estimated_cost_cny"])
            self.assertEqual(doc["known_prefix_usage"], {"input_tokens": 7, "output_tokens": 3})
            self.assertEqual(doc["known_prefix_estimated_cost_cny"], "0.000038")
            self.assertIsNone(doc["campaign_usage"])
            self.assertIsNone(doc["campaign_estimated_cost_cny"])
            self.assertEqual(doc["campaign_known_prefix_usage"], {"input_tokens": 7, "output_tokens": 3})
            self.assertEqual(doc["campaign_known_prefix_estimated_cost_cny"], "0.000038")
            journal.close()
            with self.assertRaises(live.LiveFailure) as blocked:
                live.RealDevelopmentJournal(root, "mock-prefix-restart", profile=profile, policy=policy)
            self.assertEqual(blocked.exception.code, "real_accounting_pending_unknown")

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
            patch.object(live, "_copy_projection",
                         side_effect=lambda _root, run_id: self._mock_projection(test_root, run_id)),
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
                world_artifacts = next(Path(source) for source, options in world_c.volumes.items()
                                       if options.get("bind") == "/logs/artifacts")
                runner_artifacts = next(Path(source) for source, options in runner_c.volumes.items()
                                        if options.get("bind") == "/logs/artifacts")
                self.assertEqual(world_artifacts, runner_artifacts)
                self.assertTrue((world_artifacts / "workspaces").is_dir())
                claim = json.loads((test_root / live.CLAIM_FILE).read_text())
                self.assertFalse(claim["replay_allowed"])
                self.assertEqual(claim["terminal_status"], "completed_ungraded")
                run_doc = json.loads((test_root / "runs" / f"{run_c}.json").read_text())
                self.assertEqual([item["state"] for item in run_doc["tool_dispatches"]], ["returned", "returned"])
                self.assertEqual(run_doc["real_usage"], {
                    "input_tokens": sum(row["input_tokens"] for row in run_doc["requests"]),
                    "output_tokens": sum(row["output_tokens"] for row in run_doc["requests"])})
                self.assertEqual(run_doc["campaign_usage"], {
                    "input_tokens": sum(row["input_tokens"] for row in
                                         json.loads((test_root / "runs" / f"{run_b}.json").read_text())["requests"])
                                    + run_doc["real_usage"]["input_tokens"],
                    "output_tokens": sum(row["output_tokens"] for row in
                                          json.loads((test_root / "runs" / f"{run_b}.json").read_text())["requests"])
                                     + run_doc["real_usage"]["output_tokens"]})
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

    def test_partial_network_create_keeps_claim_and_does_not_guess_cleanup(self):
        evidence_root = live.ROOT / "runs" / "real-b-c" / "impl"
        evidence_root.mkdir(parents=True, exist_ok=True)
        test_root = Path(tempfile.mkdtemp(prefix="mock-partial-create-", dir=evidence_root))
        (test_root / "runs" / "a-environment").mkdir(parents=True)
        (test_root / "projection-output").mkdir()
        identity = live._execution_identity()
        live.initialize_real_accounting(test_root, prior_source="offline-partial-create-fixture",
                                        execution_identity=identity)
        docker = FakeDocker(test_root)
        tools = [
            patch.object(live, "_model_key", return_value="mock-secret-never-real"),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "mock-secret-never-real"}),
            patch("a_environment._docker", return_value=docker),
            patch("a_environment._daemon_path", side_effect=lambda _root, path: str(path)),
            patch("a_environment._check_resource_slots", return_value=None),
            patch("a_environment.wait_world", return_value=0.0),
            patch("a_environment._capture_logs", return_value=True),
            patch.object(live, "_official_world_run_dir",
                         side_effect=lambda run_id: test_root / "runs" / "a-environment" / run_id),
            patch.object(live, "_projection_run_dir",
                         side_effect=lambda run_id: test_root / "projection-output" / run_id),
            patch.object(live, "_copy_projection", side_effect=lambda _root, run_id: self._mock_projection(test_root, run_id)),
        ]
        with patch("httpx.AsyncHTTPTransport", side_effect=lambda **_kwargs: httpx.MockTransport(FakeWire("b-smoke"))), \
             patch.object(live, "_model_key", return_value="mock-secret-never-real"), \
             patch.dict(os.environ, {"DEEPSEEK_API_KEY": "mock-secret-never-real"}):
            # Create an authentic B receipt using the offline provider fixture first.
            with patch("a_environment._docker", return_value=docker), \
                 patch("a_environment._daemon_path", side_effect=lambda _root, path: str(path)), \
                 patch("a_environment.cleanup", return_value={"container_removed": True, "network_removed": True}):
                self.assertEqual(live._orchestrate("b-smoke", "partial-b", test_root,
                                                   _test_context=live._MOCK_ORCHESTRATION_TEST)["status"], "smoke_completed")
        original_atomic = live._atomic_json

        def fail_claim_reconciliation(path, value, **kwargs):
            if path.name == live.CLAIM_FILE and value.get("state") == "failed_or_uncertain_claim_retained":
                raise OSError("synthetic claim persistence failure")
            return original_atomic(path, value, **kwargs)

        started = [item.start() for item in tools]
        try:
            with patch.object(docker, "create", side_effect=live.LiveFailure("controlled_network_create_error")), \
                 patch.object(live, "_atomic_json", side_effect=fail_claim_reconciliation):
                result = live._orchestrate("c-once", "partial-c", test_root,
                                           _test_context=live._MOCK_ORCHESTRATION_TEST)
            claim = json.loads((test_root / live.CLAIM_FILE).read_text())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["primary_error_code"], "controlled_network_create_error")
            self.assertEqual(result["persistence_error_code"], "claim_evidence_persist_failed")
            self.assertEqual(claim["terminal_status"], "failed")
        finally:
            for item in reversed(tools):
                item.stop()

    @staticmethod
    def _mock_projection(test_root: Path, run_id: str) -> Path:
        projection = test_root / "projection-output" / run_id
        projection.mkdir(parents=True)
        (projection / "instruction.md").write_text("Offline task instruction.")
        (projection / "tool_reference.md").write_text("Offline tool reference.")
        for alias in ("healthverse-task-assets", "chi-bench-task-assets"):
            (projection / alias).mkdir()
            (projection / alias / "tool_reference.md").write_text("Offline tool reference.")
        handbook = projection / "workspace/skills/managed-care-operations-handbook"
        handbook.mkdir(parents=True)
        (handbook / "SKILL.md").write_text("Offline handbook.")
        return projection

    def test_worker_cli_scope_is_fixed(self):
        args = Namespace(kind="c-once", run_id="c-run", budget_root=Path("/tmp/budget"),
                         logs_dir=Path("/tmp/logs"), instruction_file=Path("/tmp/instruction"),
                         mcp_url="http://wrong/mcp")
        with self.assertRaises(live.LiveFailure) as blocked:
            live._validate_worker_mounts(args)
        self.assertEqual(blocked.exception.code, "worker_scope_arguments_invalid")

    def test_official_workspace_reset_removes_child_not_bind_mount_and_scope_stays_narrow(self):
        from chi_bench.core.context import ServiceContext

        with tempfile.TemporaryDirectory() as temp:
            artifacts = Path(temp) / "artifacts"
            workspace = artifacts / "workspaces"
            old_case = workspace / "case-17" / "provider"
            old_case.mkdir(parents=True)
            (old_case / "old.txt").write_text("old")
            controller_file = artifacts / "controller.log"
            controller_file.write_text("outside workspace subtree")

            official_context = object.__new__(ServiceContext)
            official_context.workspace_root = workspace
            official_context._reset_workspace_root()

            self.assertTrue(artifacts.is_dir())
            self.assertTrue(workspace.is_dir())
            self.assertFalse((workspace / "case-17").exists())
            self.assertTrue(controller_file.is_file())

            self.assertEqual(live._workspace_path(workspace, str(workspace / "case-17/provider"),
                                                  allow_directory=True),
                             workspace / "case-17/provider")
            self.assertEqual(live._workspace_path(workspace, str(workspace / "case-17/shared/file.txt")),
                             workspace / "case-17/shared/file.txt")
            for denied in (str(artifacts / "controller.log"), str(workspace / "case-17/payer/secret.txt"),
                           str(workspace / "../controller.log")):
                self.assertIsNone(live._workspace_path(workspace, denied))

    def test_b_receipt_is_revoked_when_controller_cleanup_fails(self):
        evidence_root = live.ROOT / "runs" / "real-b-c" / "impl"
        evidence_root.mkdir(parents=True, exist_ok=True)
        test_root = Path(tempfile.mkdtemp(prefix="mock-b-cleanup-failure-", dir=evidence_root))
        identity = live._execution_identity()
        live.initialize_real_accounting(test_root, prior_source="offline-cleanup-fixture",
                                        execution_identity=identity)
        docker = FakeDocker(test_root)
        original_remove = FakeContainer.remove

        def fail_runner_remove(container, force=False):
            if container.name.startswith("chi-agent-real-runner-"):
                raise OSError("synthetic cleanup failure")
            return original_remove(container, force=force)

        with patch.object(live, "_model_key", return_value="mock-secret-never-real"), \
             patch.dict(os.environ, {"DEEPSEEK_API_KEY": "mock-secret-never-real"}), \
             patch("httpx.AsyncHTTPTransport", side_effect=lambda **_kwargs: httpx.MockTransport(FakeWire("b-smoke"))), \
             patch("a_environment._docker", return_value=docker), \
             patch("a_environment._daemon_path", side_effect=lambda _root, path: str(path)), \
             patch.object(FakeContainer, "remove", fail_runner_remove):
            result = live._orchestrate("b-smoke", "cleanup-b", test_root,
                                       _test_context=live._MOCK_ORCHESTRATION_TEST)
        self.assertEqual(result["status"], "cleanup_failed")
        self.assertFalse((test_root / "b-success.json").exists())
        run_doc = json.loads((test_root / "runs" / "cleanup-b.json").read_text())
        self.assertEqual(run_doc["state"], "incomplete")
        self.assertEqual(run_doc["orchestration_status"], "cleanup_failed")


def _adopt_synthetic_history(base: Path, root: Path) -> None:
    import hashlib
    old = base / "prior-fixture"
    old.mkdir(parents=True)
    state = live.initialize_real_accounting(old, prior_source="synthetic")
    state.update(profile_sha256=live.load_profile().sha256, known_input_tokens=7,
                 known_output_tokens=3, known_settled_cost_cny="0.000038")
    live._atomic_json(old / "accounting.json", state)
    (old / ".real-accounting.lock").touch()
    run = {"schema": "chi-real-provider-run-v1", "campaign_id": live.CAMPAIGN_ID,
           "state": "complete", "execution_identity": state["execution_identity"],
           "profile_sha256": state["profile_sha256"], "real_usage": {"input_tokens": 7, "output_tokens": 3},
           "estimated_cost_cny": "0.000038"}
    run_path = old / "runs" / "b.json"
    live._atomic_json(run_path, run)
    logs = old / "b" / "runner-logs"
    logs.mkdir(parents=True)
    for name in ("run_result.json", "run_output.txt", "trace.jsonl", "run_log.txt"):
        (logs / name).write_text("synthetic")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = {"schema": live.B_SUCCESS_SCHEMA, "campaign_id": live.CAMPAIGN_ID, "task_id": live.TASK_ID,
               "run_id": "b", "status": "success", "profile_sha256": state["profile_sha256"],
               "execution_identity": state["execution_identity"], "usage": run["real_usage"],
               "estimated_cost_cny": run["estimated_cost_cny"], "official_reward": None,
               "run_journal_sha256": digest(run_path), "runner_result_sha256": digest(logs / "run_result.json"),
               "run_output_sha256": digest(logs / "run_output.txt"), "trace_sha256": digest(logs / "trace.jsonl"),
               "run_log_sha256": digest(logs / "run_log.txt")}
    live._atomic_json(old / "b-success.json", receipt)
    claim = {"schema": live.CLAIM_SCHEMA, "campaign_id": live.CAMPAIGN_ID, "task_id": live.TASK_ID,
             "run_id": "c", "execution_identity": state["execution_identity"],
             "profile_sha256": state["profile_sha256"], "official_reward": None, "replay_allowed": False,
             "finished_at": "synthetic", "cleanup_error_code": None, "terminal_status": "failed",
             "state": "failed_or_uncertain_claim_retained",
             "b_success_sha256": hashlib.sha256(live._json(receipt).encode()).hexdigest()}
    live._atomic_json(old / live.CLAIM_FILE, claim)
    live._atomic_json(old / "c" / "orchestration.json", {"run_id": "c", "status": "failed",
        "finished_at": "synthetic", "cleanup_error_code": None, "world": {"logs_captured": True},
        "cleanup": {"world_removed": True, "network_removed": True}})
    live.adopt_prior(old, root, _test_context=live._MOCK_ORCHESTRATION_TEST)
    live.rebind_source(root, "synthetic source transition")


class ContinuedDevelopmentTests(unittest.TestCase):
    def test_real_projection_copy_uses_explicit_new_run_directory(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            revision = "5ce88104df2a91e057619eb70fb51f56fc5949eb"
            dataset = root / "data" / "a-environment" / f"download-{revision}"
            records = {}
            for name in ("instruction.md", "tool_reference.md"):
                relative = f"prior_auth_provider/tasks/{live.TASK_ID}/{name}"
                path = dataset / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic public input")
                records[relative] = {"size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            live._atomic_json(dataset / ".a-environment-data-manifest.json", {"revision": revision, "files": records})
            handbook = root / "data" / "skills" / "managed-care-operations-handbook"
            handbook.mkdir(parents=True)
            (handbook / "sample.md").write_text("synthetic")
            destination = root / "runs" / "real-c-development" / "attempt"
            with patch("a_environment._verify_handbook"):
                projection = live._copy_projection(root, "attempt", output_parent=destination)
            self.assertEqual(projection, destination / "projection")
            self.assertTrue((projection / "instruction.md").is_file())
            self.assertFalse((root / "runs" / "real-b-c").exists())

    def test_missing_or_modified_provenance_blocks_before_key_and_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _adopt_synthetic_history(root, root)
            adoption = root / "adoption.json"
            original = adoption.read_bytes()
            transition = next((root / "source-transitions").iterdir())
            original_transition = transition.read_bytes()
            for path, payload in ((adoption, None), (adoption, b"{}"), (transition, b"{}")):
                if payload is None:
                    path.unlink()
                else:
                    path.write_bytes(payload)
                with patch.object(live, "_model_key") as key, patch.object(live, "_orchestrate") as orchestration:
                    with self.assertRaises(live.LiveFailure) as error:
                        live._k_locked(root, lambda: live._k_run("b-smoke", "attempt", root))
                    self.assertEqual(error.exception.code, "real_provenance_invalid")
                    key.assert_not_called()
                    orchestration.assert_not_called()
                adoption.write_bytes(original)
                transition.write_bytes(original_transition)
            state = live._read_json(root / "accounting.json")
            state["prior_spend_cny"] = "1"
            live._atomic_json(root / "accounting.json", state)
            with self.assertRaises(live.LiveFailure):
                live._k_locked(root, lambda: live._k_run("b-smoke", "attempt", root))

    def test_credential_failure_does_not_poison_controller_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _adopt_synthetic_history(root, root)
            with patch.object(live, "_model_key", side_effect=live.LiveFailure("provider_credential_missing")):
                with self.assertRaises(live.LiveFailure):
                    live._k_locked(root, lambda: live._k_run("b-smoke", "first", root))
            self.assertFalse((root / "controller-state.json").exists())
            self.assertEqual(live._read_json(root / "pre-resource-failures" / "first.json")["error_code"], "provider_credential_missing")
            with patch.object(live, "_model_key", return_value="synthetic"), patch.object(
                    live, "_orchestrate", side_effect=lambda *args, **kw: (
                        kw["_before_resources"]() or {"status": "smoke_completed"})) as run:
                live._k_locked(root, lambda: live._k_run("b-smoke", "second", root))
                run.assert_called_once()
            self.assertEqual(live._read_json(root / "controller-state.json")["state"], "clean")

    def test_two_fresh_mock_worlds_after_current_b(self):
        evidence_root = live.ROOT / "runs" / "real-b-c" / "impl"
        evidence_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="mock-k-e2e-", dir=evidence_root))
        _adopt_synthetic_history(root, root)
        docker = FakeDocker(root)
        kind = {"value": "b-smoke"}
        wires = {"b-smoke": FakeWire("b-smoke"), "c-once": FakeWire("c-once")}
        patches = [patch.object(live, "_model_key", return_value="synthetic-secret"),
                   patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-secret"}),
                   patch("httpx.AsyncHTTPTransport", side_effect=lambda **kw: httpx.MockTransport(wires[kind["value"]])),
                   patch("a_environment._docker", return_value=docker),
                   patch("a_environment._daemon_path", side_effect=lambda _root, path: str(path)),
                   patch("a_environment._check_resource_slots", return_value=None),
                   patch("a_environment.wait_world", return_value=0.0),
                   patch("a_environment._capture_logs", return_value=True),
                   patch.object(live, "_official_world_run_dir", side_effect=lambda run_id: root / "worlds" / run_id),
                   patch.object(live, "_copy_projection", side_effect=lambda _r, run_id, **kw: LiveDevelopmentTests._mock_projection(root, run_id)),
                   patch("agents.mcp.MCPServerStreamableHttp", side_effect=lambda *a, **kw: FakeMCP([]))]
        for item in patches:
            item.start()
        try:
            result = live._orchestrate("b-smoke", "k-b", root, _test_context=live._MOCK_ORCHESTRATION_TEST, k=True)
            self.assertEqual(result["status"], "smoke_completed", result)
            kind["value"] = "c-once"
            for run_id in ("k-c-one", "k-c-two"):
                wires["c-once"] = FakeWire("c-once")
                result = live._orchestrate("c-once", run_id, root, _test_context=live._MOCK_ORCHESTRATION_TEST, k=True)
                self.assertEqual(result["status"], "completed_ungraded", result)
                self.assertEqual(result["review_input"]["status"], "unavailable")
                self.assertTrue(result["cleanup"]["world_removed"])
                self.assertTrue(result["cleanup"]["network_removed"])
            self.assertEqual(len(list((root / "claims").iterdir())), 2)
            live._check_k_attempts_clean(root)
            old_receipt = (root / "b-success.json").read_bytes()
            new_identity = {**live._execution_identity(k=True), "synthetic_revision": "next"}
            with patch.object(live, "_execution_identity", return_value=new_identity):
                live.rebind_source(root, "synthetic revision")
            self.assertFalse((root / "b-success.json").exists())
            self.assertEqual((root / "b-receipts" / "k-b.json").read_bytes(), old_receipt)
            self.assertEqual(live._read_json(root / "accounting.json")["execution_identity"], new_identity)
        finally:
            for item in reversed(patches):
                item.stop()

    def test_adoption_preserves_prior_and_requires_explicit_source_transition(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            old, new = Path(temp) / "old", Path(temp) / "new"
            old.mkdir()
            state = live.initialize_real_accounting(old, prior_source="synthetic")
            state.update(profile_sha256=live.load_profile().sha256, known_input_tokens=7,
                         known_output_tokens=3, known_settled_cost_cny="0.000038")
            live._atomic_json(old / "accounting.json", state)
            (old / ".real-accounting.lock").touch()
            run = {"schema": "chi-real-provider-run-v1", "campaign_id": live.CAMPAIGN_ID,
                   "state": "complete", "execution_identity": state["execution_identity"],
                   "profile_sha256": state["profile_sha256"], "real_usage": {"input_tokens": 7, "output_tokens": 3},
                   "estimated_cost_cny": "0.000038"}
            run_path = old / "runs" / "b.json"
            live._atomic_json(run_path, run)
            logs = old / "b" / "runner-logs"
            logs.mkdir(parents=True)
            for name in ("run_result.json", "run_output.txt", "trace.jsonl", "run_log.txt"):
                (logs / name).write_text("synthetic evidence")
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            receipt = {"schema": live.B_SUCCESS_SCHEMA, "campaign_id": live.CAMPAIGN_ID, "task_id": live.TASK_ID,
                       "run_id": "b", "status": "success", "profile_sha256": state["profile_sha256"],
                       "execution_identity": state["execution_identity"], "usage": run["real_usage"],
                       "estimated_cost_cny": run["estimated_cost_cny"], "official_reward": None,
                       "run_journal_sha256": digest(run_path), "runner_result_sha256": digest(logs / "run_result.json"),
                       "run_output_sha256": digest(logs / "run_output.txt"), "trace_sha256": digest(logs / "trace.jsonl"),
                       "run_log_sha256": digest(logs / "run_log.txt")}
            live._atomic_json(old / "b-success.json", receipt)
            claim = {"schema": live.CLAIM_SCHEMA, "campaign_id": live.CAMPAIGN_ID, "task_id": live.TASK_ID,
                     "run_id": "c", "execution_identity": state["execution_identity"],
                     "profile_sha256": state["profile_sha256"], "official_reward": None, "replay_allowed": False,
                     "finished_at": "synthetic", "cleanup_error_code": None, "terminal_status": "failed",
                     "state": "failed_or_uncertain_claim_retained",
                     "b_success_sha256": hashlib.sha256(live._json(receipt).encode()).hexdigest()}
            live._atomic_json(old / live.CLAIM_FILE, claim)
            live._atomic_json(old / "c" / "orchestration.json", {"run_id": "c", "status": "failed",
                "finished_at": "synthetic", "cleanup_error_code": None,
                "world": {"logs_captured": True}, "cleanup": {"world_removed": True, "network_removed": True}})
            before = {path: path.read_bytes() for path in old.rglob("*") if path.is_file()}
            live.adopt_prior(old, new, _test_context=live._MOCK_ORCHESTRATION_TEST)
            adopted = live._read_json(new / "accounting.json")
            self.assertEqual(adopted["prior_spend_cny"], "0.000038")
            self.assertEqual(adopted["known_input_tokens"], 7)
            self.assertEqual(adopted["execution_identity"], state["execution_identity"])
            live.rebind_source(new, "synthetic change")
            self.assertEqual(live._read_json(new / "accounting.json")["execution_identity"], live._execution_identity(k=True))
            self.assertEqual(len(list((new / "source-transitions").iterdir())), 1)
            self.assertEqual(before, {path: path.read_bytes() for path in old.rglob("*") if path.is_file()})
            with self.assertRaises(live.LiveFailure):
                live.adopt_prior(old, new, _test_context=live._MOCK_ORCHESTRATION_TEST)
            (logs / "trace.jsonl").write_text("tampered")
            with self.assertRaises(live.LiveFailure):
                live.adopt_prior(old, Path(temp) / "bad", _test_context=live._MOCK_ORCHESTRATION_TEST)

    def test_record_only_known_above_five_and_unknown_blocks(self):
        from decimal import Decimal
        from b_execution_policy import load_real_development_policy
        profile = live.load_profile()
        policy = load_real_development_policy()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _adopt_synthetic_history(root, root)
            journal = live.RealDevelopmentJournal(root, "k-one", profile=profile, policy=policy)
            request = httpx.Request("POST", profile.endpoint + "/v1/chat/completions", content=b"synthetic")
            for number in range(1, 4):
                journal.reserve(profile, request, {"model": profile.model}, b"synthetic", 8192, number)
                journal.settle(Decimal("2"), 1_000_000, 0)
            self.assertGreater(journal.cumulative_spend, Decimal("5"))
            journal.reserve(profile, request, {"model": profile.model}, b"synthetic", 1024, 1)
            journal.settle(Decimal("0.000038"), 7, 3)
            journal.reserve(profile, request, {"model": profile.model}, b"synthetic-two", 1024, 2)
            journal.mark_unknown("transport_timeout")
            journal.finalize(status="incomplete")
            self.assertIsNone(journal.run_doc["campaign_estimated_cost_cny"])
            self.assertEqual(journal.run_doc["prior_spend_cny"], "0.000038")
            journal.close()
            with self.assertRaises(live.LiveFailure):
                live.RealDevelopmentJournal(root, "k-two", profile=profile, policy=policy)

    def test_per_run_claim_and_controller_lock(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b = {"execution_identity": {"synthetic": True}, "profile_sha256": live.load_profile().sha256}
            live._claim_c_once(root, "one", b, k=True)
            live._claim_c_once(root, "two", b, k=True)
            with self.assertRaises(live.LiveFailure):
                live._claim_c_once(root, "one", b, k=True)
            lock = os.open(root / ".controller.lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(live.LiveFailure) as error:
                    live._k_locked(root, lambda: None)
                self.assertEqual(error.exception.code, "controller_busy")
            finally:
                os.close(lock)


if __name__ == "__main__":
    unittest.main()


def test_capture_timeout_closes_archive_and_rejects_parent_symlink(tmp_path, monkeypatch):
    clock = {"seconds": 0.0}
    monkeypatch.setattr(live.time, "monotonic", lambda: clock["seconds"])
    class API:
        timeout = 30
    class Client:
        api = API()
    class World:
        id = "synthetic-world"
        client = Client()
        closed = False
        def exec_run(self, *args, **kwargs):
            return 0, b'{"world_id":"synthetic-world"}'
        def get_archive(self, path):
            def chunks():
                try:
                    clock["seconds"] = 61.0
                    yield b"synthetic"
                finally:
                    self.closed = True
            return chunks(), {}
    world = World()
    result = live._capture_review_input(world, tmp_path / "captures", "attempt", {})
    assert result["status"] == "unavailable" and world.closed
    assert world.client.api.timeout == 30
    link = tmp_path / "linked"
    link.symlink_to(tmp_path, target_is_directory=True)
    result = live._capture_review_input(world, link / "captures", "attempt", {})
    assert result["status"] == "unavailable"
    assert not (tmp_path / "captures").exists()
