"""Offline regression tests for the bounded B synthetic protocol probe."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import b_model_probe as probe
from b_model_adapter import CANDIDATE_PROFILE, make_assistant_message


class TestBModelProbe(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tempdir.name) / "run-1"
        self.run_dir.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def evidence(self):
        return json.loads((self.run_dir / "evidence.json").read_text(encoding="utf-8"))

    def test_success_preserves_candidate_fields_history_and_tool_call_links(self):
        transport = probe.SyntheticScenarioTransport("success")
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="success")

        self.assertEqual(result["status"], "offline_synthetic_completion")
        self.assertEqual(transport.calls, 3)
        self.assertEqual(len(result["requests"]), 3)
        for captured in result["requests"]:
            request = captured["request"]
            for field in ("model", "endpoint", "api", "thinking", "reasoning_effort", "max_tokens"):
                self.assertEqual(request[field], CANDIDATE_PROFILE[field])
            self.assertGreater(captured["input_token_upper_bound"], 0)

        second_request_history = result["requests"][1]["request"]["messages"]
        assistant_first = second_request_history[1]
        tool_first = second_request_history[2]
        self.assertEqual(assistant_first["content"], "Synthetic first step.")
        self.assertEqual(assistant_first["reasoning_content"], "opaque synthetic reasoning 1")
        self.assertEqual(assistant_first["tool_calls"][0]["id"], "synthetic-call-1")
        self.assertEqual(tool_first["tool_call_id"], "synthetic-call-1")
        third_request_history = result["requests"][2]["request"]["messages"]
        self.assertEqual(third_request_history[3]["reasoning_content"], "opaque synthetic reasoning 2")
        self.assertEqual(third_request_history[4]["tool_call_id"], "synthetic-call-2")
        self.assertGreater(
            result["requests"][2]["input_token_upper_bound"],
            result["requests"][1]["input_token_upper_bound"],
        )
        self.assertIsNone(result["real_provider_usage"])
        self.assertIsNone(result["real_provider_cost_cny"])
        self.assertEqual(result["official_reward"], None)
        self.assertEqual(result["accounting"]["provenance"], "synthetic_fixture_only")

    def test_invalid_batch_is_rejected_before_any_call_executes(self):
        class BatchTransport:
            def __init__(self):
                self.calls = 0

            def __call__(self, request):
                self.calls += 1
                first = make_assistant_message(
                    content=None, reasoning_content="reason", call_id="first", name="synthetic_lookup", arguments={"key": "sample"}
                )["tool_calls"][0]
                second = make_assistant_message(
                    content=None, reasoning_content="reason", call_id="second", name="unknown", arguments={}
                )["tool_calls"][0]
                return {
                    "choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "reason", "tool_calls": [first, second]}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        transport = BatchTransport()
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="invalid-batch")
        self.assertEqual(result["status"], "rejected_response")
        self.assertEqual(result["failure_code"], "unknown_tool")
        self.assertEqual(result["tool_executions"], [])
        self.assertEqual(transport.calls, 1)

    def test_missing_reasoning_is_rejected_before_tool_execution(self):
        def transport(_request):
            return {
                "choices": [{"message": {
                    "role": "assistant", "content": None,
                    "tool_calls": make_assistant_message(
                        content=None, reasoning_content="unused", call_id="call-1", name="synthetic_lookup", arguments={"key": "sample"}
                    )["tool_calls"],
                }}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="missing-reasoning")
        self.assertEqual(result["failure_code"], "missing_reasoning_content")
        self.assertEqual(result["tool_executions"], [])

    def test_duplicate_call_id_across_rounds_is_rejected_without_replaying_tool(self):
        class DuplicateIdTransport:
            def __init__(self):
                self.calls = 0

            def __call__(self, _request):
                self.calls += 1
                name = "synthetic_lookup" if self.calls == 1 else "synthetic_format"
                arguments = {"key": "sample"} if self.calls == 1 else {"text": "again"}
                return {
                    "choices": [{"message": make_assistant_message(
                        content="step", reasoning_content="synthetic reasoning",
                        call_id="reused-id", name=name, arguments=arguments,
                    )}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        transport = DuplicateIdTransport()
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="duplicate-id")
        self.assertEqual(result["failure_code"], "duplicate_tool_call_id")
        self.assertEqual(transport.calls, 2)
        self.assertEqual(len(result["tool_executions"]), 1)

    def test_missing_usage_stops_before_next_request_after_recording_tool_effect(self):
        transport = probe.SyntheticScenarioTransport("missing-usage")
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="missing-usage")
        self.assertEqual(result["status"], "unverified_unknown_usage")
        self.assertEqual(transport.calls, 1)
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(len(result["tool_executions"]), 1)
        self.assertEqual(result["tool_executions"][0]["tool_call_id"], "synthetic-call-1")

    def test_post_tool_transport_rejection_is_separate_and_never_retried(self):
        transport = probe.SyntheticScenarioTransport("post-tool-rejection")
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="post-tool-rejection")
        self.assertEqual(result["status"], "transport_rejected")
        self.assertEqual(result["terminal_phase"], "transport_after_tool")
        self.assertEqual(transport.calls, 2)
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(len(result["tool_executions"]), 1)
        self.assertEqual(result["responses"][-1]["exception_class"], "PermissionError")

    def test_transport_exception_message_is_not_written_to_evidence(self):
        def transport(_request):
            raise RuntimeError("secret=synthetic-secret-value")

        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="secret-error")
        evidence_text = (self.run_dir / "evidence.json").read_text(encoding="utf-8")
        self.assertEqual(result["failure_code"], "transport_rejected")
        self.assertNotIn("synthetic-secret-value", evidence_text)
        self.assertEqual(result["responses"][0]["exception_class"], "RuntimeError")

    def test_live_mode_and_input_limit_refuse_before_transport(self):
        class NoCall:
            calls = 0

            def __call__(self, _request):
                self.calls += 1
                raise AssertionError("transport must not be called")

        transport = NoCall()
        live = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="success", mode="live")
        self.assertEqual(live["status"], "refused_live_mode")
        self.assertEqual(transport.calls, 0)

        other_run = Path(self.tempdir.name) / "run-2"
        other_run.mkdir()
        too_small = probe.run_probe(
            run_dir=other_run, transport=transport, scenario="success", max_input_tokens=1,
        )
        self.assertEqual(too_small["status"], "stopped_input_limit")
        self.assertEqual(transport.calls, 0)

    def test_cli_run_id_is_restricted_and_existing_output_is_not_overwritten(self):
        with patch.object(probe, "RUNS_ROOT", Path(self.tempdir.name) / "runs"):
            self.assertEqual(probe.main(["--run-id", "../escape"]), 2)
            self.assertEqual(probe.main(["--run-id", "safe-id"]), 0)
            evidence_path = Path(self.tempdir.name) / "runs" / "safe-id" / "evidence.json"
            original = evidence_path.read_text(encoding="utf-8")
            self.assertEqual(probe.main(["--run-id", "safe-id"]), 2)
            self.assertEqual(evidence_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
