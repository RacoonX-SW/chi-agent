"""Cross-check the fixed limits: profile file, entry config, guard and journal.

The check is behavioural: it sends the value that the profile declares and asserts
the guard accepts it, then sends neighbouring values and asserts rejection before
dispatch. It also proves the journal records the same value. No implementation
constant is re-derived from another implementation in the test.
"""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path

import httpx

import chi_agent.cli as entry
from chi_agent.request_guard import ChiGuard
from chi_agent.journal import ChiJournal
from chi_agent.opencode_go_provider import GoFailure
from chi_agent.request_budget import feedback

URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
SECRET = "synthetic-test-secret"
SESSION = "chi-" + "b" * 32
TOOLS = [{"type": "function", "function": {"name": "read", "description": "Read", "strict": False,
          "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}]
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
         "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}


def body(max_tokens, n=0):
    return {"model": "deepseek-v4.1-flash",
            "messages": [{"role": "system", "content": "system" + feedback(n, False)[0]},
                         {"role": "user", "content": "instruction"}],
            "tools": TOOLS, "max_tokens": max_tokens,
            "thinking": {"type": "enabled"}, "reasoning_effort": "high"}


def request(data):
    return httpx.Request("POST", URL, headers={"Authorization": "Bearer " + SECRET,
                         "User-Agent": "chi-agent", "X-OpenCode-Session": SESSION}, json=data)


def usage(**overrides):
    value = copy.deepcopy(USAGE)
    value.update(overrides)
    return value


class ConfigLimitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.profile = json.loads((entry.ROOT / "profiles/go-chi-entry.json").read_text())

    def test_profile_matches_entry_config(self):
        self.assertTrue(entry._same(self.profile, entry.CONFIG))
        self.assertEqual(self.profile["chi_max_output_tokens"],
                         entry.CONFIG["chi_max_output_tokens"])

    def test_guard_accepts_declared_limit_and_rejects_neighbours(self):
        declared = entry.CONFIG["chi_max_output_tokens"]
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="c" * 64, evaluation="e", task="t",
                                 attempt="a", run="r")
            calls = []

            async def answer(req):
                calls.append(req)
                return httpx.Response(200, request=req, json={
                    "usage": USAGE, "model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "done"}}]})

            guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer), tools=TOOLS,
                             system="system", instruction="instruction",
                             claimed=lambda: False, confirmation=lambda: None)
            asyncio.run(guard.handle_async_request(request(body(declared))))
            self.assertEqual(len(calls), 1)
            self.assertEqual(journal.run["requests"][0]["max_tokens"], declared)
            for value in (declared + 1, declared - 1, True, "8192", None):
                with self.subTest(value=value):
                    calls.clear()
                    with self.assertRaisesRegex(GoFailure, "chi_request_invalid"):
                        asyncio.run(guard.handle_async_request(request(body(value, n=1))))
                    self.assertEqual(calls, [])
            journal.finish("complete")
            journal.close()

    def test_profile_value_drift_is_detected(self):
        for key, value in (("chi_max_output_tokens", 16384),
                           ("chi_max_requests", 51),
                           ("confirmation_max_output_tokens", 16384)):
            with self.subTest(key=key):
                mutated = copy.deepcopy(self.profile)
                mutated[key] = value
                self.assertFalse(entry._same(mutated, entry.CONFIG))
        mutated = copy.deepcopy(self.profile)
        mutated["time_policy"]["main_read_seconds"] += 1
        self.assertFalse(entry._same(mutated, entry.CONFIG))
        mutated = copy.deepcopy(self.profile)
        mutated["unknown_field"] = True
        self.assertFalse(entry._same(mutated, entry.CONFIG))


class JournalLimitTests(unittest.TestCase):
    def test_journal_records_the_declared_limit(self):
        declared = entry.CONFIG["chi_max_output_tokens"]
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="d" * 64, evaluation="e", task="t",
                                 attempt="a", run="r")
            journal.reserve(b"{}", "main")
            self.assertEqual(journal.run["requests"][0]["max_tokens"], declared)
            journal.record_response(json.dumps({"usage": USAGE}).encode(), 200, 1)
            journal.settle(USAGE)
            journal.finish("complete")
            journal.close()


if __name__ == "__main__":
    unittest.main()
