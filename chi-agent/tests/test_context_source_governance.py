import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from go_chi_journal import ChiJournal
from opencode_go_provider import GoFailure


def view_identity(**overrides):
    value = {
        "schema": "chi-view-identity-v1",
        "source_sha256": "a" * 64,
        "view_sha256": "b" * 64,
        "anchor_sha256": None,
        "history_length": 3,
        "recovery_mode": "main",
        "parent_round": None,
        "frozen_view": False,
        "projection_rule": "chi-context-projection-v1",
        "pressure": False,
    }
    value.update(overrides)
    return value


def source_body(size=100):
    return {"messages": [{"role": "system", "content": "x" * size}]}


class SourceGovernanceTests(unittest.TestCase):
    def _journal(self, directory):
        return ChiJournal(Path(directory), identity="a" * 64, evaluation="e",
                          task="t", attempt="a", run="r", launch={})

    def test_source_total_cap_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self._journal(directory)
            with patch("go_chi_journal.MAX_SOURCE_TOTAL_BYTES", 10):
                with self.assertRaises(GoFailure) as caught:
                    journal.reserve(b"{}", "main", view_identity=view_identity(),
                                    source_body=source_body())
            self.assertEqual(caught.exception.code, "chi_source_too_large")
            journal.finish("failed")
            journal.close()

    def test_source_orphan_is_removed_when_reserve_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self._journal(root)
            with patch.object(ChiJournal, "_mark_tool_inflight",
                              side_effect=RuntimeError("synthetic failure")):
                with self.assertRaises(RuntimeError):
                    journal.reserve(b"{}", "main", view_identity=view_identity(),
                                    source_body=source_body())
            self.assertFalse((root / "wire-evidence" / "r" / "001-source.json").exists())
            journal.finish("failed")
            journal.close()

    def test_main_regenerate_projection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self._journal(directory)
            with self.assertRaises(GoFailure) as caught:
                journal.reserve(
                    b"{}", "main",
                    view_identity=view_identity(
                        projection_rule="chi-context-projection-regenerate-v1"))
            self.assertEqual(caught.exception.code, "chi_reservation_invalid")
            journal.finish("failed")
            journal.close()

    def test_source_bytes_requires_source_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self._journal(root)
            journal.reserve(b"{}", "main", view_identity=view_identity(),
                            source_body=source_body())
            journal.finish("failed")
            journal.close()
            raw = (root / "chi-accounting.json").read_bytes()
            data = json.loads(raw)
            item = data["attempts"][0]["requests"][0]
            self.assertIn("source_bytes", item)
            self.assertIn("source_evidence_sha256", item)


if __name__ == "__main__":
    unittest.main()
