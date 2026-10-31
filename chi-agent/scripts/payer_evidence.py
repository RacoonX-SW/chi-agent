"""Bounded source-reference validation for the payer shadow prototype.

The module is deliberately pure: no filesystem, network, model, credential or
world access. It checks whether a checklist cites text that this run actually
sent to the main model and whether the cited character span is well formed.
It never assesses clinical meaning, rule necessity, signature validity or
whether a quote supports a claim.
"""
from __future__ import annotations

import hashlib
import json
import re

SOURCE_ID = re.compile(r"^src-[0-9]{4}$")
CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
CLAIM_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

CATEGORIES = frozenset({"fact", "inference", "rule_interpretation"})
STATUSES = frozenset({"met", "not_met", "unclear", "not_applicable"})
RULE_NATURES = frozenset({"required", "recommended", "unknown", "not_applicable"})
UNRESOLVED_KINDS = frozenset({"missing", "conflict", "unknown"})

LIMITS = {
    "payload_bytes": 65536,
    "claims": 32,
    "claim_id_chars": 64,
    "claim_text_chars": 2000,
    "action_chars": 2000,
    "case_id_chars": 96,
    "span_chars": 4000,
    "unresolved": 16,
    "unresolved_topic_chars": 500,
    "sources": 64,
    "source_text_chars": 262144,
    "registry_chars": 1048576,
    "excerpt_chars": 2000,
    "result_excerpt_chars": 200,
}

# Tool names whose results are not evidence for this contract: local directory
# listings, and the shadow tools themselves (their output is never a source).
EXCLUDED_TOOLS = frozenset({"local-fs-list"})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _unique(items):
    seen, result = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class EvidenceRegistry:
    """Per-run registry of text actually observed by the main model request."""

    def __init__(self, *, instruction: str, limits: dict | None = None):
        if type(instruction) is not str:
            raise ValueError("instruction_invalid")
        self.limits = dict(LIMITS)
        if limits is not None:
            self.limits.update(limits)
        self._sources: list[dict] = []
        self._by_call: dict[str, str | None] = {}
        self._total_chars = 0
        self._not_registered = 0
        self._case_id: str | None = None
        self._register(kind="instruction", tool=None, call_id=None, text=instruction,
                       case_scope="run", observed_round=0)

    # -- registration -----------------------------------------------------
    def _register(self, *, kind: str, tool: str | None, call_id: str | None,
                  text: str, case_scope: str, observed_round: int) -> str | None:
        if len(self._sources) >= self.limits["sources"]:
            self._not_registered += 1
            if call_id is not None:
                self._by_call[call_id] = None
            return None
        citable, reason = True, None
        if len(text) > self.limits["source_text_chars"]:
            citable, reason = False, "source_too_large"
        elif self._total_chars + len(text) > self.limits["registry_chars"]:
            citable, reason = False, "registry_limit"
        source_id = "src-%04d" % (len(self._sources) + 1)
        record = {"source_id": source_id, "kind": kind, "tool": tool, "call_id": call_id,
                  "text": text if citable else None, "chars": len(text),
                  "sha256": _sha256(text), "case_scope": case_scope,
                  "observed_round": observed_round, "citable": citable, "reason": reason}
        self._sources.append(record)
        self._total_chars += len(text) if citable else 0
        if call_id is not None:
            self._by_call[call_id] = source_id
        return source_id

    def register_observations(self, exchanges, event_for=None) -> int:
        """Register tool results that a later main request actually carried.

        ``exchanges`` is the runtime's existing observed-tool list; entries are
        only added when a request body already contained the tool message.
        """
        added = 0
        if not isinstance(exchanges, list):
            return added
        for entry in exchanges:
            if type(entry) is not dict:
                continue
            call_id = entry.get("call_id")
            if type(call_id) is not str or call_id in self._by_call:
                continue
            tool = entry.get("tool")
            if type(tool) is not str:
                continue
            if tool in EXCLUDED_TOOLS or tool.startswith("local-evidence-"):
                self._by_call[call_id] = None
                continue
            event = event_for(call_id) if callable(event_for) else "returned"
            if event != "returned":
                self._by_call[call_id] = None
                continue
            result = entry.get("result")
            if type(result) is not str or result.startswith(("ERROR:", "REFUSED:")):
                self._by_call[call_id] = None
                continue
            round_number = entry.get("observed_at_request_round")
            if type(round_number) is not int:
                continue
            self._register(kind="tool_result", tool=tool, call_id=call_id, text=result,
                           case_scope=self._case_scope(entry.get("arguments")),
                           observed_round=round_number)
            added += 1
        return added

    @staticmethod
    def _case_scope(arguments) -> str:
        """Bind a result to a case only when the call argument states one."""
        if type(arguments) is not str or not arguments:
            return "run"
        try:
            parsed = json.loads(arguments)
        except Exception:
            return "run"
        value = parsed.get("case_id") if type(parsed) is dict else None
        if type(value) is str and CASE_ID.fullmatch(value):
            return value
        return "run"

    # -- read-only views --------------------------------------------------
    def source(self, source_id: str) -> dict | None:
        if type(source_id) is not str:
            return None
        for record in self._sources:
            if record["source_id"] == source_id and record["citable"]:
                return record
        return None

    def listing(self) -> dict:
        return {
            "mode": "shadow",
            "source_count": sum(1 for item in self._sources if item["citable"]),
            "uncitable_count": sum(1 for item in self._sources if not item["citable"]),
            "not_registered_count": self._not_registered,
            "limits": {"sources": self.limits["sources"],
                       "source_text_chars": self.limits["source_text_chars"],
                       "span_chars": self.limits["span_chars"]},
            "sources": [{key: item[key] for key in
                         ("source_id", "kind", "tool", "call_id", "chars", "sha256",
                          "case_scope", "observed_round", "citable", "reason")}
                        for item in self._sources],
        }

    def excerpt(self, source_id, start_char, end_char) -> dict:
        if not (type(source_id) is str and SOURCE_ID.fullmatch(source_id)):
            return {"error": "source_id_invalid"}
        record = self.source(source_id)
        if record is None:
            return {"error": "source_unknown" if not self._known(source_id) else "source_uncitable"}
        if type(start_char) is not int or type(end_char) is not int:
            return {"error": "range_invalid"}
        if start_char < 0 or end_char <= start_char:
            return {"error": "range_invalid"}
        if end_char > len(record["text"]):
            return {"error": "range_invalid"}
        if end_char - start_char > self.limits["excerpt_chars"]:
            return {"error": "range_too_large"}
        text = record["text"][start_char:end_char]
        return {"source_id": source_id, "start_char": start_char, "end_char": end_char,
                "text": text, "span_sha256": _sha256(text),
                "source_sha256": record["sha256"]}

    def _known(self, source_id: str) -> bool:
        return any(item["source_id"] == source_id for item in self._sources)

    # -- validation -------------------------------------------------------
    def validate(self, checklist, *, payload_bytes: int | None = None) -> dict:
        reasons: list[str] = []
        limit = self.limits["payload_bytes"]
        if payload_bytes is None:
            try:
                payload_bytes = len(_dump(checklist).encode("utf-8"))
            except Exception:
                reasons.append("checklist_malformed")
                return self._result(reasons, None, [], [])
        if type(payload_bytes) is not int or payload_bytes < 0:
            reasons.append("checklist_malformed")
            return self._result(reasons, None, [], [])
        if payload_bytes > limit:
            reasons.append("checklist_too_large")
            return self._result(reasons, None, [], [])

        if type(checklist) is not dict or set(checklist) != {"case_id", "proposed_action",
                                                             "claims", "unresolved"}:
            reasons.append("checklist_malformed")
            return self._result(reasons, None, [], [])

        case_id = checklist["case_id"]
        if (type(case_id) is not str or len(case_id) > self.limits["case_id_chars"]
                or not CASE_ID.fullmatch(case_id)):
            reasons.append("case_id_invalid")
            return self._result(reasons, None, [], [])

        action = checklist["proposed_action"]
        if type(action) is not str or not action or len(action) > self.limits["action_chars"]:
            reasons.append("action_invalid")

        claims = checklist["claims"]
        unresolved = checklist["unresolved"]
        if type(claims) is not list or not claims or len(claims) > self.limits["claims"]:
            reasons.append("claims_invalid")
            claims = []
        if type(unresolved) is not list or len(unresolved) > self.limits["unresolved"]:
            reasons.append("unresolved_invalid")
            unresolved = []

        # Freeze the target case once a structurally usable checklist appears.
        if self._case_id is None:
            self._case_id = case_id
        elif self._case_id != case_id:
            reasons.append("case_scope_mismatch")

        results, seen = [], set()
        for index, claim in enumerate(claims):
            entry, claim_reasons = self._claim(claim, index, seen, case_id)
            results.append(entry)
            reasons.extend(claim_reasons)

        unresolved_out = []
        for item in unresolved:
            if (type(item) is not dict or set(item) != {"topic", "kind"}
                    or type(item["topic"]) is not str or not item["topic"]
                    or len(item["topic"]) > self.limits["unresolved_topic_chars"]
                    or type(item["kind"]) is not str or item["kind"] not in UNRESOLVED_KINDS):
                reasons.append("unresolved_invalid")
                continue
            unresolved_out.append({"topic": item["topic"], "kind": item["kind"]})
        return self._result(reasons, case_id, results, unresolved_out)

    def _claim(self, claim, index: int, seen: set, case_id: str):
        reasons: list[str] = []
        if type(claim) is not dict:
            return {"claim_id": None, "reference": "invalid", "reason": "claim_malformed"}, ["claim_malformed"]
        allowed = {"claim_id", "text", "category", "source_id", "start_char", "end_char",
                   "rule_nature", "status"}
        keys = set(claim)
        if not keys <= allowed | {"source_sha256"} or not allowed <= keys:
            return {"claim_id": claim.get("claim_id") if type(claim.get("claim_id")) is str else None,
                    "reference": "invalid", "reason": "claim_malformed"}, ["claim_malformed"]
        claim_id = claim["claim_id"]
        if (type(claim_id) is not str or len(claim_id) > self.limits["claim_id_chars"]
                or not CLAIM_ID.fullmatch(claim_id)):
            reasons.append("claim_id_invalid")
        elif claim_id in seen:
            reasons.append("claim_id_duplicate")
        else:
            seen.add(claim_id)
        text = claim["text"]
        if type(text) is not str or not text or len(text) > self.limits["claim_text_chars"]:
            reasons.append("claim_text_invalid")
        for key, allowed_values, code in (("category", CATEGORIES, "category_invalid"),
                                          ("rule_nature", RULE_NATURES, "rule_nature_invalid"),
                                          ("status", STATUSES, "status_invalid")):
            value = claim[key]
            if type(value) is not str or value not in allowed_values:
                reasons.append(code)
        entry = {"claim_id": claim_id if type(claim_id) is str else None,
                 "category_reported": claim["category"] if type(claim["category"]) is str else None,
                 "rule_nature_reported": claim["rule_nature"] if type(claim["rule_nature"]) is str else None,
                 "status_reported": claim["status"] if type(claim["status"]) is str else None,
                 "source_id": claim["source_id"] if type(claim["source_id"]) is str else None,
                 "start_char": claim["start_char"] if type(claim["start_char"]) is int else None,
                 "end_char": claim["end_char"] if type(claim["end_char"]) is int else None,
                 "reference": "invalid", "reason": None, "span_sha256": None, "excerpt": None}
        source_id = claim["source_id"]
        record = None
        if type(source_id) is not str or not SOURCE_ID.fullmatch(source_id):
            reasons.append("source_id_invalid")
        else:
            record = self.source(source_id)
            if record is None:
                reasons.append("source_unknown" if not self._known(source_id) else "source_uncitable")
        if record is not None and record["case_scope"] != "run" and record["case_scope"] != case_id:
            reasons.append("source_case_mismatch")
        supplied = claim.get("source_sha256")
        if supplied is not None:
            if type(supplied) is not str or not SHA256.fullmatch(supplied):
                reasons.append("source_hash_invalid")
            elif record is not None and supplied != record["sha256"]:
                reasons.append("source_hash_mismatch")
        start, end = claim["start_char"], claim["end_char"]
        if type(start) is not int or type(end) is not int or start < 0 or end <= start:
            reasons.append("range_invalid")
        elif record is not None and end > len(record["text"]):
            reasons.append("range_invalid")
        elif end - start > self.limits["span_chars"]:
            reasons.append("range_too_large")
        elif record is not None:
            span = record["text"][start:end]
            entry["span_sha256"] = _sha256(span)
            shown = span[:self.limits["result_excerpt_chars"]]
            entry["excerpt"] = shown
            entry["excerpt_truncated"] = len(shown) != len(span)
        if not reasons:
            entry["reference"] = "valid"
        entry["reason"] = reasons[0] if reasons else None
        return entry, reasons

    def _result(self, reasons, case_id, claims, unresolved):
        unique = _unique(reasons)
        return {
            "mode": "shadow",
            "reference_validation": "invalid" if unique else "valid",
            "reasons": unique,
            "case_id": case_id,
            "claims": claims,
            "unresolved": unresolved,
            "semantic_assessment": "not_performed",
            "rule_nature_status": "unverified_model_report",
            "source_count": sum(1 for item in self._sources if item["citable"]),
        }
