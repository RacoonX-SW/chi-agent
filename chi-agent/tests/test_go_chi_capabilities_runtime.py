import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

from go_chi_context import DEFAULT_BUDGET
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
                       fail=None, expect_failure=False, context_budget=DEFAULT_BUDGET):
        journal = ChiJournal(self.root / "state", identity="a" * 64, evaluation="eval",
                             task=role, attempt="a", run="run")
        server = Server(names, fail=fail)
        observed = []
        async def wire(request):
            observed.append(json.loads(request.content))
            return httpx.Response(200, request=request, json=responses[len(observed) - 1])
        try:
            try:
                output = await run_chi(journal, "synthetic-secret", role=role,
                    instruction="Synthetic payer instruction", mcp_url="http://synthetic.invalid/mcp",
                    instruction_path=self.instruction, logs_dir=self.root / "logs",
                    workspace_root=self.workspace, handbook_root=self.handbook, tool_references=[],
                    lower=httpx.MockTransport(wire), server_factory=lambda _url: server,
                    capabilities=capabilities, context_budget=context_budget)
            except GoFailure:
                if not expect_failure:
                    raise
                return None, observed, server, journal
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
            completion([("call_5", "local-task-state", {}),
                        ("call_6", "local-completion-check", {})]),
            completion([("call_7", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, server, journal = await self.exercise(responses)
        self.assertEqual(output, "done")
        self.assertEqual(server.calls, [("triage.get", {"case_id": "CASE-A"})])
        tools = {item["function"]["name"] for item in observed[0]["tools"]}
        for name in ("local-task-state", "local-state-update", "local-role-guidance",
                     "local-fs-search", "local-completion-check"):
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
        self.assertRegex(log["task_state_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(log["context_budget"], "chi-context-budget-v1")
        context_lines = (self.root / "logs" / "context.jsonl").read_text().splitlines()
        self.assertEqual(len(context_lines), log["context_requests"])
        self.assertGreater(log["context_max_chars"], 0)
        self.assertNotIn("Synthetic payer instruction", "\n".join(context_lines))
        self.assertEqual(log["completion"]["verification"], "mechanical_pass")
        self.assertEqual(log["completion"]["business_effect"], "observed")
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
                "target": {"case_id": "CASE-A"},
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
                "target": {"case_id": "CASE-A"},
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

    async def test_post_claim_mutation_is_refused_across_turns(self):
        responses = [
            completion([("call_1", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_2", "local-claim_done", {})]),
            completion([("call_3", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion(),
        ]
        output, observed, server, journal = await self.exercise(
            responses, names=("triage.get", "payer_intake_hub.confirm_decisions"), expect_failure=True)
        self.assertIsNone(output)
        self.assertEqual(server.calls, [("triage.get", {"case_id": "CASE-A"})])
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("task_already_claimed_mutation_forbidden", results["call_3"])
        self.assertTrue(journal.run["claim_done"])
        state = json.loads((self.root / "logs" / "task-state" / "task-state.json").read_text())
        self.assertIsNotNone(state["claim"])
        self.assertTrue(state["claim_violation"])
        log = json.loads((self.root / "logs" / "run_log.txt").read_text())
        self.assertEqual(log["status"], "incomplete")
        self.assertEqual(log["safe_error_code"], "chi_claim_violation")
        self.assertTrue(log["task_state_claim_violation"])

    async def test_search_other_case_is_refused(self):
        (self.workspace / "CASE-B" / "payer").mkdir(parents=True)
        (self.workspace / "CASE-B" / "payer" / "secret.md").write_text("secret policy\n", encoding="utf-8")
        responses = [
            completion([("call_1", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_2", "local-state-update", {"target": {"case_id": "CASE-A"}})]),
            completion([("call_3", "local-fs-search",
                         {"path": str(self.workspace / "CASE-B" / "payer"), "query": "secret"})]),
            completion(),
        ]
        output, observed, _, _ = await self.exercise(responses)
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("REFUSED: search_path_outside_allowlist", results["call_3"])

    async def test_workspace_search_without_target_is_refused(self):
        responses = [
            completion([("call_1", "local-fs-search",
                         {"path": str(self.workspace / "CASE-A" / "payer"), "query": "anything"})]),
            completion(),
        ]
        output, observed, _, _ = await self.exercise(responses)
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("REFUSED: search_path_outside_allowlist", results["call_1"])

    async def test_corrupt_single_file_search_returns_unreadable_error(self):
        (self.handbook / "bad.md").write_bytes(b"\xff\xfe\x00broken")
        responses = [
            completion([("call_1", "local-fs-search",
                         {"path": str(self.handbook / "bad.md"), "query": "anything"})]),
            completion(),
        ]
        output, observed, _, _ = await self.exercise(responses)
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("ERROR: search_unreadable", results["call_1"])

    async def test_damaged_pdf_search_returns_unreadable_error(self):
        (self.handbook / "bad.pdf").write_bytes(b"%PDF-corrupt")
        responses = [
            completion([("call_1", "local-fs-search",
                         {"path": str(self.handbook / "bad.pdf"), "query": "anything"})]),
            completion(),
        ]
        output, observed, _, _ = await self.exercise(responses)
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("ERROR: search_unreadable", results["call_1"])

    async def test_context_budget_exceeded_stops_before_send(self):
        tiny = {"schema": "chi-context-budget-v1", "max_chars": 10,
                "max_estimated_tokens": 10, "output_reserve_tokens": 1, "basis": "test"}
        output, observed, server, _ = await self.exercise(
            [completion()], expect_failure=True, context_budget=tiny)
        self.assertIsNone(output)
        self.assertEqual(observed, [])
        self.assertEqual(server.calls, [])
        log = json.loads((self.root / "logs" / "run_log.txt").read_text())
        self.assertEqual(log["status"], "incomplete")
        self.assertEqual(log["safe_error_code"], "chi_context_budget_exceeded")
        self.assertEqual(log["context_requests"], 0)

    async def test_unknown_write_can_be_read_back_and_resolved(self):
        responses = [
            completion([("call_1", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_2", "determination__get_summary", {"case_id": "CASE-A"})]),
            completion([("call_3", "local-state-update", {
                "target": {"case_id": "CASE-A"},
                "latest_business_status": {"text": "determined", "source_call_id": "call_2"},
                "resolve_unknown": [{"unknown_id": "u1", "source_call_id": "call_2",
                                     "note": "read after transport loss"}]})]),
            completion([("call_4", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, server, journal = await self.exercise(
            responses, names=("payer_intake_hub.confirm_decisions", "determination.get_summary"),
            fail="payer_intake_hub.confirm_decisions")
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("UNKNOWN_WRITE_EFFECT", results["call_1"])
        self.assertIn("task marked as done", results["call_4"])
        state = json.loads((self.root / "logs" / "task-state" / "task-state.json").read_text())
        self.assertEqual(state["unknowns"][0]["status"], "resolved")
        self.assertIsNotNone(state["claim"])
        self.assertEqual([call[0] for call in server.calls],
                         ["payer_intake_hub.confirm_decisions", "determination.get_summary"])

    async def test_unresolved_unknown_write_ends_incomplete(self):
        responses = [
            completion([("call_1", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion(),
        ]
        output, _, _, _ = await self.exercise(
            responses, names=("payer_intake_hub.confirm_decisions",),
            fail="payer_intake_hub.confirm_decisions", expect_failure=True)
        self.assertIsNone(output)
        log = json.loads((self.root / "logs" / "run_log.txt").read_text())
        self.assertEqual(log["status"], "incomplete")
        self.assertEqual(log["safe_error_code"], "chi_unknown_write_effect")
        state = json.loads((self.root / "logs" / "task-state" / "task-state.json").read_text())
        self.assertEqual(state["unknowns"][0]["status"], "open")

    async def test_write_is_blocked_while_unknown_is_open(self):
        responses = [
            completion([("call_1", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_2", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_3", "determination__get_summary", {"case_id": "CASE-A"})]),
            completion([("call_4", "local-state-update", {
                "target": {"case_id": "CASE-A"},
                "latest_business_status": {"text": "determined", "source_call_id": "call_3"},
                "resolve_unknown": [{"unknown_id": "u1", "source_call_id": "call_3",
                                     "note": "read after loss"}]})]),
            completion([("call_5", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, server, _ = await self.exercise(
            responses, names=("payer_intake_hub.confirm_decisions", "determination.get_summary"),
            fail="payer_intake_hub.confirm_decisions")
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("unknown_write_effect_pending", results["call_2"])
        self.assertEqual([call[0] for call in server.calls],
                         ["payer_intake_hub.confirm_decisions", "determination.get_summary"])

    async def test_repeated_write_is_refused(self):
        responses = [
            completion([("call_1", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_2", "payer_intake_hub__confirm_decisions", {"case_id": "CASE-A"})]),
            completion([("call_3", "determination__get_summary", {"case_id": "CASE-A"})]),
            completion([("call_4", "local-state-update", {
                "target": {"case_id": "CASE-A"},
                "latest_business_status": {"text": "determined", "source_call_id": "call_3"}})]),
            completion([("call_5", "local-claim_done", {})]),
            completion(),
        ]
        output, observed, server, _ = await self.exercise(
            responses, names=("payer_intake_hub.confirm_decisions", "determination.get_summary"))
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("repeated_write_forbidden", results["call_2"])
        self.assertEqual([call[0] for call in server.calls],
                         ["payer_intake_hub.confirm_decisions", "determination.get_summary"])

    async def test_repeated_read_warns_then_is_blocked(self):
        responses = [
            completion([("call_1", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_2", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_3", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_4", "triage__get", {"case_id": "CASE-A"})]),
            completion([("call_5", "triage__get", {"case_id": "CASE-A"})]),
            completion(),
        ]
        output, observed, server, _ = await self.exercise(responses)
        self.assertEqual(output, "done")
        results = {message.get("tool_call_id"): message.get("content")
                   for request in observed for message in request["messages"]
                   if message.get("role") == "tool"}
        self.assertIn("STAGNATION", results["call_3"])
        self.assertIn("stagnation_detected", results["call_5"])
        self.assertEqual(len(server.calls), 4)

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
