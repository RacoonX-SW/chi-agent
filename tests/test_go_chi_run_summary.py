import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.tools.summarize_runs as summary
from chi_agent.journal import ChiJournal
from chi_agent.opencode_go_provider import GoFailure

IDENTITY = "a" * 64
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
         "opencode": {"billing_source": "go", "list_cost": 0.1, "allowance": 0.1}}


def settle(journal, usage=USAGE):
    journal.record_response(json.dumps({"usage": usage}).encode(), 200, 1)
    journal.settle(usage)
    journal.record_diagnostic("ok", 1)


def tree_digest(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


class SummaryTests(unittest.TestCase):
    def digest(self, root: Path) -> str:
        return hashlib.sha256((root / "chi-accounting.json").read_bytes()).hexdigest()

    def test_complete_run_is_stable_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); settle(journal); journal.finish("complete"); journal.close()
            before = tree_digest(root)
            first = summary.summarize(root, IDENTITY, self.digest(root))
            second = summary.summarize(root, IDENTITY, self.digest(root))
            self.assertEqual(first, second)
            self.assertEqual(tree_digest(root), before)
            self.assertFalse(first["execution_allowed"])
            self.assertEqual(first["schema"], "chi-go-run-summary-v1")
            run = first["runs"][0]
            self.assertEqual((run["run"], run["status"], run["role"]), ("r", "complete", None))
            self.assertEqual(run["totals"]["input_tokens_known"], 3)
            self.assertEqual(run["totals"]["usd"]["charged_usd"]["known"], "0")
            self.assertTrue(run["totals"]["usd"]["list_cost_usd"]["complete"])
            self.assertEqual(run["by_purpose"]["main"]["settled"], 1)

    def test_pending_unknown_is_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); journal.close()
            result = summary.summarize(root, IDENTITY, self.digest(root))
            self.assertEqual(result["validation"]["pending"], {"run": "r", "round": 1})
            request = result["runs"][0]["requests"][0]
            self.assertEqual(request["status"], "pending")
            self.assertIsNone(request["tokens"])
            self.assertEqual(result["runs"][0]["totals"]["unknown_tokens"], 1)
            self.assertFalse(result["runs"][0]["totals"]["usd"]["charged_usd"]["complete"])

    def test_known_tokens_with_missing_fees_keep_null_and_halt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost": 0,
                     "opencode": {"billing_source": "go"}}
            journal.reserve(b"{}", "main")
            journal.record_response(json.dumps({"usage": usage}).encode(), 200, 1)
            with self.assertRaises(GoFailure):
                journal.settle(usage)
            journal.record_diagnostic("billing_details_unknown", 1)
            journal.finish("failed", "billing_details_unknown")
            journal.close()
            result = summary.summarize(root, IDENTITY, self.digest(root))
            self.assertEqual(result["validation"]["halted"], "billing_details_unknown")
            request = result["runs"][0]["requests"][0]
            self.assertIsNone(request["billing"]["list_cost_usd"])
            self.assertFalse(request["billing"]["currency"] != "USD")
            self.assertEqual(request["billing_error"], "billing_details_unknown")

    def test_main_and_patient_requests_are_grouped_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launch = {"kind": "chi", "role": "cm", "aux_contract": "patient-simulator-v1"}
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a",
                                 run="r", launch=launch)
            journal.reserve(b"{}", "main"); settle(journal)
            journal.start_tool("call_1", "cm_outreach.send_message", {})
            journal.reserve(b"{}", "patient_simulator", parent_call_id="call_1"); settle(journal)
            journal.record_tool("call_1", "cm_outreach.send_message", "ok")
            journal.finish("complete"); journal.close()
            result = summary.summarize(root, IDENTITY, self.digest(root))
            purposes = result["runs"][0]["by_purpose"]
            self.assertEqual(set(purposes), {"main", "patient_simulator"})
            self.assertEqual(purposes["main"]["requests"], 1)
            self.assertEqual(purposes["patient_simulator"]["requests"], 1)
            self.assertEqual(result["totals"]["requests"], 2)

    def test_snapshot_change_between_inspection_and_projection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); settle(journal); journal.finish("complete"); journal.close()
            digest = self.digest(root)
            original = summary.inspect_history

            def racing(target, identity, sha):
                result = original(target, identity, sha)
                state = target / "chi-accounting.json"
                state.write_bytes(state.read_bytes() + b"\n")
                return result

            with patch('scripts.tools.summarize_runs.inspect_history', side_effect=racing):
                with self.assertRaises(summary.SummaryError) as caught:
                    summary.summarize(root, IDENTITY, digest)
            self.assertEqual(caught.exception.code, "summary_snapshot_changed")

    def test_wrong_identity_hash_and_corrupt_state_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); settle(journal); journal.finish("complete"); journal.close()
            digest = self.digest(root)
            with self.assertRaisesRegex(GoFailure, "chi_history_invalid"):
                summary.summarize(root, "b" * 64, digest)
            with self.assertRaisesRegex(GoFailure, "chi_inspect_hash_mismatch"):
                summary.summarize(root, IDENTITY, "c" * 64)
            (root / "chi-accounting.json").write_text("{not json")
            with self.assertRaises(GoFailure):
                summary.summarize(root, IDENTITY, hashlib.sha256(b"{not json").hexdigest())

    def test_invalid_run_selection_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); settle(journal); journal.finish("complete"); journal.close()
            with self.assertRaises(summary.SummaryError) as caught:
                summary.summarize(root, IDENTITY, self.digest(root), "missing-run")
            self.assertEqual(caught.exception.code, "summary_run_missing")
            result = summary.summarize(root, IDENTITY, self.digest(root), "r")
            self.assertEqual(result["selection"], {"mode": "run", "run": "r"})
            self.assertEqual([run["run"] for run in result["runs"]], ["r"])

    def test_cli_exit_codes_and_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); settle(journal); journal.finish("complete"); journal.close()
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = summary.main(["--root", str(root), "--identity", IDENTITY,
                                     "--accounting-sha256", self.digest(root)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["schema"], "chi-go-run-summary-v1")
            self.assertEqual(err.getvalue(), "")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = summary.main(["--root", str(root), "--identity", IDENTITY,
                                     "--accounting-sha256", "d" * 64])
            self.assertEqual(code, 1)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(json.loads(err.getvalue())["code"], "chi_inspect_hash_mismatch")

    def test_old_state_without_new_sections_is_summarised(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ChiJournal(root, identity=IDENTITY, evaluation="e", task="t", attempt="a", run="r")
            journal.reserve(b"{}", "main"); settle(journal); journal.finish("complete"); journal.close()
            state = json.loads((root / "chi-accounting.json").read_text())
            self.assertNotIn("reconciliations", state)
            result = summary.summarize(root, IDENTITY, self.digest(root))
            self.assertEqual(result["validation"]["input_summaries"], [])
            self.assertEqual(result["validation"]["reconciled_provider_timeouts"], [])


if __name__ == "__main__":
    unittest.main()
