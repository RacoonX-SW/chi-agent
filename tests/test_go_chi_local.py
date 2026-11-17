import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx
import chi_agent.models.opencode_go_provider as go
from chi_agent.accounting.local_history import acquire_existing_history


class LocalHistoryTests(unittest.TestCase):
    def test_requires_existing_history_and_holds_q_lock(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaisesRegex(go.GoFailure, "go_history_missing"):
                acquire_existing_history(root)
            result = asyncio.run(go._run_probe(root, "old", "synthetic-secret", lower=httpx.MockTransport(go._offline_responder())))
            self.assertEqual(result["status"], "complete")
            before = (root / "accounting.json").read_bytes()
            q = acquire_existing_history(root)
            with self.assertRaisesRegex(go.GoFailure, "go_journal_locked_or_invalid"):
                acquire_existing_history(root)
            q.close()
            self.assertEqual(before, (root / "accounting.json").read_bytes())
