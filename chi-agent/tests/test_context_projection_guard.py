import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from go_chi_assembly import truncate_tool_text
from go_chi_context import DEFAULT_BUDGET_V3, measure_request
from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal
from opencode_go_provider import GoFailure
from request_budget import feedback
from test_go_chi_guard import SECRET, SESSION, TOOLS, USAGE, URL, body, request


def assistant(call_id):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": "read", "arguments": "{}"}}]}


def source_body():
    data = body()
    data["messages"] = data["messages"][:2]
    for index in range(1, 4):
        data["messages"].append(assistant(f"c{index}"))
        data["messages"].append({"role": "tool", "tool_call_id": f"c{index}",
                                 "content": f"tool result {index} " + "x" * 4000})
    return data


class GuardProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_projection_preserves_source_validation_and_records_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity="a" * 64, evaluation="e", task="t",
                                 attempt="a", run="r",
                                 launch={"context_policy": "chi-context-v3"})
            data = source_body()
            limit = dict(DEFAULT_BUDGET_V3)
            upper = measure_request(data, budget=limit)["estimated_tokens_upper"]
            limit["max_input_tokens"] = upper - 1
            sent = []

            async def answer(req):
                sent.append(json.loads(req.content))
                return httpx.Response(200, request=req, json={
                    "model": "deepseek-v4.1-flash", "usage": USAGE,
                    "choices": [{"finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "done"}}]})

            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer),
                             tools=TOOLS, system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None,
                             canonical_tools={"read": "local-fs-read"},
                             context_limit=limit)
            for index in range(1, 4):
                call_id = f"c{index}"
                message = assistant(call_id)
                text = f"tool result {index} " + "x" * 4000
                guard.contract.accept_batch(message)
                guard.contract.record_result(call_id, text)
                journal.start_tool(call_id, "read", {})
                journal.record_tool(call_id, "read", text)
            await guard.handle_async_request(request(data))
            self.assertEqual(len(sent), 1)
            wire = sent[0]
            self.assertEqual(wire["messages"][-1]["role"], "tool")
            self.assertIn("chi-tool-result-ref-v1", wire["messages"][3]["content"])
            self.assertIn("tool result 2", wire["messages"][5]["content"])
            entry = journal.run["requests"][0]
            self.assertIn("projection", entry)
            self.assertEqual(entry["projection"]["schema"], "chi-context-assembly-v1")
            self.assertGreater(entry["projection"]["saved_bytes"], 0)
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            from go_chi_journal import inspect_history
            self.assertEqual(inspect_history(root, "a" * 64,
                                             __import__("hashlib").sha256(raw).hexdigest())["status"],
                             "inspected")

    async def test_replay_includes_refused_and_failed_tool_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity="a" * 64, evaluation="e", task="t",
                                 attempt="a", run="r",
                                 launch={"context_policy": "chi-context-v3",
                                         "source_evidence_policy": "canonical-v1"})
            data = source_body()
            # Replace the three read batches with one refused mutation and one failed read.
            data["messages"] = data["messages"][:2]
            data["messages"].extend([
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "bad1", "type": "function",
                                 "function": {"name": "write", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "bad1", "content": "REFUSED: blocked"},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "bad2", "type": "function",
                                 "function": {"name": "read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "bad2", "content": "ERROR: unavailable"},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "ok3", "type": "function",
                                 "function": {"name": "read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "ok3", "content": "latest result"},
            ])
            tools = copy.deepcopy(TOOLS)
            tools.append({"type": "function", "function": {
                "name": "write", "description": "Write", "strict": False,
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}})
            data["tools"] = tools
            sent = []

            async def answer(req):
                sent.append(json.loads(req.content))
                return httpx.Response(200, request=req, json={
                    "model": "deepseek-v4.1-flash", "usage": USAGE,
                    "choices": [{"finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "done"}}]})

            anchor_doc = {"text": '{"schema":"chi-intent-anchor-v1"}',
                          "sha256": hashlib.sha256(b'{"schema":"chi-intent-anchor-v1"}').hexdigest()}
            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer),
                             tools=tools, system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None,
                             canonical_tools={"read": "local-fs-read", "write": "local-fs-write"},
                             context_limit=dict(DEFAULT_BUDGET_V3,
                                                max_input_tokens=measure_request(
                                                    data, budget=DEFAULT_BUDGET_V3)["estimated_tokens_upper"] * 2),
                             anchor_getter=lambda: anchor_doc)
            guard.contract.accept_batch(data["messages"][2])
            guard.contract.record_result("bad1", "REFUSED: blocked")
            journal.refuse_tool("bad1", "write", {}, "REFUSED: blocked")
            guard.contract.accept_batch(data["messages"][4])
            guard.contract.record_result("bad2", "ERROR: unavailable")
            journal.start_tool("bad2", "local-fs-read", {})
            journal.record_tool("bad2", "local-fs-read", "ERROR: unavailable", event="failed")
            guard.contract.accept_batch(data["messages"][6])
            guard.contract.record_result("ok3", "latest result")
            journal.start_tool("ok3", "local-fs-read", {})
            journal.record_tool("ok3", "local-fs-read", "latest result")
            await guard.handle_async_request(request(data))
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            from go_chi_journal import inspect_history
            self.assertEqual(inspect_history(root, "a" * 64,
                                             hashlib.sha256(raw).hexdigest())["status"], "inspected")

    async def test_projection_uses_full_evidence_hash_not_visible_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity="a" * 64, evaluation="e", task="t",
                                 attempt="a", run="r",
                                 launch={"context_policy": "chi-context-v3"})
            full = "full " + "x" * 9000
            visible, _ = truncate_tool_text(full, tool="local-fs-read")
            data = body()
            data["messages"] = data["messages"][:2]
            data["messages"].extend([assistant("c1"), {"role": "tool", "tool_call_id": "c1",
                                                       "content": visible}])
            for index in (2, 3):
                data["messages"].extend([assistant(f"c{index}"),
                                         {"role": "tool", "tool_call_id": f"c{index}",
                                          "content": f"small {index}"}])
            sent = []

            async def answer(req):
                sent.append(json.loads(req.content))
                return httpx.Response(200, request=req, json={
                    "model": "deepseek-v4.1-flash", "usage": USAGE,
                    "choices": [{"finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "done"}}]})

            anchor = {"text": '{"schema":"chi-intent-anchor-v1"}', "sha256":
                      hashlib.sha256(b'{"schema":"chi-intent-anchor-v1"}').hexdigest()}
            limit = dict(DEFAULT_BUDGET_V3, max_input_tokens=1000)
            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer),
                             tools=TOOLS, system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None,
                             canonical_tools={"read": "local-fs-read"},
                             context_limit=limit,
                             anchor_getter=lambda: anchor)
            guard.contract.accept_batch(assistant("c1"))
            guard.contract.record_result("c1", visible)
            guard.record_full_result("c1", full)
            for index in (2, 3):
                guard.contract.accept_batch(assistant(f"c{index}"))
                guard.contract.record_result(f"c{index}", f"small {index}")
            await guard.handle_async_request(request(data))
            tool_message = sent[0]["messages"][4]
            placeholder = json.loads(tool_message["content"])
            self.assertEqual(placeholder["result_sha256"],
                             hashlib.sha256(full.encode()).hexdigest())
            self.assertNotEqual(placeholder["result_sha256"],
                                hashlib.sha256(visible.encode()).hexdigest())
            journal.finish("failed")
            journal.close()

    async def test_anchor_is_injected_at_index_two_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity="a" * 64, evaluation="e", task="t",
                                 attempt="a", run="r",
                                 launch={"context_policy": "chi-context-v3"})
            data = source_body()
            sent = []
            text = '{"schema":"chi-intent-anchor-v1","current_step":"x"}'
            anchor = {"text": text,
                      "sha256": hashlib.sha256(text.encode()).hexdigest()}

            async def answer(req):
                sent.append(json.loads(req.content))
                return httpx.Response(200, request=req, json={
                    "model": "deepseek-v4.1-flash", "usage": USAGE,
                    "choices": [{"finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "done"}}]})

            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer),
                             tools=TOOLS, system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None,
                             canonical_tools={"read": "local-fs-read"},
                             context_limit=DEFAULT_BUDGET_V3,
                             anchor_getter=lambda: anchor)
            for index in range(1, 4):
                call_id = f"c{index}"
                guard.contract.accept_batch(assistant(call_id))
                guard.contract.record_result(call_id, f"tool result {index} " + "x" * 4000)
            await guard.handle_async_request(request(data))
            self.assertEqual(sent[0]["messages"][2],
                             {"role": "user", "content": anchor["text"]})
            self.assertIn("tool result 1", sent[0]["messages"][4]["content"])
            self.assertNotIn("chi-tool-result-ref-v1", sent[0]["messages"][4]["content"])
            entry = journal.run["requests"][0]
            self.assertEqual(entry["projection"]["anchor_sha256"], anchor["sha256"])
            journal.finish("failed")
            journal.close()


class FullResultLimitTests(unittest.TestCase):
    def test_total_limit_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e",
                                 task="t", attempt="a", run="r",
                                 launch={"context_policy": "chi-context-v3"})
            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(lambda r: r),
                             tools=TOOLS, system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None)
            with patch("go_chi_guard.MAX_FULL_RESULTS_TOTAL_BYTES", 10):
                guard.record_full_result("c1", "123456")
                with self.assertRaises(GoFailure) as caught:
                    guard.record_full_result("c2", "123456")
                self.assertEqual(caught.exception.code, "chi_context_assembly_limit")
            with self.assertRaises(GoFailure) as caught:
                guard.record_full_result("c3", "x" * (8 * 1024 * 1024 + 1))
            self.assertEqual(caught.exception.code, "chi_tool_event_invalid")
            journal.finish("failed")
            journal.close()


if __name__ == "__main__":
    unittest.main()
