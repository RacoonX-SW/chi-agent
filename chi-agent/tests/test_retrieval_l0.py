import tempfile
import unittest
from pathlib import Path

from go_chi_index import build_index, read_hit, search_index


class RetrievalL0Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "handbook"
        for role, year, category, title in (
                ("provider", 2026, "bariatric", "Bariatric Surgery"),
                ("payer", 2025, "bariatric", "Bariatric Review"),
                ("cm", 2026, "asthma", "Asthma Care")):
            directory = self.root / role / str(year) / category
            directory.mkdir(parents=True)
            (directory / "policy.md").write_text(
                f"# {title}\n\n## Coverage\n\nsite of service rule for {role}\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_has_title_section_and_metadata(self):
        index = build_index([self.root])
        self.assertEqual(index["files"], 3)
        entry = next(item for item in index["entries"]
                     if item["metadata"]["role"] == "provider")
        self.assertEqual(entry["title"], "Bariatric Surgery")
        self.assertEqual(entry["metadata"]["category"], "bariatric")
        self.assertEqual(entry["metadata"]["year"], 2026)

    def test_filters_and_hit_fields(self):
        index = build_index([self.root])
        result = search_index(index, "site of service", filters={"role": "provider", "year": 2026})
        self.assertEqual(result["total_matches"], 1)
        hit = result["hits"][0]
        self.assertEqual(hit["section"], "Coverage")
        self.assertEqual(hit["line"], 5)
        self.assertEqual(hit["sha256"],
                         next(item for item in index["entries"]
                              if item["path"] == hit["path"])["sha256"])
        self.assertIn("path", hit)

    def test_max_results_and_omitted(self):
        index = build_index([self.root])
        result = search_index(index, "rule", max_results=1)
        self.assertEqual(len(result["hits"]), 1)
        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["omitted"], 2)
        self.assertTrue(result["truncated"])

    def test_role_aliases_and_shared_namespaces(self):
        base = Path(self.tmp.name) / "aliases"
        for role in ("provider-pa", "payer-um", "care-manager", "medical-library", "platform"):
            directory = base / role / "2026" / "policy"
            directory.mkdir(parents=True)
            (directory / "doc.md").write_text("# Doc\n\nneedle\n", encoding="utf-8")
        index = build_index([base], use_cache=False)
        roles = {item["metadata"]["role"] for item in index["entries"]}
        self.assertEqual(roles, {"provider", "payer", "cm", "shared"})

    def test_index_cache_hit(self):
        first = build_index([self.root])
        second = build_index([self.root])
        self.assertIs(first, second)

    def test_read_hit_verifies_hash_and_detects_staleness(self):
        index = build_index([self.root])
        hit = search_index(index, "site of service")["hits"][0]
        value = read_hit(hit)
        self.assertIn("site of service", value["text"])
        Path(hit["path"]).write_text("# changed\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_hit(hit)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            build_index([])
        with self.assertRaises(ValueError):
            search_index({}, "x")


if __name__ == "__main__":
    unittest.main()
