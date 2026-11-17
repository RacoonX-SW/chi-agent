import json
import tempfile
import unittest
from pathlib import Path

from chi_agent.context.context_assembly import (canonical_record, key_ids_for, reduce_tool_result,
                             truncate_tool_text)
from chi_agent.tools.text_search import (DEFAULT_RESULTS, MAX_RESULTS, SINGLE_FILE_MAX_RESULTS,
                           SearchRefusal, search)


class ToolTruncationTests(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        text = "a" * 100
        visible, meta = truncate_tool_text(text)
        self.assertEqual(visible, text)
        self.assertIsNone(meta)

    def test_long_text_keeps_head_tail_and_marker(self):
        text = "H" * 4096 + "M" * 5000 + "T" * 1024
        visible, meta = truncate_tool_text(text, tool="local-fs-read",
                                           arguments={"path": "/x"})
        self.assertTrue(visible.startswith("H" * 100))
        self.assertTrue(visible.endswith("T" * 100))
        self.assertIn("[chi-truncated]", visible)
        self.assertTrue(meta["truncated"])
        self.assertIsNone(meta["next_offset"])
        self.assertIn("offset", meta["offset_unit"])
        self.assertLessEqual(len(visible), 8192 + 512)
        self.assertLessEqual(len(visible.encode("utf-8")), 32 * 1024)

    def test_multibyte_text_stays_below_byte_cap(self):
        text = "汉" * 20000
        visible, meta = truncate_tool_text(text)
        self.assertTrue(meta["truncated"])
        self.assertLessEqual(len(visible.encode("utf-8")), 32 * 1024)

    def test_json_results_stay_valid(self):
        payload = json.dumps({"results": [{"path": "/x", "line": i, "excerpt": "a" * 200}
                                          for i in range(100)]})
        visible, meta = truncate_tool_text(payload, tool="local-fs-search")
        value = json.loads(visible)
        self.assertTrue(meta["structured"])
        self.assertIn("results", value)
        self.assertLessEqual(len(value["results"]), 10)
        self.assertEqual(value["results_total"], 100)
        self.assertGreaterEqual(value["results_omitted"], 1)

    def test_unknown_json_tool_stays_valid(self):
        payload = json.dumps({"weird": [{"x": "y" * 5000} for _ in range(20)]})
        visible, meta = truncate_tool_text(payload, tool="unknown.tool")
        value = json.loads(visible)
        self.assertTrue(meta["structured"])
        self.assertIn("weird", value)

    def test_reducer_handles_result_key(self):
        payload = json.dumps({"result": [{"id": f"INTAKE-{i}", "case_id": f"CASE-{i}",
                                          "status": "complete",
                                          "diagnoses": [{"x": "y" * 100}]}
                                         for i in range(25)]})
        reduced, meta = reduce_tool_result("payer_intake_hub.list_intake_queue", payload)
        value = json.loads(reduced)
        self.assertEqual(len(value["result"]), 10)
        self.assertEqual(value["total"], 25)
        self.assertEqual(value["omitted"], 15)
        self.assertEqual(meta["list_key"], "result")
        self.assertIn("status", value["result"][0])

    def test_canonical_record_derives_key_ids_and_full_hash(self):
        result = json.dumps({"case_id": "CASE-A", "id": "DOC-1", "status": "saved"})
        record = canonical_record("call_1", "docs.upload_evidence", "returned",
                                  result, {"case_id": "CASE-A"})
        self.assertEqual(record["schema"], "chi-tool-record-v1")
        self.assertEqual(record["key_ids"]["case_id"], "CASE-A")
        self.assertEqual(record["key_ids"]["document_id"], "DOC-1")
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["result_sha256"],
                         __import__("hashlib").sha256(result.encode()).hexdigest())

    def test_reducer_preserves_selection_fields(self):
        payload = {"items": [{"id": f"i{i}", "case_id": "CASE-A", "status": "new",
                              "detail": "x" * 100} for i in range(25)]}
        reduced, meta = reduce_tool_result("payer_intake_hub.list_intake_queue",
                                           json.dumps(payload))
        value = json.loads(reduced)
        self.assertEqual(len(value["items"]), 10)
        self.assertEqual(value["total"], 25)
        self.assertEqual(value["omitted"], 15)
        self.assertIn("status", value["items"][0])
        self.assertNotIn("detail", value["items"][0])
        self.assertEqual(meta["reducer"], "list_first_n_selected_fields")

    def test_unknown_shape_is_not_reduced(self):
        original = '{"a": 1}'
        self.assertEqual(reduce_tool_result("unknown.tool", original), (original, None))


class SearchLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for index in range(60):
            (self.root / f"f{index:02d}.md").write_text("needle\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_is_ten_and_total_matches(self):
        value = search([self.root], "needle")
        self.assertEqual(len(value["results"]), DEFAULT_RESULTS)
        self.assertEqual(value["total_matches"], 60)
        self.assertEqual(value["omitted"], 50)
        self.assertEqual(value["limits"]["results"], MAX_RESULTS)

    def test_single_file_allows_fifty(self):
        path = self.root / "one.md"
        path.write_text("\n".join("needle" for _ in range(60)), encoding="utf-8")
        value = search([path], "needle", max_results=50, single_file=True)
        self.assertEqual(len(value["results"]), 50)
        self.assertEqual(value["total_matches"], 60)
        self.assertEqual(value["limits"]["results"], SINGLE_FILE_MAX_RESULTS)

    def test_over_cap_is_actionable(self):
        with self.assertRaises(SearchRefusal) as caught:
            search([self.root], "needle", max_results=30)
        self.assertEqual(caught.exception.code, "search_max_results_out_of_range")
        self.assertEqual(caught.exception.detail["requested"], 30)
        self.assertEqual(caught.exception.detail["allowed_max"], 20)

    def test_zero_is_rejected(self):
        with self.assertRaises(SearchRefusal):
            search([self.root], "needle", max_results=0)


if __name__ == "__main__":
    unittest.main()
