import unittest

from go_chi_contract import ContractFailure, ToolContract
from request_budget import feedback


def definition():
    return [{"type": "function", "function": {"name": "read", "description": "Read", "strict": False,
        "parameters": {"type": "object", "properties": {"id": {"type": "integer"}},
                       "required": ["id"], "additionalProperties": False}}}]


def call(call_id, arguments):
    return {"id": call_id, "type": "function", "function": {"name": "read", "arguments": arguments}}


def provenance_definitions():
    return [
        {"type": "function", "function": {
            "name": "start", "description": "Start", "strict": False,
            "parameters": {"type": "object", "properties": {},
                           "required": [], "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "send", "description": "Send", "strict": False,
            "parameters": {"type": "object",
                           "properties": {"session_id": {"type": "string"},
                                          "message": {"type": "string"}},
                           "required": ["session_id", "message"],
                           "additionalProperties": False}}},
    ]


def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments}}


def message(calls):
    return {"role": "assistant", "content": None, "reasoning_content": "think", "tool_calls": calls}


class ContractTests(unittest.TestCase):
    def test_reasoning_presence_and_content_are_history_bound(self):
        import copy
        for reasoning in (None, '', 'reason'):
            with self.subTest(reasoning=reasoning):
                contract = ToolContract(definition())
                batch = message([call('a', '{"id":1}')])
                if reasoning is None: del batch['reasoning_content']
                else: batch['reasoning_content'] = reasoning
                contract.accept_batch(batch); contract.record_result('a', 'observed')
                history = [{'role': 'system', 'content': 'system' + feedback(1, False)[0]},
                           {'role': 'user', 'content': 'instruction'}, copy.deepcopy(batch),
                           {'role': 'tool', 'tool_call_id': 'a', 'content': 'observed'}]
                contract.validate_history(history, system='system', instruction='instruction', used=1, claimed=False)
                if reasoning is None: history[2]['reasoning_content'] = ''
                else: del history[2]['reasoning_content']
                with self.assertRaises(ContractFailure):
                    contract.validate_history(history, system='system', instruction='instruction', used=1, claimed=False)

    def test_invalid_second_call_refuses_whole_batch(self):
        contract = ToolContract(definition())
        calls = contract.accept_batch(message([call("a", '{"id":1}'), call("b", '{"id":"bad"}')]), recover_schema=True)
        self.assertEqual([item["id"] for item in calls], ["a", "b"])
        self.assertEqual(len(contract.records), 2)
        for item in calls:
            self.assertTrue(contract.refusals[item["id"]].startswith("chi_tool_arguments_invalid: read:"))
            contract.record_result(item["id"], "REFUSED: " + contract.refusals[item["id"]])
        contract.accept_batch(message([call("c", '{"id":1}')]))

    def test_schema_refusal_names_missing_and_unknown_fields(self):
        contract = ToolContract(definition())
        calls = contract.accept_batch(message([call("a", '{}')]), recover_schema=True)
        self.assertIn("missing required field(s) id", contract.refusals["a"])
        contract.record_result("a", "REFUSED: " + contract.refusals["a"])
        calls = contract.accept_batch(message([call("b", '{"id":1,"extra":2}')]), recover_schema=True)
        self.assertIn("unknown field(s) extra", contract.refusals["b"])
        contract.record_result("b", "REFUSED: " + contract.refusals["b"])

    def test_schema_refusal_is_bounded(self):
        contract = ToolContract(definition())
        for index in range(ToolContract.RECOVERABLE_SCHEMA_LIMIT):
            call_id = f"a{index}"
            calls = contract.accept_batch(message([call(call_id, '{}')]), recover_schema=True)
            contract.record_result(call_id, "REFUSED: " + contract.refusals[call_id])
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("overflow", '{}')]), recover_schema=True)

    def test_missing_argument_hint_uses_prior_result(self):
        contract = ToolContract(provenance_definitions())
        contract.accept_batch(message([tool_call("s1", "start", "{}")]))
        contract.record_result("s1", '{"session_id":"SES-6046D5EC","status":"active"}')
        contract.accept_batch(message([tool_call("m1", "send", '{"message":"hello"}')]),
                              recover_schema=True)
        refusal = contract.refusals["m1"]
        self.assertIn("missing required field(s) session_id", refusal)
        self.assertIn("session_id=SES-6046D5EC", refusal)
        self.assertIn("from start (s1)", refusal)

    def test_missing_argument_hint_accepts_text_block_results(self):
        contract = ToolContract(provenance_definitions())
        contract.accept_batch(message([tool_call("s1", "start", "{}")]))
        contract.record_result("s1", [{"type": "text",
                                       "text": '{"session_id":"SES-TEXT","status":"active"}'}])
        contract.accept_batch(message([tool_call("m1", "send", '{"message":"hello"}')]),
                              recover_schema=True)
        self.assertIn("session_id=SES-TEXT", contract.refusals["m1"])

    def test_missing_argument_hint_absent_without_prior_value(self):
        contract = ToolContract(provenance_definitions())
        contract.accept_batch(message([tool_call("m1", "send", '{"message":"hello"}')]),
                              recover_schema=True)
        self.assertIn("missing required field(s) session_id", contract.refusals["m1"])
        self.assertNotIn("observed ", contract.refusals["m1"])

    def test_missing_argument_hint_ignores_non_json_results(self):
        contract = ToolContract(provenance_definitions())
        contract.accept_batch(message([tool_call("s1", "start", "{}")]))
        contract.record_result("s1", "not json")
        contract.accept_batch(message([tool_call("m1", "send", '{"message":"hello"}')]),
                              recover_schema=True)
        self.assertNotIn("observed ", contract.refusals["m1"])

    def test_json_syntax_error_is_refused_atomically(self):
        contract = ToolContract(definition())
        calls = contract.accept_batch(message([call("a", '{"id":"secret-value"')]), recover_schema=True)
        self.assertEqual([item["id"] for item in calls], ["a"])
        self.assertIn("chi_tool_arguments_json_invalid", contract.refusals["a"])
        self.assertNotIn("secret-value", contract.refusals["a"])
        self.assertEqual(contract.json_refusals, 1)
        self.assertEqual(contract.total_refusals, 1)
        self.assertEqual(contract.records[0]["arguments"], {"__chi_invalid_json__": True})
        contract.record_result("a", "REFUSED: " + contract.refusals["a"])
        contract.accept_batch(message([call("b", '{"id":1}')]))

    def test_json_syntax_error_stays_fatal_without_recovery(self):
        contract = ToolContract(definition())
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("a", '{"id":')]))

    def test_total_recovery_limit_spans_schema_and_json(self):
        contract = ToolContract(definition())
        for index in range(ToolContract.RECOVERABLE_SCHEMA_LIMIT):
            call_id = f"s{index}"
            calls = contract.accept_batch(message([call(call_id, '{}')]), recover_schema=True)
            contract.record_result(call_id, "REFUSED: " + contract.refusals[call_id])
        calls = contract.accept_batch(message([call("j0", '{"id":')]), recover_schema=True)
        contract.record_result("j0", "REFUSED: " + contract.refusals["j0"])
        self.assertEqual(contract.total_refusals, 3)
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("overflow", '{"id":1,"extra":2}')]), recover_schema=True)

    def test_duplicate_id_and_result_are_rejected(self):
        contract = ToolContract(definition())
        contract.accept_batch(message([call("a", '{"id":1}')]))
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("b", '{"id":2}')]))
        contract.record_result("a", "ok")
        with self.assertRaises(ContractFailure):
            contract.record_result("a", "again")
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("a", '{"id":1}')]))

    def test_definitions_are_frozen_and_duplicate_json_rejected(self):
        defs = definition()
        contract = ToolContract(defs)
        defs[0]["function"]["description"] = "changed"
        self.assertFalse(contract.definitions_match(defs))
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("x", '{"id":1,"id":2}')]))

    def test_history_requires_recorded_result_and_current_feedback(self):
        contract = ToolContract(definition())
        batch = message([call("a", '{"id":1}')])
        contract.accept_batch(batch)
        contract.record_result("a", "observed")
        prefix = [{"role": "system", "content": "system" + feedback(1, False)[0]},
                  {"role": "user", "content": "instruction"}]
        history = prefix + [batch, {"role": "tool", "tool_call_id": "a", "content": "observed"}]
        contract.validate_history(history, system="system", instruction="instruction", used=1, claimed=False)
        with self.assertRaises(ContractFailure):
            contract.validate_history(history, system="system", instruction="instruction", used=2, claimed=False)
        history[-1]["content"] = "forged"
        with self.assertRaises(ContractFailure):
            contract.validate_history(history, system="system", instruction="instruction", used=1, claimed=False)

    def test_optional_position_index_is_dropped_from_stored_batch(self):
        contract = ToolContract(definition())
        indexed = call('a', '{"id":1}')
        indexed["index"] = 0
        batch = message([indexed])
        calls = contract.accept_batch(batch)
        self.assertEqual([c['name'] for c in calls], ['read'])
        self.assertEqual(contract.batches[0]["message"]["tool_calls"], [call('a', '{"id":1}')])
        self.assertNotIn("index", contract.batches[0]["message"]["tool_calls"][0])
        contract.record_result('a', 'observed')
        history = [{'role': 'system', 'content': 'system' + feedback(1, False)[0]},
                   {'role': 'user', 'content': 'instruction'},
                   message([indexed]),
                   {'role': 'tool', 'tool_call_id': 'a', 'content': 'observed'}]
        contract.validate_history(history, system='system', instruction='instruction', used=1, claimed=False)

    def test_unknown_tool_call_field_is_rejected_without_commit(self):
        contract = ToolContract(definition())
        forged = call('a', '{"id":1}')
        forged["parallel"] = True
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([forged]))
        self.assertEqual(contract.records, [])
        self.assertEqual(contract.batches, [])

    def test_invalid_position_index_is_rejected(self):
        for value in (-1, "0", 0.0, True, None):
            with self.subTest(index=value):
                contract = ToolContract(definition())
                indexed = call('a', '{"id":1}')
                indexed["index"] = value
                with self.assertRaises(ContractFailure):
                    contract.accept_batch(message([indexed]))
                self.assertEqual(contract.records, [])

    def test_text_block_result_must_replay_exactly(self):
        contract = ToolContract(definition())
        batch = message([call("a", '{"id":1}')])
        contract.accept_batch(batch)
        blocks = [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]
        contract.record_result("a", blocks)
        history = [{"role": "system", "content": "system" + feedback(1, False)[0]},
                   {"role": "user", "content": "instruction"}, batch,
                   {"role": "tool", "tool_call_id": "a", "content": blocks}]
        contract.validate_history(history, system="system", instruction="instruction", used=1, claimed=False)
        history[-1]["content"] = "onetwo"
        with self.assertRaises(ContractFailure):
            contract.validate_history(history, system="system", instruction="instruction", used=1, claimed=False)


if __name__ == "__main__":
    unittest.main()
