import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

from chi_agent.accounting.journal import ChiJournal
from chi_agent.agent.runtime_policy import TIME_POLICY
from chi_agent.agent.runtime import run_chi


class Result:
    isError = False
    structuredContent = {"items": []}
    content = []
    def model_dump(self, **kwargs):
        return {"structuredContent": self.structuredContent, "content": [], "isError": False}


class Server:
    def __init__(self, name):
        self.name = name
        self.calls = []
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_args):
        return False
    async def list_tools(self):
        return [SimpleNamespace(name=self.name, description="Synthetic read", inputSchema={"type": "object", "properties": {}, "additionalProperties": False})]
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return Result()


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_mixed_batch_refuses_all_then_model_continues(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval", task="t", attempt="a", run="run")
            instruction = root / "instruction.md"; instruction.write_text("Synthetic instruction")
            handbook, workspace = root / "handbook", root / "workspace"
            handbook.mkdir(); workspace.mkdir()
            server = Server("people.list_contacts")
            observed = []
            batch = [("local-fs-read", {"path": str(instruction)}), ("people__list_contacts", {}),
                     ("local-claim_done", {}), ("local-confirm-patient", {"patient_id": "p", "instruction_quote": "x", "chart_quote": "x"}),
                     ("people__list_contacts", {})]
            async def wire(request):
                body = json.loads(request.content); observed.append(body)
                if len(observed) == 1:
                    message = {"role": "assistant", "content": None, "reasoning_content": "reason", "tool_calls": [
                        {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                        for i, (name, args) in enumerate(batch)]}
                    finish = "tool_calls"
                else:
                    message, finish = {"role": "assistant", "content": "done"}, "stop"
                return httpx.Response(200, request=request, json={"id": "synthetic", "object": "chat.completion", "created": 0,
                    "model": "deepseek-v4.1-flash", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                              "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}})
            try:
                result = await run_chi(journal, "synthetic-secret", role="provider", instruction="Synthetic instruction",
                    mcp_url="http://synthetic.invalid/mcp", instruction_path=instruction, logs_dir=root / "logs",
                    workspace_root=workspace, handbook_root=handbook, tool_references=[], lower=httpx.MockTransport(wire),
                    server_factory=lambda _url: server)
                self.assertEqual(result, "done")
                self.assertEqual(server.calls, [])
                self.assertFalse(journal.run["claim_done"])
                self.assertEqual(len(observed), 2)
                results = [m for m in observed[1]["messages"] if m["role"] == "tool"]
                self.assertEqual({m["tool_call_id"] for m in results}, {f"call_{i}" for i in range(len(batch))})
                self.assertTrue(all("REFUSED: confirmation_must_be_called_alone" in str(m["content"]) for m in results))
                self.assertEqual([e["event"] for e in journal.run["tool_events"]], ["refused"] * len(batch))
                self.assertFalse(journal.run["patient_binding_events"])
                journal.finish("complete")
            finally:
                journal.close()

    async def test_three_role_sdk_tool_exchanges(self):
        for role, raw_name in (("provider", "people.list_contacts"), ("payer", "triage.get"), ("cm", "cm_chart.get_chart_data")):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval", task=role, attempt="a", run="run")
                instruction = root / "instruction.md"
                instruction.write_text("Synthetic instruction")
                handbook, workspace = root / "handbook", root / "workspace"
                handbook.mkdir(); workspace.mkdir()
                server = Server(raw_name)
                calls = []
                async def wire(request):
                    calls.append(request)
                    if len(calls) == 1:
                        message = {"role": "assistant", "content": None, "reasoning_content": "reason", "tool_calls": [
                            {"id": "call_1", "type": "function", "function": {"name": raw_name.replace(".", "__"), "arguments": "{}"}}]}
                        finish = "tool_calls"
                    else:
                        message = {"role": "assistant", "content": "synthetic complete"}
                        finish = "stop"
                    return httpx.Response(200, request=request, json={"id": "synthetic", "object": "chat.completion", "created": 0,
                        "model": "deepseek-v4.1-flash", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                                  "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}})
                try:
                    output = await run_chi(journal, "synthetic-secret", role=role, instruction="Synthetic instruction",
                        mcp_url="http://synthetic.invalid/mcp", instruction_path=instruction, logs_dir=root / "logs",
                        workspace_root=workspace, handbook_root=handbook, tool_references=[], lower=httpx.MockTransport(wire),
                        server_factory=lambda _url: server)
                    self.assertEqual(output, "synthetic complete")
                    self.assertEqual(server.calls, [(raw_name, {})])
                    self.assertEqual(len(calls), 2)
                    self.assertTrue((root / "logs" / "trace.jsonl").is_file())
                    journal.finish("complete")
                finally:
                    journal.close()

    async def test_provider_confirmation_shares_budget_and_refreshes_feedback(self):
        await self._exercise_confirmation(False)

    async def test_confirmation_truncation_returns_to_model_without_binding(self):
        await self._exercise_confirmation(True)

    async def _exercise_confirmation(self, truncated):
        import json
        patients = [{"id": "P1", "dob": "1970-01-01", "sex": "male"}]
        roster = {"items": patients, "total": 1}
        chart = {"patient": patients[0], "orders": [{"id": "O1", "patient_id": "P1"}],
                 "summaries": ["90 day treatment trial"]}
        class PatientServer(Server):
            async def list_tools(self):
                empty = {"type": "object", "properties": {}, "additionalProperties": False}
                chart_schema = {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"], "additionalProperties": False}
                return [SimpleNamespace(name="chart.search_patients", description="Search", inputSchema=empty),
                        SimpleNamespace(name="chart.get_patient_chart_by_patient", description="Chart", inputSchema=chart_schema)]
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                value = roster if name == "chart.search_patients" else chart
                return SimpleNamespace(isError=False, structuredContent=value, content=[],
                                       model_dump=lambda **_: {"structuredContent": value, "content": [], "isError": False})
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval", task="provider", attempt="a", run="run")
            instruction = root / "instruction.md"; instruction.write_text("90 day treatment trial")
            handbook, workspace = root / "handbook", root / "workspace"; handbook.mkdir(); workspace.mkdir()
            server = PatientServer("unused")
            calls = []
            timeouts = []
            async def wire(request):
                body = json.loads(request.content)
                calls.append(body)
                timeouts.append(dict(request.extensions['timeout']))
                index = len(calls)
                if "response_format" in body:
                    verdict = {"status": "unique_match", "selected_patient_id": "P1", "matches": ["P1"], "mismatches": [], "unknown": [],
                               "evidence": [{"instruction_quote": "90 day treatment trial", "chart_quote": "90 day treatment trial"}]}
                    message, finish = {"role": "assistant", "content": json.dumps(verdict)}, "length" if truncated else "stop"
                elif index < 4:
                    name, args = [("chart__search_patients", {}), ("chart__get_patient_chart_by_patient", {"patient_id": "P1"}),
                                  ("local-confirm-patient", {"patient_id": "P1", "instruction_quote": "90 day treatment trial", "chart_quote": "90 day treatment trial"})][index - 1]
                    message = {"role": "assistant", "content": None, "reasoning_content": "reason", "tool_calls": [{"id": "call_" + str(index), "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
                    finish = "tool_calls"
                else:
                    message, finish = {"role": "assistant", "content": "synthetic complete"}, "stop"
                return httpx.Response(200, request=request, json={"id": "synthetic", "object": "chat.completion", "created": 0,
                    "model": "deepseek-v4.1-flash", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                              "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}})
            try:
                await run_chi(journal, "synthetic-secret", role="provider", instruction="90 day treatment trial",
                    mcp_url="http://synthetic.invalid/mcp", instruction_path=instruction, logs_dir=root / "logs",
                    workspace_root=workspace, handbook_root=handbook, tool_references=[], lower=httpx.MockTransport(wire),
                    server_factory=lambda _url: server)
                self.assertEqual(len(calls), 5)
                self.assertEqual(calls[3]["max_tokens"], 32768)
                main_read = TIME_POLICY['main_read_seconds']
                confirmation_read = TIME_POLICY['confirmation_read_seconds']
                self.assertEqual([t['read'] for t in timeouts],
                                 [main_read, main_read, main_read, confirmation_read, main_read])
                self.assertTrue(all(t['connect'] == TIME_POLICY['connect_seconds']
                                    and t['write'] == TIME_POLICY['write_seconds']
                                    and t['pool'] == TIME_POLICY['pool_seconds'] for t in timeouts))
                self.assertIn("Already sent before this request: 4", calls[4]["messages"][0]["content"])
                self.assertEqual([item["purpose"] for item in journal.run["requests"]], ["main", "main", "main", "confirmation", "main"])
                self.assertTrue(any(e["event"] == "confirmation_result" for e in journal.run["patient_binding_events"]))
                if truncated:
                    result = next(e["result"] for e in journal.run["patient_binding_events"] if e["event"] == "confirmation_result")
                    self.assertEqual(result, {"status": "invalid", "reason": "confirmation_output_truncated"})
                    self.assertFalse(any(e["event"] == "patient_bound" for e in journal.run["patient_binding_events"]))
                    tool_result = next(m for m in calls[4]["messages"] if m.get("tool_call_id") == "call_3")
                    self.assertIn("confirmation_output_truncated", tool_result["content"])
                journal.finish("complete")
            finally:
                journal.close()

    async def test_mcp_business_error_reaches_model_without_retry(self):
        import json
        from mcp.types import CallToolResult, TextContent
        class ErrorServer(Server):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return CallToolResult(isError=True, content=[TextContent(type="text", text="validation: missing business prerequisite")])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval", task="provider", attempt="a", run="run")
            instruction = root / "instruction.md"; instruction.write_text("Synthetic instruction")
            handbook, workspace = root / "handbook", root / "workspace"; handbook.mkdir(); workspace.mkdir()
            server = ErrorServer("people.list_contacts")
            requests = []
            async def wire(request):
                requests.append(json.loads(request.content)); n = len(requests)
                if n < 3:
                    name = "people__list_contacts" if n == 1 else "local-claim_done"
                    message = {"role": "assistant", "content": None, "reasoning_content": "reason", "tool_calls": [
                        {"id": f"call_{n}", "type": "function", "function": {"name": name, "arguments": "{}"}}]}
                    finish = "tool_calls"
                else:
                    message, finish = {"role": "assistant", "content": "Unable to complete due to the prerequisite."}, "stop"
                return httpx.Response(200, request=request, json={"id": "synthetic", "object": "chat.completion", "created": 0,
                    "model": "deepseek-v4.1-flash", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                              "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}})
            try:
                output = await run_chi(journal, "synthetic-secret", role="provider", instruction="Synthetic instruction",
                    mcp_url="http://synthetic.invalid/mcp", instruction_path=instruction, logs_dir=root / "logs",
                    workspace_root=workspace, handbook_root=handbook, tool_references=[], lower=httpx.MockTransport(wire),
                    server_factory=lambda _url: server)
                self.assertIn("Unable to complete", output)
                self.assertEqual(server.calls, [("people.list_contacts", {})])
                tool = next(m for m in requests[1]["messages"] if m.get("tool_call_id") == "call_1")
                self.assertIn("validation: missing business prerequisite", tool["content"])
                self.assertTrue(json.loads(tool["content"])["isError"])
                self.assertEqual([(e["call_id"], e["event"]) for e in journal.run["tool_events"]],
                                 [("call_1", "started"), ("call_1", "returned_error"),
                                  ("call_2", "started"), ("call_2", "returned")])
                evidence = json.loads((root / "state" / "tool-evidence" / "run" / "call_1.json").read_text())
                self.assertIn("validation: missing business prerequisite", evidence["body_utf8"])
                self.assertFalse(journal.run["patient_binding_events"])
                self.assertTrue((root / "logs" / "run_log.txt").is_file())
                journal.finish("complete")
            finally:
                journal.close()
