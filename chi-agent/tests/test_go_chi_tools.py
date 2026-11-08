import asyncio
import contextvars
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents.models.openai_chatcompletions import Converter
from go_chi_contract import ToolContract
from go_chi_state import TaskState
from go_chi_tools import local_tools
from opencode_go_provider import GoFailure


class Journal:
    def record_claim(self):
        pass
    def record_tool(self, *_args, **_kwargs):
        pass
    def start_tool(self, *_args):
        pass
    def refuse_tool(self, *_args, **_kwargs):
        pass


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_payer_cannot_write_provider_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / "workspace"
            (workspace / "case" / "provider").mkdir(parents=True)
            (workspace / "case" / "payer").mkdir()
            handbook = root / "handbook"
            handbook.mkdir()
            instruction = root / "instruction.md"
            instruction.write_text("synthetic")
            holder = {}
            tools = local_tools(role="payer", workspace_root=workspace, instruction_path=instruction,
                tool_references=[], handbook_root=handbook, journal=Journal(), binding=None,
                guard_getter=lambda: holder["guard"], client_getter=lambda: None,
                confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[], dispatch_lock=asyncio.Lock())
            guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in tools]), secret="secret", session="session")
            holder["guard"] = guard
            path = str(workspace / "case" / "provider" / "result.txt")
            import json
            args = {"path": path, "content": "bad"}
            guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function", "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            result = await write.on_invoke_tool(None, json.dumps(args))
            self.assertTrue(result.startswith("REFUSED:"))
            self.assertFalse(Path(path).exists())

    async def test_failed_local_write_keeps_case_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / "workspace"
            (workspace / "CASE-A" / "payer" / "sub").mkdir(parents=True)
            handbook = root / "handbook"
            handbook.mkdir()
            instruction = root / "instruction.md"
            instruction.write_text("synthetic")
            state = TaskState(root / "state", run="run_1", role="payer")
            holder = {}
            tools = local_tools(role="payer", workspace_root=workspace, instruction_path=instruction,
                tool_references=[], handbook_root=handbook, journal=Journal(), binding=None,
                guard_getter=lambda: holder["guard"], client_getter=lambda: None,
                confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[],
                dispatch_lock=asyncio.Lock(), state=state, capabilities="f0-f3-v1")
            guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in tools]),
                                    secret="secret", session="session")
            holder["guard"] = guard
            path = str(workspace / "CASE-A" / "payer" / "sub")
            import json
            args = {"path": path, "content": "x"}
            guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            with self.assertRaises(GoFailure):
                await write.on_invoke_tool(None, json.dumps(args))
            observation = state.data["observations"][-1]
            self.assertEqual(observation["effect"], "mutation")
            self.assertEqual(observation["event"], "failed")
            self.assertEqual(observation["scope"], "case:CASE-A")

    async def test_state_update_schema_accepts_null_target_fields(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / "workspace"; workspace.mkdir()
            handbook = root / "handbook"; handbook.mkdir()
            instruction = root / "instruction.md"; instruction.write_text("synthetic")
            state = TaskState(root / "state", run="run", role="payer")
            holder = {}
            tools = local_tools(role="payer", workspace_root=workspace, instruction_path=instruction,
                tool_references=[], handbook_root=handbook, journal=Journal(), binding=None,
                guard_getter=lambda: holder["guard"], client_getter=lambda: None,
                confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[],
                dispatch_lock=asyncio.Lock(), state=state, capabilities="f0-f3-v1")
            guard = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in tools]),
                                    secret="secret", session="session")
            holder["guard"] = guard
            import json
            args = {"target": {"case_id": None}}
            guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-state-update", "arguments": json.dumps(args)}}]})
            update = next(t for t in tools if t.name == "local-state-update")
            props = update.params_json_schema["properties"]["target"]["properties"]
            self.assertEqual(props["case_id"]["type"], ["string", "null"])
            self.assertNotIn("patient_id", props)
            guard.contract.record_result("c", "updated")
            guard.contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "d", "type": "function",
                                "function": {"name": "local-state-update",
                                             "arguments": json.dumps({"target": {"case_id": "CASE-A",
                                                                                 "patient_id": "PAT-1"}})}}]},
                recover_schema=True)
            self.assertIn("patient_id", guard.contract.refusals["d"])

    async def test_context_v3_state_update_schema_is_model_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / "workspace"; workspace.mkdir()
            handbook = root / "handbook"; handbook.mkdir()
            instruction = root / "instruction.md"; instruction.write_text("synthetic")
            state = TaskState(root / "state", run="run", role="payer",
                              context_policy="chi-context-v3")
            holder = {}
            tools = local_tools(role="payer", workspace_root=workspace, instruction_path=instruction,
                tool_references=[], handbook_root=handbook, journal=Journal(), binding=None,
                guard_getter=lambda: holder["guard"], client_getter=lambda: None,
                confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[],
                dispatch_lock=asyncio.Lock(), state=state, capabilities="f0-f3-v1",
                context_policy="chi-context-v3")
            update = next(t for t in tools if t.name == "local-state-update")
            props = update.params_json_schema["properties"]
            self.assertNotIn("facts", props)
            self.assertNotIn("target", props)
            self.assertIn("plans", props)

    async def test_provider_target_schema_includes_patient_id(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / "workspace"; workspace.mkdir()
            handbook = root / "handbook"; handbook.mkdir()
            instruction = root / "instruction.md"; instruction.write_text("synthetic")
            state = TaskState(root / "state", run="run", role="provider")
            holder = {}
            tools = local_tools(role="provider", workspace_root=workspace, instruction_path=instruction,
                tool_references=[], handbook_root=handbook, journal=Journal(), binding=SimpleNamespace(),
                guard_getter=lambda: holder["guard"], client_getter=lambda: None,
                confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[],
                dispatch_lock=asyncio.Lock(), state=state, capabilities="f0-f3-v1")
            update = next(t for t in tools if t.name == "local-state-update")
            props = update.params_json_schema["properties"]["target"]["properties"]
            self.assertIn("patient_id", props)
            self.assertEqual(props["patient_id"]["type"], ["string", "null"])

    async def test_payer_target_schema_omits_patient_id(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / "workspace"; workspace.mkdir()
            handbook = root / "handbook"; handbook.mkdir()
            instruction = root / "instruction.md"; instruction.write_text("synthetic")
            state = TaskState(root / "state", run="run", role="payer")
            holder = {}
            tools = local_tools(role="payer", workspace_root=workspace, instruction_path=instruction,
                tool_references=[], handbook_root=handbook, journal=Journal(), binding=None,
                guard_getter=lambda: holder["guard"], client_getter=lambda: None,
                confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[],
                dispatch_lock=asyncio.Lock(), state=state, capabilities="f0-f3-v1")
            update = next(t for t in tools if t.name == "local-state-update")
            props = update.params_json_schema["properties"]["target"]["properties"]
            self.assertIn("case_id", props)
            self.assertNotIn("patient_id", props)


class WorkspaceWriteTests(unittest.IsolatedAsyncioTestCase):
    def _tools(self, root, role, workspace, state=None, binding=None):
        handbook = root / "handbook"; handbook.mkdir(exist_ok=True)
        instruction = root / "instruction.md"; instruction.write_text("synthetic")
        holder = {}
        tools = local_tools(role=role, workspace_root=workspace, instruction_path=instruction,
            tool_references=[], handbook_root=handbook, journal=Journal(), binding=binding,
            guard_getter=lambda: holder["guard"], client_getter=lambda: None,
            confirmation_context=contextvars.ContextVar("test", default=None), exchanges=[],
            dispatch_lock=asyncio.Lock(), state=state, capabilities="f0-f3-v1")
        holder["guard"] = SimpleNamespace(contract=ToolContract([Converter.tool_to_openai(t) for t in tools]),
                                          secret="secret", session="session")
        return tools, holder

    async def test_write_creates_missing_parent_directories(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace = root / "workspace"; workspace.mkdir()
            state = TaskState(root / "state", run="run_1", role="cm")
            tools, holder = self._tools(root, "cm", workspace, state=state)
            (workspace / "CASE-A").mkdir()
            path = str(workspace / "CASE-A" / "cm" / "notes" / "deep" / "letter.md")
            args = {"path": path, "content": "written"}
            holder["guard"].contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            self.assertEqual(await write.on_invoke_tool(None, json.dumps(args)), "workspace file written")
            self.assertEqual(Path(path).read_text(), "written")

    async def test_cm_write_bootstraps_missing_case_root(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace = root / "workspace"; workspace.mkdir()
            state = TaskState(root / "state", run="run_1", role="cm")
            state.observe(call_id="call_1", tool="cm_chart.get_chart_data", kind="mcp",
                          arguments={"case_id": "CM-CASE-X"}, result="ok")
            tools, holder = self._tools(root, "cm", workspace, state=state)
            path = workspace / "CM-CASE-X" / "cm" / "note.md"
            args = {"path": str(path), "content": "written"}
            holder["guard"].contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            self.assertEqual(await write.on_invoke_tool(None, json.dumps(args)), "workspace file written")
            self.assertEqual(path.read_text(), "written")

    async def test_cm_write_rejects_unobserved_case_root(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace = root / "workspace"; workspace.mkdir()
            state = TaskState(root / "state", run="run_1", role="cm")
            tools, holder = self._tools(root, "cm", workspace, state=state)
            path = workspace / "CM-CASE-X" / "cm" / "note.md"
            args = {"path": str(path), "content": "written"}
            holder["guard"].contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            self.assertTrue((await write.on_invoke_tool(None, json.dumps(args))).startswith("REFUSED:"))
            self.assertFalse((workspace / "CM-CASE-X").exists())

    async def test_write_refuses_case_directory_that_does_not_exist(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace = root / "workspace"; workspace.mkdir()
            state = TaskState(root / "state", run="run_1", role="cm")
            tools, holder = self._tools(root, "cm", workspace, state=state)
            path = str(workspace / "CASE-FAKE" / "cm" / "letter.md")
            args = {"path": path, "content": "x"}
            holder["guard"].contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            result = await write.on_invoke_tool(None, json.dumps(args))
            self.assertTrue(result.startswith("REFUSED:"))
            self.assertFalse((workspace / "CASE-FAKE").exists())

    async def test_write_does_not_follow_symlinked_role_directory(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace = root / "workspace"; outside = root / "outside"
            workspace.mkdir(); outside.mkdir()
            (workspace / "CASE-A").mkdir()
            (workspace / "CASE-A" / "cm").symlink_to(outside)
            state = TaskState(root / "state", run="run_1", role="cm")
            tools, holder = self._tools(root, "cm", workspace, state=state)
            path = str(workspace / "CASE-A" / "cm" / "letter.md")
            args = {"path": path, "content": "leak"}
            holder["guard"].contract.accept_batch({"role": "assistant", "content": None, "reasoning_content": "reason",
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {"name": "local-fs-write", "arguments": json.dumps(args)}}]})
            write = next(t for t in tools if t.name == "local-fs-write")
            result = await write.on_invoke_tool(None, json.dumps(args))
            self.assertTrue(result.startswith(("ERROR:", "REFUSED:")))
            self.assertFalse((outside / "letter.md").exists())
