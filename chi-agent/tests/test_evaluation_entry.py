from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import b_provider_profile
import evaluation_bundle as bundle
import evaluation_entry as entry


class EvaluationEntryBundleTests(unittest.TestCase):
    def build(self, temp: str) -> tuple[Path, bundle.BundleIdentity]:
        target = Path(temp) / "package"
        identity = bundle.build_bundle(target, source_root=PROJECT_ROOT)
        return target, identity

    def test_bundle_contains_only_explicit_runtime_allowlist_and_fixed_entry_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root, identity = self.build(temp)
            expected = set(bundle.PACKAGE_FILES) | {bundle.MANIFEST_NAME}
            found = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(found, expected)
            self.assertFalse((root / "profiles" / "local-development-policy.json").exists())
            self.assertFalse((root / "runs").exists())
            self.assertFalse((root / "data").exists())
            self.assertEqual(list((root / "vendor" / "chi-bench").iterdir()), [])
            self.assertEqual(bundle.validate_bundle(root).manifest_sha256, identity.manifest_sha256)
            with patch.object(entry, "ROOT", root), patch.object(
                    entry, "ENTRY_CONFIG_PATH", root / "profiles" / "evaluation-entry.json"), patch.object(
                    b_provider_profile, "PROFILE_PATH", root / "profiles" / "deepseek-flash-prepared.json"):
                context = entry._load_context()
            self.assertEqual(context.policy.scope, "evaluation_rehearsal")
            self.assertEqual(context.policy.mode, "record_only")
            self.assertIsNone(context.policy.hard_cap_cny)
            self.assertEqual(context.bundle.manifest_sha256, identity.manifest_sha256)

    def test_build_refuses_existing_target_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "existing"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaises(bundle.BundleFailure) as error:
                bundle.build_bundle(target, source_root=PROJECT_ROOT)
            self.assertEqual(error.exception.code, "bundle_target_exists")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

    def test_failed_build_keeps_reserved_incomplete_target_without_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            for relative, source in bundle.PACKAGE_FILES.items():
                if relative == "RUN_EVALUATION.md":
                    continue
                source_path = PROJECT_ROOT / source
                target = root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, target)
            target = Path(temp) / "incomplete"
            with self.assertRaises(bundle.BundleFailure) as error:
                bundle.build_bundle(target, source_root=root)
            self.assertEqual(error.exception.code, "bundle_source_invalid")
            self.assertTrue(target.is_dir())
            self.assertFalse((target / bundle.MANIFEST_NAME).exists())
            with self.assertRaises(bundle.BundleFailure) as retry_error:
                bundle.build_bundle(target, source_root=PROJECT_ROOT)
            self.assertEqual(retry_error.exception.code, "bundle_target_exists")
            self.assertFalse((target / bundle.MANIFEST_NAME).exists())

    def test_validation_rejects_extra_forbidden_file_and_config_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            forbidden = root / "profiles" / "local-development-policy.json"
            forbidden.write_text("{}", encoding="utf-8")
            with self.assertRaises(bundle.BundleFailure) as error:
                bundle.validate_bundle(root)
            self.assertEqual(error.exception.code, "bundle_tree_invalid")
            forbidden.unlink()
            config_path = root / "profiles" / "evaluation-entry.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["policy_mode"] = "capped"
            config["hard_cap_cny"] = "1"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(bundle.BundleFailure) as error:
                bundle.validate_bundle(root)
            self.assertEqual(error.exception.code, "bundle_file_digest_mismatch")

    def test_rehashed_manifest_cannot_authorize_changed_policy_or_unknown_config_fields(self):
        for alteration in ("policy", "unknown-field"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as temp:
                root, _ = self.build(temp)
                config_path = root / "profiles" / "evaluation-entry.json"
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if alteration == "policy":
                    config["policy_mode"] = "capped"
                    config["hard_cap_cny"] = "1"
                else:
                    config["unexpected"] = True
                config_bytes = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
                config_path.write_bytes(config_bytes)
                manifest_path = root / bundle.MANIFEST_NAME
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["files"]["profiles/evaluation-entry.json"] = {
                    "sha256": hashlib.sha256(config_bytes).hexdigest(),
                    "size": len(config_bytes),
                }
                manifest["entry_config_sha256"] = manifest["files"]["profiles/evaluation-entry.json"]["sha256"]
                manifest["manifest_sha256"] = bundle._manifest_digest(manifest)
                manifest_path.write_bytes(bundle._canonical(manifest) + b"\n")
                with patch.object(entry, "ROOT", root), patch.object(
                        entry, "ENTRY_CONFIG_PATH", config_path), patch.object(
                        b_provider_profile, "PROFILE_PATH", root / "profiles" / "deepseek-flash-prepared.json"):
                    with self.assertRaises(entry.EntryFailure) as error:
                        entry._load_context()
                self.assertEqual(error.exception.code, "evaluation_entry_config_invalid")

    def test_live_rejects_before_reading_bundle_or_configuration(self):
        output = io.StringIO()
        with patch.object(entry, "_load_context", side_effect=AssertionError("config read")), contextlib.redirect_stdout(output):
            self.assertEqual(entry.main(["live"]), 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["safe_error_code"], "real_execution_paused")
        self.assertFalse(result["config_read"])
        self.assertFalse(result["bundle_read"])

    def test_plan_can_report_missing_runtime_but_preflight_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            with patch.object(entry, "ROOT", root), patch.object(
                    entry, "ENTRY_CONFIG_PATH", root / "profiles" / "evaluation-entry.json"), patch.object(
                    b_provider_profile, "PROFILE_PATH", root / "profiles" / "deepseek-flash-prepared.json"):
                context = entry._load_context()
            missing = {"status": "unavailable", "sdk": None, "source": None,
                       "safe_error_code": "optional_sdk_layer_unavailable"}
            plan_output, preflight_output = io.StringIO(), io.StringIO()
            with patch.object(entry, "_load_context", return_value=context), patch.object(
                    entry, "_runtime_identity", return_value=missing):
                with contextlib.redirect_stdout(plan_output):
                    self.assertEqual(entry.main(["plan"]), 0)
                with contextlib.redirect_stdout(preflight_output):
                    self.assertEqual(entry.main(["preflight"]), 1)
            plan = json.loads(plan_output.getvalue())
            report = json.loads(preflight_output.getvalue())
            self.assertFalse(plan["technical_ready"])
            self.assertEqual(plan["identity"]["safe_error_code"], "optional_sdk_layer_unavailable")
            self.assertFalse(report["technical_ready"])


if __name__ == "__main__":
    unittest.main()
