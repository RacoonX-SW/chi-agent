import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx

import go_chi_bundle as bundle
import payer_evidence
from go_chi_contract import ToolContract
from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal
from go_chi_runtime import run_chi
from go_chi_tools import local_tools
from opencode_go_provider import GoFailure
from agents.models.openai_chatcompletions import Converter

INSTRUCTION = ("Synthetic payer instruction for case-synthetic-001. "
               "Review the referral and prepare a determination.")


class Result:
    isError = False
    content = []

    def __init__(self, structured):
        self.structuredContent = structured

    def model_dump(self, **kwargs):
        return {"structuredContent": self.structuredContent, "content": [], "isError": False}


class PayerServer:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def list_tools(self):
        schema = {"type": "object", "properties": {"case_id": {"type": "string"}},
                  "required": ["case_id"], "additionalProperties": False}
        return [SimpleNamespace(name="triage.get", description="Synthetic triage read",
                                inputSchema=schema)]

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return Result({"finding": "specialist consultation is recommended"})


def response(request, message, finish):
    return httpx.Response(200, request=request, json={
        "id": "synthetic", "object": "chat.completion", "created": 0,
        "model": "deepseek-v4.1-flash",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                  "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}})


def call(call_id, name, arguments):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def instruction_span():
    start = INSTRUCTION.index("case-synthetic-001")
    return start, start + len("case-synthetic-001")


def checklist(source_id="src-0001"):
    start, end = instruction_span()
    return {"case_id": "case-synthetic-001", "proposed_action": "prepare_determination",
            "claims": [{"claim_id": "c1", "text": "Synthetic claim.", "category": "fact",
                        "source_id": source_id, "start_char": start, "end_char": end,
                        "rule_nature": "unknown", "status": "unclear"}],
            "unresolved": []}


class ShadowRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, script, *, shadow=None, role="payer", prepare=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval",
                             task=role, attempt="a", run="run")
        self.addCleanup(journal.close)
        instruction = root / "instruction.md"
        instruction.write_text(INSTRUCTION)
        handbook, workspace = root / "handbook", root / "workspace"
        handbook.mkdir()
        workspace.mkdir()
        if prepare is not None:
            prepare(root, workspace, handbook)
        server = PayerServer()
        bodies = []

        async def wire(request):
            body = json.loads(request.content)
            bodies.append(body)
            message, finish = script(body, len(bodies))
            return response(request, message, finish)

        kwargs = dict(role=role, instruction=INSTRUCTION, mcp_url="http://synthetic.invalid/mcp",
                      instruction_path=instruction, logs_dir=root / "logs",
                      workspace_root=workspace, handbook_root=handbook, tool_references=[],
                      lower=httpx.MockTransport(wire), server_factory=lambda _url: server)
        if shadow is not None:
            kwargs["evidence_shadow"] = shadow
        output = await run_chi(journal, "synthetic-secret", **kwargs)
        return SimpleNamespace(root=root, journal=journal, server=server, bodies=bodies,
                               output=output)

    @staticmethod
    def _tool_message(body, call_id):
        return next(item for item in body["messages"]
                    if item.get("role") == "tool" and item.get("tool_call_id") == call_id)

    async def test_off_path_has_no_shadow_tools_or_prompt_change(self):
        def script(body, index):
            if index == 1:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "triage__get",
                                            {"case_id": "case-synthetic-001"})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        plain = await self._run(script)
        explicit = await self._run(script, shadow="off")
        for run in (plain, explicit):
            names = [tool["function"]["name"] for tool in run.bodies[0]["tools"]]
            self.assertFalse([name for name in names if name.startswith("local-evidence-")])
            self.assertEqual(run.output, "done")
            self.assertEqual(run.server.calls, [("triage.get", {"case_id": "case-synthetic-001"})])
        self.assertEqual(plain.bodies[0]["tools"], explicit.bodies[0]["tools"])
        self.assertEqual(plain.bodies[0]["messages"][0], explicit.bodies[0]["messages"][0])

    async def test_shadow_adds_bounded_tools_and_records_valid_reference(self):
        def script(body, index):
            if index == 1:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "triage__get",
                                            {"case_id": "case-synthetic-001"})]}, "tool_calls"
            if index == 2:
                value = checklist(source_id="src-0002")
                value["claims"][0]["start_char"] = 0
                value["claims"][0]["end_char"] = 10
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_2", "local-evidence-check",
                                            {"checklist": value})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        run = await self._run(script, shadow="shadow")
        names = [tool["function"]["name"] for tool in run.bodies[0]["tools"]]
        self.assertEqual(names[-3:], ["local-evidence-sources", "local-evidence-excerpt",
                                      "local-evidence-check"])
        self.assertEqual(run.output, "done")
        self.assertEqual(run.server.calls, [("triage.get", {"case_id": "case-synthetic-001"})])
        payload = json.loads(self._tool_message(run.bodies[2], "call_2")["content"])
        self.assertEqual(payload["reference_validation"], "valid", payload)
        self.assertEqual(payload["semantic_assessment"], "not_performed")
        events = [(item["call_id"], item["tool"], item["event"])
                  for item in run.journal.run["tool_events"]]
        self.assertIn(("call_2", "local-evidence-check", "returned"), events)
        evidence = json.loads((run.root / "state" / "tool-evidence" / "run" / "call_2.json").read_text())
        self.assertEqual(json.loads(evidence["body_utf8"]), payload)

    async def test_same_batch_result_is_not_citable(self):
        def script(body, index):
            if index == 1:
                value = checklist(source_id="src-0002")
                value["claims"][0]["start_char"] = 0
                value["claims"][0]["end_char"] = 10
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "triage__get",
                                            {"case_id": "case-synthetic-001"}),
                                       call("call_2", "local-evidence-check",
                                            {"checklist": value})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        run = await self._run(script, shadow="shadow")
        payload = json.loads(self._tool_message(run.bodies[1], "call_2")["content"])
        self.assertEqual(payload["reference_validation"], "invalid")
        self.assertIn("source_unknown", payload["reasons"])
        self.assertEqual(run.server.calls, [("triage.get", {"case_id": "case-synthetic-001"})])
        self.assertEqual(run.output, "done")

    async def test_shadow_structure_error_only_rejects_that_request(self):
        def script(body, index):
            if index == 1:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "local-evidence-check",
                                            {"checklist": {"unexpected": True}})]}, "tool_calls"
            if index == 2:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_2", "triage__get",
                                            {"case_id": "case-synthetic-001"})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        run = await self._run(script, shadow="shadow")
        payload = json.loads(self._tool_message(run.bodies[1], "call_1")["content"])
        self.assertEqual(payload["reference_validation"], "invalid")
        self.assertIn("checklist_malformed", payload["reasons"])
        self.assertEqual(run.server.calls, [("triage.get", {"case_id": "case-synthetic-001"})])
        self.assertEqual(run.output, "done")

    async def test_runtime_file_from_other_case_is_rejected(self):
        holder = {}

        def prepare(_root, workspace, _handbook):
            case = workspace / "CASE_B" / "payer"
            case.mkdir(parents=True)
            path = case / "record.txt"
            path.write_text("CASE_B-only synthetic finding")
            holder["path"] = str(path)

        def script(body, index):
            if index == 1:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "local-fs-read",
                                            {"path": holder["path"]})]}, "tool_calls"
            if index == 2:
                value = checklist(source_id="src-0002")
                value["claims"][0].update(start_char=0, end_char=6)
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_2", "local-evidence-check",
                                            {"checklist": value})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        run = await self._run(script, shadow="shadow", prepare=prepare)
        payload = json.loads(self._tool_message(run.bodies[2], "call_2")["content"])
        self.assertEqual(payload["reference_validation"], "invalid", payload)
        self.assertIn("source_case_mismatch", payload["reasons"])

    async def test_runtime_shared_handbook_is_valid_support(self):
        holder = {}

        def prepare(_root, _workspace, handbook):
            path = handbook / "policy.md"
            path.write_text("Synthetic shared policy: nurses may approve when criteria are met.")
            holder["path"] = str(path)

        def script(body, index):
            if index == 1:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "local-fs-read",
                                            {"path": holder["path"]})]}, "tool_calls"
            if index == 2:
                value = checklist(source_id="src-0002")
                value["claims"][0].update(start_char=0, end_char=8)
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_2", "local-evidence-check",
                                            {"checklist": value})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        run = await self._run(script, shadow="shadow", prepare=prepare)
        payload = json.loads(self._tool_message(run.bodies[2], "call_2")["content"])
        self.assertEqual(payload["reference_validation"], "valid", payload)

    async def test_runtime_resource_update_supersedes_old_file(self):
        holder = {}

        def prepare(_root, workspace, _handbook):
            case = workspace / "case-synthetic-001" / "payer"
            case.mkdir(parents=True)
            path = case / "record.txt"
            path.write_text("old record")
            holder["path"] = str(path)

        def script(body, index):
            if index == 1:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_1", "local-fs-read",
                                            {"path": holder["path"]})]}, "tool_calls"
            if index == 2:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_2", "local-fs-write",
                                            {"path": holder["path"],
                                             "content": "new record"})]}, "tool_calls"
            if index == 3:
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_3", "local-fs-read",
                                            {"path": holder["path"]})]}, "tool_calls"
            if index == 4:
                value = checklist(source_id="src-0002")
                value["claims"][0].update(start_char=0, end_char=10,
                                          source_sha256=hashlib.sha256(b"old record").hexdigest())
                value["claims"].append({
                    "claim_id": "c2", "text": "Synthetic current claim.", "category": "fact",
                    "source_id": "src-0004", "start_char": 0, "end_char": 10,
                    "rule_nature": "unknown", "status": "unclear"})
                return {"role": "assistant", "content": None, "reasoning_content": "r",
                        "tool_calls": [call("call_4", "local-evidence-check",
                                            {"checklist": value})]}, "tool_calls"
            return {"role": "assistant", "content": "done"}, "stop"

        run = await self._run(script, shadow="shadow", prepare=prepare)
        payload = json.loads(self._tool_message(run.bodies[4], "call_4")["content"])
        self.assertEqual(payload["reference_validation"], "invalid", payload)
        self.assertIn("source_superseded", payload["reasons"])
        old, new = payload["claims"]
        self.assertFalse(old["source_current"])
        self.assertEqual(old["superseded_by"], "src-0004")
        self.assertEqual(new["reference"], "valid")
        self.assertEqual((run.root / "workspace" / "case-synthetic-001" / "payer" /
                          "record.txt").read_text(), "new record")

    async def test_shadow_is_payer_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval",
                                 task="provider", attempt="a", run="run")
            try:
                with self.assertRaises(Exception) as caught:
                    await run_chi(journal, "synthetic-secret", role="provider",
                                  instruction=INSTRUCTION,
                                  mcp_url="http://synthetic.invalid/mcp",
                                  instruction_path=root / "instruction.md",
                                  logs_dir=root / "logs", workspace_root=root,
                                  handbook_root=root, tool_references=[],
                                  lower=httpx.MockTransport(lambda request: None),
                                  server_factory=lambda _url: PayerServer(),
                                  evidence_shadow="shadow")
                self.assertEqual(getattr(caught.exception, "code", None),
                                 "chi_evidence_shadow_role_invalid")
            finally:
                journal.close()


class ShadowGuardTests(unittest.IsolatedAsyncioTestCase):
    async def _tools(self, fatal):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval",
                             task="payer", attempt="a", run="run")
        self.addCleanup(journal.close)
        instruction = root / "instruction.md"
        instruction.write_text(INSTRUCTION)
        handbook, workspace = root / "handbook", root / "workspace"
        handbook.mkdir()
        workspace.mkdir()
        holder = {}
        tools = local_tools(role="payer", workspace_root=workspace,
                            instruction_path=instruction, tool_references=[],
                            handbook_root=handbook, journal=journal, binding=None,
                            guard_getter=lambda: holder.get("guard"), client_getter=lambda: None,
                            confirmation_context=None, exchanges=[], dispatch_lock=asyncio.Lock(),
                            instruction=INSTRUCTION, evidence_shadow="shadow")
        guard = ChiGuard(journal, "synthetic-secret", "chi-" + "a" * 32,
                         httpx.MockTransport(lambda request: None),
                         tools=[Converter.tool_to_openai(tool) for tool in tools],
                         system="synthetic system", instruction=INSTRUCTION,
                         claimed=lambda: False, confirmation=lambda: None,
                         fatal_getter=lambda: fatal)
        holder["guard"] = guard
        return journal, tools, guard

    async def test_other_roles_have_no_shadow_tools(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instruction = root / "instruction.md"
            instruction.write_text(INSTRUCTION)
            handbook, workspace = root / "handbook", root / "workspace"
            handbook.mkdir()
            workspace.mkdir()
            tools = local_tools(role="cm", workspace_root=workspace,
                                instruction_path=instruction, tool_references=[],
                                handbook_root=handbook, journal=None, binding=None,
                                guard_getter=lambda: None, client_getter=lambda: None,
                                confirmation_context=None, exchanges=[], dispatch_lock=asyncio.Lock())
            self.assertFalse([tool for tool in tools if tool.name.startswith("local-evidence-")])
            with self.assertRaises(GoFailure) as caught:
                local_tools(role="cm", workspace_root=workspace,
                            instruction_path=instruction, tool_references=[],
                            handbook_root=handbook, journal=None, binding=None,
                            guard_getter=lambda: None, client_getter=lambda: None,
                            confirmation_context=None, exchanges=[], dispatch_lock=asyncio.Lock(),
                            evidence_shadow="shadow")
            self.assertEqual(caught.exception.code, "chi_evidence_shadow_role_invalid")

    async def test_fatal_stops_shadow_tool_before_execution(self):
        journal, tools, guard = await self._tools("chi_test_fatal")
        guard.contract.accept_batch({"role": "assistant", "content": None,
                                     "reasoning_content": "r",
                                     "tool_calls": [call("call_1", "local-evidence-sources", {})]})
        sources = next(tool for tool in tools if tool.name == "local-evidence-sources")
        with self.assertRaises(GoFailure) as caught:
            await sources.on_invoke_tool(None, "{}")
        self.assertEqual(caught.exception.code, "chi_test_fatal")
        self.assertEqual(journal.run["tool_events"], [])

    async def test_cancellation_is_recorded_and_propagated(self):
        journal, tools, guard = await self._tools(None)
        guard.contract.accept_batch({"role": "assistant", "content": None,
                                     "reasoning_content": "r",
                                     "tool_calls": [call("call_1", "local-evidence-sources", {})]})
        sources = next(tool for tool in tools if tool.name == "local-evidence-sources")
        with mock.patch.object(payer_evidence.EvidenceRegistry, "listing",
                               side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await sources.on_invoke_tool(None, "{}")
        self.assertEqual([(item["call_id"], item["event"]) for item in journal.run["tool_events"]],
                         [("call_1", "started"), ("call_1", "failed")])
        self.assertEqual(journal.run["tool_events"][-1]["safe_error_code"], "chi_tool_cancelled")


class BundleTests(unittest.TestCase):
    def test_bundle_contains_module_and_excludes_dev_assembly(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / "bundle"
            built = bundle.build_bundle(destination)
            identity = bundle.validate_bundle(destination)
            self.assertEqual(identity.manifest_sha256, built.manifest_sha256)
            self.assertIn("scripts/payer_evidence.py", identity.files)
            self.assertFalse((destination / "scripts" / "role_runner.py").exists())
            self.assertFalse((destination / "tests").exists())
            env = dict(os.environ)
            env["PYTHONPATH"] = str(destination / "scripts") + ":" + env.get("PYTHONPATH", "")
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [sys.executable, "-c", "import go_chi_tools, payer_evidence; print('ok')"],
                cwd=destination, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
