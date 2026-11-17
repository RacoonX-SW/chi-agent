import json
import hashlib
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from chi_agent.models.request_guard import ChiGuard
from chi_agent.accounting.journal import ChiJournal
from chi_agent.models.opencode_go_provider import GoFailure, SYSTEM, INSTRUCTION, SCHEMAS, DESCRIPTIONS
from chi_agent.agent.runtime_policy import TIME_POLICY
from chi_agent.accounting.request_budget import feedback

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
    def test_main_read_window_covers_measured_generations(self):
        self.assertGreaterEqual(TIME_POLICY["main_read_seconds"], 180)
        self.assertGreater(TIME_POLICY["main_io_seconds"], TIME_POLICY["main_read_seconds"])
        self.assertGreater(TIME_POLICY["confirmation_read_seconds"], TIME_POLICY["main_read_seconds"])
        self.assertLess(TIME_POLICY["main_io_seconds"], TIME_POLICY["chi_admission_seconds"])
        self.assertLess(TIME_POLICY["chi_operator_seconds"], TIME_POLICY["operator_max_seconds"])

    async def test_purpose_timeouts_and_dispatch_evidence(self):
        for confirmation in (False, True):
            with self.subTest(confirmation=confirmation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
                seen = []
                async def answer(req):
                    seen.append(req.extensions['timeout'])
                    return httpx.Response(200, request=req, json={'usage': USAGE, 'model': 'deepseek-v4.1-flash',
                        'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'done'}}]})
                guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                    system='system', instruction='instruction', claimed=lambda: False,
                    confirmation=lambda: ('prompt', 'evidence') if confirmation else None)
                data = body()
                if confirmation:
                    data.update(messages=[{'role': 'system', 'content': 'prompt'}, {'role': 'user', 'content': 'evidence'}],
                                max_tokens=32768, response_format={'type': 'json_object'})
                    del data['tools']
                await guard.handle_async_request(request(data))
                self.assertEqual(seen, [{'connect': TIME_POLICY['connect_seconds'],
                    'read': TIME_POLICY['confirmation_read_seconds' if confirmation else 'main_read_seconds'],
                    'write': TIME_POLICY['write_seconds'], 'pool': TIME_POLICY['pool_seconds']}])
                doc = json.loads((root / 'wire-evidence/r/001-request.json').read_text())
                self.assertEqual(doc['dispatch']['purpose'], 'confirmation' if confirmation else 'main')
                self.assertEqual(doc['dispatch']['session_sha256'], hashlib.sha256(SESSION.encode()).hexdigest())
                self.assertEqual(doc['dispatch']['body_bytes'], len(doc['body_utf8'].encode()))
                self.assertNotIn(SESSION, json.dumps(doc))
                j.finish('failed'); j.close()
                next_j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='b', run='s')
                next_j.finish('failed'); next_j.close()

    async def test_wall_timeout_and_admission_are_distinct(self):
        from chi_agent.agent.runtime_policy import TIME_POLICY
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
            calls = []
            async def answer(req):
                calls.append(req)
                await asyncio.sleep(0.1)
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                system='system', instruction='instruction', claimed=lambda: False, confirmation=lambda: None)
            with patch.dict(TIME_POLICY, {'main_io_seconds': 0.01}):
                with self.assertRaisesRegex(GoFailure, 'chi_timeout'):
                    await guard.handle_async_request(request(body()))
            self.assertEqual(len(calls), 1)
            self.assertIsNotNone(j.state['pending'])
            j.finish('failed', guard.error); j.close()

    async def test_confirmation_wall_timeout_preserves_pending(self):
        from chi_agent.agent.runtime_policy import TIME_POLICY
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
            async def answer(_req): await asyncio.sleep(0.1)
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                system='system', instruction='instruction', claimed=lambda: False, confirmation=lambda: ('prompt', 'evidence'))
            data = body(); del data['tools']
            data.update(messages=[{'role': 'system', 'content': 'prompt'}, {'role': 'user', 'content': 'evidence'}],
                        max_tokens=32768, response_format={'type': 'json_object'})
            with patch.dict(TIME_POLICY, {'confirmation_io_seconds': 0.01}):
                with self.assertRaisesRegex(GoFailure, 'chi_timeout'):
                    await guard.handle_async_request(request(data))
            diagnostic = json.loads((root / 'wire-evidence/r/001-diagnostic.json').read_text())
            self.assertEqual(diagnostic['code'], 'chi_timeout')
            self.assertEqual(j.state['pending'], {'run': 'r', 'round': 1})
            j.finish('failed', guard.error); j.close()

    async def test_admitted_request_can_finish_after_window(self):
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
            async def answer(req):
                guard.run_started -= 10000
                return httpx.Response(200, request=req, json={'usage': USAGE, 'model': 'deepseek-v4.1-flash',
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'done'}}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                system='system', instruction='instruction', claimed=lambda: False, confirmation=lambda: None)
            await guard.handle_async_request(request(body()))
            self.assertEqual(j.run['requests'][0]['status'], 'settled')
            self.assertIsNone(j.state['pending'])
            j.finish('failed'); j.close()

    async def test_expired_admission_does_not_reserve(self):
        async def answer(_req):
            raise AssertionError('must not send')
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r')
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                system='system', instruction='instruction', claimed=lambda: False, confirmation=lambda: None, run_started=-10000)
            with self.assertRaisesRegex(GoFailure, 'chi_run_time_limit'):
                await guard.handle_async_request(request(body()))
            self.assertEqual(j.run['requests'], [])
            self.assertIsNone(j.state['pending'])
            j.finish('failed', guard.error); j.close()

    async def test_b_expired_admission_does_not_reserve(self):
        from chi_agent.agent.runtime_policy import TIME_POLICY
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity='a' * 64, evaluation='e', task='t', attempt='a', run='r', kind='coding_b')
            defs = [{'type': 'function', 'function': {'name': name, 'description': DESCRIPTIONS[name],
                'parameters': SCHEMAS[name], 'strict': False}} for name in ('inspect_code', 'verify_patch')]
            async def answer(_req): raise AssertionError('must not send')
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=defs,
                system=SYSTEM, instruction=INSTRUCTION, claimed=lambda: False, confirmation=lambda: None)
            bbody = {'model': 'deepseek-v4.1-flash', 'messages': [{'role': 'system', 'content': SYSTEM},
                     {'role': 'user', 'content': INSTRUCTION}], 'tools': defs, 'max_tokens': 1024,
                     'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'}
            guard.run_started -= TIME_POLICY['b_admission_seconds']
            with self.assertRaisesRegex(GoFailure, 'chi_run_time_limit'):
                await guard.handle_async_request(request(bbody))
            self.assertEqual(j.run['requests'], []); self.assertIsNone(j.state['pending'])
            j.finish('failed', guard.error); j.close()

    async def test_main_truncation_settles_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            j = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            async def answer(req):
                return httpx.Response(200, request=req, json={"usage": USAGE, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": "partial"}}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_output_truncated"):
                await guard.handle_async_request(request(body()))
            self.assertEqual(j.run["requests"][0]["status"], "settled")
            j.finish("failed"); j.close()

    async def test_request_51_never_reaches_lower_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            for i in range(50):
                j.reserve(str(i).encode(), "main")
                j.record_response(json.dumps({"usage": USAGE}).encode(), 200, 1)
                j.settle(USAGE); j.record_diagnostic("ok", 1)
            calls = []
            async def answer(req):
                calls.append(req)
                return httpx.Response(500, request=req)
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_request_limit"):
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
            diagnostic = json.loads((root / "wire-evidence" / "r" / "001-diagnostic.json").read_text())
            self.assertEqual(diagnostic["code"], "chi_cancelled")
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
            usage = {**USAGE, "completion_tokens_details": {"reasoning_tokens": 1},
                     "prompt_tokens_details": {"cached_tokens": 1}}
            payload = {"usage": usage, "model": "wrong", "choices": []}
            async def answer(req):
                return httpx.Response(200, request=req, json=payload)
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_response_invalid"):
                await guard.handle_async_request(request(body()))
            self.assertIsNone(j.state["pending"])
            self.assertEqual(j.run["requests"][0]["status"], "settled")
            ev = Path(directory) / "wire-evidence" / "r"
            request_doc = json.loads((ev / "001-request.json").read_text())
            response_doc = json.loads((ev / "001-response.json").read_text())
            diagnostic = json.loads((ev / "001-diagnostic.json").read_text())
            self.assertEqual(json.loads(request_doc["body_utf8"]), body())
            self.assertEqual(json.loads(response_doc["body_utf8"]), payload)
            self.assertEqual(response_doc["raw_sha256"], hashlib.sha256(response_doc["body_utf8"].encode()).hexdigest())
            self.assertEqual(response_doc["usage"], usage)
            self.assertGreaterEqual(response_doc["elapsed_ms"], 0)
            self.assertEqual(diagnostic["code"], "chi_response_invalid")
            j.finish("failed"); j.close()
            reopened = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="b", run="s")
            reopened.finish("failed"); reopened.close()
            (ev / "001-response.json").unlink()
            with self.assertRaisesRegex(GoFailure, "chi_history_invalid"):
                ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t", attempt="c", run="t")

    async def test_secret_echo_is_redacted_after_known_usage_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            usage = {**USAGE, "diagnostic": SECRET}
            async def answer(req):
                return httpx.Response(200, request=req, json={"usage": usage, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": SECRET}}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            with self.assertRaisesRegex(GoFailure, "chi_secret_in_body"):
                await guard.handle_async_request(request(body()))
            doc = json.loads((root / "wire-evidence" / "r" / "001-response.json").read_text())
            self.assertEqual(doc["redaction"], "secret_detected")
            self.assertIsNone(doc["body_utf8"])
            self.assertEqual(doc["usage"]["diagnostic"], "[REDACTED]")
            self.assertNotIn(SECRET, (root / "wire-evidence" / "r" / "001-response.json").read_text())
            self.assertEqual(j.run["requests"][0]["status"], "settled")
            j.finish("failed"); j.close()
            next_j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="b", run="s")
            next_j.finish("failed"); next_j.close()

    async def test_response_persistence_failure_keeps_known_usage_and_blocks_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            async def answer(req):
                return httpx.Response(200, request=req, json={"usage": USAGE, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            from chi_agent.accounting.journal import write_evidence
            def fail_response(root, run, number, kind, value):
                if kind == "response": raise OSError("synthetic write failure")
                return write_evidence(root, run, number, kind, value)
            with patch('chi_agent.accounting.journal.write_evidence', side_effect=fail_response):
                with self.assertRaisesRegex(GoFailure, "chi_evidence_persistence_failed"):
                    await guard.handle_async_request(request(body()))
            self.assertEqual(j.run["requests"][0]["usage"]["input_tokens"], 3)
            j.finish("failed"); j.close()
            with self.assertRaisesRegex(GoFailure, "chi_history_invalid"):
                ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="b", run="s")

    async def test_unknown_usage_and_http_error_leave_explainable_pending(self):
        for status, payload, expected in ((200, {"error": "missing usage"}, "chi_usage_unknown"),
                                          (503, {"error": "unavailable"}, "chi_http_error")):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
                sends = []
                async def answer(req):
                    sends.append(req)
                    return httpx.Response(status, request=req, json=payload)
                guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                                 system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
                with self.assertRaisesRegex(GoFailure, expected):
                    await guard.handle_async_request(request(body()))
                self.assertEqual(len(sends), 1)
                ev = root / "wire-evidence" / "r"
                response = json.loads((ev / "001-response.json").read_text())
                diagnostic = json.loads((ev / "001-diagnostic.json").read_text())
                self.assertEqual(response["http_status"], status)
                self.assertEqual(diagnostic["code"], expected)
                self.assertIsNotNone(j.state["pending"])
                j.finish("failed"); j.close()
                with self.assertRaisesRegex(GoFailure, "chi_usage_unknown"):
                    ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="b", run="s")

    async def test_invalid_json_is_distinct_and_known_http_error_is_settled(self):
        for status, response_body, expected, settled in (
            (200, b"{invalid", "chi_response_json_invalid", False),
            (503, json.dumps({"usage": USAGE, "error": "unavailable"}).encode(), "chi_http_error", True),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
                async def answer(req):
                    return httpx.Response(status, request=req, content=response_body)
                guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                                 system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
                with self.assertRaisesRegex(GoFailure, expected):
                    await guard.handle_async_request(request(body()))
                self.assertEqual(j.run["requests"][0]["status"] == "settled", settled)
                response_doc = json.loads((root / "wire-evidence" / "r" / "001-response.json").read_text())
                self.assertEqual(response_doc["http_status"], status)
                if status == 200:
                    self.assertEqual(response_doc["redaction"], "unparseable_body")
                else:
                    self.assertEqual(response_doc["usage"], USAGE)
                j.finish("failed", expected); j.close()

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


    async def test_tool_call_position_index_is_tolerated_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity="a" * 64, evaluation="e", task="t", attempt="a", run="r")
            assistant = {"role": "assistant", "content": None, "reasoning_content": "think",
                         "tool_calls": [{"index": 0, "id": "call_0_read", "type": "function",
                                         "function": {"name": "read", "arguments": "{}"}}]}
            async def answer(req):
                payload = json.loads(req.content)
                if len(payload["messages"]) == 2:
                    return httpx.Response(200, request=req, json={"usage": USAGE, "model": "deepseek-v4.1-flash",
                        "choices": [{"finish_reason": "tool_calls", "message": assistant}]})
                return httpx.Response(200, request=req, json={"usage": USAGE, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})
            guard = ChiGuard(j, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction", claimed=lambda: False, confirmation=lambda: None)
            await guard.handle_async_request(request(body()))
            self.assertEqual([c["name"] for c in guard.contract.records], ["read"])
            guard.contract.record_result("call_0_read", "ok")
            replay = body(1)
            replay["messages"] += [
                {"role": "assistant", "content": None, "reasoning_content": "think",
                 "tool_calls": [{"index": 0, "id": "call_0_read", "type": "function",
                                 "function": {"name": "read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_0_read", "content": "ok"}]
            await guard.handle_async_request(request(replay))
            self.assertEqual([item["status"] for item in j.run["requests"]], ["settled", "settled"])
            j.finish("complete"); j.close()


if __name__ == "__main__":
    unittest.main()
