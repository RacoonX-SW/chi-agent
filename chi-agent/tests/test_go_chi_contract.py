import unittest

from go_chi_contract import ContractFailure, ToolContract
from request_budget import feedback


def definition():
    return [{"type": "function", "function": {"name": "read", "description": "Read", "strict": False,
        "parameters": {"type": "object", "properties": {"id": {"type": "integer"}},
                       "required": ["id"], "additionalProperties": False}}}]


def call(call_id, arguments):
    return {"id": call_id, "type": "function", "function": {"name": "read", "arguments": arguments}}


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

    def test_invalid_second_call_does_not_commit_first(self):
        contract = ToolContract(definition())
        with self.assertRaises(ContractFailure):
            contract.accept_batch(message([call("a", '{"id":1}'), call("b", '{"id":"bad"}')]))
        self.assertEqual(contract.records, [])
        self.assertEqual(contract.seen, set())
        contract.accept_batch(message([call("a", '{"id":1}')]))

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
