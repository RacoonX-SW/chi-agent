import asyncio
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import chi_agent.cli as entry
import chi_agent.models.opencode_go_provider as go


class EntryTests(unittest.TestCase):
    def test_local_q_unknown_usage_blocks_new_chi_namespace(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); qroot = root / "q"
            q = go.GoJournal(qroot, "old", go.source_identity())
            q.reserve(1, b"synthetic-wire"); q.close()
            args = ["coding-b", "--bundle-sha256", "a" * 64, "--evaluation-id", "eval", "--task-id", "synthetic-coding-b",
                    "--attempt-id", "attempt", "--run-id", "run", "--logs-dir", str(root / "logs"),
                    "--history-mode", "local", "--local-q-root", str(qroot), "--output-root", str(qroot / "chi-evaluation")]
            with patch.object(entry, "_identity", return_value=("b" * 64, {})), patch.dict(os.environ, {}, clear=True):
                out = io.StringIO()
                with contextlib.redirect_stdout(out): code = entry.main(args)
            self.assertEqual(code, 1)
            self.assertIn("go_usage_unknown", out.getvalue())
            self.assertFalse((qroot / "chi-evaluation").exists())

    def test_local_namespace_cannot_be_replaced_by_new_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            qroot = root / "q"
            result = asyncio.run(go._run_probe(qroot, "q-b", "synthetic-secret", lower=httpx.MockTransport(go._offline_responder())))
            self.assertEqual(result["status"], "complete")
            q_bytes = (qroot / "accounting.json").read_bytes()
            base = ["coding-b", "--bundle-sha256", "a" * 64, "--evaluation-id", "eval", "--task-id", "synthetic-coding-b",
                    "--attempt-id", "attempt", "--run-id", "run", "--logs-dir", str(root / "logs"),
                    "--history-mode", "local", "--local-q-root", str(qroot)]
            with patch.object(entry, "_identity", return_value=("b" * 64, {})), patch.dict(os.environ, {}, clear=True):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = entry.main(base + ["--output-root", str(root / "new")])
                self.assertEqual(code, 1)
                self.assertIn("chi_local_history_path_invalid", out.getvalue())
                self.assertFalse((root / "new").exists())
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = entry.main(base + ["--output-root", str(qroot / "chi-evaluation")])
                self.assertEqual(code, 1)
                self.assertIn("chi_credential_missing", out.getvalue())
                self.assertTrue((qroot / "chi-evaluation" / "chi-accounting.json").exists())
            self.assertEqual(q_bytes, (qroot / "accounting.json").read_bytes())

    def test_context_cap_is_parsed_for_live(self):
        args = entry._parser().parse_args(["live", "--bundle-sha256", "a" * 64,
                                           "--context-max-estimated-tokens", "2000000"])
        self.assertEqual(args.context_max_estimated_tokens, 2_000_000)

    def test_main_max_tokens_is_parsed_for_live(self):
        args = entry._parser().parse_args(["live", "--bundle-sha256", "a" * 64,
                                           "--main-max-tokens", "16384"])
        self.assertEqual(args.main_max_tokens, 16384)

    def test_profile_matches_entry_config_without_patching(self):
        raw = (entry.ROOT / "profiles/go-chi-entry.json").read_bytes()
        config = entry.json.loads(raw, object_pairs_hook=entry._pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        self.assertTrue(entry._same(config, entry.CONFIG))
        self.assertEqual(config["time_policy"]["main_read_seconds"],
                         entry.TIME_POLICY["main_read_seconds"])

    def test_reference_forbids_fixture_paths(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fixtures" / "instruction.md"
            path.parent.mkdir(); path.write_text("synthetic")
            with self.assertRaisesRegex(go.GoFailure, "chi_instruction_forbidden"):
                entry._instruction(path)
