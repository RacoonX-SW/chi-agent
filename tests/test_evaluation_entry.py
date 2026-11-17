from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import chi_agent.models.provider_profile as b_provider_profile
import chi_agent.evaluation_bundle as bundle
import chi_agent.evaluation_cli as entry


class EvaluationEntryBundleTests(unittest.TestCase):
    def test_v3_requires_subpackage_initializers_and_rejects_v2_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            (root / 'scripts/chi_agent/evaluation/__init__.py').unlink()
            with self.assertRaisesRegex(bundle.BundleFailure, 'bundle_tree_invalid'):
                bundle.validate_bundle(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in bundle.V2_PACKAGE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('v2')
            (root / bundle.MANIFEST_NAME).write_text(json.dumps({
                'schema': 'chi-evaluation-entry-bundle-v3',
                'bundle_id': 'evaluation-entry-identified-record-only-v3',
            }))
            with self.assertRaisesRegex(bundle.BundleFailure, 'bundle_tree_invalid'):
                bundle.validate_bundle(root)

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

    def test_output_root_may_not_overlap_bundle_in_either_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            for output in (root, root.parent, root.parent.parent, root / "output"):
                with self.subTest(output=output), self.assertRaises(entry.EntryFailure) as error:
                    entry._safe_output_root(output, root)
                self.assertEqual(error.exception.code, "evaluation_output_path_invalid")
            outside = Path(temp) / "separate-output"
            self.assertEqual(entry._safe_output_root(outside, root), outside)

    def test_failed_manifest_publication_stays_incomplete_if_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "package"
            original_fsync = bundle._fsync_dir
            original_unlink = Path.unlink

            def fail_final_fsync(path):
                if path == target and (target / bundle.MANIFEST_NAME).exists():
                    raise bundle.BundleFailure("bundle_write_failed")
                return original_fsync(path)

            def fail_manifest_cleanup(path, *args, **kwargs):
                if path == target / bundle.MANIFEST_NAME:
                    raise OSError("injected cleanup failure")
                return original_unlink(path, *args, **kwargs)

            with patch.object(bundle, "_fsync_dir", side_effect=fail_final_fsync), patch.object(
                    Path, "unlink", new=fail_manifest_cleanup):
                with self.assertRaises(bundle.BundleFailure):
                    bundle.build_bundle(target, source_root=PROJECT_ROOT)
            self.assertTrue((target / bundle.INCOMPLETE_NAME).is_file())
            self.assertTrue((target / bundle.MANIFEST_NAME).is_file())
            with self.assertRaises(bundle.BundleFailure) as error:
                bundle.validate_bundle(target)
            self.assertEqual(error.exception.code, "bundle_incomplete")

    def test_oversized_bundle_file_is_rejected_before_unbounded_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            oversized = root / "scripts" / "evaluation_entry.py"
            with oversized.open("ab") as handle:
                handle.truncate(bundle.MAX_FILE_BYTES + 1)
            original_read_bytes = Path.read_bytes
            read_attempts = []

            def record_read(path):
                if path == oversized:
                    read_attempts.append(path)
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", new=record_read):
                with self.assertRaises(bundle.BundleFailure):
                    bundle.validate_bundle(root)
            self.assertEqual(read_attempts, [])

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

    def test_launch_inputs_accept_bounded_utf8_and_http_mcp_but_reject_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            input_dir = Path(temp) / "external-input"
            input_dir.mkdir()
            instruction_file = input_dir / "task.txt"
            instruction_file.write_text("Use the tools to help the user.", encoding="utf-8")
            output_root = Path(temp) / "output"
            logs_dir = Path(temp) / "logs" / "one"
            logs_dir.parent.mkdir()
            instruction, url, normalized_logs = entry._read_launch_inputs(
                instruction_file, "http://localhost:8020/mcp", logs_dir, root, output_root)
            self.assertEqual(instruction, "Use the tools to help the user.")
            self.assertEqual(url, "http://localhost:8020/mcp")
            self.assertTrue(normalized_logs.is_absolute())

            for invalid in ("http://user:pass@localhost:8020/mcp", "http://localhost:8020/mcp?x=1",
                            "http://localhost:8020/health", "http://localhost/mcp",
                            "file:///tmp/mcp", "http://localhost:99999/mcp"):
                with self.subTest(url=invalid), self.assertRaises(entry.EntryFailure) as error:
                    entry._read_launch_inputs(instruction_file, invalid, logs_dir, root, output_root)
                self.assertEqual(error.exception.code, "evaluation_mcp_url_invalid")

            fixture = input_dir / "tasks.jsonl"
            fixture.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(entry.EntryFailure) as error:
                entry._read_launch_inputs(fixture, "http://localhost:8020/mcp", logs_dir, root, output_root)
            self.assertEqual(error.exception.code, "evaluation_fixture_input_forbidden")

            instruction_file.write_bytes(b"\xff")
            with self.assertRaises(entry.EntryFailure) as error:
                entry._read_launch_inputs(instruction_file, "http://localhost:8020/mcp", logs_dir, root, output_root)
            self.assertEqual(error.exception.code, "evaluation_instruction_invalid")

    def test_launch_logs_destination_must_be_new_disjoint_and_external(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            input_dir = Path(temp) / "input"
            input_dir.mkdir()
            instruction_file = input_dir / "instruction.txt"
            instruction_file.write_text("instruction", encoding="utf-8")
            output_root = Path(temp) / "output"
            for logs_dir in (root / "logs", output_root / "logs", input_dir):
                with self.subTest(logs=logs_dir), self.assertRaises(entry.EntryFailure):
                    entry._read_launch_inputs(instruction_file, "https://docker-host:8020/mcp",
                                              logs_dir, root, output_root)
            existing = Path(temp) / "existing-logs"
            existing.mkdir()
            with self.assertRaises(entry.EntryFailure) as error:
                entry._read_launch_inputs(instruction_file, "https://docker-host:8020/mcp",
                                          existing, root, output_root)
            self.assertEqual(error.exception.code, "evaluation_logs_destination_exists")

    def test_fifo_instruction_is_rejected_promptly_and_other_nonregular_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.build(temp)
            external = Path(temp) / "external"
            external.mkdir()
            fifo = external / "instruction.fifo"
            os.mkfifo(fifo)
            logs_parent = Path(temp) / "logs"
            logs_parent.mkdir()
            command = (
                "import sys; from pathlib import Path; "
                "sys.path.insert(0, sys.argv[1]); import chi_agent.evaluation_cli as e; "
                "import chi_agent.models.provider_profile as p; "
                "e.ROOT=Path(sys.argv[2]); e.ENTRY_CONFIG_PATH=Path(sys.argv[2])/'profiles/evaluation-entry.json'; "
                "p.PROFILE_PATH=Path(sys.argv[2])/'profiles/deepseek-flash-prepared.json'; "
                "raise SystemExit(e.main(['launch-rehearse','--evaluation-id','fifo-test',"
                "'--task-id','task','--attempt-id','attempt','--run-id','fifo-run',"
                "'--output-root',sys.argv[3],'--instruction-file',sys.argv[4],"
                "'--mcp-url','http://localhost:8020/mcp','--logs-dir',sys.argv[5]]))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", command, str(PROJECT_ROOT / "src"), str(root),
                 str(Path(temp) / "output"), str(fifo), str(logs_parent / "runner")],
                capture_output=True, text=True, timeout=3,
            )
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["safe_error_code"], "evaluation_instruction_invalid")
            self.assertFalse((logs_parent / "runner").exists())

            directory = external / "instruction-directory"
            directory.mkdir()
            with self.assertRaises(entry.EntryFailure) as error:
                entry._read_launch_inputs(directory, "http://localhost:8020/mcp",
                                          logs_parent / "directory-logs", root, Path(temp) / "output")
            self.assertEqual(error.exception.code, "evaluation_instruction_invalid")

            socket_path = external / "instruction.socket"
            local_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                local_socket.bind(str(socket_path))
            finally:
                local_socket.close()
            with self.assertRaises(entry.EntryFailure) as error:
                entry._read_launch_inputs(socket_path, "http://localhost:8020/mcp",
                                          logs_parent / "socket-logs", root, Path(temp) / "output")
            self.assertEqual(error.exception.code, "evaluation_instruction_invalid")

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
