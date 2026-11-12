"""Source-bound request limit and ephemeral runtime feedback for K C only."""
import hashlib

CONTRACT_VERSION = "k-c-request-budget-v1"
FEEDBACK_VERSION = "k-c-runtime-feedback-v1"
MAX_REQUESTS = 50
SOFT_WARNING_AT = 5
K_C_CONTRACT = object()


def claim_recorded(journal):
    return any(item.get("model_name") == "local-claim_done" and item.get("state") == "returned"
               for item in journal.run_doc.get("tool_dispatches", []))


def feedback(used, claimed):
    if type(used) is not int or not 0 <= used < MAX_REQUESTS or type(claimed) is not bool:
        raise ValueError("request_budget_invalid")
    current = used + 1
    after = MAX_REQUESTS - current
    state = ("A completion declaration has returned; this current request can provide the final response. "
             "The declaration records a process event and does not establish business success."
             if claimed else
             "If you choose the completion declaration in this current request, a final response needs at least "
             "one additional request: two requests from now including this one. A declaration does not establish business success.")
    reminder = ("Budget is low; plan remaining work carefully. " if after <= SOFT_WARNING_AT else "")
    text = (f"\n\n<runtime_request_budget version=\"{FEEDBACK_VERSION}\">\n"
            f"Total provider request limit: {MAX_REQUESTS}. Already sent before this request: {used}. "
            f"Current request number: {current}. Remaining including this request: {MAX_REQUESTS - used}. "
            f"Remaining after this request: {after}. Counts include prior patient confirmation requests.\n"
            f"{state}\n{reminder}Finish promptly when the task's public requirements are met. "
            "If unfinished, honestly distinguish completed and remaining work; do not claim success falsely. "
            "A submitted request and a final approval are distinct unless the public task says otherwise.\n"
            "</runtime_request_budget>")
    record = {"contract_version": CONTRACT_VERSION, "feedback_version": FEEDBACK_VERSION,
              "limit": MAX_REQUESTS, "sent_before": used, "current_request": current,
              "remaining_including_current": MAX_REQUESTS - used, "remaining_after_current": after,
              "claim_recorded": claimed, "prompt_mode": "claim_recorded" if claimed else "claim_not_recorded",
              "soft_warning": after <= SOFT_WARNING_AT,
              "feedback_sha256": hashlib.sha256(text.encode()).hexdigest()}
    return text, record
