import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

from go_chi_entry import REQUIREMENTS_POLICY as ENTRY_POLICY
from go_chi_entry import _is_completion, _read_run_log_checked, main as entry_main
from go_chi_guidance import VERSION, VERSION_REQUIREMENTS, digest, guidance
from go_chi_journal import ChiJournal
from go_chi_readiness_inventory import _completion_state
from go_chi_runtime import run_chi
from go_chi_state import (MAX_REQUIREMENTS, MAX_STATE_BYTES, MAX_TEXT,
                          REQUIREMENTS_POLICY, StateRefusal, TaskState, _atomic_write)
from go_chi_tools import local_tools
from opencode_go_provider import GoFailure
from role_runner import reject_shadow_with_validation_flags, selected_validation_flags

INSTRUCTION = (
    "The member must submit a prior authorization request with supporting clinical documentation. "
    "The reviewer must document the applicable public rule and the final determination. "
    "The care manager must record the patient's preference and any refusal before closing the case."
)
Q1 = "prior authorization request"
Q2 = "supporting clinical documentation"
Q3 = "document the applicable public rule"
Q4 = "final determination"
Q5 = "record the patient's preference"


def item(identifier="r1", quote=Q1, status="open", evidence=None, waiver=None, note=None):
    return {"id": identifier, "quote": quote, "status": status,
            "evidence_call_id": evidence, "waiver_reason": waiver, "note": note}


def make_state(root, *, role="provider", instruction=INSTRUCTION, binding=None):
    return TaskState(root, run="run", role=role, binding=binding,
                     requirements=REQUIREMENTS_POLICY, instruction=instruction)


def shared(state, call_id="call_1", *, tool="local-fs-read", event="returned", result="public rule"):
    return state.observe(call_id=call_id, tool=tool, kind="local",
                         arguments={"path": "/workspace/skills/managed-care-operations-handbook/rule.md"},
                         result=result, event=event, scope="shared_public")


def case_read(state, call_id="call_1", *, case_id="CASE-A", tool="triage.get", event="returned"):
    return state.observe(call_id=call_id, tool=tool, kind="mcp",
                         arguments={"case_id": case_id}, result={"ok": True},
                         event=event, scope="case:" + case_id)


class RequirementsStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"

    def tearDown(self):
        self.temp.cleanup()

    def test_v4_initial_and_valid_quote(self):
        state = make_state(self.root)
        self.assertEqual(state.data["schema"], "chi-task-state-v4")
        self.assertFalse(state.data["requirements_declared"])
        self.assertEqual(state.data["requirements"], [])
        state.propose({"requirements": [item()]})
        self.assertTrue(state.data["requirements_declared"])
        self.assertEqual(state.data["requirements"][0]["status"], "open")
        report = state.completion_report()
        self.assertEqual(report["schema"], "chi-completion-v4")
        self.assertEqual(report["requirements"]["status"], "open")
        self.assertEqual(report["requirements"]["open_ids"], ["r1"])
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertEqual(reason, "completion_requirements_open:r1")

    def test_quote_must_be_exact_and_normalized_length(self):
        state = make_state(self.root)
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(quote="prior  authorization request")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_quote_invalid")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(quote="submit the prior authorization request")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_quote_invalid")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(quote="short quote")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_quote_invalid")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(quote="x" * (MAX_TEXT + 1))]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_quote_invalid")

    def test_limits_and_structure(self):
        state = make_state(self.root)
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(f"r{i}", Q1) for i in range(MAX_REQUIREMENTS + 1)]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_invalid")
        state.propose({"requirements": [item(f"r{i}", Q1) for i in range(1, MAX_REQUIREMENTS + 1)]})
        self.assertEqual(len(state.data["requirements"]), MAX_REQUIREMENTS)
        fresh = make_state(Path(self.temp.name) / "fresh")
        with self.assertRaises(StateRefusal) as caught:
            fresh.propose({"requirements": [item("r1", Q1), item("r1", Q2)]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_invalid")
        with self.assertRaises(StateRefusal) as caught:
            fresh.propose({"requirements": [{"id": "r1", "quote": Q1, "status": "open",
                                             "evidence_call_id": None, "waiver_reason": None,
                                             "note": None, "extra": 1}]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_invalid")
        with self.assertRaises(StateRefusal) as caught:
            fresh.propose({"requirements": [item(status="bogus")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_invalid")

    def test_instruction_binding_and_protected_fields(self):
        with self.assertRaises(GoFailure):
            TaskState(self.root, run="run", role="provider", requirements=REQUIREMENTS_POLICY)
        other = Path(self.temp.name) / "other"
        state = make_state(other)
        before = dict(state.data)
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements_declared": True})
        self.assertEqual(caught.exception.code, "chi_state_update_invalid")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements_instruction_sha256": "0" * 64})
        self.assertEqual(caught.exception.code, "chi_state_update_invalid")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"schema": "chi-task-state-v3"})
        self.assertEqual(caught.exception.code, "chi_state_update_invalid")
        self.assertEqual(state.data, before)

    def test_snapshot_append_and_open_only(self):
        state = make_state(self.root)
        state.propose({"requirements": [item("r1", Q1)]})
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item("r1", Q1), item("r2", Q2, "done",
                                                                 "call_1", None, "note")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_transition_invalid")
        state.propose({"requirements": [item("r1", Q1), item("r2", Q2)]})
        shared(state, "call_1")
        state.propose({"requirements": [item("r1", Q1), item("r2", Q2, "done",
                                                             "call_1", None, "observed rule")]})
        self.assertEqual(state.data["requirements"][1]["status"], "done")

    def test_terminal_immutability_and_rollback(self):
        state = make_state(self.root)
        shared(state, "call_1")
        state.propose({"requirements": [item("r1", Q1), item("r2", Q2)]})
        state.propose({"requirements": [item("r1", Q1, "done", "call_1", None, "note"),
                                        item("r2", Q2)]})
        version = state.data["version"]
        before = json.dumps(state.data, sort_keys=True)
        cases = [
            [item("r1", Q1, "done", "call_1", None, "note")],  # delete r2
            [item("r2", Q2), item("r1", Q1, "done", "call_1", None, "note")],  # reorder
            [item("r1", Q2, "done", "call_1", None, "note"), item("r2", Q2)],  # quote change
            [item("r1", Q1, "open"), item("r2", Q2)],  # terminal rollback
            [item("r1", Q1, "done", "call_1", None, "other"), item("r2", Q2)],  # terminal edit
        ]
        for payload in cases:
            with self.assertRaises(StateRefusal) as caught:
                state.propose({"requirements": payload})
            self.assertEqual(caught.exception.code, "chi_state_requirement_transition_invalid")
            self.assertEqual(state.data["version"], version)
            self.assertEqual(json.dumps(state.data, sort_keys=True), before)

    def test_missing_field_and_empty_declared(self):
        state = make_state(self.root)
        state.propose({"plans": ["plan"]})
        self.assertFalse(state.data["requirements_declared"])
        state.propose({"requirements": []})
        self.assertTrue(state.data["requirements_declared"])
        report = state.completion_report()
        self.assertEqual(report["requirements"]["status"], "empty_unverified")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertEqual(reason, "completion_requirements_empty")

    def test_atomic_update_and_version(self):
        state = make_state(self.root)
        shared(state, "call_1")
        version = state.data["version"]
        before = json.dumps(state.data, sort_keys=True)
        with self.assertRaises(StateRefusal):
            state.propose({"facts": [{"text": "fact", "source_call_id": "call_1"}],
                           "requirements": [item(quote="not in the instruction")]})
        self.assertEqual(state.data["version"], version)
        self.assertEqual(json.dumps(state.data, sort_keys=True), before)
        self.assertEqual(state.data["facts"], [])

    def test_done_source_rules(self):
        state = make_state(self.root)
        state.propose({"requirements": [item()]})
        for call_id in ("missing",):
            with self.assertRaises(StateRefusal) as caught:
                state.propose({"requirements": [item(status="done", evidence=call_id, note="note")]})
            self.assertEqual(caught.exception.code, "chi_state_requirement_evidence_invalid")
        for event in ("returned_error", "refused", "failed"):
            shared(state, "bad_" + event, event=event)
            with self.assertRaises(StateRefusal) as caught:
                state.propose({"requirements": [item(status="done", evidence="bad_" + event, note="note")]})
            self.assertEqual(caught.exception.code, "chi_state_requirement_evidence_invalid")
        state.observe(call_id="neutral", tool="local-task-state", kind="local",
                      arguments={}, result="state", event="returned", scope="shared_public")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(status="done", evidence="neutral", note="note")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_evidence_invalid")
        shared(state, "good")
        state.propose({"requirements": [item(status="done", evidence="good", note="observed rule")]})
        self.assertEqual(state.data["requirements"][0]["status"], "done")

    def test_waived_source_rules(self):
        state = make_state(self.root)
        state.propose({"requirements": [item()]})
        shared(state, "read")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(status="waived", evidence="read",
                                                 waiver="insufficient_evidence", note="note")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_transition_invalid")
        case_read(state, "mut", case_id="CASE-A", tool="triage.set_disposition")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(status="waived", evidence="mut",
                                                 waiver="not_applicable_public_rule", note="note")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_evidence_invalid")
        state.propose({"requirements": [item(status="waived", evidence="read",
                                             waiver="not_applicable_public_rule",
                                             note="public rule says not applicable")]})
        report = state.completion_report()
        self.assertEqual(report["requirements"]["status"], "closed_with_waivers")
        self.assertEqual(report["requirements"]["waived"], 1)

    def test_case_scope_rules(self):
        state = make_state(self.root)
        state.propose({"requirements": [item()]})
        case_read(state, "case_read")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": [item(status="done", evidence="case_read", note="note")]})
        self.assertEqual(caught.exception.code, "chi_state_requirement_evidence_invalid")
        shared(state, "shared")
        state.propose({"requirements": [item(status="done", evidence="shared", note="note")]})
        state.propose({"target": {"case_id": "CASE-A"}})
        self.assertEqual(state.data["requirements"][0]["status"], "done")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"target": {"case_id": "CASE-B"}})
        self.assertIn(caught.exception.code, {"chi_state_target_locked", "chi_state_case_mismatch"})

    def test_completion_gate_reasons(self):
        state = make_state(self.root)
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertEqual(reason, "completion_requirements_undeclared")
        state.propose({"requirements": []})
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertEqual(reason, "completion_requirements_empty")
        state.propose({"requirements": [item("r1", Q1), item("r2", Q2)]})
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertEqual(reason, "completion_requirements_open:r1")
        self.assertEqual(state.completion_report()["requirements"]["open_ids"], ["r1", "r2"])

    def test_closed_does_not_bypass_readback_unknown_file_claim(self):
        state = make_state(self.root)
        shared(state, "read")
        state.propose({"requirements": [item()]})
        state.propose({"requirements": [item(status="done", evidence="read", note="note")]})
        state.observe(call_id="write", tool="triage.set_disposition", kind="mcp",
                      arguments={"case_id": "CASE-A"}, result={"ok": True},
                      event="returned", scope="case:CASE-A")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_readback_required:"))
        # Unknown write still wins over a closed requirements list.
        state.observe(call_id="bad_write", tool="triage.set_disposition", kind="mcp",
                      arguments={"case_id": "CASE-A"}, result={"ok": False},
                      event="failed", scope="case:CASE-A")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_blocked_unknown:"))

    def test_completion_v4_counts_and_claim(self):
        state = make_state(self.root)
        shared(state, "read")
        state.propose({"requirements": [item("r1", Q1), item("r2", Q2)]})
        state.propose({"requirements": [item("r1", Q1, "done", "read", None, "note"),
                                        item("r2", Q2, "done", "read", None, "note")]})
        report = state.completion_report()
        req = report["requirements"]
        self.assertEqual(req["count"], 2)
        self.assertEqual(req["done"], 2)
        self.assertEqual(req["waived"], 0)
        self.assertEqual(req["open"], 0)
        self.assertEqual(req["open_ids"], [])
        self.assertEqual(req["status"], "closed_reported")
        self.assertEqual(req["verification"], "provenance_only")
        self.assertFalse(req["semantic_completion_verified"])
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        self.assertEqual(state.record_claim()["status"], "recorded")

    def test_duplicate_identical_resend_and_size_limit(self):
        state = make_state(self.root)
        state.propose({"requirements": [item()]})
        version = state.data["version"]
        state.propose({"requirements": [item()]})
        self.assertEqual(len(state.data["requirements"]), 1)
        self.assertEqual(state.data["version"], version + 1)
        self.assertEqual(MAX_STATE_BYTES, 65536)
        with self.assertRaises(StateRefusal) as caught:
            _atomic_write(Path(self.temp.name) / "oversize.json",
                          {"x": "a" * (MAX_STATE_BYTES + 1)})
        self.assertEqual(caught.exception.code, "chi_state_limit")

    def test_completion_revalidates_source(self):
        state = make_state(self.root)
        shared(state, "read")
        state.propose({"requirements": [item()]})
        state.propose({"requirements": [item(status="done", evidence="read", note="note")]})
        state.data["observations"][0]["event"] = "failed"
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_requirements_evidence_invalid:r1"))

    def test_off_path_v3_unchanged(self):
        state = TaskState(Path(self.temp.name) / "v3", run="run", role="provider")
        self.assertEqual(state.data["schema"], "chi-task-state-v3")
        self.assertNotIn("requirements", state.data)
        self.assertEqual(state.completion_report()["schema"], "chi-completion-v3")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"requirements": []})
        self.assertEqual(caught.exception.code, "chi_state_update_invalid")

    def test_v3_v4_isolation(self):
        v3 = TaskState(Path(self.temp.name) / "v3", run="run", role="provider")
        v4 = make_state(Path(self.temp.name) / "v4")
        v4.propose({"requirements": [item()]})
        self.assertNotIn("requirements", v3.data)
        self.assertEqual(v4.data["schema"], "chi-task-state-v4")
        self.assertEqual(len(v4.data["requirements"]), 1)


class GuidanceAndToolTests(unittest.IsolatedAsyncioTestCase):
    def test_guidance_off_and_on(self):
        off = guidance("provider")
        self.assertEqual(off["schema"], VERSION)
        self.assertNotIn("requirements_policy", off)
        self.assertEqual(digest(None), digest())
        on = guidance("provider", {"requirements_declared": True}, REQUIREMENTS_POLICY)
        self.assertEqual(on["schema"], VERSION_REQUIREMENTS)
        self.assertEqual(on["requirements_policy"], REQUIREMENTS_POLICY)
        self.assertIn("chi-requirements-v1", " ".join(on["invariants"]))
        self.assertNotEqual(digest(REQUIREMENTS_POLICY), digest())

    async def test_tool_schema_off_and_on(self):
        import asyncio
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instruction = root / "instruction.md"
            instruction.write_text(INSTRUCTION)
            handbook, workspace = root / "handbook", root / "workspace"
            handbook.mkdir(); workspace.mkdir()
            journal = SimpleNamespace(run={"requests": []})
            state = make_state(root / "state")
            common = dict(role="payer", workspace_root=workspace, instruction_path=instruction,
                          tool_references=[], handbook_root=handbook, journal=journal,
                          binding=None, guard_getter=lambda: None, client_getter=lambda: None,
                          confirmation_context=__import__("contextvars").ContextVar("x"),
                          exchanges=[], dispatch_lock=asyncio.Lock(), instruction=INSTRUCTION,
                          state=state, capabilities="f0-f3-v1")
            off = local_tools(**common)
            on = local_tools(**common, requirements=REQUIREMENTS_POLICY)
            off_update = next(tool for tool in off if tool.name == "local-state-update")
            on_update = next(tool for tool in on if tool.name == "local-state-update")
            self.assertNotIn("requirements", off_update.params_json_schema["properties"])
            self.assertIn("requirements", on_update.params_json_schema["properties"])
            self.assertNotIn("chi-requirements-v1", off_update.description)
            self.assertIn("chi-requirements-v1", on_update.description)


class EntryAndInventoryTests(unittest.TestCase):
    def _report(self):
        with tempfile.TemporaryDirectory() as d:
            state = make_state(Path(d) / "state")
            shared(state, "read")
            state.propose({"requirements": [item()]})
            state.propose({"requirements": [item(status="done", evidence="read", note="note")]})
            return state.completion_report()

    def test_entry_reader_v4(self):
        report = self._report()
        self.assertTrue(_is_completion(report))
        bad = json.loads(json.dumps(report))
        bad["requirements"]["count"] = True
        self.assertFalse(_is_completion(bad))
        bad = json.loads(json.dumps(report))
        bad["requirements"]["count"] = 2
        self.assertFalse(_is_completion(bad))
        bad = json.loads(json.dumps(report))
        bad["requirements"]["semantic_completion_verified"] = True
        self.assertFalse(_is_completion(bad))

    def test_inventory_v4(self):
        report = self._report()
        self.assertEqual(_completion_state(report)[0], "present")
        bad = json.loads(json.dumps(report))
        bad["requirements"]["open_ids"] = ["r9"]
        self.assertEqual(_completion_state(bad)[0], "invalid")

    def test_run_log_reader_v4_and_malformed(self):
        report = self._report()
        base = {"schema": "chi-go-run-log-v2", "status": "complete", "safe_error_code": None,
                "provider_requests": 1, "tool_events": 0, "official_reward": None,
                "capabilities": "f0-f3-v1", "completion": report,
                "task_state_target": {"case_id": None, "patient_id": None},
                "task_state_version": 1, "task_state_claim": None,
                "task_state_open_unknowns": [], "task_state_claim_violation": False,
                "requirements_policy": REQUIREMENTS_POLICY,
                "guidance_version": "chi-role-guidance-v4"}
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d)
            (logs / "run_log.txt").write_text(json.dumps(base), encoding="utf-8")
            self.assertIsNotNone(_read_run_log_checked(logs))
            bad = json.loads(json.dumps(base))
            bad["completion"]["requirements"]["count"] = True
            (logs / "run_log.txt").write_text(json.dumps(bad), encoding="utf-8")
            self.assertIsNone(_read_run_log_checked(logs))

    def test_runner_shadow_and_argv_abbreviation(self):
        self.assertEqual(selected_validation_flags(["--requirements=chi-requirements-v1"]),
                         {"--requirements"})
        self.assertEqual(selected_validation_flags(["--require", "chi-requirements-v1"]),
                         {"--requirements"})
        with self.assertRaises(RuntimeError):
            reject_shadow_with_validation_flags(["--requirements", "chi-requirements-v1"],
                                                {"CHI_DEV_EVIDENCE_SHADOW": "shadow"})

    def test_entry_early_reject(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = entry_main(["live", "--bundle-sha256", "a" * 64,
                               "--requirements", ENTRY_POLICY,
                               "--input-summary", "chi-input-summary-v1"])
        self.assertEqual(code, 1)
        self.assertIn("chi_requirements_configuration_invalid", out.getvalue())


class RuntimeRequirementsTests(unittest.IsolatedAsyncioTestCase):
    class Server:
        def __init__(self, name):
            self.name = name
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return False
        async def list_tools(self):
            return [SimpleNamespace(name=self.name, description="Synthetic read",
                                    inputSchema={"type": "object", "properties": {},
                                                 "additionalProperties": False})]
        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=False, structuredContent={"items": []}, content=[],
                                   model_dump=lambda **_: {"structuredContent": {"items": []},
                                                           "content": [], "isError": False})

    async def test_three_role_requirements_claim(self):
        for role, raw in (("provider", "people.list_contacts"),
                          ("payer", "triage.get"),
                          ("cm", "cm_chart.get_chart_data")):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                launch = {"kind": "chi", "role": role,
                          "fee_policy": "go-chi-record-incomplete-fees-v1",
                          "requirements": REQUIREMENTS_POLICY}
                journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval",
                                     task=role, attempt="a", run="run", launch=launch)
                instruction = root / "instruction.md"
                instruction.write_text(INSTRUCTION)
                handbook, workspace = root / "handbook", root / "workspace"
                handbook.mkdir(); workspace.mkdir()
                server = self.Server(raw)
                calls = []
                async def wire(request):
                    body = json.loads(request.content)
                    calls.append(body)
                    n = len(calls)
                    if n == 1:
                        name, args = "local-fs-read", {"path": str(instruction)}
                    elif n == 2:
                        name, args = "local-state-update", {"requirements": [item()]}
                    elif n == 3:
                        name, args = "local-state-update", {"requirements": [item(status="done",
                                                                                 evidence="call_1",
                                                                                 note="observed rule")]}
                    elif n == 4:
                        name, args = "local-claim_done", {}
                    else:
                        name, args = None, None
                    if name is not None:
                        message = {"role": "assistant", "content": None, "reasoning_content": "r",
                                   "tool_calls": [{"id": f"call_{n}", "type": "function",
                                                   "function": {"name": name,
                                                                "arguments": json.dumps(args)}}]}
                        finish = "tool_calls"
                    else:
                        message, finish = {"role": "assistant", "content": "complete"}, "stop"
                    return httpx.Response(200, request=request, json={
                        "id": "synthetic", "object": "chat.completion", "created": 0,
                        "model": "deepseek-v4.1-flash",
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                                  "cost": 0, "opencode": {"billing_source": "go",
                                                          "list_cost": 0.1, "allowance": 0.1}}})
                try:
                    output = await run_chi(
                        journal, "synthetic-secret", role=role, instruction=INSTRUCTION,
                        mcp_url="http://synthetic.invalid/mcp", instruction_path=instruction,
                        logs_dir=root / "logs", workspace_root=workspace,
                        handbook_root=handbook, tool_references=[],
                        lower=httpx.MockTransport(wire), server_factory=lambda _url: server,
                        requirements=REQUIREMENTS_POLICY)
                    self.assertEqual(output, "complete")
                    self.assertTrue(journal.run["claim_done"])
                    log = json.loads((root / "logs" / "run_log.txt").read_text())
                    self.assertEqual(log["completion"]["schema"], "chi-completion-v4")
                    self.assertEqual(log["completion"]["requirements"]["status"], "closed_reported")
                    self.assertEqual(log["requirements_policy"], REQUIREMENTS_POLICY)
                    self.assertEqual(log["guidance_version"], VERSION_REQUIREMENTS)
                    journal.finish("complete")
                finally:
                    journal.close()


    async def test_no_claim_final_keeps_open_requirements(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            launch = {"kind": "chi", "role": "provider",
                      "fee_policy": "go-chi-record-incomplete-fees-v1",
                      "requirements": REQUIREMENTS_POLICY}
            journal = ChiJournal(root / "state", identity="a" * 64, evaluation="eval",
                                 task="provider", attempt="a", run="run", launch=launch)
            instruction = root / "instruction.md"
            instruction.write_text(INSTRUCTION)
            handbook, workspace = root / "handbook", root / "workspace"
            handbook.mkdir(); workspace.mkdir()
            server = self.Server("people.list_contacts")
            calls = []
            async def wire(request):
                body = json.loads(request.content)
                calls.append(body)
                n = len(calls)
                if n == 1:
                    name, args = "local-fs-read", {"path": str(instruction)}
                elif n == 2:
                    name, args = "local-state-update", {"requirements": [item()]}
                else:
                    name, args = None, None
                if name is not None:
                    message = {"role": "assistant", "content": None, "reasoning_content": "r",
                               "tool_calls": [{"id": f"call_{n}", "type": "function",
                                               "function": {"name": name,
                                                            "arguments": json.dumps(args)}}]}
                    finish = "tool_calls"
                else:
                    message, finish = {"role": "assistant", "content": "incomplete"}, "stop"
                return httpx.Response(200, request=request, json={
                    "id": "synthetic", "object": "chat.completion", "created": 0,
                    "model": "deepseek-v4.1-flash",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                              "cost": 0, "opencode": {"billing_source": "go",
                                                      "list_cost": 0.1, "allowance": 0.1}}})
            try:
                output = await run_chi(
                    journal, "synthetic-secret", role="provider", instruction=INSTRUCTION,
                    mcp_url="http://synthetic.invalid/mcp", instruction_path=instruction,
                    logs_dir=root / "logs", workspace_root=workspace,
                    handbook_root=handbook, tool_references=[],
                    lower=httpx.MockTransport(wire), server_factory=lambda _url: server,
                    requirements=REQUIREMENTS_POLICY)
                self.assertEqual(output, "incomplete")
                self.assertFalse(journal.run["claim_done"])
                self.assertEqual(len(calls), 3)
                log = json.loads((root / "logs" / "run_log.txt").read_text())
                self.assertEqual(log["completion"]["requirements"]["status"], "open")
                self.assertEqual(log["completion"]["requirements"]["open_ids"], ["r1"])
                self.assertEqual(log["provider_requests"], 3)
                journal.finish("complete")
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
