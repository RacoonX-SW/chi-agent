import tempfile
import unittest
from pathlib import Path

from go_chi_search import MAX_FILE_BYTES, MAX_RESULTS, SearchRefusal, search


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "handbook"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_hit_has_path_line_offset_and_hash(self):
        self.write("policy/lumbar.md", "intro\nA lumbar MRI needs prior therapy.\nend\n")
        value = search([self.root], "prior therapy")
        self.assertFalse(value["no_matches"])
        hit = value["results"][0]
        self.assertTrue(hit["path"].endswith("policy/lumbar.md"))
        self.assertEqual(hit["line"], 2)
        self.assertEqual(hit["byte_offset"], len("intro\n"))
        self.assertRegex(hit["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("prior therapy", hit["excerpt"])
        self.assertEqual(value["files_scanned"], 1)

    def test_case_insensitive_by_default_and_case_sensitive_option(self):
        self.write("a.md", "Lumbar MRI\n")
        self.assertEqual(len(search([self.root], "lumbar mri")["results"]), 1)
        self.assertEqual(search([self.root], "lumbar mri", case_sensitive=True)["results"], [])

    def test_hidden_and_blocked_directories_are_skipped(self):
        self.write("public.md", "covered term\n")
        self.write("fixtures/secret.md", "covered term\n")
        self.write(".hidden/secret.md", "covered term\n")
        self.write("judge/secret.md", "covered term\n")
        value = search([self.root], "covered term")
        self.assertEqual([Path(item["path"]).name for item in value["results"]], ["public.md"])

    def test_symlink_is_not_followed(self):
        target = Path(self.temp.name) / "outside.md"
        target.write_text("covered term\n", encoding="utf-8")
        (self.root / "link.md").symlink_to(target)
        value = search([self.root], "covered term")
        self.assertEqual(value["results"], [])
        self.assertTrue(value["no_matches"])

    def test_no_match_is_explicit(self):
        self.write("a.md", "nothing here\n")
        value = search([self.root], "absent")
        self.assertTrue(value["no_matches"])
        self.assertEqual(value["results"], [])

    def test_result_limit_marks_truncated(self):
        self.write("a.md", "\n".join(f"line {i} covered" for i in range(MAX_RESULTS + 5)))
        value = search([self.root], "covered", max_results=MAX_RESULTS)
        self.assertEqual(len(value["results"]), MAX_RESULTS)
        self.assertTrue(value["truncated"])
        self.assertGreater(value["omitted"], 0)

    def test_large_file_is_skipped(self):
        path = self.root / "large.txt"
        path.write_bytes(b"a" * (MAX_FILE_BYTES + 1))
        value = search([self.root], "a")
        self.assertEqual(value["results"], [])
        self.assertEqual(value["skipped_files"], 1)

    def test_invalid_query_and_arguments(self):
        for query in ("", "   ", "x" * 201, "bad\nquery"):
            with self.assertRaises(SearchRefusal) as caught:
                search([self.root], query)
            self.assertEqual(caught.exception.code, "search_query_invalid")
        with self.assertRaises(SearchRefusal):
            search([self.root], "ok", max_results=0)
        with self.assertRaises(SearchRefusal):
            search([], "ok")

    def test_custom_text_loader_supports_pdf_like_materials(self):
        path = self.root / "handbook.pdf"
        path.write_bytes(b"%PDF-not-really")
        value = search([self.root], "coverage rule",
                       read_text=lambda _path: "page text\ncoverage rule applies\n")
        self.assertEqual(len(value["results"]), 1)
        self.assertIn("coverage rule", value["results"][0]["excerpt"])

    def test_unreadable_loader_is_reported_as_skipped(self):
        self.write("a.md", "covered\n")
        value = search([self.root], "covered", read_text=lambda _path: None)
        self.assertEqual(value["results"], [])
        self.assertEqual(value["skipped_files"], 1)


if __name__ == "__main__":
    unittest.main()
