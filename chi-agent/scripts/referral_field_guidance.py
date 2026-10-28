"""Versioned, general public-source guidance for existing provider tools."""
import hashlib
import json

VERSION = "referral-field-provenance-v1"
MARKER = f"[public-field-guidance:{VERSION}]"
GUIDANCE = {
    "cases.create_from_order": (
        "For procedure, service category, urgency, diagnoses, and care setting, separately use the public "
        "task instruction, the selected patient's observed order/chart, and applicable public rules. "
        "Service category and care setting are independent fields; an institution or brand name alone "
        "does not establish the actual setting or level of care. Map supported facts to the tool enums and "
        "briefly note the source and reasoning in existing working notes or rationale. If evidence is missing "
        "or conflicts, check relevant public materials instead of guessing. Reuse observations when possible."),
    "auth.submit_authorization": (
        "Before submission, cross-check the request, form responses, and evidence package against their "
        "original public sources. Repeating a guess does not establish source support. Resolve missing or "
        "conflicting evidence using available public materials, and do not create another case to conceal an error."),
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


GUIDANCE_SHA256 = sha256(json.dumps(GUIDANCE, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def append_description(name: str, original: str) -> tuple[str, dict] | None:
    guidance = GUIDANCE.get(name)
    if guidance is None:
        return None
    if type(original) is not str or MARKER in original:
        raise ValueError("referral_guidance_description_invalid")
    final = f"{original}\n\n{MARKER}\n{guidance}"
    return final, {"guidance_sha256": sha256(guidance), "original_description_sha256": sha256(original),
                   "appended_description_sha256": sha256(final)}
