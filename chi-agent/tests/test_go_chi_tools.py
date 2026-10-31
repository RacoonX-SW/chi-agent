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
