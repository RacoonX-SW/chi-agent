import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import experiment_manifest
import experiment_summary
from experiment_manifest import ManifestError, freeze_manifest, validate_manifest
from experiment_summary import SummaryError, summarize

TASKS = ["pa_t013_t013_o002_p01_new_referral_provider"]


def task(task_id="pa_t013_t013_o002_p01_new_referral_provider", role="provider", attempt=1):
    return {"task_id": task_id, "role": role, "attempt": attempt,
            "resources": {"manifest_sha256": "c" * 64, "world_image_id": "world-v1"},
            "checks": ["request_budget", "case_status"]}


def cell(cell_id, mechanism, mode, **extra):
    value = {"cell_id": cell_id, "mechanism": mechanism, "mode": mode,
             "tasks": [task()], "limits": {"provider_requests": 50, "output_tokens": 8192}}
    value.update(extra)
    return value


def manifest(cells=None):
    return {
        "schema": "chi-experiment-campaign-v1",
        "campaign_id": "f7-synthetic-001",
        "candidate": {"source_sha256": "a" * 64, "bundle_sha256": "b" * 64,
                      "model": "deepseek-v4.1-flash", "endpoint": "opencode-go",
                      "simulator": "dev-go-patient-v1", "capabilities": "f0-f6-v1"},
        "cells": cells or [
            cell("F4-off", "F4", "off", toggle="context_budget", hypothesis="off baseline"),
            cell("F4-on", "F4", "on", toggle="context_budget", hypothesis="measure and stop"),
        ],
        "stop_conditions": ["unknown_usage", "cross_patient_write", "cleanup_unconfirmed"],
        "created_at": "2026-11-01T00:00:00Z",
    }


def record(cell_id, *, status="completed", checks=None, logs=True, business="observed",
           evidence="public status read", official=None, usage=None, failure=None,
           task_id="pa_t013_t013_o002_p01_new_referral_provider", role="provider", attempt=1):
    return {
        "schema": "chi-experiment-record-v1",
        "campaign_id": "f7-synthetic-001",
        "cell_id": cell_id, "task_id": task_id, "role": role, "attempt": attempt,
        "candidate": copy.deepcopy(manifest()["candidate"]),
        "run": {"status": status, "safe_error_code": "synthetic_error" if status == "failed" else None},
        "logs": {"present": logs, "reason": None if logs else "missing_log"},
        "checks": checks if checks is not None else [
            {"id": "request_budget", "status": "pass"}, {"id": "case_status", "status": "pass"}],
        "business": {"state": business, "evidence": evidence if business == "observed" else None},
        "content": {"status": "not_performed", "result": None},
        "official_reward": official,
        "usage": usage if usage is not None else {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.1},
        "failure": failure,
    }


class ManifestTests(unittest.TestCase):
    def test_valid_manifest_freezes_deterministically(self):
        value = manifest()
        first = freeze_manifest(value)
        second = freeze_manifest(copy.deepcopy(value))
        self.assertEqual(first, second)
        self.assertRegex(first[1], r"^[0-9a-f]{64}$")
        normalized = validate_manifest(value)
        self.assertEqual([cell["mode"] for cell in normalized["cells"]], ["off", "on"])

    def test_unknown_field_and_incomplete_pair_are_rejected(self):
        value = manifest()
        value["unexpected"] = True
        with self.assertRaises(ManifestError) as caught:
            validate_manifest(value)
        self.assertEqual(caught.exception.code, "manifest_invalid")
        with self.assertRaises(ManifestError) as caught:
            validate_manifest(manifest([cell("F4-on", "F4", "on", toggle="t", hypothesis="h")]))
        self.assertEqual(caught.exception.code, "manifest_mechanism_incomplete")

    def test_off_on_arms_must_share_tasks_and_limits(self):
        bad = manifest()
        bad["cells"][1]["tasks"][0]["task_id"] = "pa_t014_t014_o001_p01_new_referral_provider"
        with self.assertRaises(ManifestError) as caught:
            validate_manifest(bad)
        self.assertEqual(caught.exception.code, "manifest_comparison_mismatch")

    def test_not_applicable_cell_requires_reason(self):
        value = manifest([cell("F2-na", "F2", "na")])
        with self.assertRaises(ManifestError):
            validate_manifest(value)
        value["cells"][0]["reason"] = "not independently toggleable in this candidate"
        normalized = validate_manifest(value)
        self.assertEqual(normalized["cells"][0]["mode"], "na")


class SummaryTests(unittest.TestCase):
    def test_full_denominator_includes_not_run(self):
        summary = summarize(manifest(), [record("F4-off"), record("F4-on")])
        self.assertEqual(summary["planned_tasks"], 2)
        self.assertEqual(summary["totals"]["completed"], 2)
        self.assertEqual(summary["totals"]["not_run"], 0)
        summary = summarize(manifest(), [record("F4-off")])
        self.assertEqual(summary["totals"]["completed"], 1)
        self.assertEqual(summary["totals"]["not_run"], 1)
        self.assertNotIn("success_rate", summary)

    def test_skipped_and_blocked_are_not_passes(self):
        failure = {"code": "cleanup_failed", "phase": "cleanup"}
        summary = summarize(manifest(), [
            record("F4-off", status="skipped"),
            record("F4-on", status="blocked", failure=failure),
        ])
        self.assertEqual(summary["totals"]["skipped"], 1)
        self.assertEqual(summary["totals"]["blocked"], 1)
        self.assertEqual(summary["totals"]["completed"], 0)
        for cell in summary["cells"]:
            self.assertEqual(cell["checks"]["pass"], 0)
            self.assertEqual(cell["checks"]["not_run"], 2)

    def test_missing_logs_are_counted_not_treated_as_pass(self):
        summary = summarize(manifest(), [record("F4-off", logs=False)])
        self.assertEqual(summary["totals"]["missing_evidence"], 1)
        self.assertEqual(summary["totals"]["completed"], 1)
        self.assertEqual(summary["cells"][0]["checks"]["pass"], 2)
        self.assertEqual(summary["note"].startswith("counts/denominators"), True)

    def test_missing_usage_keeps_known_sum_and_missing_count(self):
        usage = {"input_tokens": None, "output_tokens": 5, "cost_usd": None}
        summary = summarize(manifest(), [record("F4-off", usage=usage)])
        cell = summary["cells"][0]
        self.assertEqual(cell["usage"]["input_tokens_known_sum"], 0)
        self.assertEqual(cell["usage"]["input_tokens_missing"], 1)
        self.assertEqual(cell["usage"]["output_tokens_known_sum"], 5)
        self.assertEqual(cell["usage"]["cost_usd_missing"], 1)

    def test_record_candidate_mismatch_is_rejected(self):
        bad = record("F4-off")
        bad["candidate"]["model"] = "other-model"
        with self.assertRaises(SummaryError) as caught:
            summarize(manifest(), [bad])
        self.assertEqual(caught.exception.code, "record_candidate_mismatch")

    def test_duplicate_and_unplanned_records_are_rejected(self):
        with self.assertRaises(SummaryError) as caught:
            summarize(manifest(), [record("F4-off"), record("F4-off")])
        self.assertEqual(caught.exception.code, "record_duplicate")
        with self.assertRaises(SummaryError) as caught:
            summarize(manifest(), [record("F4-on", task_id="pa_t014_t014_o001_p01_new_referral_provider")])
        self.assertEqual(caught.exception.code, "record_unplanned")

    def test_unplanned_check_and_observed_without_evidence_are_rejected(self):
        bad = record("F4-off")
        bad["checks"].append({"id": "invented_check", "status": "pass"})
        with self.assertRaises(SummaryError) as caught:
            summarize(manifest(), [bad])
        self.assertEqual(caught.exception.code, "record_checks_invalid")
        bad = record("F4-off")
        bad["business"] = {"state": "observed", "evidence": None}
        with self.assertRaises(SummaryError) as caught:
            summarize(manifest(), [bad])
        self.assertEqual(caught.exception.code, "record_business_evidence_missing")

    def test_official_reward_is_preserved_or_absent_never_synthesized(self):
        summary = summarize(manifest(), [record("F4-off", official=None),
                                          record("F4-on", official=0.75)])
        cells = {cell["cell_id"]: cell for cell in summary["cells"]}
        self.assertEqual(cells["F4-off"]["official_reward"], {"present": 0, "absent": 1})
        self.assertEqual(cells["F4-on"]["official_reward"], {"present": 1, "absent": 0})
        self.assertNotIn("official_reward_mean", summary)

    def test_by_role_keeps_planned_not_run_tasks(self):
        summary = summarize(manifest(), [record("F4-off")])
        cell = summary["cells"][0]
        self.assertEqual(cell["by_role"]["provider"]["planned"], 1)
        role = next(item for item in summary["cells"] if item["cell_id"] == "F4-on")["by_role"]
        self.assertEqual(role["provider"]["planned"], 1)
        self.assertEqual(role["provider"]["not_run"], 1)


class CliTests(unittest.TestCase):
    def test_validate_freeze_and_summarize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            records_path = root / "records.json"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            records_path.write_text(json.dumps([record("F4-off")]), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(experiment_manifest.main(
                    ["validate", "--manifest", str(manifest_path)]), 0)
                frozen = json.loads(output.getvalue())
                self.assertEqual(frozen["status"], "valid")
                self.assertRegex(frozen["manifest_sha256"], r"^[0-9a-f]{64}$")
                output.seek(0)
                output.truncate(0)
                self.assertEqual(experiment_summary.main(
                    ["summarize", "--manifest", str(manifest_path),
                     "--records", str(records_path)]), 0)
                summary = json.loads(output.getvalue())
                self.assertEqual(summary["schema"], "chi-experiment-summary-v1")
                self.assertEqual(summary["totals"]["completed"], 1)

    def test_invalid_manifest_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(experiment_manifest.main(["validate", "--manifest", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
