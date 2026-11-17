"""Local tool contract matrix: description promises, accepted inputs and boundaries.

These are independent synthetic cases. They do not read hidden expectations,
real task data, credentials or live services.
"""
import asyncio
import contextvars
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents.models.openai_chatcompletions import Converter
from chi_agent.tools.tool_contract import ContractFailure, ToolContract
from chi_agent.roles.role_guidance import VERSION as GUIDANCE_VERSION
from chi_agent.agent.task_state import TaskState
from chi_agent.tools.local_tools import local_tools


class Journal:
    def record_claim(self):
        pass
    def record_tool(self, *_args, **_kwargs):
        pass
    def start_tool(self, *_args):
        pass
    def refuse_tool(self, *_args, **_kwargs):
        pass


def accept(guard, name, args, call_id="c"):
    return guard.contract.accept_batch({
        "role": "assistant", "content": None, "reasoning_content": "reason",
        "tool_calls": [{"id": call_id, "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)}}],
    })


async def invoke(tools, guard, name, args, call_id="c"):
    accept(guard, name, args, call_id)
    tool = next(item for item in tools if item.name == name)
    return await tool.on_invoke_tool(None, json.dumps(args))


class Contract:
    def __init__(self, root, role="payer", binding=None):
        self.root = root
        self.workspace = root / "workspace"
        (self.workspace / "CASE-A" / "payer").mkdir(parents=True, exist_ok=True)
        (self.workspace / "CASE-A" / "shared").mkdir(parents=True, exist_ok=True)
        (self.workspace / "CASE-A" / "provider").mkdir(parents=True, exist_ok=True)
        (self.workspace / "CASE-B" / "payer").mkdir(parents=True, exist_ok=True)
        self.handbook = root / "handbook"
        self.handbook.mkdir(exist_ok=True)
        (self.handbook / "policy.md").write_text("A lumbar MRI needs prior therapy.\n", encoding="utf-8")
        self.instruction = root / "instruction.md"
        self.instruction.write_text("Synthetic instruction", encoding="utf-8")
        self.state = TaskState(root / "state", run="run", role=role, binding=binding)
        holder = {}
        self.tools = local_tools(
            role=role, workspace_root=self.workspace, instruction_path=self.instruction,
            tool_references=[], handbook_root=self.handbook, journal=Journal(),
            binding=binding, guard_getter=lambda: holder.get("guard"),
            client_getter=lambda: None, confirmation_context=contextvars.ContextVar("test", default=None),
            exchanges=[], dispatch_lock=asyncio.Lock(), state=self.state, capabilities="f0-f3-v1")
        self.guard = SimpleNamespace(
            contract=ToolContract([Converter.tool_to_openai(tool) for tool in self.tools]),
            secret="secret", session="session")
        holder["guard"] = self.guard


class LocalContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    async def test_fs_read_accepts_allowlisted_files_and_rejects_outside_or_bad_bounds(self):
        contract = Contract(self.root)
        target = contract.workspace / "CASE-A" / "payer" / "note.txt"
        target.write_text("alpha\nbeta\n", encoding="utf-8")
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-read",
                                      {"path": str(target)}), "alpha\nbeta\n")
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-read",
                                      {"path": str(target), "offset": 2, "limit": 1}, "c2"), "beta\n")
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-read",
                                      {"path": str(contract.handbook / "policy.md")}, "c3"),
                         "A lumbar MRI needs prior therapy.\n")
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-read",
                                      {"path": "/etc/passwd"}, "c4")).startswith("ERROR:"))
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-read",
                                      {"path": "relative.txt"}, "c5")).startswith("ERROR:"))
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-fs-read", {"path": str(target), "offset": 0}, "c6")

    async def test_fs_list_accepts_directories_and_rejects_files(self):
        contract = Contract(self.root)
        target = contract.workspace / "CASE-A" / "payer" / "note.txt"
        target.write_text("x", encoding="utf-8")
        self.assertIn("note.txt", await invoke(contract.tools, contract.guard, "local-fs-list",
                                                {"path": str(target.parent)}))
        self.assertIn("policy.md", await invoke(contract.tools, contract.guard, "local-fs-list",
                                                {"path": str(contract.handbook)}, "c2"))
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-list",
                                      {"path": str(target)}, "c3")).startswith("ERROR:"))
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-list",
                                      {"path": "/"}, "c4")).startswith("ERROR:"))

    async def test_fs_write_and_edit_follow_role_paths_and_edit_semantics(self):
        contract = Contract(self.root)
        role_path = contract.workspace / "CASE-A" / "payer" / "a.txt"
        shared_path = contract.workspace / "CASE-A" / "shared" / "b.txt"
        other_path = contract.workspace / "CASE-A" / "provider" / "c.txt"
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-write",
                                      {"path": str(role_path), "content": "one one"}), "workspace file written")
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-write",
                                      {"path": str(shared_path), "content": "shared"}, "c2"),
                         "workspace file written")
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-write",
                                      {"path": str(other_path), "content": "bad"}, "c3")).startswith("REFUSED:"))
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-write",
                                      {"path": "relative.txt", "content": "bad"}, "c4")).startswith("REFUSED:"))
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-fs-write", {"path": str(role_path)}, "c5")
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-edit",
                                      {"path": str(role_path), "old_string": "one", "new_string": "two"}, "c6"),
                         "workspace file written")
        self.assertEqual(role_path.read_text(), "two one")
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-fs-edit",
                                      {"path": str(role_path), "old_string": "one", "new_string": "two",
                                       "replace_all": True}, "c7"), "workspace file written")
        self.assertEqual(role_path.read_text(), "two two")
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-edit",
                                      {"path": str(role_path), "old_string": "missing", "new_string": "x"},
                                      "c8")).startswith("ERROR:"))
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-fs-edit",
                   {"path": str(role_path), "old_string": "", "new_string": "x"}, "c9")

    async def test_fs_search_accepts_target_workspace_and_rejects_other_case(self):
        contract = Contract(self.root)
        (contract.workspace / "CASE-A" / "payer" / "note.md").write_text("prior therapy documented\n", encoding="utf-8")
        (contract.workspace / "CASE-B" / "payer" / "secret.md").write_text("prior therapy secret\n", encoding="utf-8")
        contract.state.observe(call_id="r1", tool="triage.get", kind="mcp",
                               arguments={"case_id": "CASE-A"}, result={"ok": True})
        contract.state.propose({"target": {"case_id": "CASE-A"}})
        result = json.loads(await invoke(contract.tools, contract.guard, "local-fs-search",
                                         {"path": str(contract.workspace / "CASE-A" / "payer"),
                                          "query": "prior therapy"}))
        self.assertTrue(result["results"][0]["path"].endswith("note.md"))
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-fs-search",
                                      {"path": str(contract.workspace / "CASE-B" / "payer"),
                                       "query": "prior therapy"}, "c2")).startswith("REFUSED:"))
        handbook = json.loads(await invoke(contract.tools, contract.guard, "local-fs-search",
                                           {"path": str(contract.handbook), "query": "prior therapy"}, "c3"))
        self.assertTrue(handbook["results"])
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-fs-search",
                   {"path": str(contract.handbook), "query": "x", "max_results": 0}, "c4")

    async def test_claim_refuses_missing_readback_and_open_unknown(self):
        contract = Contract(self.root)
        contract.state.observe(call_id="w1", tool="triage.set_disposition", kind="mcp",
                               arguments={"case_id": "CASE-A"}, result={"ok": True})
        self.assertTrue((await invoke(contract.tools, contract.guard, "local-claim_done", {}, "c1"))
                        .startswith("REFUSED: completion_readback_required:"))
        contract.state.observe(call_id="r1", tool="triage.get", kind="mcp",
                               arguments={"case_id": "CASE-A"}, result={"ok": True})
        contract.state.propose({"target": {"case_id": "CASE-A"},
                                "latest_business_status": {"text": "set", "source_call_id": "r1"}})
        self.assertEqual(await invoke(contract.tools, contract.guard, "local-claim_done", {}, "c2"),
                         "task marked as done")

        second = Contract(self.root / "second")
        second.state.observe(call_id="w2", tool="triage.set_disposition", kind="mcp",
                             arguments={"case_id": "CASE-A"}, result={"ok": True}, event="failed")
        self.assertTrue((await invoke(second.tools, second.guard, "local-claim_done", {}, "c3"))
                        .startswith("REFUSED: completion_blocked_unknown:"))

    async def test_state_and_completion_tools_are_bounded_and_versioned(self):
        contract = Contract(self.root)
        contract.state.observe(call_id="r1", tool="triage.get", kind="mcp",
                               arguments={"case_id": "CASE-A"}, result={"raw": "secret"})
        state = json.loads(await invoke(contract.tools, contract.guard, "local-task-state", {}))
        self.assertEqual(state["schema"], "chi-task-state-v3")
        self.assertNotIn("raw", state["observations"][0])
        completion = json.loads(await invoke(contract.tools, contract.guard, "local-completion-check", {}, "c2"))
        self.assertEqual(completion["schema"], "chi-completion-v3")
        self.assertIn("claim_policy", completion)
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-role-guidance", {"unexpected": True}, "c3")
        guidance = json.loads(await invoke(contract.tools, contract.guard, "local-role-guidance", {}, "c4"))
        self.assertEqual(guidance["schema"], GUIDANCE_VERSION)

    async def test_state_update_description_matches_actual_status_sources(self):
        contract = Contract(self.root)
        description = next(tool for tool in contract.tools
                           if tool.name == "local-state-update").description
        for name in ("cases.get_case", "auth.check_status",
                     "payer_intake_hub.get_intake_case", "triage.get",
                     "review.get_nurse_review_data", "review.get_md_review_data",
                     "determination.get_summary", "p2p.list",
                     "payer_letter_center.list", "cm_chart.get_chart_data"):
            self.assertIn(name, description)
        self.assertIn("not proof of care-plan finalize", description)
        from chi_agent.agent.task_state import source_kind_for
        self.assertEqual(source_kind_for("payer", "payer_letter_center.list", "mcp", "case:CASE-A"),
                         "business_status")
        self.assertEqual(source_kind_for("payer", "payer_letter_center.get", "mcp", "case:CASE-A"),
                         "business_evidence")
        self.assertEqual(source_kind_for("cm", "cm_chart.get_chart_data", "mcp", "case:CASE-A"),
                         "business_status")
        self.assertEqual(source_kind_for("cm", "cm_intake.get_referral", "mcp", "case:CASE-A"),
                         "business_evidence")
        self.assertEqual(source_kind_for("cm", "cm_outreach.get_transcript", "mcp", "case:CASE-A"),
                         "business_evidence")
        self.assertEqual(source_kind_for("provider", "chart.get_patient_chart_by_patient",
                                         "mcp", "case:CASE-A"), "business_evidence")

    async def test_patient_tool_schemas_reject_missing_or_negative_values(self):
        binding = SimpleNamespace(bound=None)
        contract = Contract(self.root, role="provider", binding=binding)
        names = {tool.name for tool in contract.tools}
        self.assertIn("local-read-patient-observation", names)
        self.assertIn("local-confirm-patient", names)
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-read-patient-observation", {"patient_id": "P1"}, "c1")
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-read-patient-observation",
                   {"patient_id": "P1", "offset": -1}, "c2")
        with self.assertRaises(ContractFailure):
            accept(contract.guard, "local-confirm-patient",
                   {"patient_id": "P1", "instruction_quote": "", "chart_quote": "x"}, "c3")


if __name__ == "__main__":
    unittest.main()
