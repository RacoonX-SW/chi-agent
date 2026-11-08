"""Program-derived completion evidence for chi-context-v3 runs.

The model's claim is only a signal. This module inspects program observations and
returns stable missing-step/terminal-object codes; it never reads model prose and
never produces a clinical or official verdict.
"""
from __future__ import annotations

SCHEMA = "chi-completion-evidence-v1"
POLICY = "chi-context-v3"

TERMINAL = {
    "provider": {"auth.submit_authorization", "auth.finalize_provider_determination"},
    "payer": {"review.submit_nurse_case_recommendation", "review.submit_md_case_decision",
              "determination.finalize"},
    "cm": {"cm_assessment.complete_assessment", "cm_care_plan.finalize",
           "cm_outreach.end_outreach_call"},
}
REQUIRED = {
    "provider": (
        {"chart.get_patient_chart_by_patient", "chart.search_patients"},
        {"cases.create_from_order"},
    ),
    "payer": (
        {"payer_intake_hub.get_intake_case"},
        {"triage.get", "triage.set_disposition"},
        {"review.get_nurse_review_data", "review.save_criteria_evaluation",
         "review.get_md_review_data", "review.save_md_review"},
    ),
    "cm": (
        {"cm_chart.get_chart_data"},
        {"cm_assessment.start_assessment", "cm_assessment.save_section",
         "cm_assessment.complete_assessment", "cm_care_plan.create_draft",
         "cm_care_plan.save_care_plan", "cm_care_plan.finalize",
         "cm_outreach.end_outreach_call"},
    ),
}


def evaluate(state_data):
    """Return (allowed, reason, details) from program-owned observations."""
    if type(state_data) is not dict:
        return False, "completion_state_invalid", {}
    role = state_data.get("role")
    if role not in TERMINAL:
        return False, "completion_role_invalid", {}
    observed = {item.get("tool") for item in state_data.get("observations", [])
                if type(item) is dict and item.get("event") in {"returned", "returned_error"}}
    missing = []
    for group in REQUIRED[role]:
        if not (group & observed):
            missing.append(sorted(group))
    terminal = sorted(TERMINAL[role] & observed)
    details = {"missing_steps": missing, "terminal_objects": terminal,
               "policy": POLICY, "schema": SCHEMA}
    if missing:
        return False, "completion_missing_step:" + missing[0][0], details
    if not terminal:
        return False, "completion_terminal_object_missing", details
    return True, None, details
