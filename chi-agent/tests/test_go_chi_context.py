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
        self.assertEqual(metric["schema"], "chi-context-v2")
        self.assertEqual(metric["system_chars"], len("system text"))
        self.assertEqual(metric["instruction_chars"], len("instruction text"))
        self.assertEqual(metric["tool_result_chars"], len("tool result text"))
        self.assertEqual(metric["reasoning_chars"], len("reason"))
        self.assertGreater(metric["tools_chars"], 0)
        self.assertGreaterEqual(metric["total_bytes"], metric["total_chars"])
        self.assertEqual(metric["token_estimate"], "utf8_bytes_upper_estimate_not_tokenizer")
        self.assertEqual(metric["estimated_tokens"], max(metric["total_bytes"], metric["raw_bytes"]))
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
        tiny = {"schema": "chi-context-budget-v2", "max_chars": 10,
                "max_estimated_tokens": 10, "output_reserve_tokens": 1,
                "basis": "test"}
        self.assertEqual(check_budget(metric, tiny), "chi_context_budget_exceeded")
        invalid = dict(DEFAULT_BUDGET)
        invalid["schema"] = "wrong"
        self.assertEqual(check_budget(metric, invalid), "chi_context_budget_invalid")

    def test_unknown_budget_is_rejected(self):
        self.assertEqual(check_budget(measure_request(body()), None), "chi_context_budget_invalid")

    def test_wire_growth_and_reservation(self):
        import json
        b = body()
        raw = json.dumps(b, ensure_ascii=True, indent=2).encode()
        metric = measure_request(b, raw)
        self.assertEqual(metric["raw_bytes"], len(raw))
        before = metric["estimated_tokens"]
        b["messages"][2]["reasoning_content"] += "汉" * 100
        b["messages"][2]["tool_calls"][0]["function"]["arguments"] += "a" * 100
        self.assertGreater(measure_request(b)["estimated_tokens"], before)
        b["max_tokens"] = 32768
        m = measure_request(b)
        budget = dict(DEFAULT_BUDGET, max_estimated_tokens=m["estimated_tokens"] + 8192)
        self.assertEqual(check_budget(m, budget), "chi_context_budget_exceeded")
        for bad in (True, None, -1):
            broken = dict(m, estimated_tokens=bad)
            self.assertEqual(check_budget(broken, DEFAULT_BUDGET), "chi_context_budget_invalid")
        for broken in (dict(m, reasoning_chars=True), dict(m, unexpected=1),
                       dict(m, total_bytes=0), dict(m, effective_output_reserve_tokens=1)):
            self.assertEqual(check_budget(broken, DEFAULT_BUDGET), "chi_context_budget_invalid")

    def test_legacy_calculation_is_unchanged(self):
        old = {"schema": "chi-context-v1", "total_chars": 40, "estimated_tokens": 10}
        budget = {"schema": "chi-context-budget-v1", "max_chars": 100, "max_estimated_tokens": 20, "output_reserve_tokens": 10}
        self.assertIsNone(check_budget(old, budget))
        budget["output_reserve_tokens"] = 11
        self.assertEqual(check_budget(old, budget), "chi_context_budget_exceeded")

    def test_wire_comparison_preserves_boolean_type(self):
        import json
        original = body()
        original['tools'][0]['function']['strict'] = False
        wire_body = body()
        wire_body['tools'][0]['function']['strict'] = 0
        with self.assertRaises(ValueError):
            measure_request(original, json.dumps(wire_body).encode())

    def test_default_budget_is_conservative_and_documented(self):
        self.assertEqual(DEFAULT_BUDGET["schema"], "chi-context-budget-v2")
        self.assertLess(DEFAULT_BUDGET["max_estimated_tokens"], 1_048_576)
        self.assertIn("configured_unverified", DEFAULT_BUDGET["basis"])


if __name__ == "__main__":
    unittest.main()
