import json
import shutil
import tempfile
import unittest
from pathlib import Path

import chi_agent.bundle as go_chi_bundle
import scripts.tools.inspect_imports as import_inventory


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SyntheticTreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write(self.root / "requirements.lock", "httpx==0.28.1 \\\n")
        write(self.root / "scripts/go_chi_bundle.py",
              "PACKAGE_FILES = {'scripts/a.py': 'scripts/a.py'}\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_top_level_and_nested_self_imports_are_reported(self):
        write(self.root / "scripts/go_chi_bundle.py",
              "PACKAGE_FILES = {'scripts/a.py': 'scripts/a.py', 'scripts/b.py': 'scripts/b.py', "
              "'scripts/c.py': 'scripts/c.py'}\n")
        write(self.root / "scripts/a.py", "import b\n\ndef run():\n    import c\n")
        write(self.root / "scripts/b.py", "")
        write(self.root / "scripts/c.py", "")
        result = import_inventory.inventory(self.root)
        self.assertEqual(result["closure_gaps"], [])
        self.assertIn("a", result["modules"]["b"]["importers"])
        self.assertIn("a", result["modules"]["c"]["importers"])

    def test_packaged_module_importing_unpackaged_module_is_a_gap(self):
        write(self.root / "scripts/a.py", "import b\n")
        write(self.root / "scripts/b.py", "")
        result = import_inventory.inventory(self.root)
        self.assertEqual(result["closure_gaps"], [{"module": "a", "imports": "b"}])

    def test_nested_import_of_unpackaged_module_is_a_gap(self):
        write(self.root / "scripts/a.py", "def run():\n    from b import thing\n")
        write(self.root / "scripts/b.py", "thing = 1\n")
        result = import_inventory.inventory(self.root)
        self.assertEqual(result["closure_gaps"], [{"module": "a", "imports": "b"}])

    def test_classification_covers_stdlib_locked_vendor_and_dynamic(self):
        write(self.root / "requirements.lock", "httpx==0.28.1 \\\n")
        write(self.root / "scripts/a.py",
              "import json\nimport httpx\nimport chi_bench.mcp\nimport mystery_pkg\n"
              "def run():\n    return __import__('json')\n")
        result = import_inventory.inventory(self.root)
        classes = {entry.split(":", 1)[0] for entry in result["modules"]["a"]["top"]}
        self.assertEqual(classes, {"stdlib", "third_party", "vendor", "unknown"})
        self.assertEqual(result["modules"]["a"]["dynamic"], ["run:__import__"])
        self.assertEqual(result["unknown_imports"], [{"module": "a", "imports": ["mystery_pkg"]}])

    def test_class_method_and_nested_function_imports_are_nested(self):
        write(self.root / "scripts/a.py",
              "class A:\n    def run(self):\n        import b\n"
              "def outer():\n    def inner():\n        from c import thing\n")
        write(self.root / "scripts/b.py", "")
        write(self.root / "scripts/c.py", "thing = 1\n")
        result = import_inventory.inventory(self.root)
        self.assertEqual({(gap["module"], gap["imports"]) for gap in result["closure_gaps"]},
                         {("a", "b"), ("a", "c")})
        self.assertIn("a", result["modules"]["b"]["importers"])
        self.assertIn("a", result["modules"]["c"]["importers"])
        nested = result["modules"]["a"]["nested"]
        self.assertTrue(any("run:b" in entry for entry in nested), nested)
        self.assertTrue(any("inner:c" in entry for entry in nested), nested)

    def test_relative_import_is_not_unknown(self):
        write(self.root / "scripts/a.py", "from . import b\n")
        write(self.root / "scripts/b.py", "")
        result = import_inventory.inventory(self.root)
        self.assertEqual(result["unknown_imports"], [])

    def test_missing_scripts_directory_fails(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(SystemExit):
                import_inventory.inventory(Path(empty))


class RealTreeTests(unittest.TestCase):
    def test_real_tree_has_no_packaged_closure_gaps(self):
        result = import_inventory.inventory(import_inventory.ROOT)
        self.assertGreaterEqual(result["packaged_count"], 30)
        self.assertEqual(set(result["package_counts"]), {"go", "evaluation"})
        self.assertEqual(result["closure_gaps"], [])
        self.assertEqual(result["unknown_imports"], [])
        unlocked = {name for item in result["unlocked_externals"] for name in item["imports"]}
        self.assertLessEqual(unlocked, {"docker", "docker.types", "huggingface_hub"})

    def test_isolated_package_has_budget_dependency(self):
        source = import_inventory.ROOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for destination, origin in go_chi_bundle.PACKAGE_FILES.items():
                target = root / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / origin, target)
            result = import_inventory.inventory(root)
            unknown = next((item for item in result["unknown_imports"]
                            if item["module"] == "chi_agent.model_runner_adapter"), None)
            self.assertTrue(unknown is None or "chi_agent.budget_evaluation" not in unknown["imports"])
            self.assertNotIn({"module": "chi_agent.model_runner_adapter", "imports": "chi_agent.budget_evaluation"},
                             result["closure_gaps"])
            (root / "scripts/chi_agent/budget_evaluation.py").unlink()
            missing = import_inventory.inventory(root)
            unknown = next(item for item in missing["unknown_imports"]
                           if item["module"] == "chi_agent.model_runner_adapter")
            self.assertIn("chi_agent.budget_evaluation", unknown["imports"])


if __name__ == "__main__":
    unittest.main()
