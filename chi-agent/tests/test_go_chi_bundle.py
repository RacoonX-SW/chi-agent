import tempfile
import unittest
from pathlib import Path

import go_chi_bundle as bundle


class BundleTests(unittest.TestCase):
    def test_allowlisted_tree_and_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "source"
            source.mkdir()
            for name in bundle.PACKAGE_FILES.values():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding="utf-8")
            (source / ".env").write_text("not exported", encoding="utf-8")
            destination = base / "bundle"
            built = bundle.build_bundle(destination, source_root=source)
            self.assertEqual(bundle.validate_bundle(destination).manifest_sha256, built.manifest_sha256)
            self.assertFalse((destination / ".env").exists())
            (destination / "scripts" / "go_chi_guard.py").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(bundle.BundleFailure, "bundle_file_digest_mismatch"):
                bundle.validate_bundle(destination)
