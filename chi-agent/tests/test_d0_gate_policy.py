"""Synthetic contract tests for the shared D0 readiness/run gate."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from d0_gate_policy import evaluate_gate  # noqa: E402


class GateFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "data"
        self.data_dir.mkdir()
        self.handbook_dir = self.data_dir / "skills" / "managed-care-operations-handbook"
        self.task_name = "synthetic-pa-task"
        self.task_dir = self.data_dir / "prior_auth_provider" / "tasks" / self.task_name
        self.task_dir.mkdir(parents=True)
        self.task_records = {}
        for name, content in {
            "instruction.md": "synthetic instruction\n",
            "task.toml": "schema_version = '1.1'\n",
            "tool_reference.md": "synthetic tool reference\n",
        }.items():
            self._write_source_file(self.data_dir, f"prior_auth_provider/tasks/{self.task_name}/{name}", content)

        self.handbook_records = {}
        for rel, content in {
            "managed-care-operations-handbook/SKILL.md": "synthetic root reference\n",
            "managed-care-operations-handbook/references/provider-pa/SKILL.md": "synthetic provider reference\n",
            "managed-care-operations-handbook/references/payer-um/SKILL.md": "synthetic UM reference\n",
            "managed-care-operations-handbook/references/care-manager/SKILL.md": "synthetic care reference\n",
        }.items():
            self._write_source_file(self.data_dir / "skills", rel, content)

        self.project_config = self.root / "project.yaml"
        self.project_config.write_text(
            "handbook:\n  dataset: actava/managed-care-operations-handbook\n"
            "  revision: synthetic-handbook-rev\n",
            encoding="utf-8",
        )
        self.source_manifest = self.data_dir / "source-downloads.json"
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def _write_source_file(self, root: Path, rel: str, content: str):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        record = {
            "path": rel,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if rel.startswith("managed-care-operations-handbook/"):
            self.handbook_records[rel] = record
        else:
            self.task_records[rel] = record

    @staticmethod
    def source(repo, commit, scope, records):
        return {
            "repo": repo,
            "commit": commit,
            "download_scope": scope,
            "local_dir": "synthetic",
            "verified_file_count": len(records),
            "verified_bytes": sum(item["bytes"] for item in records),
            "files": records,
        }

    def write_manifest(self, *, handbook_commit="synthetic-handbook-rev", handbook_records=None):
        hand_records = list((handbook_records if handbook_records is not None else self.handbook_records).values())
        bench = self.source("actava/chi-bench", "synthetic-bench-rev", "one synthetic task", list(self.task_records.values()))
        handbook = self.source("actava/managed-care-operations-handbook", handbook_commit, "full_snapshot", hand_records)
        self.source_manifest.write_text(json.dumps({"sources": [bench, handbook]}), encoding="utf-8")

    def run_gate(self, *, mode="scored", env=None, **overrides):
        args = {
            "mode": mode,
            "domain": "pa_provider",
            "task_name": self.task_name,
            "model": "deepseek/chat-test",
            "env": {"DEEPSEEK_API_KEY": "synthetic-runner", "ANTHROPIC_API_KEY": "synthetic-judge"} if env is None else env,
            "data_dir": self.data_dir,
            "handbook_dir": self.handbook_dir,
            "project_config_path": self.project_config,
            "source_manifest_path": self.source_manifest,
        }
        args.update(overrides)
        return evaluate_gate(**args)


class TestD0GatePolicy(GateFixture):
    def test_scored_selection_with_synthetic_full_evidence_is_ready_but_not_authenticated(self):
        result = self.run_gate()
        self.assertTrue(result["ready"], result["failures"])
        self.assertEqual(result["evidence"]["provider"], "deepseek")
        self.assertFalse(result["evidence"]["judge_auth"]["authentication_verified"])
        self.assertFalse(result["evidence"]["runner_credential"]["connectivity_verified"])

    def test_ungraded_mode_is_blocked_by_same_shared_policy(self):
        result = self.run_gate(mode="ungraded")
        self.assertFalse(result["ready"])
        self.assertTrue(any("unsupported" in reason.lower() for reason in result["failures"]))

    def test_missing_selection_and_missing_task_are_blocked(self):
        result = self.run_gate(domain=None, task_name=None, model=None)
        self.assertFalse(result["ready"])
        self.assertTrue(any("selection incomplete" in reason.lower() for reason in result["failures"]))
        missing = self.run_gate(domain="cm", task_name="not-downloaded")
        self.assertTrue(any("task directory is missing" in reason.lower() for reason in missing["failures"]))

    def test_task_name_cannot_escape_selected_domain(self):
        result = self.run_gate(task_name="../synthetic-pa-task")
        self.assertTrue(any("invalid path characters" in reason.lower() for reason in result["failures"]))

    def test_unrelated_provider_key_does_not_satisfy_selected_model(self):
        result = self.run_gate(env={"OPENAI_API_KEY": "unrelated"})
        self.assertTrue(any("selected provider deepseek" in reason.lower() for reason in result["failures"]))
        self.assertNotIn("unrelated", json.dumps(result))

    def test_unknown_provider_and_conflicting_explicit_provider_are_blocked(self):
        unknown = self.run_gate(model="vendor-alias-without-prefix", env={"OPENAI_API_KEY": "x"})
        self.assertTrue(any("unknown model provider" in reason.lower() for reason in unknown["failures"]))
        conflict = self.run_gate(provider="openai")
        self.assertTrue(any("does not match" in reason.lower() for reason in conflict["failures"]))

    def test_missing_selected_handbook_reference_is_blocked(self):
        records = dict(self.handbook_records)
        del records["managed-care-operations-handbook/references/provider-pa/SKILL.md"]
        self.write_manifest(handbook_records=records)
        result = self.run_gate()
        self.assertTrue(any("required file" in reason.lower() and "provider-pa" in reason for reason in result["failures"]))

    def test_handbook_revision_mismatch_is_blocked(self):
        self.write_manifest(handbook_commit="other-revision")
        result = self.run_gate()
        self.assertTrue(any("does not match project.yaml revision" in reason for reason in result["failures"]))

    def test_handbook_hash_or_size_mismatch_is_blocked(self):
        path = self.handbook_dir / "references/provider-pa/SKILL.md"
        path.write_text("changed synthetic content\n", encoding="utf-8")
        result = self.run_gate()
        self.assertTrue(any("integrity mismatch" in reason.lower() for reason in result["failures"]))

    def test_malformed_manifest_with_huge_integer_blocks_without_raising(self):
        self.source_manifest.write_text(
            '{"sources":[],"oversized":' + ("9" * 5000) + "}", encoding="utf-8"
        )
        result = self.run_gate()
        self.assertFalse(result["ready"])
        self.assertTrue(any("cannot read source-downloads.json" in reason.lower() for reason in result["failures"]))

    def test_selected_task_file_missing_from_inventory_is_blocked(self):
        task_file = self.task_dir / "tool_reference.md"
        task_file.unlink()
        result = self.run_gate()
        self.assertTrue(any("selected task is incomplete" in reason.lower() for reason in result["failures"]))

    def test_oauth_path_is_reported_unverified_and_does_not_pass(self):
        result = self.run_gate(env={
            "DEEPSEEK_API_KEY": "synthetic-runner",
            "CLAUDE_CODE_OAUTH_TOKEN": "synthetic-token",
        })
        self.assertFalse(result["ready"])
        self.assertTrue(any("oauth" in reason.lower() and "unverified" in reason.lower() for reason in result["failures"]))
        self.assertNotIn("synthetic-token", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
