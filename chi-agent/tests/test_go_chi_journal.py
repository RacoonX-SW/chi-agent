import tempfile
import unittest
from pathlib import Path

from go_chi_journal import ChiJournal, publish_b_receipt
from opencode_go_provider import GoFailure

IDENTITY = "a" * 64
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0,
         "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}


def journal(root, attempt="a", run="r", identity=IDENTITY):
    return ChiJournal(root, identity=identity, evaluation="eval", task="task", attempt=attempt, run=run)


class JournalTests(unittest.TestCase):
    def test_b_receipt_required_and_bound_to_completed_run(self):
        import copy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            b = ChiJournal(root, identity=IDENTITY, evaluation="e", task="synthetic-coding-b", attempt="b", run="b", kind="coding_b", launch={"kind": "coding_b"})
            for n in range(3):
                b.reserve(str(n).encode(), "main"); b.settle(USAGE)
            b.record_tool("one", "inspect_code", "def add(a, b):\n    return a - b\n")
            b.record_tool("two", "verify_patch", "verification:pass")
            b.finish("complete"); saved = copy.deepcopy(b.run); b.close()
            with self.assertRaisesRegex(GoFailure, "chi_b_receipt_missing"):
                ChiJournal(root, identity=IDENTITY, evaluation="e", task="clinical", attempt="c", run="c", require_b=True)
            publish_b_receipt(root, IDENTITY, saved)
            c = ChiJournal(root, identity=IDENTITY, evaluation="e", task="clinical", attempt="c", run="c", require_b=True)
            c.finish("complete"); c.close()
            (root / "b-receipts" / "b.json").write_text("{}")
            with self.assertRaisesRegex(GoFailure, "chi_b_receipt_missing"):
                ChiJournal(root, identity=IDENTITY, evaluation="e", task="other", attempt="d", run="d", require_b=True)

    def test_live_attempt_requires_completed_matching_b(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(GoFailure, "chi_b_receipt_missing"):
                ChiJournal(root, identity=IDENTITY, evaluation="e", task="clinical", attempt="a", run="c", require_b=True)
            self.assertEqual(__import__("json").loads((root / "chi-accounting.json").read_text())["attempts"], [])

    def test_coding_b_has_six_requests_and_no_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = ChiJournal(root, identity=IDENTITY, evaluation="e", task="synthetic", attempt="a", run="b", kind="coding_b")
            with self.assertRaisesRegex(GoFailure, "chi_reservation_invalid"):
                j.reserve(b"confirmation", "confirmation")
            for i in range(6):
                j.reserve(str(i).encode(), "main")
                self.assertEqual(j.run["requests"][-1]["max_tokens"], 1024)
                j.settle(USAGE)
            with self.assertRaisesRegex(GoFailure, "chi_request_limit"):
                j.reserve(b"seventh", "main")
            j.finish("complete"); j.close()
            j = journal(root, attempt="c", run="c")
            self.assertEqual(j.usage_totals()["input_tokens_known"], 18)
            j.finish("complete"); j.close()

    def test_shared_50_request_limit_and_attempt_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = journal(root)
            for i in range(50):
                j.reserve(str(i).encode(), "confirmation" if i in (3, 9) else "main")
                j.settle(USAGE)
            totals = j.usage_totals()
            self.assertEqual(totals["usd"]["charged_usd"]["known"], "0")
            self.assertEqual(totals["usd"]["list_cost_usd"]["known"], "5.0")
            self.assertEqual(totals["usd"]["allowance_usd"]["known"], "5.0")
            self.assertEqual(totals["account_prior_history"], "unknown")
            with self.assertRaisesRegex(GoFailure, "chi_request_limit"):
                j.reserve(b"51", "main")
            j.finish("complete"); j.close()
            with self.assertRaisesRegex(GoFailure, "chi_attempt_or_run_exists"):
                journal(root, run="new")
            j = journal(root, attempt="b", run="new")
            j.finish("complete"); j.close()

    def test_unknown_and_billing_halt_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = journal(root); j.reserve(b"wire", "main"); j.close()
            with self.assertRaisesRegex(GoFailure, "chi_usage_unknown"):
                journal(root, attempt="b", run="new")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = journal(root); j.reserve(b"wire", "main")
            bad = {**USAGE, "cost": 1}
            with self.assertRaisesRegex(GoFailure, "billing_source_unexpected"):
                j.settle(bad)
            j.finish("failed"); j.close()
            with self.assertRaisesRegex(GoFailure, "chi_billing_halted"):
                journal(root, attempt="b", run="new")

    def test_confirmation_limit_and_identity_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            j = journal(root)
            for i in range(2):
                j.reserve(str(i).encode(), "confirmation"); j.settle(USAGE)
            with self.assertRaisesRegex(GoFailure, "chi_confirmation_limit"):
                j.reserve(b"third", "confirmation")
            j.finish("failed"); j.close()
            with self.assertRaisesRegex(GoFailure, "chi_history_invalid"):
                journal(root, attempt="b", run="new", identity="b" * 64)


if __name__ == "__main__":
    unittest.main()
