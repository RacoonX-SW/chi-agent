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

import scripts.experiments.probe_model_tools as probe
from chi_agent.models.model_adapter import CANDIDATE_PROFILE, make_assistant_message


class TestBModelProbe(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tempdir.name) / "run-1"
        self.run_dir.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def evidence(self):
        return json.loads((self.run_dir / "evidence.json").read_text(encoding="utf-8"))

    def modified_success_transport(self, modify):
        base = probe.SyntheticScenarioTransport("success")

        def transport(request):
            response = base(request)
            return modify(base.calls, response)

        return transport, base

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
        self.assertEqual(result["accounting"]["synthetic_budget_cap_cny"], 5.0)
        self.assertEqual(result["accounting"]["synthetic_input_price_usd_per_million"], 1.0)
        self.assertEqual(result["accounting"]["synthetic_output_price_usd_per_million"], 1.0)
        self.assertEqual(result["accounting"]["synthetic_usd_to_cny"], 7.2)

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
                    "choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "reason", "tool_calls": [first, second]}, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        transport = BatchTransport()
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="invalid-batch")
        self.assertEqual(result["status"], "rejected_response")
        self.assertEqual(result["failure_code"], "unknown_tool")
        self.assertEqual(result["tool_executions"], [])
        self.assertEqual(result["accounting"]["synthetic_usage"], {"input_tokens": 1, "output_tokens": 1})
        self.assertEqual(transport.calls, 1)

    def test_missing_reasoning_is_rejected_before_tool_execution(self):
        def transport(_request):
            return {
                "choices": [{"message": {
                    "role": "assistant", "content": None,
                    "tool_calls": make_assistant_message(
                        content=None, reasoning_content="unused", call_id="call-1", name="synthetic_lookup", arguments={"key": "sample"}
                    )["tool_calls"],
                }, "finish_reason": "tool_calls"}],
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
                    ), "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        transport = DuplicateIdTransport()
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="duplicate-id")
        self.assertEqual(result["failure_code"], "duplicate_tool_call_id")
        self.assertEqual(transport.calls, 2)
        self.assertEqual(len(result["tool_executions"]), 1)

    def test_missing_usage_stops_before_next_request_without_zero_accounting(self):
        transport = probe.SyntheticScenarioTransport("missing-usage")
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="missing-usage")
        self.assertEqual(result["status"], "unverified_unknown_usage")
        self.assertEqual(transport.calls, 1)
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["tool_executions"], [])
        self.assertIsNone(result["accounting"]["synthetic_usage"])
        self.assertIsNone(result["accounting"]["synthetic_cost_cny"])
        self.assertFalse(result["accounting"]["usage_complete"])
        self.assertEqual(result["accounting"]["known_prefix_usage"], {"input_tokens": 0, "output_tokens": 0})

    def test_missing_final_usage_makes_total_usage_and_cost_unknown(self):
        transport, _ = self.modified_success_transport(
            lambda call, response: {key: value for key, value in response.items() if key != "usage"} if call == 3 else response
        )
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="missing-final-usage")
        self.assertEqual(result["status"], "unverified_unknown_usage")
        self.assertIsNone(result["accounting"]["synthetic_usage"])
        self.assertIsNone(result["accounting"]["synthetic_cost_cny"])
        self.assertEqual(result["accounting"]["known_prefix_usage"], {"input_tokens": 32, "output_tokens": 11})

    def test_immediate_final_response_is_not_a_probe_completion(self):
        def without_tools(call, response):
            if call == 1:
                response["choices"][0]["message"] = {
                    "role": "assistant", "content": "synthetic early final", "reasoning_content": "opaque fixture"
                }
                response["choices"][0]["finish_reason"] = "stop"
            return response

        transport, _ = self.modified_success_transport(without_tools)
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="no-tool-exchange")
        self.assertEqual(result["status"], "incomplete_response")
        self.assertEqual(result["failure_code"], "insufficient_tool_exchange_rounds")
        self.assertEqual(result["tool_exchange_rounds"], 0)

    def test_truncated_final_response_is_not_reported_complete(self):
        def truncated_final(call, response):
            if call == 3:
                response["choices"][0]["finish_reason"] = "length"
            return response

        transport, _ = self.modified_success_transport(truncated_final)
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="truncated-final")
        self.assertEqual(result["status"], "incomplete_response")
        self.assertEqual(result["failure_code"], "final_finish_reason_not_stop")
        self.assertEqual(result["tool_exchange_rounds"], 2)

    def test_final_null_tool_calls_is_accepted_as_normal_completion_shape(self):
        def nullable_calls(call, response):
            if call == 3:
                response["choices"][0]["message"]["tool_calls"] = None
            return response

        transport, _ = self.modified_success_transport(nullable_calls)
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="nullable-final-calls")
        self.assertEqual(result["status"], "offline_synthetic_completion")
        self.assertIsNone(result["history"][-1]["tool_calls"])

    def test_unsupported_tool_call_type_is_rejected_before_any_tool_runs(self):
        def unsupported_type(call, response):
            if call == 1:
                response["choices"][0]["message"]["tool_calls"][0]["type"] = "unsupported"
            return response

        transport, _ = self.modified_success_transport(unsupported_type)
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="unsupported-tool-type")
        self.assertEqual(result["status"], "rejected_response")
        self.assertEqual(result["failure_code"], "unsupported_tool_call_type")
        self.assertEqual(result["tool_executions"], [])

    def test_finish_reason_must_match_tool_call_presence(self):
        def wrong_tool_reason(call, response):
            if call == 1:
                response["choices"][0]["finish_reason"] = "stop"
            return response

        transport, _ = self.modified_success_transport(wrong_tool_reason)
        result = probe.run_probe(run_dir=self.run_dir, transport=transport, scenario="finish-reason-mismatch")
        self.assertEqual(result["failure_code"], "finish_reason_tool_call_mismatch")
        self.assertEqual(result["tool_executions"], [])

        final_dir = Path(self.tempdir.name) / "final-mismatch"
        final_dir.mkdir()

        def wrong_final_reason(call, response):
            if call == 3:
                response["choices"][0]["finish_reason"] = "tool_calls"
            return response

        transport, _ = self.modified_success_transport(wrong_final_reason)
        result = probe.run_probe(run_dir=final_dir, transport=transport, scenario="final-finish-reason-mismatch")
        self.assertEqual(result["failure_code"], "finish_reason_tool_call_mismatch")

    def test_boolean_and_fractional_limits_are_rejected_with_evidence(self):
        cases = (("max_rounds", True), ("max_rounds", 1.5), ("max_tokens", False), ("max_input_tokens", 1.5))
        for index, (name, value) in enumerate(cases):
            with self.subTest(name=name, value=value):
                case_dir = Path(self.tempdir.name) / f"invalid-{index}"
                case_dir.mkdir()
                transport = probe.SyntheticScenarioTransport("success")
                kwargs = {"max_rounds": 30, "max_tokens": 8192, "max_input_tokens": 65_536}
                kwargs[name] = value
                result = probe.run_probe(run_dir=case_dir, transport=transport, scenario="invalid-limit", **kwargs)
                self.assertEqual(result["status"], "stopped_invalid_limits")
                self.assertEqual(transport.calls, 0)
                self.assertEqual(result["failure_code"], "invalid_" + ("round" if name == "max_rounds" else "output" if name == "max_tokens" else "input") + "_limit")

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
