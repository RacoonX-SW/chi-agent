import hashlib
import json
import unittest

from payer_evidence import EvidenceRegistry, LIMITS

INSTRUCTION = ("Synthetic payer instruction for case-synthetic-001. "
               "Review the referral, cite the observed material and prepare a determination.")
NURSE_POLICY = ("Synthetic policy excerpt: a registered nurse may approve when all applicable "
                "conditions are documented and no escalation trigger is present.")
GAP_POLICY = ("Synthetic coverage note: a specialist consultation is recommended but not required "
              "for this service when the remaining criteria are met.")
CONFLICT_A = "Synthetic source A: the form requires a signature before submission."
CONFLICT_B = "Synthetic source B: an unsigned form may be accepted for initial review."


def span(text, quote, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(quote, start + 1)
    return start, start + len(quote)


def claim(source_id, start, end, **over):
    value = {"claim_id": "c1", "text": "Synthetic claim text.", "category": "fact",
             "source_id": source_id, "start_char": start, "end_char": end,
             "rule_nature": "unknown", "status": "unclear"}
    value.update(over)
    return value


def checklist(claims, case_id="case-synthetic-001", action="prepare_determination", unresolved=None):
    return {"case_id": case_id, "proposed_action": action, "claims": claims,
            "unresolved": unresolved or []}


def observed(call_id, text, *, tool="triage.get", arguments="{}", round_number=1):
    return {"call_id": call_id, "tool": tool, "arguments": arguments, "result": text,
            "observed_at_request_round": round_number}


class RegistryTests(unittest.TestCase):
    def test_instruction_citation_is_valid_and_semantic_stays_unperformed(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        start, end = span(INSTRUCTION, "case-synthetic-001")
        result = registry.validate(checklist([claim("src-0001", start, end)]))
        self.assertEqual(result["reference_validation"], "valid", result)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["semantic_assessment"], "not_performed")
        self.assertEqual(result["rule_nature_status"], "unverified_model_report")
        entry = result["claims"][0]
        self.assertEqual(entry["excerpt"], "case-synthetic-001")
        self.assertEqual(entry["span_sha256"],
                         hashlib.sha256(b"case-synthetic-001").hexdigest())
        self.assertNotIn("approved", json.dumps(result))

    def test_unobserved_and_future_ids_are_invalid_until_observed(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        result = registry.validate(checklist([claim("src-0002", 0, 1)]))
        self.assertEqual(result["reference_validation"], "invalid")
        self.assertIn("source_unknown", result["reasons"])
        registry.register_observations([observed("call_1", GAP_POLICY)])
        start, end = span(GAP_POLICY, "recommended")
        result = registry.validate(checklist([claim("src-0002", start, end)]))
        self.assertEqual(result["reference_validation"], "valid", result)

    def test_same_batch_result_is_not_citable_until_next_request(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        exchanges = []
        registry.register_observations(exchanges)
        result = registry.validate(checklist([claim("src-0002", 0, 4)]))
        self.assertIn("source_unknown", result["reasons"])
        exchanges.append(observed("call_1", GAP_POLICY))
        registry.register_observations(exchanges)
        result = registry.validate(checklist([claim("src-0002", 0, 4)]))
        self.assertEqual(result["reference_validation"], "valid", result)

    def test_errors_listings_and_shadow_results_are_not_sources(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        exchanges = [
            observed("call_1", "a.txt\nb.txt", tool="local-fs-list"),
            observed("call_2", '{"mode":"shadow"}', tool="local-evidence-sources"),
            observed("call_3", "not evidence", tool="triage.get"),
            observed("call_4", "REFUSED: case_unverified", tool="triage.get"),
        ]
        events = {"call_1": "returned", "call_2": "returned",
                  "call_3": "returned_error", "call_4": "refused"}
        registry.register_observations(exchanges, events.get)
        listing = registry.listing()
        self.assertEqual(listing["source_count"], 1)
        self.assertTrue(listing["sources"][0]["source_id"] == "src-0001")
        result = registry.validate(checklist([claim("src-0002", 0, 1)]))
        self.assertIn("source_unknown", result["reasons"])

    def test_source_from_another_case_is_rejected(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([
            observed("call_1", GAP_POLICY, arguments='{"case_id": "case-synthetic-999"}')])
        start, end = span(GAP_POLICY, "recommended")
        result = registry.validate(checklist([claim("src-0002", start, end)]))
        self.assertEqual(result["reference_validation"], "invalid")
        self.assertIn("source_case_mismatch", result["reasons"])

    def test_source_without_case_argument_is_run_scoped(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([
            observed("call_1", GAP_POLICY, arguments='{"note": "no case id"}')])
        start, end = span(GAP_POLICY, "recommended")
        result = registry.validate(checklist([claim("src-0002", start, end)]))
        self.assertEqual(result["reference_validation"], "valid", result)

    def test_range_boundaries_and_span_limit(self):
        text = "x" * 5000
        registry = EvidenceRegistry(instruction=text)
        good = registry.validate(checklist([claim("src-0001", 0, 4000)]))
        self.assertEqual(good["reference_validation"], "valid", good)
        too_long = registry.validate(checklist([claim("src-0001", 0, 4001)]))
        self.assertIn("range_too_large", too_long["reasons"])
        self.assertIn("range_invalid", registry.validate(
            checklist([claim("src-0001", 4001, 4001)]))["reasons"])
        self.assertIn("range_invalid", registry.validate(
            checklist([claim("src-0001", -1, 4)]))["reasons"])
        self.assertIn("range_invalid", registry.validate(
            checklist([claim("src-0001", 0, 5001)]))["reasons"])
        self.assertIn("range_invalid", registry.validate(
            checklist([claim("src-0001", True, 4)]))["reasons"])

    def test_source_hash_tampering_is_rejected(self):
        registry = EvidenceRegistry(instruction=GAP_POLICY)
        start, end = span(GAP_POLICY, "recommended")
        correct = hashlib.sha256(GAP_POLICY.encode()).hexdigest()
        ok = registry.validate(checklist([claim("src-0001", start, end, source_sha256=correct)]))
        self.assertEqual(ok["reference_validation"], "valid", ok)
        wrong = registry.validate(checklist([claim("src-0001", start, end,
                                                   source_sha256="0" * 64)]))
        self.assertIn("source_hash_mismatch", wrong["reasons"])
        bad = registry.validate(checklist([claim("src-0001", start, end, source_sha256="xyz")]))
        self.assertIn("source_hash_invalid", bad["reasons"])

    def test_duplicate_and_bad_claim_ids(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        start, end = span(INSTRUCTION, "case-synthetic-001")
        duplicate = registry.validate(checklist([
            claim("src-0001", start, end, claim_id="c1"),
            claim("src-0001", start, end, claim_id="c1")]))
        self.assertIn("claim_id_duplicate", duplicate["reasons"])
        bad = registry.validate(checklist([claim("src-0001", start, end, claim_id="bad id!")]))
        self.assertIn("claim_id_invalid", bad["reasons"])

    def test_malformed_structures_are_rejected(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        start, end = span(INSTRUCTION, "case-synthetic-001")
        self.assertIn("checklist_malformed", registry.validate("not a dict")["reasons"])
        self.assertIn("checklist_malformed", registry.validate(
            {"case_id": "case-synthetic-001", "proposed_action": "x", "claims": []})["reasons"])
        extra = checklist([claim("src-0001", start, end)])
        extra["extra"] = True
        self.assertIn("checklist_malformed", registry.validate(extra)["reasons"])
        extra_claim = claim("src-0001", start, end)
        extra_claim["extra"] = True
        self.assertIn("claim_malformed", registry.validate(checklist([extra_claim]))["reasons"])
        self.assertIn("category_invalid", registry.validate(
            checklist([claim("src-0001", start, end, category="clinical_truth")]))["reasons"])
        self.assertIn("unresolved_invalid", registry.validate(
            checklist([claim("src-0001", start, end)],
                      unresolved=[{"topic": "x", "kind": "missing", "extra": 1}]))["reasons"])

    def test_size_limits_and_exact_boundaries(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        start, end = span(INSTRUCTION, "case-synthetic-001")
        self.assertEqual(registry.validate(checklist([claim("src-0001", start, end)]),
                                           payload_bytes=LIMITS["payload_bytes"])
                         ["reference_validation"], "valid")
        self.assertIn("checklist_too_large", registry.validate(
            checklist([claim("src-0001", start, end)]),
            payload_bytes=LIMITS["payload_bytes"] + 1)["reasons"])
        many = [claim("src-0001", start, end, claim_id="c%d" % index)
                for index in range(LIMITS["claims"] + 1)]
        self.assertIn("claims_invalid", registry.validate(checklist(many))["reasons"])
        exactly = [claim("src-0001", start, end, claim_id="c%d" % index)
                   for index in range(LIMITS["claims"])]
        self.assertEqual(registry.validate(checklist(exactly))["reference_validation"], "valid")
        long_text = "x" * LIMITS["claim_text_chars"]
        self.assertEqual(registry.validate(checklist([
            claim("src-0001", start, end, text=long_text)]))["reference_validation"], "valid")
        self.assertIn("claim_text_invalid", registry.validate(checklist([
            claim("src-0001", start, end, text=long_text + "x")]))["reasons"])
        unresolved = [{"topic": "t", "kind": "unknown"} for _ in range(LIMITS["unresolved"] + 1)]
        self.assertIn("unresolved_invalid", registry.validate(
            checklist([claim("src-0001", start, end)], unresolved=unresolved))["reasons"])
        self.assertEqual(registry.validate(checklist(
            [claim("src-0001", start, end)],
            unresolved=unresolved[:LIMITS["unresolved"]]))["reference_validation"], "valid")
        self.assertIn("case_id_invalid", registry.validate(
            checklist([claim("src-0001", start, end)], case_id="c" * 97))["reasons"])

    def test_recommended_gap_is_kept_as_unresolved_not_converted(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([observed("call_1", GAP_POLICY)])
        start, end = span(GAP_POLICY, "recommended but not required")
        result = registry.validate(checklist([
            claim("src-0002", start, end, category="rule_interpretation",
                  rule_nature="recommended", status="not_met", text="Consultation is recommended.")],
            unresolved=[{"topic": "consultation", "kind": "missing"}]))
        self.assertEqual(result["reference_validation"], "valid", result)
        self.assertEqual(result["unresolved"], [{"topic": "consultation", "kind": "missing"}])
        self.assertEqual(result["claims"][0]["rule_nature_reported"], "recommended")
        self.assertEqual(result["rule_nature_status"], "unverified_model_report")
        self.assertFalse(any(key in result for key in ("pending", "blocked", "approved")))

    def test_required_gap_and_missing_file_are_represented_without_submission(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([observed("call_1", CONFLICT_A)])
        start, end = span(CONFLICT_A, "requires a signature")
        result = registry.validate(checklist([
            claim("src-0002", start, end, category="rule_interpretation",
                  rule_nature="required", status="not_met")],
            unresolved=[{"topic": "signed form", "kind": "missing"}]))
        self.assertEqual(result["reference_validation"], "valid", result)
        self.assertEqual(result["claims"][0]["status_reported"], "not_met")
        self.assertNotIn("request_info", json.dumps(result))
        self.assertEqual(result["semantic_assessment"], "not_performed")

    def test_conflicting_sources_are_both_located(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([observed("call_1", CONFLICT_A),
                                        observed("call_2", CONFLICT_B)])
        first = span(CONFLICT_A, "requires a signature")
        second = span(CONFLICT_B, "may be accepted")
        result = registry.validate(checklist([
            claim("src-0002", *first, claim_id="a", category="rule_interpretation",
                  rule_nature="required"),
            claim("src-0003", *second, claim_id="b", category="rule_interpretation",
                  rule_nature="unknown")],
            unresolved=[{"topic": "signature", "kind": "conflict"}]))
        self.assertEqual(result["reference_validation"], "valid", result)
        self.assertNotEqual(result["claims"][0]["span_sha256"],
                            result["claims"][1]["span_sha256"])
        self.assertEqual(result["unresolved"][0]["kind"], "conflict")

    def test_semantically_wrong_but_structurally_valid_reference(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([observed("call_1", NURSE_POLICY)])
        start, end = span(NURSE_POLICY, "a registered nurse may approve")
        result = registry.validate(checklist([
            claim("src-0002", start, end, category="rule_interpretation",
                  rule_nature="required",
                  text="Policy mandates immediate suspension of all approvals.")]))
        self.assertEqual(result["reference_validation"], "valid", result)
        self.assertEqual(result["semantic_assessment"], "not_performed")
        self.assertNotIn("incorrect", result["reasons"])

    def test_nurse_approval_route_is_not_structurally_rejected(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([observed("call_1", NURSE_POLICY)])
        start, end = span(NURSE_POLICY, "a registered nurse may approve")
        result = registry.validate(checklist(
            [claim("src-0002", start, end, category="rule_interpretation",
                   rule_nature="recommended", status="met")],
            action="approve_nurse_recommendation"))
        self.assertEqual(result["reference_validation"], "valid", result)
        self.assertEqual(result["semantic_assessment"], "not_performed")

    def test_target_case_is_frozen_after_first_structural_check(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        start, end = span(INSTRUCTION, "case-synthetic-001")
        self.assertEqual(registry.validate(checklist([claim("src-0001", start, end)]))
                         ["reference_validation"], "valid")
        second = registry.validate(checklist([claim("src-0001", start, end)],
                                             case_id="case-synthetic-002"))
        self.assertIn("case_scope_mismatch", second["reasons"])

    def test_results_are_deterministic_and_do_not_mutate_sources(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        start, end = span(INSTRUCTION, "case-synthetic-001")
        payload = checklist([claim("src-0001", start, end)])
        first = registry.validate(payload)
        second = registry.validate(payload)
        self.assertEqual(first, second)
        self.assertEqual(registry.listing()["source_count"], 1)

    def test_excerpt_tool_bounds_and_text(self):
        registry = EvidenceRegistry(instruction=GAP_POLICY)
        start, end = span(GAP_POLICY, "recommended")
        exact = registry.excerpt("src-0001", start, end)
        self.assertEqual(exact["text"], "recommended")
        self.assertEqual(exact["span_sha256"], hashlib.sha256(b"recommended").hexdigest())
        self.assertIn("error", registry.excerpt("src-0001", 0, 10 ** 6))
        self.assertEqual(registry.excerpt("src-9999", 0, 1)["error"], "source_unknown")
        self.assertEqual(registry.excerpt("bad", 0, 1)["error"], "source_id_invalid")
        long_registry = EvidenceRegistry(instruction="q" * 3000)
        self.assertEqual(long_registry.excerpt("src-0001", 0, LIMITS["excerpt_chars"] + 1)["error"],
                         "range_too_large")

    def test_oversized_source_is_listed_but_uncitable(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([
            observed("call_1", "y" * LIMITS["source_text_chars"])])
        exact = next(item for item in registry.listing()["sources"]
                     if item["source_id"] == "src-0002")
        self.assertTrue(exact["citable"])
        big = "y" * (LIMITS["source_text_chars"] + 1)
        registry.register_observations([observed("call_2", big)])
        listing = registry.listing()
        source = next(item for item in listing["sources"] if item["source_id"] == "src-0003")
        self.assertFalse(source["citable"])
        self.assertEqual(source["reason"], "source_too_large")
        self.assertEqual(registry.excerpt("src-0003", 0, 4)["error"], "source_uncitable")
        result = registry.validate(checklist([claim("src-0003", 0, 4)]))
        self.assertIn("source_uncitable", result["reasons"])

    def test_source_and_registry_limits_are_enforced(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        exchanges = [observed("call_%d" % index, "text-%04d" % index)
                     for index in range(LIMITS["sources"])]
        registry.register_observations(exchanges)
        listing = registry.listing()
        self.assertEqual(len(listing["sources"]), LIMITS["sources"])
        self.assertEqual(listing["not_registered_count"], 1)

        registry = EvidenceRegistry(instruction=INSTRUCTION)
        chunk = "z" * 200000
        registry.register_observations([observed("call_%d" % index, chunk)
                                        for index in range(6)])
        uncitable = [item for item in registry.listing()["sources"] if not item["citable"]]
        self.assertTrue(uncitable)
        self.assertIn("registry_limit", {item["reason"] for item in uncitable})

    def test_listing_never_returns_source_text(self):
        registry = EvidenceRegistry(instruction=INSTRUCTION)
        registry.register_observations([observed("call_1", GAP_POLICY)])
        encoded = json.dumps(registry.listing())
        self.assertNotIn(GAP_POLICY, encoded)
        self.assertNotIn('"text"', encoded)


if __name__ == "__main__":
    unittest.main()
