import tempfile
import unittest
from pathlib import Path

import chi_agent.bundle as bundle


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
            (destination / "scripts" / "chi_agent" / "models" / "request_guard.py").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(bundle.BundleFailure, "bundle_file_digest_mismatch"):
                bundle.validate_bundle(destination)

    def test_v3_requires_subpackage_initializers_and_rejects_v2_tree(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'bundle'
            bundle.build_bundle(root)
            (root / 'scripts/chi_agent/models/__init__.py').unlink()
            with self.assertRaisesRegex(bundle.BundleFailure, 'bundle_tree_invalid'):
                bundle.validate_bundle(root)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in bundle.V2_PACKAGE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('v2')
            (root / bundle.MANIFEST_NAME).write_text(
                '{"schema":"chi-go-evaluation-bundle-v3",'
                '"bundle_id":"go-chi-evaluation-record-only-v3"}')
            with self.assertRaisesRegex(bundle.BundleFailure, 'bundle_tree_invalid'):
                bundle.validate_bundle(root)
