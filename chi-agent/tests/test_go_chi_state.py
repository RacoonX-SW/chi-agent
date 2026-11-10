import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from opencode_go_provider import GoFailure
from go_chi_state import (CONTEXT_POLICY_V3, LIMITS, MAX_STATE_BYTES, StateRefusal,
                          TaskState, effect_for)


class Binding:
    def __init__(self, bound=None):
        self.bound = bound


def read_call(state, call_id="call_1", case_id="CASE-A", tool="triage.get", event="returned"):
    return state.observe(call_id=call_id, tool=tool, kind="mcp",
                         arguments={"case_id": case_id}, result={"ok": True}, event=event)


def write_call(state, call_id="call_w1", case_id="CASE-A", event="returned"):
    return state.observe(call_id=call_id, tool="triage.set_disposition", kind="mcp",
                         arguments={"case_id": case_id}, result={"ok": True}, event=event)


def file_call(state, call_id="call_f1", *, event="returned", tool="local-fs-write",
              scope="case:CASE-A", path="/workspace/CASE-A/payer/letter.md"):
    return state.observe(call_id=call_id, tool=tool, kind="local",
                         arguments={"path": path}, result="workspace file written",
                         event=event, scope=scope)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "task-state"

    def tearDown(self):
        self.temp.cleanup()

    def state(self, role="payer", binding=None):
        return TaskState(self.root, run="run_1", role=role, binding=binding)

    def test_effect_classification(self):
        self.assertEqual(effect_for("triage.get", "mcp"), "read")
        self.assertEqual(effect_for("payer_intake_hub.list_documents", "mcp"), "read")
        self.assertEqual(effect_for("auth.submit_authorization", "mcp"), "mutation")
        self.assertEqual(effect_for("local-fs-search", "local"), "read")
        self.assertEqual(effect_for("local-fs-write", "local"), "mutation")
        self.assertEqual(effect_for("some_unknown_tool", "local"), "mutation")
        self.assertEqual(effect_for("future.publish", "mcp"), "mutation")

    def test_fact_and_status_require_observed_source(self):
        state = self.state()
        read_call(state)
        result = state.propose({
            "target": {"case_id": "CASE-A"},
            "facts": [{"text": "chart observed", "source_call_id": "call_1"}],
            "latest_business_status": {"text": "case open", "source_call_id": "call_1"},
        })
        self.assertEqual(result["status"], "updated")
        self.assertEqual(state.data["target"]["case_id"], "CASE-A")
        self.assertEqual(state.data["latest_business_status"]["source_seq"], 1)
        self.assertTrue((self.root / "versions" / "000002.json").is_file())
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"facts": [{"text": "made up", "source_call_id": "call_9"}]})
        self.assertEqual(caught.exception.code, "chi_state_source_unobserved")

    def test_null_target_fields_are_noops(self):
        state = self.state()
        result = state.propose({"target": {"case_id": None, "patient_id": None}})
        self.assertEqual(result["status"], "updated")
        self.assertIsNone(state.data["target"]["case_id"])
        self.assertIsNone(state.data["target"]["patient_id"])

    def test_stale_status_cannot_overwrite_newer(self):
        state = self.state()
        read_call(state, "call_1")
        read_call(state, "call_2")
        state.propose({"target": {"case_id": "CASE-A"},
                       "latest_business_status": {"text": "new", "source_call_id": "call_2"}})
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"latest_business_status": {"text": "old", "source_call_id": "call_1"}})
        self.assertEqual(caught.exception.code, "chi_state_stale")
        self.assertEqual(state.data["latest_business_status"]["source_call_id"], "call_2")

    def test_wrong_case_and_conflict_sources_are_refused(self):
        state = self.state()
        read_call(state, "call_1", "CASE-A")
        read_call(state, "call_2", "CASE-B")
        state.propose({"target": {"case_id": "CASE-A"}})
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"facts": [{"text": "other case", "source_call_id": "call_2"}]})
        self.assertEqual(caught.exception.code, "chi_state_case_mismatch")
        state.observe(call_id="call_3", tool="local-fs-read", kind="local",
                      arguments={"path": "/workspace/CASE-A/payer/a.txt"}, result="x",
                      scope="conflict")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"facts": [{"text": "conflict", "source_call_id": "call_3"}]})
        self.assertEqual(caught.exception.code, "chi_state_source_conflict")

    def test_provider_patient_must_be_bound_and_locked(self):
        unbound = self.state(role="provider", binding=Binding())
        read_call(unbound)
        unbound.propose({"target": {"case_id": "CASE-A"}})
        with self.assertRaises(StateRefusal) as caught:
            unbound.propose({"target": {"patient_id": "P1"}})
        self.assertEqual(caught.exception.code, "chi_state_patient_unbound")

        close = tempfile.TemporaryDirectory()
        self.addCleanup(close.cleanup)
        bound = TaskState(Path(close.name) / "state", run="run_2", role="provider",
                          binding=Binding("P1"))
        read_call(bound)
        bound.propose({"target": {"case_id": "CASE-A", "patient_id": "P1"}})
        with self.assertRaises(StateRefusal) as caught:
            bound.propose({"target": {"patient_id": "P2"}})
        self.assertIn(caught.exception.code, {"chi_state_target_locked", "chi_state_case_mismatch"})
        with self.assertRaises(StateRefusal) as caught:
            bound.propose({"target": {"case_id": "CASE-B"}})
        self.assertIn(caught.exception.code, {"chi_state_target_locked", "chi_state_case_mismatch"})

    def test_unknown_write_blocks_claim_until_later_read_resolves(self):
        state = self.state()
        write_call(state, event="failed")
        self.assertEqual(state.data["unknowns"][0]["status"], "open")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_blocked_unknown:"))
        read_call(state, "call_2")
        with self.assertRaises(StateRefusal):
            state.propose({"resolve_unknown": [{"unknown_id": "u9", "source_call_id": "call_2",
                                                "note": "no such unknown"}]})
        state.propose({"resolve_unknown": [{"unknown_id": "u1", "source_call_id": "call_2",
                                            "note": "status observed after failure"}],
                       "target": {"case_id": "CASE-A"}})
        # Resolving the unknown is not enough: the write still needs a readback.
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_readback_required:"))
        read_call(state, "call_3")
        state.propose({"latest_business_status": {"text": "submitted", "source_call_id": "call_3"}})
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        self.assertEqual(state.record_claim()["status"], "recorded")
        self.assertEqual(state.data["claim"]["kind"], "model_claim")

    def test_mutation_requires_readback_before_claim(self):
        state = self.state()
        write_call(state)
        state.propose({"target": {"case_id": "CASE-A"}})
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_readback_required:"))
        read_call(state, "call_2")
        state.propose({"latest_business_status": {"text": "accepted", "source_call_id": "call_2"}})
        allowed, _ = state.can_claim()
        self.assertTrue(allowed)

    def test_post_claim_mutation_invalidates_state_claim(self):
        state = self.state()
        read_call(state)
        state.propose({"target": {"case_id": "CASE-A"}})
        self.assertEqual(state.record_claim()["status"], "recorded")
        self.assertTrue(state.claim_recorded())
        write_call(state, "call_w2")
        self.assertFalse(state.claim_recorded())
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_readback_required:"))
        read_call(state, "call_3")
        state.propose({"latest_business_status": {"text": "accepted", "source_call_id": "call_3"}})
        self.assertEqual(state.record_claim()["status"], "recorded")

    def test_mutation_block_reason_after_claim(self):
        state = self.state()
        read_call(state)
        state.propose({"target": {"case_id": "CASE-A"}})
        state.record_claim()
        self.assertEqual(state.block_mutation("auth.submit_authorization", "mcp"),
                         "task_already_claimed_mutation_forbidden")
        self.assertTrue(state.data["claim_violation"])
        self.assertIsNone(state.block_mutation("triage.get", "mcp"))
        self.assertIsNone(state.block_mutation("local-claim_done", "local"))

    def test_case_scoped_facts_require_a_target(self):
        state = self.state()
        read_call(state, "call_1", "CASE-A")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"facts": [{"text": "x", "source_call_id": "call_1"}]})
        self.assertEqual(caught.exception.code, "chi_state_target_required")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"latest_business_status": {"text": "x", "source_call_id": "call_1"}})
        self.assertEqual(caught.exception.code, "chi_state_target_required")
        state.propose({"target": {"case_id": "CASE-A"}})
        state.propose({"facts": [{"text": "x", "source_call_id": "call_1"}]})

    def test_no_mutation_keeps_original_claim_behavior(self):
        state = self.state()
        read_call(state)
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        self.assertEqual(state.record_claim()["status"], "recorded")

    def test_completion_report_grades_claim_and_effect(self):
        state = self.state()
        read_call(state)
        state.propose({"target": {"case_id": "CASE-A"}})
        report = state.completion_report()
        self.assertEqual(report["verification"], "not_applicable")
        self.assertEqual(report["business_effect"], "not_observed")
        write_call(state)
        report = state.completion_report()
        self.assertEqual(report["verification"], "blocked")
        self.assertEqual(report["business_effect"], "not_verified")
        read_call(state, "call_2")
        state.propose({"latest_business_status": {"text": "accepted", "source_call_id": "call_2"}})
        report = state.completion_report()
        self.assertEqual(report["verification"], "mechanical_pass")
        self.assertEqual(report["business_effect"], "observed")
        self.assertEqual(report["last_mutation_call_id"], "call_w1")
        self.assertIn("not a clinical", report["note"])

    def test_completion_report_marks_unknown_and_violation(self):
        state = self.state()
        write_call(state, event="failed")
        report = state.completion_report()
        self.assertEqual(report["verification"], "blocked")
        self.assertEqual(report["business_effect"], "unknown")
        self.assertEqual(report["open_unknowns"], ["u1"])

    def test_limits_and_size_are_enforced(self):
        state = self.state()
        read_call(state)
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"facts": [{"text": "x" * 801, "source_call_id": "call_1"}]})
        self.assertEqual(caught.exception.code, "chi_state_update_invalid")
        with self.assertRaises(StateRefusal):
            state.propose({"plans": ["p"] * (LIMITS["plans"] + 1)})
        with self.assertRaises(StateRefusal):
            state.propose({"unknown": "field"})
        self.assertEqual(state.data["version"], 1)

    def test_persistence_failure_stops_without_advancing_version(self):
        state = self.state()
        read_call(state)
        before = state.data["version"]
        with mock.patch("go_chi_state._atomic_write", side_effect=OSError("disk")):
            with self.assertRaises(GoFailure) as caught:
                state.propose({"plans": ["next"]})
        self.assertEqual(caught.exception.code, "chi_state_persistence_failed")
        self.assertEqual(state.data["version"], before)
        self.assertEqual(state.data["plans"], [])

    def test_version_snapshots_are_kept(self):
        state = self.state()
        read_call(state)
        state.propose({"plans": ["first"]})
        state.propose({"plans": ["second"]})
        versions = sorted((self.root / "versions").glob("*.json"))
        self.assertGreaterEqual(len(versions), 3)
        last = json.loads(versions[-1].read_text())
        self.assertEqual(last["version"], state.data["version"])
        self.assertEqual(last["plans"][-1]["text"], "second")

    def test_summary_is_bounded_and_has_no_raw_results(self):
        state = self.state()
        read_call(state)
        state.propose({"plans": ["first"]})
        summary = state.summary()
        self.assertEqual(summary["schema"], "chi-task-state-v3")
        self.assertEqual(summary["observations"][0]["source_kind"], "business_status")
        self.assertNotIn("result", summary["observations"][0])
        self.assertLessEqual(len(summary["observations"]), LIMITS["observations_in_summary"])
        self.assertLess(len(json.dumps(summary).encode()), MAX_STATE_BYTES)

    def test_file_write_after_business_readback_does_not_require_another(self):
        state = self.state()
        write_call(state)
        read_call(state, "call_2")
        state.propose({"target": {"case_id": "CASE-A"},
                       "latest_business_status": {"text": "accepted", "source_call_id": "call_2"}})
        self.assertTrue(state.can_claim()[0])
        file_call(state)
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        report = state.completion_report()
        self.assertEqual(report["schema"], "chi-completion-v3")
        self.assertEqual(report["verification"], "mechanical_pass")
        self.assertEqual(report["last_business_mutation"]["call_id"], "call_w1")
        self.assertEqual(report["last_file_mutation"]["call_id"], "call_f1")
        self.assertIsNone(report["required_readback"])
        self.assertEqual(state.record_claim()["status"], "recorded")

    def test_file_policy_and_patient_reads_cannot_become_business_status(self):
        state = self.state()
        read_call(state, "call_1", "CASE-A")
        state.propose({"target": {"case_id": "CASE-A"}})
        cases = [
            ("file", dict(tool="local-fs-read", scope="case:CASE-A",
                          path="/workspace/CASE-A/payer/letter.md")),
            ("policy", dict(tool="local-fs-read", scope="shared_public",
                            path="/handbook/policy.md")),
            ("patient", dict(tool="local-read-patient-observation", scope="unattributed",
                             path="/workspace/CASE-A/payer/observation")),
            ("chart", dict(tool="chart.get_patient_chart_by_patient", scope="case:CASE-A",
                           path="/workspace/CASE-A/payer/chart")),
        ]
        for index, (name, values) in enumerate(cases, start=1):
            with self.subTest(source=name):
                call_id = "call_x" + str(index)
                state.observe(call_id=call_id, tool=values["tool"], kind="local"
                              if values["tool"].startswith("local-") else "mcp",
                              arguments={"path": values["path"]}, result="observed",
                              scope=values["scope"])
                with self.assertRaises(StateRefusal) as caught:
                    state.propose({"latest_business_status": {"text": "done", "source_call_id": call_id}})
                self.assertEqual(caught.exception.code, "chi_state_source_not_business")
        for event in ("returned_error", "refused"):
            with self.subTest(event=event):
                call_id = "call_" + event
                read_call(state, call_id, event=event)
                with self.assertRaises(StateRefusal) as caught:
                    state.propose({"latest_business_status": {"text": "done", "source_call_id": call_id}})
                self.assertEqual(caught.exception.code, "chi_state_source_not_read")
        self.assertIsNone(state.data["latest_business_status"])

    def test_file_write_failure_still_blocks_completion(self):
        state = self.state()
        file_call(state, event="returned_error")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:"))
        report = state.completion_report()
        self.assertEqual(report["verification"], "blocked")
        self.assertEqual(report["required_readback"], "file_delivery")

    def test_refused_file_write_is_not_a_failed_delivery(self):
        state = self.state()
        file_call(state, event="refused")
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        self.assertEqual(state.completion_report()["verification"], "not_applicable")

    def test_repaired_same_file_delivery_clears_failure(self):
        state = self.state()
        write_call(state)
        read_call(state, "call_2")
        state.propose({"target": {"case_id": "CASE-A"},
                       "latest_business_status": {"text": "accepted", "source_call_id": "call_2"}})
        file_call(state, "bad_edit", tool="local-fs-edit", event="returned_error")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:bad_edit"))
        file_call(state, "fixed_write", tool="local-fs-write", event="returned")
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        report = state.completion_report()
        self.assertEqual(report["verification"], "mechanical_pass")
        self.assertEqual(report["unresolved_file_deliveries"], [])
        self.assertEqual(state.record_claim()["status"], "recorded")

    def test_unrelated_or_other_case_file_success_does_not_clear_failure(self):
        state = self.state()
        file_call(state, "bad_edit", tool="local-fs-edit", event="returned_error")
        file_call(state, "other_file", tool="local-fs-write", event="returned",
                  path="/workspace/CASE-A/payer/other.md")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:bad_edit"))
        file_call(state, "other_case", tool="local-fs-write", event="returned",
                  path="/workspace/CASE-B/payer/letter.md")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:bad_edit"))
        file_call(state, "other_role", tool="local-fs-write", event="returned",
                  path="/workspace/CASE-A/provider/letter.md")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:bad_edit"))
        report = state.completion_report()
        self.assertEqual([item["call_id"] for item in report["unresolved_file_deliveries"]],
                         ["bad_edit"])

    def test_later_failure_after_repair_blocks_again(self):
        state = self.state()
        file_call(state, "bad_edit", tool="local-fs-edit", event="returned_error")
        file_call(state, "fixed_write", tool="local-fs-write", event="returned")
        self.assertTrue(state.can_claim()[0])
        file_call(state, "bad_again", tool="local-fs-edit", event="returned_error")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:bad_again"))

    def test_unknown_file_failure_still_requires_same_resource_repair(self):
        state = self.state()
        file_call(state, "bad_write", tool="local-fs-write", event="failed")
        self.assertEqual(state.data["unknowns"][0]["status"], "open")
        file_call(state, "file_read", tool="local-fs-read", event="returned")
        state.propose({"resolve_unknown": [{"unknown_id": "u1", "source_call_id": "file_read",
                                            "note": "read after failure"}]})
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_file_write_failed:bad_write"))
        file_call(state, "fixed_write", tool="local-fs-write", event="returned")
        self.assertTrue(state.can_claim()[0])

    def test_failed_file_write_registers_unknown_and_blocks_claim(self):
        state = self.state()
        file_call(state, event="failed")
        self.assertEqual(state.data["unknowns"][0]["status"], "open")
        allowed, reason = state.can_claim()
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("completion_blocked_unknown:"))

    def test_refused_business_write_does_not_require_readback(self):
        state = self.state()
        write_call(state, event="refused")
        allowed, reason = state.can_claim()
        self.assertTrue(allowed, reason)
        self.assertEqual(state.completion_report()["verification"], "not_applicable")

    def test_claim_and_report_share_the_same_blocked_reason(self):
        state = self.state()
        write_call(state)
        state.propose({"target": {"case_id": "CASE-A"}})
        allowed, reason = state.can_claim()
        report = state.completion_report()
        self.assertFalse(allowed)
        self.assertEqual(report["reason"], reason)
        self.assertEqual(report["verification"], "blocked")
        self.assertEqual(report["required_readback"], "business_status")
        self.assertIn("final_text_without_claim_not_blocked", report["remaining_limitations"])

    def test_claim_violation_blocks_claim_and_report(self):
        state = self.state()
        read_call(state)
        state.propose({"target": {"case_id": "CASE-A"}})
        state.record_claim()
        state.block_mutation("triage.set_disposition", "mcp")
        allowed, reason = state.can_claim()
        report = state.completion_report()
        self.assertFalse(allowed)
        self.assertEqual(reason, "completion_blocked_claim_violation")
        self.assertEqual(report["reason"], reason)
        self.assertEqual(report["business_effect"], "violation")

    def test_business_status_read_must_match_target_case(self):
        state = self.state()
        read_call(state, "call_1", "CASE-A")
        read_call(state, "call_2", "CASE-B")
        state.propose({"target": {"case_id": "CASE-A"}})
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"latest_business_status": {"text": "wrong", "source_call_id": "call_2"}})
        self.assertEqual(caught.exception.code, "chi_state_case_mismatch")

    def test_unknown_resolution_requires_matching_evidence_kind(self):
        state = self.state()
        write_call(state, event="failed")
        file_call(state, "call_f2", tool="local-fs-read", path="/workspace/CASE-A/payer/letter.md")
        with self.assertRaises(StateRefusal) as caught:
            state.propose({"resolve_unknown": [{"unknown_id": "u1", "source_call_id": "call_f2",
                                                "note": "file read"}]})
        self.assertEqual(caught.exception.code, "chi_state_source_not_read")
        read_call(state, "call_2")
        state.propose({"resolve_unknown": [{"unknown_id": "u1", "source_call_id": "call_2",
                                            "note": "status observed"}]})
        self.assertEqual(state.data["unknowns"][0]["status"], "resolved")

    def test_business_status_reads_are_exact_public_canonical_names(self):
        from go_chi_state import BUSINESS_STATUS_READS
        from go_chi_mcp import role_allowlists
        expected = {
            "provider": {"cases.get_case", "auth.check_status"},
            "payer": {"payer_intake_hub.get_intake_case", "triage.get",
                      "review.get_nurse_review_data", "review.get_md_review_data",
                      "determination.get_summary", "p2p.list", "payer_letter_center.list"},
            "cm": {"cm_chart.get_chart_data"},
        }
        self.assertEqual({role: set(names) for role, names in BUSINESS_STATUS_READS.items()}, expected)
        allowed = role_allowlists()
        for role, names in expected.items():
            self.assertTrue(names <= allowed[role], (role, names - allowed[role]))


class TargetBindingTests(unittest.TestCase):
    """The target binds only from a successful task-scoped read."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "task-state"

    def tearDown(self):
        self.temp.cleanup()

    def state(self, role="payer"):
        return TaskState(self.root, run="run_1", role=role,
                         context_policy=CONTEXT_POLICY_V3)

    def test_mcp_case_read_does_not_bind_target(self):
        state = self.state()
        read_call(state, "call_1", case_id="CASE-WRONG")
        self.assertIsNone(state.data["target"]["case_id"])

    def test_local_workspace_read_binds_target(self):
        state = self.state()
        file_call(state, "call_f1", tool="local-fs-read", scope="case:CASE-RIGHT",
                  path="/workspace/CASE-RIGHT/payer/incoming/request.pdf")
        self.assertEqual(state.data["target"]["case_id"], "CASE-RIGHT")

    def test_wrong_mcp_case_then_workspace_read_binds_workspace_case(self):
        state = self.state()
        read_call(state, "call_1", case_id="CASE-WRONG")
        file_call(state, "call_f1", tool="local-fs-read", scope="case:CASE-RIGHT",
                  path="/workspace/CASE-RIGHT/payer/incoming/request.pdf")
        self.assertEqual(state.data["target"]["case_id"], "CASE-RIGHT")

    def test_no_workspace_read_leaves_target_null(self):
        state = self.state()
        state.observe(call_id="call_1", tool="local-fs-read", kind="local",
                      arguments={"path": "/handbook/policy.md"}, result="policy",
                      event="returned", scope="shared_public")
        self.assertIsNone(state.data["target"]["case_id"])

    def test_failed_local_workspace_read_does_not_bind_target(self):
        state = self.state()
        state.observe(call_id="call_1", tool="local-fs-list", kind="local",
                      arguments={"path": "/workspace/CASE-WRONG/payer"},
                      result="ERROR: not found", event="returned_error",
                      scope="case:CASE-WRONG")
        self.assertIsNone(state.data["target"]["case_id"])
        file_call(state, "call_f2", tool="local-fs-list", scope="case:CASE-RIGHT",
                  path="/workspace/CASE-RIGHT/payer")
        self.assertEqual(state.data["target"]["case_id"], "CASE-RIGHT")

    def test_successful_local_list_binds_target(self):
        state = self.state()
        file_call(state, "call_f1", tool="local-fs-list", scope="case:CASE-RIGHT",
                  path="/workspace/CASE-RIGHT/payer")
        self.assertEqual(state.data["target"]["case_id"], "CASE-RIGHT")

    def test_cm_chart_read_binds_target(self):
        state = self.state(role="cm")
        state.observe(call_id="call_1", tool="cm_chart.get_chart_data", kind="mcp",
                      arguments={"case_id": "CM-CASE-RIGHT"}, result="{}",
                      event="returned", scope="case:CM-CASE-RIGHT")
        self.assertEqual(state.data["target"]["case_id"], "CM-CASE-RIGHT")

    def test_cm_failed_chart_read_does_not_bind_target(self):
        state = self.state(role="cm")
        state.observe(call_id="call_1", tool="cm_chart.get_chart_data", kind="mcp",
                      arguments={"case_id": "CM-CASE-WRONG"}, result="ERROR",
                      event="returned_error", scope="case:CM-CASE-WRONG")
        self.assertIsNone(state.data["target"]["case_id"])

    def test_cm_other_mcp_case_read_does_not_bind_target(self):
        state = self.state(role="cm")
        state.observe(call_id="call_1", tool="cm_intake.get_referral", kind="mcp",
                      arguments={"case_id": "CM-CASE-WRONG"}, result="{}",
                      event="returned", scope="case:CM-CASE-WRONG")
        self.assertIsNone(state.data["target"]["case_id"])

    def test_payer_intake_read_does_not_bind_target(self):
        state = self.state(role="payer")
        state.observe(call_id="call_1", tool="payer_intake_hub.get_intake_case", kind="mcp",
                      arguments={"case_id": "CASE-WRONG"}, result="{}",
                      event="returned", scope="case:CASE-WRONG")
        self.assertIsNone(state.data["target"]["case_id"])


if __name__ == "__main__":
    unittest.main()
