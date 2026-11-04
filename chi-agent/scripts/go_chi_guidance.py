"""Versioned role stage guidance for Go CHI (chi-role-guidance-v3).

The guidance describes legal branches, preconditions and readbacks. It never
contains task ids, expected outcomes, rubric thresholds or hidden material.
It is delivered as an explicit tool so the official system prompt and the
request-history contract stay unchanged.
"""
from __future__ import annotations

import hashlib
import json

VERSION = "chi-role-guidance-v2"

_INVARIANTS = {
    "provider": [
        "The referred patient and target service must come from public instruction/chart evidence, not from a task id.",
        "Do not submit an under-supported packet; gathering evidence, deferring or reporting incomplete is legal.",
        "Never resubmit a case that already shows a submitted/accepted state.",
        "After any business write, read the case status back before claiming completion.",
        "A latest-business-status update must cite a returned case-state read of the target case (for example cases.get_case or auth.check_status). Handbook, policy, chart, document, workspace-file and error/refused results are evidence only.",
    ],
    "payer": [
        "Approval, partial approval, denial, pend and routing are all legal outcomes; do not assume one is correct.",
        "Presence of a document does not prove a criterion is met; apply the observed public rule to the observed facts.",
        "MD review is one possible branch, not a mandatory step for every case; when the task instruction says you own the case end to end and names a later stage such as the MD decision or P2P, perform that stage before finalizing.",
        "Closing on an earlier branch is legal only when the observed public rule makes the later stage unnecessary; record that reason in the determination or notes.",
        "Letter type and finalize/deliver actions must match the observed determination and the public rule.",
        "After finalize/deliver, read the determination or letter state back before claiming completion.",
        "A latest-business-status update must cite a returned case-state read of the target case (for example triage.get, review.get_*_review_data, determination.get_summary or payer_letter_center.list). Letter/document/file reads are evidence only.",
    ],
    "cm": [
        "Respect patient STOP and contact preferences; stop outreach when the patient declines or cannot be reached.",
        "Keep chart facts, outreach statements, assessment sections and the care plan separately sourced.",
        "Do not claim a completed assessment or plan without the corresponding save/finalize result.",
        "After a finalize write, read the case/plan state back before claiming completion.",
        "A latest-business-status update must cite a returned case-scoped business read of the target case (for example cm_chart.get_chart_data). Referral, transcript, policy and workspace-file reads are evidence only.",
    ],
}

_BUSINESS_READBACK = (
    "Saving a deliverable file after a business readback does not require another business readback; "
    "a failed file write still blocks completion."
)

_WORKSPACE_INVARIANT = ("Write artifacts only under '<case_id>/<role>/' or '<case_id>/shared/' in the role workspace; "
                        "the role directory is the exact role id (provider, payer or cm), not a job title.")

_STAGES = {
    "provider": [
        {"id": "identify_target", "goal": "Identify the patient and the service supported by the public chart.",
         "preconditions": ["public instruction read", "candidate patients/charts observed"],
         "actions": ["search patients", "read the chart and candidate orders", "compare near-neighbour candidates"],
         "readback": ["patient identity and relevant order/case"],
         "stop_if": ["candidates cannot be distinguished", "instruction and chart conflict"]},
        {"id": "verify_evidence", "goal": "Establish which public facts support or contradict the requested service.",
         "preconditions": ["target patient identified"],
         "actions": ["read orders/summaries", "read relevant policy/forms", "record citation-backed facts"],
         "readback": ["each material fact has an observed source"],
         "stop_if": ["required evidence is missing", "sources conflict"]},
        {"id": "prepare_packet", "goal": "Prepare the case, forms and evidence bundle required by the public process.",
         "preconditions": ["evidence reviewed", "required forms known"],
         "actions": ["create case from order", "save/validate forms", "upload evidence", "create submission bundle"],
         "readback": ["form validation and case documents"],
         "stop_if": ["form validation fails", "required document cannot be produced"]},
        {"id": "submit_or_defer", "goal": "Submit only when the packet is supported; otherwise defer with reasons.",
         "preconditions": ["packet prepared and validated"],
         "actions": ["submit authorization", "or record an explicit deferral and missing items"],
         "readback": ["case/authorization status"],
         "stop_if": ["status already submitted/accepted", "permission or identity is unclear"]},
        {"id": "verify_and_close", "goal": "Read the resulting business state and report completion or incompleteness.",
         "preconditions": ["a write was attempted"],
         "actions": ["read case/authorization status", "finalize only when the public process requires it"],
         "readback": ["latest status, receipt or explicit unknown"],
         "stop_if": ["write effect unknown", "request budget is exhausted"]},
    ],
    "payer": [
        {"id": "intake_review", "goal": "Understand the incoming case and its documents.",
         "preconditions": ["queue/case observed"],
         "actions": ["read intake case", "list documents", "record header/diagnoses/provider/lines when required"],
         "readback": ["intake decisions and case state"],
         "stop_if": ["case identity is ambiguous", "documents conflict"]},
        {"id": "verify_documents", "goal": "Determine which public documents are present, missing or inconsistent.",
         "preconditions": ["case and documents observed"],
         "actions": ["read each relevant document", "compare with the public checklist/rule"],
         "readback": ["document list with present/missing status"],
         "stop_if": ["a required document cannot be read", "versions conflict"]},
        {"id": "assess_criteria", "goal": "Apply the public criteria to observed facts without inventing necessity.",
         "preconditions": ["documents and applicable rule observed"],
         "actions": ["evaluate each criterion", "save the evaluation", "record unresolved items"],
         "readback": ["saved evaluation and remaining gaps"],
         "stop_if": ["rule applicability is unclear", "evidence is insufficient"]},
        {"id": "choose_disposition", "goal": "Choose a legal disposition supported by the observed rule.",
         "preconditions": ["criteria evaluation recorded"],
         "actions": ["approve", "partially approve", "deny", "request information/pend", "route to MD", "schedule P2P"],
         "readback": ["disposition/route result"],
         "stop_if": ["no legal disposition is supported", "required reviewer handoff is unavailable"]},
        {"id": "produce_letter", "goal": "Produce the letter/notification that matches the disposition.",
         "preconditions": ["disposition recorded"],
         "actions": ["generate the matching letter", "audit completeness", "deliver or reissue when required"],
         "readback": ["letter type, audit result and delivery state"],
         "stop_if": ["letter type does not match disposition", "delivery effect is unknown"]},
        {"id": "finalize_and_readback", "goal": "Finalize and verify the determination state.",
         "preconditions": ["letter and disposition consistent"],
         "actions": ["finalize determination", "read determination summary and case state"],
         "readback": ["final determination and latest case state"],
         "stop_if": ["finalize result is unknown", "case is already terminal"]},
    ],
    "cm": [
        {"id": "open_case", "goal": "Take ownership of a referred case without duplicating or crossing cases.",
         "preconditions": ["referral queue/case observed"],
         "actions": ["read referral", "open case or disenroll with a recorded reason"],
         "readback": ["case ownership/status"],
         "stop_if": ["case already owned elsewhere", "target is ambiguous"]},
        {"id": "chart_review", "goal": "Establish the clinical and social facts needed for outreach and assessment.",
         "preconditions": ["case opened"],
         "actions": ["read chart", "submit chart review"],
         "readback": ["chart review result"],
         "stop_if": ["chart is unavailable", "facts conflict"]},
        {"id": "outreach", "goal": "Contact the patient and record the actual interaction.",
         "preconditions": ["chart reviewed", "contact details observed"],
         "actions": ["start outreach call or send message", "read transcript", "end the call"],
         "readback": ["transcript and contact outcome"],
         "stop_if": ["patient STOP/declines", "contact cannot be established", "budget is nearly exhausted"]},
        {"id": "assessment", "goal": "Complete the assessment from observed facts and patient statements.",
         "preconditions": ["outreach/chart facts observed"],
         "actions": ["start assessment", "save each section", "complete assessment"],
         "readback": ["saved sections and completion result"],
         "stop_if": ["required section cannot be supported", "patient withdraws"]},
        {"id": "care_plan", "goal": "Produce a care plan consistent with the assessment.",
         "preconditions": ["assessment completed"],
         "actions": ["create draft", "save care plan", "finalize"],
         "readback": ["plan version and finalize result"],
         "stop_if": ["assessment is incomplete", "finalize effect is unknown"]},
        {"id": "close_or_report", "goal": "Close the case or report the exact remaining work.",
         "preconditions": ["plan finalized or a blocking gap recorded"],
         "actions": ["read case/plan state", "close/disenroll when appropriate"],
         "readback": ["case state and unresolved items"],
         "stop_if": ["write effect unknown", "budget is exhausted"]},
    ],
}


def delivered_invariants() -> dict[str, list[str]]:
    """Invariants exactly as delivered, including shared evidence rules."""
    return {role: _INVARIANTS[role] + [_BUSINESS_READBACK, _WORKSPACE_INVARIANT]
            for role in _INVARIANTS}


def guidance(role: str, state_summary: dict | None = None) -> dict:
    if role not in _STAGES:
        raise ValueError("chi_guidance_role_invalid")
    summary = state_summary if type(state_summary) is dict else {}
    target = summary.get("target") if type(summary.get("target")) is dict else {}
    next_candidates = summary.get("next_candidates") if type(summary.get("next_candidates")) is list else []
    return {
        "schema": VERSION,
        "role": role,
        "stages": _STAGES[role],
        "invariants": delivered_invariants()[role],
        "current_target": target,
        "next_candidates": next_candidates,
        "state_version": summary.get("version"),
        "unknowns": [item for item in summary.get("unknowns", [])
                     if type(item) is dict and item.get("status") == "open"],
        "note": "Guidance only; decide from public observations and read back after writes.",
    }


def digest() -> str:
    raw = json.dumps({"version": VERSION, "invariants": delivered_invariants(), "stages": _STAGES},
                     ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
