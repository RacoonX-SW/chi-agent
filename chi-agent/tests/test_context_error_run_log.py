import json
import tempfile
import unittest
from pathlib import Path

import go_chi_entry


class ErrorCodeRunLogTests(unittest.TestCase):
    def test_new_codes_do_not_trigger_fallback(self):
        codes = ("chi_claim_required", "chi_drift_hard", "chi_drift_event_invalid",
                 "chi_anchor_invalid", "chi_context_profile_invalid",
                 "chi_state_program_owned", "chi_context_policy_incompatible",
                 "chi_context_assembly_limit")
        for code in codes:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                logs = Path(directory)
                value = {
                    "schema": go_chi_entry.RUN_LOG_SCHEMA,
                    "status": "incomplete",
                    "safe_error_code": code,
                    "provider_requests": 1,
                    "tool_events": 0,
                    "official_reward": None,
                    "log_fallback": False,
                }
                (logs / "run_log.txt").write_text(json.dumps(value), encoding="utf-8")
                parsed = go_chi_entry._read_run_log(logs)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed["safe_error_code"], code)
                self.assertFalse(parsed.get("log_fallback"))


if __name__ == "__main__":
    unittest.main()
