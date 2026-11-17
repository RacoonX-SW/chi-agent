import unittest

import chi_agent.accounting.diagnostics as diag


class CauseTests(unittest.TestCase):
    def test_every_allowed_pair_builds(self):
        for stage, reasons in diag.STAGES.items():
            for reason in reasons:
                value = diag.build_cause(stage, reason)
                self.assertTrue(diag.validate_cause(value))
                self.assertEqual(set(value), {"schema", "stage", "reason"})
                self.assertEqual(value["schema"], "chi-safe-cause-v1")

    def test_invalid_pairs_are_rejected(self):
        for stage, reason in (("tool_batch", "body_invalid"), ("request", "call_shape"),
                              ("nope", "unspecified"), ("other", "unknown")):
            with self.subTest(stage=stage, reason=reason):
                with self.assertRaises(ValueError):
                    diag.build_cause(stage, reason)

    def test_cause_rejects_extra_fields_and_bad_types(self):
        good = diag.build_cause("tool_batch", "tool_unknown")
        for value in ({**good, "detail": "x"}, {**good, "stage": 1}, {**good, "reason": None},
                      {**good, "schema": "chi-safe-cause-v2"}, [], "tool_batch", None,
                      {"schema": good["schema"], "stage": "tool_batch", "reason": "tool_unknown",
                       "message": "boom"}):
            with self.subTest(value=value):
                self.assertFalse(diag.validate_cause(value))

    def test_cause_byte_limit(self):
        value = diag.build_cause("other", "unspecified")
        self.assertLessEqual(len(__import__("json").dumps(value, sort_keys=True,
                                                          separators=(",", ":")).encode()), 256)

    def test_code_mapping_is_finite(self):
        self.assertEqual(diag.cause_for_code("chi_timeout"),
                         {"schema": "chi-safe-cause-v1", "stage": "transport", "reason": "timeout"})
        self.assertEqual(diag.cause_for_code("chi_tool_batch_invalid"),
                         {"schema": "chi-safe-cause-v1", "stage": "other", "reason": "unspecified"})
        self.assertIsNone(diag.cause_for_code("ok"))

    def test_context_engineering_codes_are_registered(self):
        for code in ("chi_claim_required", "chi_drift_hard", "chi_drift_event_invalid",
                     "chi_anchor_invalid", "chi_context_profile_invalid",
                     "chi_state_program_owned", "chi_context_policy_incompatible",
                     "chi_context_assembly_limit", "chi_recovery_view_mismatch",
                     "chi_recovery_policy_incompatible", "chi_view_source_mismatch",
                     "chi_source_too_large", "chi_source_evidence_missing"):
            with self.subTest(code=code):
                self.assertTrue(diag.is_safe_error_code(code))
                cause = diag.cause_for_code(code)
                self.assertTrue(cause is not None and diag.validate_cause(cause))


class DiagnosticVersionTests(unittest.TestCase):
    def test_v1_accepts_old_shape_and_rejects_bad_types(self):
        doc = {"schema": "chi-go-diagnostic-v1", "kind": "diagnostic",
               "code": "chi_timeout", "elapsed_ms": 0}
        self.assertTrue(diag.validate_v1(doc))
        self.assertFalse(diag.validate_v1({**doc, "elapsed_ms": True}))
        self.assertFalse(diag.validate_v1({**doc, "code": "Bad Code"}))
        self.assertFalse(diag.validate_v1({**doc, "kind": "request"}))

    def test_v2_requires_exact_fields_and_cause_rules(self):
        ok = {"schema": "chi-go-diagnostic-v2", "kind": "diagnostic", "code": "ok",
              "elapsed_ms": 3, "cause": None}
        self.assertTrue(diag.validate_v2(ok))
        self.assertFalse(diag.validate_v2({**ok, "cause": diag.build_cause("other", "unspecified")}))
        self.assertFalse(diag.validate_v2({**ok, "extra": 1}))
        bad = {"schema": "chi-go-diagnostic-v2", "kind": "diagnostic",
               "code": "chi_timeout", "elapsed_ms": 3,
               "cause": diag.build_cause("transport", "timeout")}
        self.assertTrue(diag.validate_v2(bad))
        for value in ({**bad, "cause": None}, {**bad, "cause": "timeout"},
                      {**bad, "elapsed_ms": -1}, {**bad, "elapsed_ms": True},
                      {**bad, "cause": {**bad["cause"], "extra": 1}}):
            with self.subTest(value=value):
                self.assertFalse(diag.validate_v2(value))


if __name__ == "__main__":
    unittest.main()
