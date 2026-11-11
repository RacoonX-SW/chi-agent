import json
import unittest
from types import SimpleNamespace

from agents.models.openai_chatcompletions import Converter
from go_chi_contract import ToolContract
from go_chi_mcp import MCPBridge, selected_server
from opencode_go_provider import GoFailure


class FakeResult:
    isError = False
    structuredContent = None
    content = []
    def model_dump(self, **kwargs):
        return {"content": [{"type": "text", "text": "observed"}], "isError": False}


class FakeServer:
    def __init__(self):
        self.calls = []
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return FakeResult()


class FakeBinding:
    def __init__(self):
        self.batch_refusals = {}
        self.poisoned = False
        self.observed = []
    def check(self, name, args):
        pass
    def observe(self, call_id, name, args, response):
        self.observed.append((call_id, name))


def tool(name):
    return SimpleNamespace(name=name, description="Read", inputSchema={"type": "object", "properties": {}, "additionalProperties": False})


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_error_result_is_returned_without_poison_or_observation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mcp.types import CallToolResult, TextContent
        from go_chi_journal import ChiJournal
        class BusinessError(FakeServer):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return CallToolResult(isError=True, content=[TextContent(type="text", text="validation: missing business prerequisite")])
        with TemporaryDirectory() as d:
            journal = ChiJournal(Path(d), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            server, binding = BusinessError(), FakeBinding()
            bridge = MCPBridge(server, "provider", [tool("chart.search_patients")], binding=binding)
            bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]), journal=journal, secret="secret", session="session")
            call = {"id": "x", "type": "function", "function": {"name": "chart__search_patients", "arguments": "{}"}}
            bridge.guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "r", "tool_calls": [call]})
            result = await bridge.invoke("chart__search_patients", "{}")
            self.assertIn("validation: missing business prerequisite", result)
            self.assertFalse(binding.poisoned)
            self.assertEqual(binding.observed, [])
            self.assertEqual(len(server.calls), 1)
            self.assertEqual([event["event"] for event in journal.run["tool_events"]], ["started", "returned_error"])
            journal.finish("failed"); journal.close()

    async def test_structured_and_text_result_is_returned_once(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mcp.types import CallToolResult, TextContent
        from go_chi_journal import ChiJournal
        payload = {"items": [{"id": "PAT-1", "name": "A"}], "total": 1}
        text = json.dumps(payload, indent=2)
        class Rich(FakeServer):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return CallToolResult(isError=False,
                                      content=[TextContent(type="text", text=text)],
                                      structuredContent=payload)
        with TemporaryDirectory() as d:
            journal = ChiJournal(Path(d), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            server, binding = Rich(), FakeBinding()
            bridge = MCPBridge(server, "provider", [tool("chart.search_patients")], binding=binding)
            bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]),
                                           journal=journal, secret="secret", session="session")
            call = {"id": "x", "type": "function", "function": {"name": "chart__search_patients", "arguments": "{}"}}
            bridge.guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "r", "tool_calls": [call]})
            result = await bridge.invoke("chart__search_patients", "{}")
            self.assertEqual(result, text)
            self.assertEqual(result.count('"items"'), 1)
            evidence = json.loads((Path(d) / "tool-evidence" / "r" / "x.json").read_text())
            self.assertEqual(evidence["body_utf8"], text)
            self.assertIsNone(evidence["redaction"])
            journal.finish("failed"); journal.close()

    async def test_differing_structured_and_text_are_both_preserved(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mcp.types import CallToolResult, TextContent
        from go_chi_journal import ChiJournal
        payload = {"items": [], "total": 0}
        text = "human summary"
        class Mixed(FakeServer):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return CallToolResult(isError=False,
                                      content=[TextContent(type="text", text=text)],
                                      structuredContent=payload)
        with TemporaryDirectory() as d:
            journal = ChiJournal(Path(d), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            server, binding = Mixed(), FakeBinding()
            bridge = MCPBridge(server, "provider", [tool("chart.search_patients")], binding=binding)
            bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]),
                                           journal=journal, secret="secret", session="session")
            call = {"id": "x", "type": "function", "function": {"name": "chart__search_patients", "arguments": "{}"}}
            bridge.guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "r", "tool_calls": [call]})
            result = await bridge.invoke("chart__search_patients", "{}")
            self.assertIn(text, result)
            self.assertIn('"total": 0', result)
            journal.finish("failed"); journal.close()

    async def test_uncertain_backend_failure_records_start_and_failure_and_poisons(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from go_chi_journal import ChiJournal
        class Broken(FakeServer):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                raise OSError("synthetic transport failure")
        with TemporaryDirectory() as d:
            journal = ChiJournal(Path(d), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            server, binding = Broken(), FakeBinding()
            bridge = MCPBridge(server, "provider", [tool("chart.search_patients")], binding=binding)
            bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]), journal=journal, secret="secret", session="session")
            call = {"id": "x", "type": "function", "function": {"name": "chart__search_patients", "arguments": "{}"}}
            bridge.guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "r", "tool_calls": [call]})
            with self.assertRaises(OSError):
                await bridge.invoke("chart__search_patients", "{}")
            self.assertTrue(binding.poisoned)
            self.assertEqual([event["event"] for event in journal.run["tool_events"]], ["started", "failed"])
            self.assertEqual(len(server.calls), 1)
            journal.finish("failed"); journal.close()

    async def test_unbound_provider_write_is_refused_without_backend_effect(self):
        from patient_identity_binding import PatientBinding
        class Journal:
            run_doc = {}
            def _persist(self): pass
            def record_tool(self, *_args, **_kwargs): pass
            def start_tool(self, *_args): pass
            def refuse_tool(self, *_args, **_kwargs): pass
        server = FakeServer()
        binding = PatientBinding("synthetic instruction", Journal())
        entry = SimpleNamespace(name="cases.create_from_order", description="Create", inputSchema={
            "type": "object", "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"], "additionalProperties": False})
        bridge = MCPBridge(server, "provider", [entry], binding=binding)
        bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]), journal=Journal(), secret="secret", session="session")
        call = {"id": "x", "type": "function", "function": {"name": "cases__create_from_order", "arguments": '{"patient_id":"P1"}'}}
        parsed = bridge.guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "r", "tool_calls": [call]})
        bridge.batch(parsed)
        result = await bridge.invoke("cases__create_from_order", '{"patient_id":"P1"}')
        self.assertTrue(result.startswith("REFUSED:"))
        self.assertEqual(server.calls, [])

    async def test_selected_role_and_validated_dispatch(self):
        server, binding = FakeServer(), FakeBinding()
        bridge = MCPBridge(server, "provider", [tool("chart.search_patients")], binding=binding)
        bridge.guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in bridge.tools]), secret="secret", session="session",
                                       journal=SimpleNamespace(record_tool=lambda *_, **_kw: None,
                                                               start_tool=lambda *_: None,
                                                               refuse_tool=lambda *_, **_kw: None))
        call = {"id": "x", "type": "function", "function": {"name": "chart__search_patients", "arguments": "{}"}}
        parsed = bridge.guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "x", "tool_calls": [call]})
        bridge.batch(parsed)
        result = await bridge.invoke("chart__search_patients", "{}")
        self.assertIn("observed", result)
        self.assertEqual(server.calls, [("chart.search_patients", {})])
        self.assertEqual(binding.observed, [("x", "chart.search_patients")])
        with self.assertRaisesRegex(GoFailure, "chi_mcp_call_unvalidated"):
            await bridge.invoke("chart__search_patients", "{}")

    async def test_roles_cannot_be_swapped(self):
        with self.assertRaisesRegex(GoFailure, "chi_mcp_role_mismatch"):
            MCPBridge(FakeServer(), "payer", [tool("chart.search_patients")])
        payer = MCPBridge(FakeServer(), "payer", [tool("triage__get")])
        cm = MCPBridge(FakeServer(), "cm", [tool("cm_chart-get_chart_data")])
        self.assertEqual(len(payer.tools), 1)
        self.assertEqual(len(cm.tools), 1)

    async def test_retry_configuration(self):
        server = selected_server("http://synthetic.invalid:8020/mcp")
        self.assertEqual(server.max_retry_attempts, 0)
