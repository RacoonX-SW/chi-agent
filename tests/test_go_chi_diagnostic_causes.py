import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from chi_agent.tools.tool_contract import ContractFailure, ToolContract
from chi_agent.models.request_guard import ChiGuard
from chi_agent.accounting.journal import ChiJournal, inspect_history
from chi_agent.models.opencode_go_provider import GoFailure
from chi_agent.accounting.request_budget import feedback

URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
SECRET = "synthetic-test-secret"
SESSION = "chi-" + "d" * 32
TOOLS = [{"type": "function", "function": {"name": "read", "description": "Read", "strict": False,
          "parameters": {"type": "object", "properties": {"id": {"type": "integer"}},
                         "required": ["id"], "additionalProperties": False}}}]
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
         "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}


def call(call_id="call_1", name="read", arguments='{"id":1}', **extra):
    value = {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
    value.update(extra)
    return value


def message(calls):
    return {"role": "assistant", "content": None, "reasoning_content": "think", "tool_calls": calls}


def reason_of(build):
    contract = ToolContract(TOOLS)
    try:
        build(contract)
    except ContractFailure as exc:
        return exc.cause["reason"]
    raise AssertionError("expected ContractFailure")


def body(n=0):
    return {"model": "deepseek-v4.1-flash",
            "messages": [{"role": "system", "content": "system" + feedback(n, False)[0]},
                         {"role": "user", "content": "instruction"}],
            "tools": TOOLS, "max_tokens": 8192, "thinking": {"type": "enabled"},
            "reasoning_effort": "high"}


def request(data):
    return httpx.Request("POST", URL, headers={"Authorization": "Bearer " + SECRET,
                         "User-Agent": "chi-agent", "X-OpenCode-Session": SESSION}, json=data)


class BatchReasonTests(unittest.TestCase):
    def test_nine_batch_reasons_and_atomicity(self):
        cases = {
            "assistant_shape": lambda c: c.accept_batch({"role": "user", "content": "x", "tool_calls": [call()]}),
            "unfinished_batch": lambda c: (c.accept_batch(message([call()])), c.accept_batch(message([call("call_2")]))),
            "call_shape": lambda c: c.accept_batch(message([call(extra_field=True)])),
            "call_id_invalid": lambda c: c.accept_batch(message([call(call_id="bad id")])),
            "call_id_reused": lambda c: (c.accept_batch(message([call()])), c.record_result("call_1", "ok"),
                                         c.accept_batch(message([call()]))),
            "function_shape": lambda c: c.accept_batch(message([{"id": "call_1", "type": "function",
                                                                  "function": {"name": "read"}}])),
            "tool_unknown": lambda c: c.accept_batch(message([call(name="missing")])),
            "arguments_json": lambda c: c.accept_batch(message([call(arguments="{bad")])),
            "arguments_schema": lambda c: c.accept_batch(message([call(arguments='{"id":"x"}')])),
        }
        for reason, build in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(reason_of(build), reason)

    def test_good_and_bad_call_in_one_batch_commits_nothing(self):
        contract = ToolContract(TOOLS)
        with self.assertRaises(ContractFailure) as caught:
            contract.accept_batch(message([call(), call("call_2", name="missing")]))
        self.assertEqual(caught.exception.cause["reason"], "tool_unknown")
        self.assertEqual(contract.records, [])
        self.assertEqual(contract.seen, set())
        self.assertEqual(contract.batches, [])

    def test_cause_contains_no_payload_values(self):
        payload = '{"id":1,"patient":"PATIENT-SECRET","key":"sk-live"}'
        contract = ToolContract(TOOLS)
        with self.assertRaises(ContractFailure) as caught:
            contract.accept_batch(message([call(arguments=payload)]))
        text = json.dumps(caught.exception.cause, sort_keys=True)
        self.assertEqual(caught.exception.cause["reason"], "arguments_schema")
        self.assertNotIn("PATIENT-SECRET", text)
        self.assertNotIn("sk-live", text)


class GuardCauseTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_tool_batch_settles_trusted_usage_then_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity="e" * 64, evaluation="e", task="t", attempt="a", run="r")
            lower_calls, dispatched = [], []

            async def answer(req):
                lower_calls.append(req)
                return httpx.Response(200, request=req, json={
                    "usage": USAGE, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "tool_calls", "message": {
                        "role": "assistant", "content": None, "reasoning_content": "x",
                        "tool_calls": [{"id": "call_1", "type": "function",
                                        "function": {"name": "missing", "arguments": "{}"}}]}}]})

            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None,
                             before_batch=lambda calls: dispatched.append(calls))
            with self.assertRaisesRegex(GoFailure, "chi_tool_batch_invalid"):
                await guard.handle_async_request(request(body()))
            self.assertEqual(len(lower_calls), 1)
            self.assertEqual(dispatched, [])
            entry = journal.run["requests"][0]
            self.assertEqual(entry["status"], "settled")
            doc = json.loads((root / "wire-evidence/r/001-diagnostic.json").read_text())
            self.assertEqual(doc["schema"], "chi-go-diagnostic-v2")
            self.assertEqual(doc["code"], "chi_tool_batch_invalid")
            self.assertEqual(doc["cause"], {"schema": "chi-safe-cause-v1",
                                            "stage": "tool_batch", "reason": "tool_unknown"})
            self.assertEqual(guard.safe_cause["reason"], "tool_unknown")
            journal.finish("failed", "chi_tool_batch_invalid"); journal.close()
            digest = __import__("hashlib").sha256((root / "chi-accounting.json").read_bytes()).hexdigest()
            inspected = inspect_history(root, "e" * 64, digest)
            self.assertEqual(inspected["diagnostic_causes"][0]["cause"]["reason"], "tool_unknown")

    async def test_rejected_request_before_reserve_does_not_fabricate_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="f" * 64, evaluation="e", task="t",
                                 attempt="a", run="r")
            calls = []

            async def answer(req):
                calls.append(req)
                raise AssertionError("must not dispatch")

            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None)
            bad = body(); bad["max_tokens"] = 8193
            with self.assertRaisesRegex(GoFailure, "chi_request_invalid"):
                await guard.handle_async_request(request(bad))
            self.assertEqual(calls, [])
            self.assertEqual(journal.run["requests"], [])
            self.assertEqual(guard.safe_cause["stage"], "request")
            journal.finish("failed"); journal.close()


class JournalCauseTests(unittest.TestCase):
    def test_invalid_cause_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t",
                                 attempt="a", run="r")
            journal.reserve(b"{}", "main")
            with self.assertRaisesRegex(GoFailure, "chi_diagnostic_invalid"):
                journal.record_diagnostic("chi_timeout", 1,
                                          cause={"schema": "chi-safe-cause-v1", "stage": "transport",
                                                 "reason": "bogus"})
            with self.assertRaisesRegex(GoFailure, "chi_diagnostic_invalid"):
                journal.record_diagnostic("chi_timeout", 1,
                                          cause={"schema": "chi-safe-cause-v1", "stage": "transport",
                                                 "reason": "timeout", "extra": 1})
            journal.record_diagnostic("chi_timeout", 1,
                                      cause={"schema": "chi-safe-cause-v1", "stage": "transport",
                                             "reason": "timeout"})
            journal.finish("failed", "chi_timeout"); journal.close()

    def test_ok_with_cause_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="b" * 64, evaluation="e", task="t",
                                 attempt="a", run="r")
            journal.reserve(b"{}", "main")
            with self.assertRaisesRegex(GoFailure, "chi_diagnostic_invalid"):
                journal.record_diagnostic("ok", 1,
                                          cause={"schema": "chi-safe-cause-v1", "stage": "other",
                                                 "reason": "unspecified"})
            journal.record_diagnostic("ok", 1)
            journal.finish("failed"); journal.close()


if __name__ == "__main__":
    unittest.main()
