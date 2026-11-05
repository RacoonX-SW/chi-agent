import unittest

from go_chi_guidance import VERSION, digest, guidance


class GuidanceTests(unittest.TestCase):
    def test_versioned_roles_and_digest(self):
        self.assertEqual(VERSION, "chi-role-guidance-v3")
        self.assertRegex(digest(), r"^[0-9a-f]{64}$")
        for role in ("provider", "payer", "cm"):
            value = guidance(role)
            self.assertEqual(value["schema"], VERSION)
            self.assertEqual(value["role"], role)
            self.assertGreaterEqual(len(value["stages"]), 5)
            self.assertTrue(value["invariants"])

    def test_guidance_has_no_task_ids_or_hidden_answers(self):
        for role in ("provider", "payer", "cm"):
            text = str(guidance(role)).lower()
            self.assertNotIn("pa_t0", text)
            self.assertNotIn("expectations", text)
            self.assertNotIn("rubric", text)
            self.assertNotIn("official_reward", text)

    def test_role_specific_legal_branches(self):
        provider = str(guidance("provider"))
        self.assertIn("defer", provider.lower())
        self.assertIn("do not submit", provider.lower())
        payer = str(guidance("payer"))
        self.assertIn("not a mandatory step", payer.lower())
        self.assertIn("names a later stage", payer.lower())
        self.assertIn("makes the later stage unnecessary", payer.lower())
        for outcome in ("approve", "deny", "pend", "route to md", "p2p"):
            self.assertIn(outcome, payer.lower())
        cm = str(guidance("cm"))
        self.assertIn("stop", cm.lower())
        self.assertIn("transcript", cm.lower())

    def test_state_context_and_open_unknowns_are_surfaced(self):
        summary = {"version": 7, "target": {"case_id": "CASE-A"},
                   "plans": [{"text": "finish review"}],
                   "gaps": [{"text": "missing letter", "status": "open"},
                            {"text": "old gap", "status": "resolved"}],
                   "next_candidates": [{"text": "read status"}],
                   "unknowns": [{"id": "u1", "status": "open"},
                                {"id": "u2", "status": "resolved"}]}
        value = guidance("payer", summary)
        self.assertEqual(value["state_version"], 7)
        self.assertEqual(value["current_target"], {"case_id": "CASE-A"})
        self.assertEqual(value["plans"], [{"text": "finish review"}])
        self.assertEqual([item["text"] for item in value["open_gaps"]], ["missing letter"])
        self.assertEqual(value["next_candidates"], [{"text": "read status"}])
        self.assertEqual([item["id"] for item in value["unknowns"]], ["u1"])
        self.assertTrue(value["blocked"])
        self.assertIn("patient refusal", value["note"])

    def test_workspace_convention_is_stated_for_every_role(self):
        for role in ("provider", "payer", "cm"):
            invariants = " ".join(guidance(role)["invariants"]).lower()
            self.assertIn("<case_id>/<role>/", invariants)
            self.assertIn("exact role id", invariants)

    def test_business_status_source_and_file_write_rules_are_delivered(self):
        for role in ("provider", "payer", "cm"):
            invariants = " ".join(guidance(role)["invariants"]).lower()
            self.assertIn("latest-business-status update", invariants)
            self.assertIn("evidence only", invariants)
            self.assertIn("does not require another business readback", invariants)
            self.assertIn("failed file write still blocks", invariants)
    def test_business_status_source_names_are_role_specific(self):
        provider = " ".join(guidance("provider")["invariants"]).lower()
        payer = " ".join(guidance("payer")["invariants"]).lower()
        cm = " ".join(guidance("cm")["invariants"]).lower()
        for name in ("cases.get_case", "auth.check_status"):
            self.assertIn(name, provider)
        for name in ("payer_intake_hub.get_intake_case", "triage.get",
                     "review.get_nurse_review_data", "review.get_md_review_data",
                     "determination.get_summary", "p2p.list", "payer_letter_center.list"):
            self.assertIn(name, payer)
        self.assertIn("payer_letter_center.get", payer)
        self.assertIn("cm_chart.get_chart_data", cm)
        self.assertIn("not proof that a care plan was finalized", cm)

    def test_digest_covers_the_delivered_workspace_invariant(self):
        import hashlib
        import json
        from go_chi_guidance import _INVARIANTS, _STAGES
        legacy = json.dumps({"version": VERSION, "invariants": _INVARIANTS, "stages": _STAGES},
                            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertNotEqual(digest(), hashlib.sha256(legacy).hexdigest())
        for role in ("provider", "payer", "cm"):
            self.assertEqual(guidance(role)["invariants"][-1],
                             guidance("cm")["invariants"][-1])

    def test_invalid_role_is_rejected(self):
        with self.assertRaises(ValueError):
            guidance("admin")


if __name__ == "__main__":
    unittest.main()
