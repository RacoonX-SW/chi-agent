import unittest

from chi_agent.output_recovery import mode_and_fragment


def payload(message):
    return {
        "model": "deepseek-v4.1-flash",
        "choices": [{"finish_reason": "length", "message": {"role": "assistant", **message}}],
    }


class RecoveryShapeTests(unittest.TestCase):
    def test_name_null_is_accepted_for_partial(self):
        mode, fragment = mode_and_fragment(payload({
            "name": None,
            "content": "",
            "reasoning_content": "thinking",
            "tool_calls": None,
        }))
        self.assertEqual(mode, "partial")
        self.assertEqual(fragment, {"content": "", "reasoning_content": "thinking"})

    def test_name_string_is_accepted_for_partial(self):
        mode, fragment = mode_and_fragment(payload({
            "name": "assistant",
            "content": "partial text",
            "reasoning_content": None,
            "tool_calls": None,
        }))
        self.assertEqual(mode, "partial")
        self.assertEqual(fragment, {"content": "partial text"})

    def test_name_non_string_is_rejected(self):
        with self.assertRaises(ValueError):
            mode_and_fragment(payload({
                "name": 1,
                "content": "",
                "reasoning_content": "thinking",
                "tool_calls": None,
            }))


if __name__ == "__main__":
    unittest.main()
