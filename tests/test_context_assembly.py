import json
import unittest

from chi_agent.context_assembly import canonical_sha, project_messages


def tool(call_id, result):
    return {"role": "tool", "tool_call_id": call_id, "content": result}


def assistant(call_id):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": "read", "arguments": "{}"}}]}


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.big = "read " * 2000
        self.mutation = json.dumps({"case_id": "CASE-A", "id": "CASE-A"})
        self.messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "instruction"},
            assistant("c1"), tool("c1", self.big),
            assistant("c2"), tool("c2", self.big),
            assistant("c3"), tool("c3", self.mutation),
            assistant("c4"), tool("c4", "latest"),
        ]
        self.records = {
            "c1": {"id": "c1", "name": "read", "arguments": {"path": "/a"},
                   "result": self.big},
            "c2": {"id": "c2", "name": "read", "arguments": {"path": "/b"},
                   "result": self.big},
            "c3": {"id": "c3", "name": "write", "arguments": {"case_id": "CASE-A"},
                   "result": self.mutation},
            "c4": {"id": "c4", "name": "read", "arguments": {"path": "/c"},
                   "result": "latest"},
        }

    def test_old_reads_are_placeholders_and_duplicates_are_references(self):
        projected, report = project_messages(
            self.messages, records=self.records,
            events={"c1": "returned", "c2": "returned", "c3": "returned", "c4": "returned"},
            canonical_tools={"read": "local-fs-read", "write": "cases.create_from_order"},
            keep_recent_batches=1)
        first = json.loads(projected[3]["content"])
        second = json.loads(projected[5]["content"])
        self.assertEqual(first["schema"], "chi-tool-result-ref-v1")
        self.assertEqual(first["call_id"], "c1")
        self.assertEqual(first["path"], "/a")
        self.assertEqual(first["result_sha256"],
                         __import__("hashlib").sha256(self.big.encode()).hexdigest())
        self.assertEqual(second["duplicate_of"], "c1")
        self.assertEqual(projected[9]["content"], "latest")
        self.assertGreater(report["saved_bytes"], 0)
        self.assertEqual(report["replaced"], 3)
        self.assertEqual(report["deduped"], 1)

    def test_mutations_keep_program_record(self):
        projected, _ = project_messages(
            self.messages, records=self.records,
            events={"c1": "returned", "c2": "returned", "c3": "returned", "c4": "returned"},
            canonical_tools={"read": "local-fs-read", "write": "cases.create_from_order"},
            keep_recent_batches=1)
        record = json.loads(projected[7]["content"])
        self.assertEqual(record["schema"], "chi-tool-record-v1")
        self.assertEqual(record["call_id"], "c3")
        self.assertEqual(record["event"], "returned")
        self.assertEqual(record["key_ids"]["case_id"], "CASE-A")
        self.assertEqual(record["result_sha256"],
                         __import__("hashlib").sha256(self.mutation.encode()).hexdigest())

    def test_projection_is_deterministic(self):
        one, _ = project_messages(self.messages, records=self.records,
                                  events={"c1": "returned"}, canonical_tools={},
                                  keep_recent_batches=1)
        two, _ = project_messages(self.messages, records=self.records,
                                  events={"c1": "returned"}, canonical_tools={},
                                  keep_recent_batches=1)
        self.assertEqual(canonical_sha(one), canonical_sha(two))

    def test_recent_batches_are_not_changed(self):
        projected, _ = project_messages(self.messages, records=self.records,
                                        events={"c1": "returned"},
                                        canonical_tools={"read": "local-fs-read",
                                                         "write": "cases.create_from_order"},
                                        keep_recent_batches=2)
        self.assertNotEqual(projected[3]["content"], self.big)
        self.assertNotEqual(projected[5]["content"], self.big)
        self.assertEqual(projected[7]["content"], self.mutation)
        self.assertEqual(projected[9]["content"], "latest")

    def test_anchor_only_does_not_project_results(self):
        anchor = {"text": '{"schema":"chi-intent-anchor-v1"}', "sha256": "a" * 64}
        projected, report = project_messages(
            self.messages, records=self.records,
            events={"c1": "returned", "c2": "returned", "c3": "returned", "c4": "returned"},
            canonical_tools={"read": "local-fs-read", "write": "cases.create_from_order"},
            anchor=anchor, project_results=False)
        self.assertEqual(projected[2], {"role": "user", "content": anchor["text"]})
        self.assertEqual(projected[4]["content"], self.big)
        self.assertEqual(projected[6]["content"], self.big)
        self.assertEqual(report["replaced"], 0)
        self.assertEqual(report["deduped"], 0)
        self.assertLessEqual(report["saved_bytes"], 0)

    def test_anchor_plus_pressure_projects_results(self):
        anchor = {"text": '{"schema":"chi-intent-anchor-v1"}', "sha256": "a" * 64}
        projected, report = project_messages(
            self.messages, records=self.records,
            events={"c1": "returned", "c2": "returned", "c3": "returned", "c4": "returned"},
            canonical_tools={"read": "local-fs-read", "write": "cases.create_from_order"},
            anchor=anchor, project_results=True)
        self.assertEqual(projected[2], {"role": "user", "content": anchor["text"]})
        self.assertIn("chi-tool-result-ref-v1", projected[4]["content"])
        self.assertGreater(report["replaced"], 0)
        self.assertGreater(report["saved_bytes"], 0)

    def test_anchor_only_projection_is_deterministic(self):
        anchor = {"text": '{"schema":"chi-intent-anchor-v1"}', "sha256": "a" * 64}
        one, _ = project_messages(self.messages, records=self.records, events={},
                                  canonical_tools={}, anchor=anchor, project_results=False)
        two, _ = project_messages(self.messages, records=self.records, events={},
                                  canonical_tools={}, anchor=anchor, project_results=False)
        self.assertEqual(canonical_sha(one), canonical_sha(two))

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            project_messages("bad", records={}, events={}, canonical_tools={})
        with self.assertRaises(ValueError):
            project_messages([], records=[], events={}, canonical_tools={})


if __name__ == "__main__":
    unittest.main()
