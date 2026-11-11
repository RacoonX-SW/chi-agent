import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import go_chi_release as release
from go_chi_bundle import validate_bundle
from go_chi_delivery import FORBIDDEN_ENV


ROOT = Path(__file__).parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, name="release"):
        return release.build_release(self.root / name, source_root=ROOT,
                                     source_commit="4" * 40)

    def plan(self, output):
        package = Path(output["root"]) / "package"
        (self.root / "model" / "agents").mkdir(parents=True, exist_ok=True)
        (self.root / "pdf" / "pypdf").mkdir(parents=True, exist_ok=True)
        (self.root / "vendor" / "src" / "chi_bench").mkdir(parents=True, exist_ok=True)
        (self.root / "handbook").mkdir(exist_ok=True)
        (self.root / "instruction.md").write_text("public", encoding="utf-8")
        (self.root / "tool.md").write_text("public", encoding="utf-8")
        (self.root / "state").mkdir(exist_ok=True)
        return {
            "schema": "chi-go-delivery-plan-v1", "role": "provider",
            "bundle": {"root": str(package), "sha256": output["bundle_manifest_sha256"]},
            "dependencies": {"model_root": str(self.root / "model"),
                              "pdf_root": str(self.root / "pdf")},
            "vendor": {"root": str(self.root / "vendor"), "commit": "4" * 40},
            "resources": {"instruction": str(self.root / "instruction.md"),
                          "handbook_root": str(self.root / "handbook"),
                          "tool_references": [str(self.root / "tool.md")]},
            "mcp": {"url": "http://world:8020/mcp", "role": "provider"},
            "state": {"output_root": str(self.root / "state"),
                       "logs_dir": str(self.root / "logs")},
            "history": {"mode": "external", "q_root": None},
            "credentials": {"model_env": "OPENCODE_API_KEY",
                            "forbidden_env": sorted(FORBIDDEN_ENV)},
        }

    def test_build_and_verify_with_plan(self):
        output = self.build()
        self.assertEqual(output["status"], "built")
        root = Path(output["root"])
        self.assertTrue((root / release.RELEASE_MANIFEST).is_file())
        self.assertTrue((root / release.SUMS).is_file())
        self.assertTrue((root / release.PLAN).is_file())
        self.assertFalse(any((root / name).exists() for name in
                             ("data", "vendor", "tests", "runs", ".env")))
        identity = validate_bundle(root / "package")
        self.assertEqual(identity.manifest_sha256, output["bundle_manifest_sha256"])
        report = release.verify_release(root, self.plan(output))
        self.assertEqual(report["status"], "valid")
        self.assertTrue(report["plan_checked"])
        self.assertFalse(any(name in str((root / "package").iterdir()) for name in ("data", "tests")))

    def test_tamper_and_extra_layout_are_rejected(self):
        output = self.build()
        root = Path(output["root"])
        target = root / "package" / "scripts" / "go_chi_entry.py"
        target.write_text(target.read_text() + "\n# tampered\n", encoding="utf-8")
        with self.assertRaises(release.ReleaseError) as caught:
            release.verify_release(root)
        self.assertIn(caught.exception.code,
                      {"release_checksum_invalid", "release_bundle_identity_invalid"})
        output = self.build("second")
        root = Path(output["root"])
        (root / "extra.txt").write_text("bad", encoding="utf-8")
        with self.assertRaises(release.ReleaseError) as caught:
            release.verify_release(root)
        self.assertEqual(caught.exception.code, "release_layout_invalid")

    def test_missing_manifest_and_plan_bundle_mismatch(self):
        output = self.build()
        root = Path(output["root"])
        (root / release.RELEASE_MANIFEST).unlink()
        with self.assertRaises(release.ReleaseError):
            release.verify_release(root)
        output = self.build("third")
        plan = self.plan(output)
        plan["bundle"]["root"] = str(self.root / "model")
        with self.assertRaises((release.ReleaseError, ValueError)):
            release.verify_release(Path(output["root"]), plan)

    def test_build_is_deterministic_and_cli(self):
        first = self.build("one")
        second = self.build("two")
        self.assertEqual((Path(first["root"]) / release.RELEASE_MANIFEST).read_bytes(),
                         (Path(second["root"]) / release.RELEASE_MANIFEST).read_bytes())
        self.assertEqual((Path(first["root"]) / release.SUMS).read_bytes(),
                         (Path(second["root"]) / release.SUMS).read_bytes())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(release.main(["verify", "--root", first["root"]]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "valid")

    def test_existing_target_is_not_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        with self.assertRaises(release.ReleaseError) as caught:
            release.build_release(target, source_root=ROOT, source_commit="4" * 40)
        self.assertEqual(caught.exception.code, "release_target_exists")


if __name__ == "__main__":
    unittest.main()
