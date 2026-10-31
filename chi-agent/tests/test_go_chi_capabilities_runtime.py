import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

from go_chi_journal import ChiJournal
from go_chi_runtime import run_chi
from opencode_go_provider import GoFailure


class Result:
    isError = False
    def __init__(self, payload=None):
        self.structuredContent = payload or {"case_id": "CASE-A", "status": "open"}
        self.content = []
    def model_dump(self, **kwargs):
        return {"structuredContent": self.structuredContent, "content": [], "isError": self.isError}


class Server:
    def __init__(self, names, *, fail=None):
        self.names, self.fail, self.calls = names, fail, []
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_args):
        return False
    async def list_tools(self):
        return [SimpleNamespace(name=name, description="Synthetic role tool",
                                inputSchema={"type": "object", "properties": {}, "additionalProperties": True})
                for name in self.names]
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.fail == name:
            raise RuntimeError("synthetic transport loss")
        return Result()


def completion(calls=None, content="done"):
    if calls is None:
        message = {"role": "assistant", "content": content}
        finish = "stop"
    else:
        message = {"role": "assistant", "content": None, "reasoning_content": "reason",
                   "tool_calls": [{"id": call_id, "type": "function",
                                   "function": {"name": name, "arguments": json.dumps(args)}}
                                  for call_id, name, args in calls]}
        finish = "tool_calls"
    return {"id": "synthetic", "object": "chat.completion", "created": 0,
            "model": "deepseek-v4.1-flash",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                      "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}}


class CapabilityRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.handbook = self.root / "handbook"
        self.handbook.mkdir()
        (self.handbook / "policy.md").write_text("A lumbar MRI needs prior therapy.\n", encoding="utf-8")
        self.workspace = self.root / "workspace"
        (self.workspace / "CASE-A" / "payer").mkdir(parents=True)
        self.instruction = self.root / "instruction.md"
        self.instruction.write_text("Synthetic payer instruction", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    async def exercise(self, responses, *, names=("triage.get",), role="payer", capabilities="f0-f3-v1",
                       fail=None):
        journal = ChiJournal(self.root / "state", identity="a" * 64, evaluation="eval",
                             task=role, attempt="a", run="run")
        server = Server(names, fail=fail)
        observed = []
        async def wire(request):
            observed.append(json.loads(request.content))
            return httpx.Response(200, request=request, json=responses[len(observed) - 1])
        try:
            output = await run_chi(journal, "synthetic-secret", role=role,
                instruction="Synthetic payer instruction", mcp_url="http://synthetic.invalid/mcp",
                instruction_path=self.instruction, logs_dir=self.root / "logs",
                workspace_root=self.workspace, handbook_root=self.handbook, tool_references=[],
                lower=httpx.MockTransport(wire), server_factory=lambda _url: server,
                capabilities=capabilities)
            journal.finish("complete")
            return output, observed, server, journal
        finally:
            journal.close()

    async def test_state_guidance_search_and_claim_close_the_loop(self):
        responses = [
            completion([("call_1", "local-role-guidance", {}),
                        ("call_2", "local-fs-search", {"path": str(self.handbook), "query": "prior therapy"}),
                        ("call_3", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_4", "local-state-update", {
                "target": {"case_id": "CASE-A"},
                "latest_business_status": {"text": "case open", "source_call_id": "call_3"},
                "next_candidates": ["read the documents"]})]),
            completion([("call_5", "local-task-state", {})]),
            completion([("call_6", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, server, journal = await self.exercise(responses)
        self.assertEqual(output, "done")
        self.assertEqual(server.calls, [("triage.get", {"case_id": "CASE-A"})])
        tools = {item["function"]["name"] for item in observed[0]["tools"]}
        for name in ("local-task-state", "local-state-update", "local-role-guidance", "local-fs-search"):
            self.assertIn(name, tools)
        state = json.loads((self.root / "logs" / "task-state" / "task-state.json").read_text())
        self.assertEqual(state["target"]["case_id"], "CASE-A")
        self.assertIsNone(state["target"]["patient_id"])
        self.assertEqual(state["latest_business_status"]["source_call_id"], "call_3")
        self.assertIsNotNone(state["claim"])
        self.assertTrue((self.root / "logs" / "task-state" / "versions").is_dir())
        log = json.loads((self.root / "logs" / "run_log.txt").read_text())
        self.assertEqual(log["capabilities"], "f0-f3-v1")
        self.assertEqual(log["task_state_version"], state["version"])
        self.assertRegex(log["guidance_sha256"], r"^[0-9a-f]{64}$")
        # The search tool returned a bounded hit from the public handbook.
        tool_messages = [message for request in observed for message in request["messages"]
                         if message.get("role") == "tool" and message.get("tool_call_id") == "call_2"]
        self.assertIn("policy.md", json.dumps(tool_messages))

    async def test_claim_blocks_after_mutation_until_readback(self):
        responses = [
            completion([("call_1", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_2", "local-claim_done", {})]),
            completion([("call_3", "determination__get_summary", {"case_id": "CASE-A"})]),
            completion([("call_4", "local-state-update", {
                "latest_business_status": {"text": "determined", "source_call_id": "call_3"}})]),
            completion([("call_5", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, _, journal = await self.exercise(
            responses, names=("payer_intake_hub.confirm_decisions", "determination.get_summary"))
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("completion_readback_required:call_1", results["call_2"])
        self.assertIn("task marked as done", results["call_5"])

    async def test_claim_in_the_same_batch_as_a_later_write_is_refused(self):
        responses = [
            completion([("call_1", "local-claim_done", {}),
                        ("call_2", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_3", "determination__get_summary", {"case_id": "CASE-A"})]),
            completion([("call_4", "local-state-update", {
                "latest_business_status": {"text": "determined", "source_call_id": "call_3"}})]),
            completion([("call_5", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, _, _ = await self.exercise(
            responses, names=("payer_intake_hub.confirm_decisions", "determination.get_summary"))
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("completion_batch_pending:call_2", results["call_1"])
        self.assertIn("task marked as done", results["call_5"])

    async def test_unknown_write_is_recorded_before_the_run_stops(self):
        responses = [completion([("call_1", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})])]
        with self.assertRaises(GoFailure):
            await self.exercise(responses, names=("payer_intake_hub.confirm_decisions",),
                                fail="payer_intake_hub.confirm_decisions")
        state = json.loads((self.root / "logs" / "task-state" / "task-state.json").read_text())
        self.assertEqual(state["unknowns"][0]["status"], "open")
        self.assertEqual(state["unknowns"][0]["call_id"], "call_1")

    async def test_capabilities_none_keeps_the_old_toolset_and_claim(self):
        responses = [
            completion([("call_1", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_2", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, _, _ = await self.exercise(responses, capabilities=None)
        self.assertEqual(output, "done")
        tools = {item["function"]["name"] for item in observed[0]["tools"]}
        self.assertNotIn("local-task-state", tools)
        self.assertFalse((self.root / "logs" / "task-state").exists())
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("task marked as done", results["call_2"])


if __name__ == "__main__":
    unittest.main()
