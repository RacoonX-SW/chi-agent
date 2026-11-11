import json
import tempfile
import unittest
from pathlib import Path

from chi_agent.tool_contract import ContractFailure, ToolContract, validate_anchor
from chi_agent.task_state import ANCHOR_SCHEMA, CONTEXT_POLICY_V3, StateRefusal, TaskState
from chi_agent.request_budget import feedback

SYSTEM = "system"
INSTRUCTION = "instruction"
TOOLS = [{"type": "function", "function": {"name": "read", "description": "Read",
          "strict": False, "parameters": {"type": "object", "properties": {},
                                          "additionalProperties": False}}}]


def batch(call_id="c1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": "read", "arguments": "{}"}}]}


class AnchorStateTests(unittest.TestCase):
    def test_program_binds_target_and_anchor_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TaskState(Path(directory) / "state", run="r", role="payer",
                              context_policy=CONTEXT_POLICY_V3)
            state.observe(call_id="bind", tool="local-fs-read", kind="local",
                          arguments={"path": "/workspace/CASE-A/payer/in.txt"},
                          result="read", event="returned", scope="case:CASE-A")
            state.observe(call_id="c1", tool="payer_intake_hub.get_intake_case",
                          kind="mcp", arguments={"case_id": "CASE-A"},
                          result="{}", event="returned", scope="case:CASE-A")
            self.assertEqual(state.data["target"]["case_id"], "CASE-A")
            first = state.anchor()
            second = state.anchor()
            self.assertEqual(first["sha256"], second["sha256"])
            payload = json.loads(first["text"])
            self.assertEqual(payload["schema"], ANCHOR_SCHEMA)
            self.assertEqual(payload["target"]["case_id"], "CASE-A")
            self.assertEqual(payload["current_step"], "verify_documents")
            self.assertTrue(payload["forbidden"])

    def test_model_cannot_write_program_owned_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TaskState(Path(directory) / "state", run="r", role="payer",
                              context_policy=CONTEXT_POLICY_V3)
            for payload in ({"facts": []}, {"target": {"case_id": "CASE-A"}}):
                with self.assertRaises(StateRefusal) as caught:
                    state.propose(payload)
                self.assertEqual(caught.exception.code, "chi_state_program_owned")
            self.assertEqual(state.propose({"plans": ["read the case"]})["status"], "updated")


class AnchorHistoryTests(unittest.TestCase):
    def _contract(self):
        contract = ToolContract(TOOLS)
        contract.accept_batch(batch())
        contract.record_result("c1", "ok")
        return contract

    def test_anchor_at_index_two_is_accepted(self):
        contract = self._contract()
        anchor = {"text": '{"schema":"chi-intent-anchor-v1"}', "sha256": "a" * 64}
        messages = [
            {"role": "system", "content": SYSTEM + feedback(0, False)[0]},
            {"role": "user", "content": INSTRUCTION},
            {"role": "user", "content": anchor["text"]},
            batch(), {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ]
        contract.validate_history(messages, system=SYSTEM, instruction=INSTRUCTION,
                                  used=0, claimed=False, anchor=anchor)

    def test_missing_or_duplicate_anchor_is_rejected(self):
        contract = self._contract()
        anchor = {"text": '{"schema":"chi-intent-anchor-v1"}', "sha256": "a" * 64}
        base = [
            {"role": "system", "content": SYSTEM + feedback(0, False)[0]},
            {"role": "user", "content": INSTRUCTION},
        ]
        with self.assertRaises(ContractFailure):
            contract.validate_history(base + [batch(), {"role": "tool", "tool_call_id": "c1",
                                                        "content": "ok"}],
                                      system=SYSTEM, instruction=INSTRUCTION,
                                      used=0, claimed=False, anchor=anchor)
        duplicate = base + [{"role": "user", "content": anchor["text"]},
                            {"role": "user", "content": anchor["text"]},
                            batch(), {"role": "tool", "tool_call_id": "c1", "content": "ok"}]
        with self.assertRaises(ContractFailure):
            contract.validate_history(duplicate, system=SYSTEM, instruction=INSTRUCTION,
                                      used=0, claimed=False, anchor=anchor)


class WireAnchorTests(unittest.TestCase):
    def test_validate_anchor_requires_position_hash_and_uniqueness(self):
        import hashlib
        text = '{"schema":"chi-intent-anchor-v1"}'
        anchor = {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        messages = [{"role": "system", "content": "s"},
                    {"role": "user", "content": "i"},
                    {"role": "user", "content": text}]
        validate_anchor(messages, anchor)
        for broken in ([{"role": "system", "content": "s"}, {"role": "user", "content": "i"}],
                       [{"role": "system", "content": "s"}, {"role": "user", "content": "i"},
                        {"role": "user", "content": "wrong"}],
                       [{"role": "system", "content": "s"}, {"role": "user", "content": "i"},
                        {"role": "user", "content": text}, {"role": "user", "content": text}]):
            with self.assertRaises(ContractFailure):
                validate_anchor(broken, anchor)
        with self.assertRaises(ContractFailure):
            validate_anchor(messages, dict(anchor, sha256="0" * 64))


if __name__ == "__main__":
    unittest.main()
