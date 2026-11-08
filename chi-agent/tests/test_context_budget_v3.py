import json
import math
import unittest

from go_chi_context import (DEFAULT_BUDGET, DEFAULT_BUDGET_V3, BUDGET_SCHEMA,
                            SCHEMA, budget_from_bytes, budget_from_input_tokens,
                            budget_pressure, calibration, check_budget,
                            measure_request)
from go_chi_policy import context_profile


def body(size=0):
    return {
        "model": "deepseek-v4.1-flash",
        "messages": [
            {"role": "system", "content": "system text"},
            {"role": "user", "content": "instruction text"},
            {"role": "user", "content": "x" * size},
        ],
        "tools": [{"type": "function", "function": {"name": "x", "description": "d",
                                                    "parameters": {"type": "object"}, "strict": False}}],
        "max_tokens": 8192,
    }


class ContextBudgetV3Tests(unittest.TestCase):
    def test_metric_names_and_units(self):
        metric = measure_request(body(), budget=DEFAULT_BUDGET_V3)
        self.assertEqual(metric["schema"], SCHEMA)
        self.assertIn("total_bytes", metric)
        self.assertIn("estimated_tokens_upper", metric)
        self.assertIn("estimated_tokens_calibrated", metric)
        self.assertNotIn("estimated_tokens", metric)
        self.assertEqual(metric["estimated_tokens_upper"],
                         math.ceil(max(metric["total_bytes"], metric["raw_bytes"]) / 3.0))
        self.assertGreaterEqual(metric["estimated_tokens_upper"],
                                metric["estimated_tokens_calibrated"])
        self.assertNotIn("max_chars", DEFAULT_BUDGET_V3)

    def test_profile_is_bound_to_model(self):
        profile = context_profile("deepseek-v4.1-flash")
        self.assertEqual(profile["model"], "deepseek-v4.1-flash")
        self.assertEqual(profile["provider_context_tokens"], 1_000_000)
        self.assertEqual(profile["bytes_per_token_floor"], 3.0)
        with self.assertRaises(ValueError):
            context_profile("other-model")

    def test_hard_gate_uses_upper_bound_and_bytes(self):
        metric = measure_request(body(), budget=DEFAULT_BUDGET_V3)
        self.assertIsNone(check_budget(metric, DEFAULT_BUDGET_V3))
        too_small = dict(DEFAULT_BUDGET_V3,
                         max_input_tokens=metric["estimated_tokens_upper"] - 1)
        self.assertEqual(check_budget(metric, too_small), "chi_context_budget_exceeded")
        too_few_bytes = dict(DEFAULT_BUDGET_V3,
                             max_context_bytes=metric["total_bytes"] - 1,
                             max_input_tokens=metric["estimated_tokens_upper"] - 1)
        self.assertEqual(check_budget(metric, too_few_bytes), "chi_context_budget_exceeded")

    def test_trigger_line_is_eighty_percent(self):
        budget = dict(DEFAULT_BUDGET_V3, max_input_tokens=100)
        # 240 bytes / 3.0 = 80 upper tokens, exactly the trigger.
        metric = measure_request(body(200), budget=budget)
        self.assertGreaterEqual(metric["estimated_tokens_upper"], 80)
        self.assertTrue(budget_pressure(metric, budget))
        below = dict(budget, max_input_tokens=1000)
        self.assertFalse(budget_pressure(metric, below))

    def test_calibration_records_observation_without_changing_threshold(self):
        metric = measure_request(body(), budget=DEFAULT_BUDGET_V3)
        result = calibration(metric, prompt_tokens=100)
        self.assertEqual(result["prompt_tokens_observed"], 100)
        self.assertIn("bytes_per_token_actual", result)
        self.assertFalse(result["warning"] is None)
        self.assertEqual(DEFAULT_BUDGET_V3["bytes_per_token_floor"], 3.0)

    def test_invalid_budget_and_metric_are_rejected(self):
        metric = measure_request(body(), budget=DEFAULT_BUDGET_V3)
        self.assertEqual(check_budget(metric, None), "chi_context_budget_invalid")
        for broken in (dict(metric, estimated_tokens_upper=True),
                       dict(metric, estimated_tokens_calibrated=-1),
                       dict(metric, unexpected=1),
                       dict(metric, total_bytes=0),
                       dict(metric, token_estimate="wrong")):
            self.assertEqual(check_budget(broken, DEFAULT_BUDGET_V3),
                             "chi_context_budget_invalid")
        for broken in (dict(DEFAULT_BUDGET_V3, max_chars=1),
                       dict(DEFAULT_BUDGET_V3, bytes_per_token_floor=0),
                       dict(DEFAULT_BUDGET_V3, bytes_per_token_observed=1.0)):
            self.assertEqual(check_budget(metric, broken), "chi_context_budget_invalid")

    def test_legacy_byte_override_keeps_byte_semantics(self):
        for value, expected_input in ((1_500_000, 500_000), (500_000, 166_666),
                                      (1, 1), (3_500_000, 583_616)):
            with self.subTest(value=value):
                budget = budget_from_bytes(value)
                self.assertEqual(budget["max_context_bytes"], value)
                self.assertEqual(budget["max_input_tokens"], expected_input)
        for bad in (0, -1, 3_500_001):
            with self.assertRaises(ValueError):
                budget_from_bytes(bad)
        token = budget_from_input_tokens(500_000)
        self.assertEqual(token["max_input_tokens"], 500_000)
        for bad in (0, 1_000_001):
            with self.assertRaises(ValueError):
                budget_from_input_tokens(bad)

    def test_legacy_v2_evidence_remains_readable(self):
        metric = measure_request(body())
        self.assertEqual(metric["schema"], "chi-context-v2")
        self.assertEqual(metric["estimated_tokens"],
                         max(metric["total_bytes"], metric["raw_bytes"]))
        self.assertIsNone(check_budget(metric, DEFAULT_BUDGET))
        # The same metric is invalid under a v3 budget; it must not be re-graded.
        self.assertEqual(check_budget(metric, DEFAULT_BUDGET_V3),
                         "chi_context_budget_invalid")

    def test_extreme_unicode_does_not_change_units(self):
        b = body()
        b["messages"][2]["content"] = "汉" * 1000 + "🙂" * 100
        metric = measure_request(b, budget=DEFAULT_BUDGET_V3)
        self.assertEqual(metric["total_chars"], len(json.dumps(b, ensure_ascii=False, sort_keys=True,
                                                                separators=(",", ":"))))
        self.assertEqual(metric["estimated_tokens_upper"],
                         math.ceil(metric["total_bytes"] / 3.0))


if __name__ == "__main__":
    unittest.main()
