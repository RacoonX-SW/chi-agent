import unittest

from go_chi_context import DEFAULT_BUDGET, check_budget, measure_request


def body():
    return {
        "model": "deepseek-v4.1-flash",
        "messages": [
            {"role": "system", "content": "system text"},
            {"role": "user", "content": "instruction text"},
            {"role": "assistant", "content": None, "reasoning_content": "reason",
             "tool_calls": [{"id": "call_1", "type": "function",
                             "function": {"name": "triage__get", "arguments": '{"case_id":"CASE-A"}'}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "tool result text"},
        ],
        "tools": [{"type": "function", "function": {"name": "x", "description": "d",
                                                    "parameters": {"type": "object"}, "strict": False}}],
        "max_tokens": 8192,
    }


class ContextTests(unittest.TestCase):
    def test_measurement_separates_composition_and_marks_estimate(self):
        metric = measure_request(body())
        self.assertEqual(metric["schema"], "chi-context-v1")
        self.assertEqual(metric["system_chars"], len("system text"))
        self.assertEqual(metric["instruction_chars"], len("instruction text"))
        self.assertEqual(metric["tool_result_chars"], len("tool result text"))
        self.assertEqual(metric["reasoning_chars"], len("reason"))
        self.assertGreater(metric["tools_chars"], 0)
        self.assertGreater(metric["total_bytes"], metric["total_chars"])
        self.assertEqual(metric["token_estimate"], "chars_div_4_not_tokenizer")
        self.assertEqual(metric["estimated_tokens"], (metric["total_chars"] + 3) // 4)
        self.assertEqual(metric["purpose"] if "purpose" in metric else None, None)

    def test_measurement_does_not_copy_raw_messages(self):
        metric = measure_request(body())
        rendered = str(metric)
        self.assertNotIn("system text", rendered)
        self.assertNotIn("tool result text", rendered)
        self.assertNotIn("CASE-A", rendered)

    def test_budget_accepts_small_request_and_rejects_over_limit(self):
        metric = measure_request(body())
        self.assertIsNone(check_budget(metric, DEFAULT_BUDGET))
        tiny = {"schema": "chi-context-budget-v1", "max_chars": 10,
                "max_estimated_tokens": 10, "output_reserve_tokens": 1,
                "basis": "test"}
        self.assertEqual(check_budget(metric, tiny), "chi_context_budget_exceeded")
        invalid = dict(DEFAULT_BUDGET)
        invalid["schema"] = "wrong"
        self.assertEqual(check_budget(metric, invalid), "chi_context_budget_invalid")

    def test_budget_none_is_record_only(self):
        self.assertIsNone(check_budget(measure_request(body()), None))

    def test_default_budget_is_conservative_and_documented(self):
        self.assertEqual(DEFAULT_BUDGET["schema"], "chi-context-budget-v1")
        self.assertLess(DEFAULT_BUDGET["max_estimated_tokens"], 1_048_576)
        self.assertIn("configured_unverified", DEFAULT_BUDGET["basis"])


if __name__ == "__main__":
    unittest.main()
