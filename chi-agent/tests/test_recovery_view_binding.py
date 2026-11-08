import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from go_chi_context import DEFAULT_BUDGET_V3
from go_chi_guard import ChiGuard
from go_chi_journal import ChiJournal, inspect_history
from go_chi_recovery import canonical_sha, validate_permit
from opencode_go_provider import GoFailure
from test_go_chi_guard import SECRET, SESSION, TOOLS, USAGE, URL, body, request


def anchor(text='{"schema":"chi-intent-anchor-v1"}'):
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def response(message, reason="length"):
    return {"model": "deepseek-v4.1-flash", "usage": USAGE,
            "choices": [{"finish_reason": reason,
                         "message": {"role": "assistant", **message}}]}


def setup(root, payloads):
    journal = ChiJournal(root, identity="a" * 64, evaluation="e", task="t",
                         attempt="a", run="r",
                         launch={"context_policy": "chi-context-v3",
                                 "output_recovery": "chi-output-recovery-v1",
                                 "recovery_view_policy": "canonical-v1",
                                 "role": "payer"})
    sent = []

    async def answer(req):
        sent.append(json.loads(req.content))
        item = payloads[len(sent) - 1]
        return httpx.Response(200, request=req, json=item)

    guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer),
                     tools=TOOLS, system="system", instruction="instruction",
                     claimed=lambda: False, confirmation=lambda: None,
                     canonical_tools={"read": "local-fs-read"},
                     context_limit=DEFAULT_BUDGET_V3,
                     anchor_getter=lambda: anchor())
    return journal, guard, sent


class RecoveryViewBindingTests(unittest.TestCase):
    def test_partial_freezes_v2_view_and_records_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal, guard, sent = setup(root, [
                response({"content": "part"}, "length"),
                response({"content": "done"}, "stop"),
            ])
            asyncio.run(guard.handle_async_request(request(body())))
            self.assertEqual(len(sent), 2)
            self.assertEqual(sent[0]["messages"][2]["role"], "user")
            permit = json.loads((root / "wire-evidence" / "r" / "001-recovery.json").read_text())
            self.assertEqual(permit["schema"], "chi-recovery-permit-v2")
            self.assertEqual(permit["mode"], "partial")
            self.assertTrue(permit["frozen_view"])
            self.assertIsNotNone(permit["anchor_sha256"])
            self.assertEqual(permit["history_length"], len(permit["view_body"]["messages"]))
            self.assertEqual(canonical_sha(sent[1]), permit["view_sha256"])
            self.assertEqual(journal.run["requests"][0]["view_identity"]["recovery_mode"], "main")
            self.assertEqual(journal.run["requests"][1]["view_identity"]["recovery_mode"], "continuation")
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            report = inspect_history(root, "a" * 64, hashlib.sha256(raw).hexdigest())
            self.assertEqual(report["status"], "inspected")

    def test_regenerate_records_new_view_and_frozen_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            call = {"id": "new", "type": "function",
                    "function": {"name": "read", "arguments": "{}"}}
            journal, guard, sent = setup(root, [
                response({"tool_calls": [call]}, "length"),
                response({"content": "done"}, "stop"),
            ])
            asyncio.run(guard.handle_async_request(request(body())))
            permit = json.loads((root / "wire-evidence" / "r" / "001-recovery.json").read_text())
            self.assertEqual(permit["mode"], "regenerate")
            self.assertFalse(permit["frozen_view"])
            self.assertEqual(canonical_sha(sent[1]), permit["view_sha256"])
            journal.finish("failed")
            journal.close()

    def test_missing_view_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, guard, sent = setup(Path(directory), [response({"content": "part"}),
                                                           response({"content": "done"}, "stop")])
            asyncio.run(guard.handle_async_request(request(body())))
            permit = json.loads((Path(directory) / "wire-evidence" / "r" / "001-recovery.json").read_text())
            broken = copy.deepcopy(permit)
            del broken["source_sha256"]
            with self.assertRaises(ValueError):
                validate_permit(broken, identity="a" * 64, run=journal.run,
                                parent_round=1, parent_request={"messages": []},
                                parent_response={}, response_sha256="0" * 64,
                                old_used=0, claimed=False)
            journal.finish("failed")
            journal.close()

    def test_anchor_hash_mismatch_is_rejected(self):
        text = '{"schema":"chi-intent-anchor-v1"}'
        anchor_doc = {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        parent = {"messages": [
            {"role": "system", "content": "system" + __import__("request_budget").feedback(0, False)[0]},
            {"role": "user", "content": "instruction"},
            {"role": "user", "content": text}]}
        response = {"model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "length",
                                 "message": {"role": "assistant", "content": "part"}}]}
        from go_chi_recovery import derive_view
        view = derive_view(parent, response, old_used=0, claimed=False, anchor=anchor_doc)
        run = {"evaluation": "e", "task": "t", "attempt": "a", "run": "r"}
        permit = {
            "schema": "chi-recovery-permit-v2", "policy": "chi-output-recovery-v1",
            "identity": "a" * 64, **run,
            "root_round": 1, "parent_round": 1,
            "parent_response_sha256": "b" * 64, "mode": "partial",
            "chain_ordinal": 1, "history_version": "chi-tool-history-v1",
            "history_sha256": canonical_sha(parent["messages"]),
            "instruction_version": "chi-recovery-instruction-v1",
            "view_version": "chi-recovery-view-v1",
            "view_sha256": canonical_sha(view), "view_body": view,
            "continuation_round": None, "decision": "issued", "result": "pending",
            "source_sha256": canonical_sha(parent["messages"]),
            "anchor_sha256": "0" * 64, "history_length": len(view["messages"]),
            "frozen_view": True, "projection_rule": "chi-context-projection-v1",
            "pressure": False,
        }
        with self.assertRaises(ValueError):
            validate_permit(permit, identity="a" * 64, run=run, parent_round=1,
                            parent_request=parent, parent_response=response,
                            response_sha256="b" * 64, old_used=0, claimed=False)
        broken = copy.deepcopy(permit)
        broken["view_body"]["messages"][-1]["content"] = "changed"
        with self.assertRaises(ValueError):
            validate_permit(broken, identity="a" * 64, run=run, parent_round=1,
                            parent_request=parent, parent_response=response,
                            response_sha256="b" * 64, old_used=0, claimed=False)

    def test_v3_recovery_without_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GoFailure) as caught:
                ChiJournal(Path(directory), identity="a" * 64, evaluation="e", task="t",
                           attempt="a", run="r",
                           launch={"context_policy": "chi-context-v3",
                                   "output_recovery": "chi-output-recovery-v1"})
            self.assertEqual(caught.exception.code, "chi_context_policy_incompatible")


if __name__ == "__main__":
    unittest.main()
