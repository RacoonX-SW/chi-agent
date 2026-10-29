import json
import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal
from opencode_go_provider import GoFailure, SYSTEM, INSTRUCTION, SCHEMAS, DESCRIPTIONS
from request_budget import feedback

URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
SECRET = "synthetic-test-secret"
SESSION = "chi-" + "a" * 32
TOOLS = [{"type": "function", "function": {"name": "read", "description": "Read", "strict": False,
          "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}]
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
         "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}


def body(n=0):
    return {"model": "deepseek-v4.1-flash", "messages": [
        {"role": "system", "content": "system" + feedback(n, False)[0]},
        {"role": "user", "content": "instruction"}], "tools": TOOLS,
        "max_tokens": 8192, "thinking": {"type": "enabled"}, "reasoning_effort": "high"}


def request(data):
    return httpx.Request("POST", URL, headers={"Authorization": "Bearer " + SECRET,
                         "User-Agent": "chi-agent", "X-OpenCode-Session": SESSION}, json=data)


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_51_never_reaches_lower_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            for i in range(50):
                j.reserve(str(i).encode(), "main"); j.settle(USAGE)
            calls = []
            async def answer(req):
                calls.append(req)
                return httpx.Response(500, request=req)
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_request_invalid"):
                await guard.handle_async_request(request(body(49)))
            self.assertEqual(calls, [])
            self.assertEqual(len(j.run["requests"]), 50)
            j.finish("failed"); j.close()

    async def test_cancelled_send_persists_unknown_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            async def answer(_req):
                raise asyncio.CancelledError()
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaises(asyncio.CancelledError):
                await guard.handle_async_request(request(body()))
            self.assertIsNotNone(j.state["pending"])
            j.finish("failed"); j.close()
            with self.assertRaisesRegex(GoFailure, "chi_usage_unknown"):
                ChiJournal(root, identity="a" * 64, evaluation="e", task="other", attempt="b", run="s")

    async def test_coding_b_uses_same_guard_fixed_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="synthetic", attempt="a", run="r", kind="coding_b")
            btools = [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
                       "parameters": SCHEMAS[name], "strict": False}} for name in ("inspect_code", "verify_patch")]
            calls = []
            async def answer(req):
                calls.append(req)
                return httpx.Response(200, request=req, json={"usage": USAGE, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=btools,
                             system=SYSTEM, instruction=INSTRUCTION, claimed=lambda: False, confirmation=lambda: None)
            bbody = {"model": "deepseek-v4.1-flash", "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": INSTRUCTION}], "tools": btools, "max_tokens": 1024,
                     "thinking": {"type": "enabled"}, "reasoning_effort": "high"}
            with self.assertRaisesRegex(GoFailure, "chi_b_incomplete"):
                await guard.handle_async_request(request(bbody))
            self.assertEqual(len(calls), 1)
            self.assertEqual(j.run["requests"][0]["status"], "settled")
            j.finish("failed"); j.close()

    async def test_tool_result_replayed_and_requests_continue_past_six(self):
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            calls = []
            async def answer(req):
                number = len(calls)
                calls.append(req)
                msg = {"role": "assistant", "content": None, "reasoning_content": "reason",
                       "tool_calls": [{"id": f"call_{number}", "type": "function",
                                       "function": {"name": "read", "arguments": "{}"}}]}
                return httpx.Response(200, request=req, json={"usage": USAGE,
                    "model": "deepseek-v4.1-flash", "choices": [{"finish_reason": "tool_calls", "message": msg}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            history = []
            for i in range(7):
                data = body(i)
                data["messages"].extend(history)
                await guard.handle_async_request(request(data))
                assistant = guard.contract.batches[-1]["message"]
                call_id = assistant["tool_calls"][0]["id"]
                guard.contract.record_result(call_id, "observed")
                history.extend([assistant, {"role": "tool", "tool_call_id": call_id, "content": "observed"}])
            self.assertEqual(len(calls), 7)
            j.finish("complete"); j.close()

    async def test_known_usage_settled_before_invalid_content(self):
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            async def answer(req):
                return httpx.Response(200, request=req, json={"usage": USAGE, "model": "wrong", "choices": []})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_response_invalid"):
                await guard.handle_async_request(request(body()))
            self.assertIsNone(j.state["pending"])
            self.assertEqual(j.run["requests"][0]["status"], "settled")
            j.finish("failed"); j.close()

    async def test_stale_feedback_is_rejected_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            calls = []
            async def answer(req):
                calls.append(req)
                return httpx.Response(500, request=req)
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_request_invalid"):
                await guard.handle_async_request(request(body(1)))
            self.assertFalse(calls)
            self.assertFalse(j.run["requests"])
            j.finish("failed"); j.close()


if __name__ == "__main__":
    unittest.main()
