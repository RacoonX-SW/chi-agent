import unittest

from go_chi_guidance import VERSION, digest, guidance


class GuidanceTests(unittest.TestCase):
    def test_versioned_roles_and_digest(self):
        self.assertEqual(VERSION, "chi-role-guidance-v1")
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
                   "next_candidates": [{"text": "read status"}],
                   "unknowns": [{"id": "u1", "status": "open"},
                                {"id": "u2", "status": "resolved"}]}
        value = guidance("payer", summary)
        self.assertEqual(value["state_version"], 7)
        self.assertEqual(value["current_target"], {"case_id": "CASE-A"})
        self.assertEqual(value["next_candidates"], [{"text": "read status"}])
        self.assertEqual([item["id"] for item in value["unknowns"]], ["u1"])

    def test_workspace_convention_is_stated_for_every_role(self):
        for role in ("provider", "payer", "cm"):
            invariants = " ".join(guidance(role)["invariants"]).lower()
            self.assertIn("<case_id>/<role>/", invariants)
            self.assertIn("exact role id", invariants)

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
