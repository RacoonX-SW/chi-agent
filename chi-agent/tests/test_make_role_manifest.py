import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import make_role_manifest as gen
import role_resource_preflight


def write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())


def world(world_id: str) -> str:
    return json.dumps({"world_id": world_id})


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write(self.root / "REVISION", "a" * 40 + "\n")
        write(self.root / "prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json",
              world("healthverse-pa-v2-payer"))
        write(self.root / "prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json",
              world("healthverse-pa-v2-provider"))
        write(self.root / "care_management/shared/worlds/healthverse-cm-curated25-v1.json",
              world("healthverse-cm-curated25-v1"))
        write(self.root / "care_management/shared/tool_reference.md", "ref")
        self.payer = "pa_t011_t011_o003_p01_intake_payer"
        base = self.root / "prior_auth_um/tasks" / self.payer
        write(base / "instruction.md", "instruction")
        write(base / "task.toml", "version = '1.0'\n")
        write(base / "tool_reference.md", "tool ref")
        write(base / "fixtures/manifest.json",
              json.dumps({"world_id": "healthverse-pa-v2-payer"}))
        write(base / "fixtures/expectations.json", json.dumps({"hidden": True}))
        for index in range(1, 5):
            write(base / f"fixtures/request/{index:02d}_doc.pdf", b"%PDF-1.4 test")
        self.cm = "cm_test_case_001"
        cm_base = self.root / "care_management/tasks" / self.cm
        write(cm_base / "instruction.md", "instruction")
        write(cm_base / "task.toml", "version = '1.0'\n")
        write(cm_base / "fixtures/manifest.json",
              json.dumps({"world_id": "healthverse-cm-curated25-v1"}))
        write(cm_base / "fixtures/expectations.json", json.dumps({"hidden": True}))

    def tearDown(self):
        self.temp.cleanup()

    def test_payer_manifest_is_deterministic_and_passes_preflight(self):
        first = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        second = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        self.assertEqual(first, second)
        self.assertEqual(len(first["files"]), 11)
        digest = gen.write_manifest(first, self.root / "out/payer.json", self.root,
                                    preflight=role_resource_preflight.validate)
        payload = (self.root / "out/payer.json").read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)

    def test_expectations_and_manifest_are_world_only(self):
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        visibility = {item["path"].split("/")[-1]: item["visibility"] for item in manifest["files"]}
        self.assertEqual(visibility["expectations.json"], "world_only")
        self.assertEqual(visibility["manifest.json"], "world_only")
        self.assertEqual(visibility["instruction.md"], "public")
        self.assertEqual(manifest["world"]["sha256"],
                         next(item["sha256"] for item in manifest["files"]
                              if item["path"] == manifest["world"]["path"]))

    def test_existing_output_is_not_overwritten(self):
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        target = self.root / "out.json"
        write(target, "keep me")
        with self.assertRaises(gen.ManifestError):
            gen.write_manifest(manifest, target, self.root)
        self.assertEqual(target.read_text(), "keep me")

    def test_missing_file_is_refused(self):
        (self.root / "prior_auth_um/tasks" / self.payer / "tool_reference.md").unlink()
        with self.assertRaises(gen.ManifestError):
            gen.build_manifest(self.root, "prior_auth_um", self.payer)

    def test_symlink_is_refused(self):
        target = self.root / "prior_auth_um/tasks" / self.payer / "tool_reference.md"
        target.unlink()
        target.symlink_to(self.root / "care_management/shared/tool_reference.md")
        with self.assertRaises(gen.ManifestError):
            gen.build_manifest(self.root, "prior_auth_um", self.payer)

    def test_unexpected_file_is_refused(self):
        write(self.root / "prior_auth_um/tasks" / self.payer / "notes.md", "x")
        with self.assertRaises(gen.ManifestError):
            gen.build_manifest(self.root, "prior_auth_um", self.payer)

    def test_wrong_request_count_and_missing_revision_are_refused(self):
        (self.root / "prior_auth_um/tasks" / self.payer / "fixtures/request/01_doc.pdf").unlink()
        with self.assertRaises(gen.ManifestError):
            gen.build_manifest(self.root, "prior_auth_um", self.payer)

    def test_unknown_task_is_refused(self):
        with self.assertRaises(gen.ManifestError):
            gen.build_manifest(self.root, "prior_auth_um", "pa_missing")

    def _provider_task(self, world_id: str = "healthverse-pa-v2-provider") -> str:
        task_id = "pa_provider_synthetic"
        base = self.root / "prior_auth_provider/tasks" / task_id
        write(base / "instruction.md", "instruction")
        write(base / "task.toml", "version = '1.0'\n")
        write(base / "tool_reference.md", "tool ref")
        write(base / "fixtures/manifest.json", json.dumps({"world_id": world_id}))
        write(base / "fixtures/expectations.json", json.dumps({"hidden": True}))
        return task_id

    def test_provider_uses_provider_world_and_passes_preflight(self):
        task_id = self._provider_task()
        manifest = gen.build_manifest(self.root, "prior_auth_provider", task_id)
        self.assertEqual(manifest["world"]["path"],
                         "prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json")
        self.assertEqual(len(manifest["files"]), 7)
        gen.write_manifest(manifest, self.root / "out/provider.json", self.root,
                           preflight=role_resource_preflight.validate)

    def test_payer_uses_payer_world_and_passes_preflight(self):
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        self.assertEqual(manifest["world"]["path"],
                         "prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json")
        gen.write_manifest(manifest, self.root / "out/payer-world.json", self.root,
                           preflight=role_resource_preflight.validate)

    def test_world_id_mismatch_is_refused_by_original_preflight(self):
        task_id = self._provider_task(world_id="healthverse-pa-v2-payer")
        manifest = gen.build_manifest(self.root, "prior_auth_provider", task_id)
        with self.assertRaises(ValueError):
            gen.write_manifest(manifest, self.root / "out/mismatch.json", self.root,
                               preflight=role_resource_preflight.validate)
        self.assertFalse((self.root / "out/mismatch.json").exists())

    def test_cm_manifest_uses_shared_world_and_reference(self):
        manifest = gen.build_manifest(self.root, "care_management", self.cm)
        paths = {item["path"] for item in manifest["files"]}
        self.assertIn("care_management/shared/worlds/healthverse-cm-curated25-v1.json", paths)
        self.assertIn("care_management/shared/tool_reference.md", paths)
        self.assertEqual(manifest["tool_reference_path"], "care_management/shared/tool_reference.md")
        gen.write_manifest(manifest, self.root / "out/cm.json", self.root,
                           preflight=role_resource_preflight.validate)

    def test_tampered_manifest_fails_preflight(self):
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        manifest["files"][0]["sha256"] = "b" * 64
        with self.assertRaises(ValueError):
            gen.write_manifest(manifest, self.root / "out/bad.json", self.root,
                               preflight=role_resource_preflight.validate)
        self.assertFalse((self.root / "out/bad.json").exists())

    def test_racing_writer_wins_and_keeps_original_bytes(self):
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        target = self.root / "out/race.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        def preflight(dataset, path, digest):
            role_resource_preflight.validate(dataset, path, digest)
            write(target, "created-by-another-writer")

        with self.assertRaises(gen.ManifestError):
            gen.write_manifest(manifest, target, self.root, preflight=preflight)
        self.assertEqual(target.read_text(), "created-by-another-writer")
        self.assertEqual(list(target.parent.glob(".manifest-*")), [])

    def test_existing_symlink_is_not_replaced(self):
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        target = self.root / "out/link.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(self.root / "care_management/shared/tool_reference.md")
        with self.assertRaises(gen.ManifestError):
            gen.write_manifest(manifest, target, self.root)
        self.assertTrue(target.is_symlink())
        self.assertEqual((self.root / "care_management/shared/tool_reference.md").read_text(), "ref")

    def test_write_failure_leaves_no_temp_or_output(self):
        from unittest.mock import patch
        manifest = gen.build_manifest(self.root, "prior_auth_um", self.payer)
        target = self.root / "out/fail.json"
        with patch("make_role_manifest.os.link", side_effect=OSError("boom")):
            with self.assertRaises(gen.ManifestError) as caught:
                gen.write_manifest(manifest, target, self.root)
        self.assertEqual(caught.exception.code, "manifest_write_failed")
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".manifest-*")), [])

    def test_missing_revision_is_refused(self):
        (self.root / "REVISION").unlink()
        with self.assertRaises(gen.ManifestError):
            gen.build_manifest(self.root, "prior_auth_um", self.payer)


if __name__ == "__main__":
    unittest.main()
