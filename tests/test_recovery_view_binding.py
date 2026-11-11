import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from chi_agent.context_assembly import project_messages
from chi_agent.context_budget import DEFAULT_BUDGET_V3
from chi_agent.evidence import verify_tool, write_tool
from chi_agent.request_budget import feedback
from chi_agent.request_guard import ChiGuard
from chi_agent.journal import ChiJournal, _replay_source_view, inspect_history
from chi_agent.output_recovery import canonical_sha, validate_permit
from chi_agent.opencode_go_provider import GoFailure
from test_go_chi_guard import SECRET, SESSION, TOOLS, USAGE, URL, body, request

LOCAL_TOOLS = [{"type": "function", "function": {
    "name": "local-fs-read", "description": "Read", "strict": False,
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}]


def local_body():
    data = body()
    data["tools"] = LOCAL_TOOLS
    return data


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
                                 "source_evidence_policy": "canonical-v1",
                                 "output_recovery": "chi-output-recovery-v1",
                                 "recovery_view_policy": "canonical-v1",
                                 "role": "payer"})
    sent = []

    async def answer(req):
        sent.append(json.loads(req.content))
        item = payloads[len(sent) - 1]
        return httpx.Response(200, request=req, json=item)

    guard = ChiGuard(journal, SECRET, SESSION, httpx.MockTransport(answer),
                     tools=LOCAL_TOOLS, system="system", instruction="instruction",
                     claimed=lambda: False, confirmation=lambda: None,
                     canonical_tools={"local-fs-read": "local-fs-read"},
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
            asyncio.run(guard.handle_async_request(request(local_body())))
            self.assertEqual(len(sent), 2)
            self.assertEqual(sent[0]["messages"][2]["role"], "user")
            permit = json.loads((root / "wire-evidence" / "r" / "001-recovery.json").read_text())
            self.assertEqual(permit["schema"], "chi-recovery-permit-v2")
            self.assertEqual(permit["mode"], "partial")
            self.assertTrue(permit["frozen_view"])
            self.assertEqual(permit["parent_view_sha256"], permit["view_sha256"])
            self.assertFalse(permit["pressure"])
            self.assertIsNotNone(permit["anchor_sha256"])
            self.assertEqual(permit["history_length"], len(permit["view_body"]["messages"]))
            self.assertEqual(canonical_sha(sent[1]), permit["view_sha256"])
            self.assertEqual(journal.run["requests"][0]["view_identity"]["recovery_mode"], "main")
            self.assertEqual(journal.run["requests"][1]["view_identity"]["recovery_mode"], "continuation")
            self.assertFalse(journal.run["requests"][1]["view_identity"]["pressure"])
            self.assertTrue((root / "wire-evidence" / "r" / "001-source.json").is_file())
            self.assertIn("source_evidence_sha256", journal.run["requests"][0])
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            report = inspect_history(root, "a" * 64, hashlib.sha256(raw).hexdigest())
            self.assertEqual(report["status"], "inspected")

    def test_regenerate_records_new_view_and_frozen_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            call = {"id": "new", "type": "function",
                    "function": {"name": "local-fs-read", "arguments": "{}"}}
            journal, guard, sent = setup(root, [
                response({"tool_calls": [call]}, "length"),
                response({"content": "done"}, "stop"),
            ])
            asyncio.run(guard.handle_async_request(request(local_body())))
            permit = json.loads((root / "wire-evidence" / "r" / "001-recovery.json").read_text())
            self.assertEqual(permit["mode"], "regenerate")
            self.assertFalse(permit["frozen_view"])
            self.assertTrue(permit["pressure"])
            self.assertEqual(permit["projection_rule"], "chi-context-projection-regenerate-v1")
            self.assertTrue(journal.run["requests"][1]["view_identity"]["pressure"])
            self.assertEqual(permit["parent_view_sha256"], canonical_sha(sent[0]))
            self.assertEqual(permit["view_sha256"], canonical_sha(sent[1]))
            self.assertNotEqual(permit["parent_view_sha256"], permit["view_sha256"])
            journal.finish("failed")
            journal.close()

    def test_regenerate_reprojects_older_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            call = {"id": "new", "type": "function",
                    "function": {"name": "local-fs-read", "arguments": "{}"}}
            journal, guard, sent = setup(root, [
                response({"tool_calls": [call]}, "length"),
                response({"content": "done"}, "stop"),
            ])
            data = local_body()
            data["messages"].extend([
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "old1", "type": "function",
                                 "function": {"name": "local-fs-read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "old1", "content": "old1 " + "x" * 2000},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "old2", "type": "function",
                                 "function": {"name": "local-fs-read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "old2", "content": "old2 " + "x" * 2000},
            ])
            for index, text in ((1, "old1 " + "x" * 2000), (2, "old2 " + "x" * 2000)):
                guard.contract.accept_batch(data["messages"][2 * index])
                guard.contract.record_result(f"old{index}", text)
                journal.start_tool(f"old{index}", "local-fs-read", {})
                journal.record_tool(f"old{index}", "local-fs-read", text)
            asyncio.run(guard.handle_async_request(request(data)))
            permit = json.loads((root / "wire-evidence" / "r" / "001-recovery.json").read_text())
            self.assertNotEqual(permit["parent_view_sha256"], permit["view_sha256"])
            self.assertIn("chi-tool-result-ref-v1", json.dumps(sent[1]["messages"]))
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            self.assertEqual(inspect_history(root, "a" * 64,
                                             hashlib.sha256(raw).hexdigest())["status"], "inspected")

    def test_tampered_source_body_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal, guard, sent = setup(root, [
                response({"content": "part"}, "length"),
                response({"content": "done"}, "stop"),
            ])
            asyncio.run(guard.handle_async_request(request(local_body())))
            source_path = root / "wire-evidence" / "r" / "001-source.json"
            doc = json.loads(source_path.read_text())
            body_value = json.loads(doc["body_utf8"])
            body_value["messages"][1]["content"] = "tampered"
            raw = json.dumps(body_value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()
            doc["body_utf8"] = raw.decode()
            doc["raw_sha256"] = hashlib.sha256(raw).hexdigest()
            payload = (json.dumps(doc, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")) + "\n").encode()
            source_path.write_bytes(payload)
            journal.run["requests"][0]["source_evidence_sha256"] = hashlib.sha256(payload).hexdigest()
            journal.finish("failed")
            journal.close()
            state_path = root / "chi-accounting.json"
            raw_state = state_path.read_bytes()
            with self.assertRaisesRegex(GoFailure, "chi_view_source_mismatch"):
                inspect_history(root, "a" * 64, hashlib.sha256(raw_state).hexdigest())

    def test_legacy_v3_without_claimed_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal, guard, sent = setup(root, [
                response({"content": "part"}, "length"),
                response({"content": "done"}, "stop"),
            ])
            asyncio.run(guard.handle_async_request(request(local_body())))
            for item in journal.run["requests"]:
                item["view_identity"].pop("claimed", None)
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            self.assertEqual(inspect_history(root, "a" * 64,
                                             hashlib.sha256(raw).hexdigest())["status"], "inspected")

    def test_source_policy_requires_main_source(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ChiJournal(Path(directory), identity="a" * 64, evaluation="e",
                                 task="t", attempt="a", run="r",
                                 launch={"context_policy": "chi-context-v3",
                                         "source_evidence_policy": "canonical-v1"})
            with self.assertRaisesRegex(GoFailure, "chi_source_evidence_missing"):
                journal.reserve(b"{}", "main")
            journal.close()

    def test_source_policy_requires_parent_source_for_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal, guard, sent = setup(root, [
                response({"content": "part"}, "length"),
                response({"content": "done"}, "stop"),
            ])
            asyncio.run(guard.handle_async_request(request(local_body())))
            journal.run["requests"][0].pop("source_evidence_sha256", None)
            journal.run["requests"][0].pop("source_bytes", None)
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            with self.assertRaisesRegex(GoFailure, "chi_source_evidence_missing"):
                inspect_history(root, "a" * 64, hashlib.sha256(raw).hexdigest())

    def test_missing_view_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, guard, sent = setup(Path(directory), [response({"content": "part"}),
                                                           response({"content": "done"}, "stop")])
            asyncio.run(guard.handle_async_request(request(local_body())))
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
            {"role": "system", "content": "system" + feedback(0, False)[0]},
            {"role": "user", "content": "instruction"},
            {"role": "user", "content": text}]}
        response = {"model": "deepseek-v4.1-flash",
                    "choices": [{"finish_reason": "length",
                                 "message": {"role": "assistant", "content": "part"}}]}
        from chi_agent.output_recovery import derive_view
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
            "parent_view_sha256": canonical_sha(view),
        }
        with self.assertRaisesRegex(ValueError, "chi_recovery_view_mismatch"):
            validate_permit(permit, identity="a" * 64, run=run, parent_round=1,
                            parent_request=parent, parent_response=response,
                            response_sha256="b" * 64, old_used=0, claimed=False)
        broken = copy.deepcopy(permit)
        broken["anchor_sha256"] = anchor_doc["sha256"]
        broken["view_body"]["messages"][-1]["content"] = "changed"
        broken["view_sha256"] = canonical_sha(broken["view_body"])
        broken["parent_view_sha256"] = broken["view_sha256"]
        broken["history_length"] = len(broken["view_body"]["messages"])
        with self.assertRaisesRegex(ValueError, "chi_recovery_view_mismatch"):
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


class SourceReplayEdgeTests(unittest.TestCase):
    def test_replay_includes_returned_error_and_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref1 = write_tool(root, "r", "c1", "ERROR: failed", ())
            ref2 = write_tool(root, "r", "c2", "read result", ())
            source = {"model": "deepseek-v4.1-flash", "max_tokens": 1024, "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "instruction"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "local-fs-write", "arguments": "{\"path\":\"/a\"}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "ERROR: failed"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c2", "type": "function",
                     "function": {"name": "local-fs-read", "arguments": "{\"path\":\"/b\"}"}}]},
                {"role": "tool", "tool_call_id": "c2", "content": "read result"},
            ]}
            records = {
                "c1": {"id": "c1", "name": "local-fs-write",
                       "arguments": {"path": "/a"}, "result": "ERROR: failed"},
                "c2": {"id": "c2", "name": "local-fs-read",
                       "arguments": {"path": "/b"}, "result": "read result"},
            }
            events = {"c1": "returned_error", "c2": "returned"}
            projected, _ = project_messages(
                source["messages"], records=records, events=events,
                canonical_tools={}, keep_recent_batches=1, project_results=True)
            wire = dict(source)
            wire["messages"] = projected
            run = {"run": "r", "tool_events": [
                {"call_id": "c1", "tool": "local-fs-write", "event": "returned_error",
                 "result_evidence_sha256": ref1},
                {"call_id": "c2", "tool": "local-fs-read", "event": "returned",
                 "result_evidence_sha256": ref2},
            ]}
            expected, sha = _replay_source_view(
                root, run, source, wire, keep_recent_batches=1, project_results=True)
            self.assertEqual(sha, canonical_sha(wire))
            self.assertEqual(json.loads(expected["messages"][3]["content"])["schema"],
                             "chi-tool-record-v1")

    def test_tool_evidence_keeps_non_json_text_with_backslashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = "policy \\* text"
            ref = write_tool(root, "r", "c1", result, ())
            doc = json.loads((root / "tool-evidence" / "r" / "c1.json").read_text())
            self.assertIsNone(doc["redaction"])
            self.assertEqual(doc["body_utf8"], result)
            self.assertEqual(verify_tool(root, "r", "c1", ref)["body_utf8"], result)

    def test_replay_accepts_non_json_text_with_backslashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = "policy \\* text"
            ref = write_tool(root, "r", "c1", result, ())
            source = {"model": "deepseek-v4.1-flash", "max_tokens": 1024, "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "instruction"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "local-fs-read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": result},
            ]}
            records = {"c1": {"id": "c1", "name": "local-fs-read",
                              "arguments": {}, "result": result}}
            projected, _ = project_messages(source["messages"], records=records,
                                            events={"c1": "returned"}, canonical_tools={},
                                            keep_recent_batches=1, project_results=True)
            wire = dict(source)
            wire["messages"] = projected
            run = {"run": "r", "tool_events": [
                {"call_id": "c1", "tool": "local-fs-read", "event": "returned",
                 "result_evidence_sha256": ref}]}
            _expected, sha = _replay_source_view(
                root, run, source, wire, keep_recent_batches=1, project_results=True)
            self.assertEqual(sha, canonical_sha(wire))

    def test_replay_redacted_tool_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "tool-evidence" / "r" / "c1.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema": "chi-go-tool-evidence-v1", "kind": "tool",
                "raw_sha256": "a" * 64, "body_utf8": None,
                "redaction": "body_too_large"}))
            ref = hashlib.sha256(path.read_bytes()).hexdigest()
            source = {"model": "deepseek-v4.1-flash", "max_tokens": 1024, "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "instruction"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "local-fs-read", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "redacted"},
            ]}
            wire = dict(source)
            run = {"run": "r", "tool_events": [
                {"call_id": "c1", "tool": "local-fs-read", "event": "returned",
                 "result_evidence_sha256": ref},
            ]}
            with self.assertRaises(GoFailure) as caught:
                _replay_source_view(root, run, source, wire,
                                    keep_recent_batches=1, project_results=True)
            self.assertEqual(caught.exception.code, "chi_view_source_mismatch")


if __name__ == "__main__":
    unittest.main()
