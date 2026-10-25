"""Tests for the optional fixed-SDK / official-runner integration layer."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

try:
    import model_runner_adapter as adapter
except ModuleNotFoundError as exc:  # Optional dependency layer is absent in base image.
    adapter = None
    _OPTIONAL_IMPORT_ERROR = exc
else:
    _OPTIONAL_IMPORT_ERROR = None


@unittest.skipIf(adapter is None, f"install requirements-model.lock first: {_OPTIONAL_IMPORT_ERROR}")
class ModelRunnerAdapterTests(unittest.TestCase):
    def run_scenario(self, name: str):
        return asyncio.run(adapter._run_offline(name))

    def test_actual_sdk_wire_and_two_tool_rounds_preserve_history(self):
        ledger, result = self.run_scenario("success")
        self.assertEqual(result, "Offline synthetic completion: synthetic-formatted:synthetic-value")
        self.assertEqual(ledger.transport_calls, 3)
        self.assertEqual(ledger.rounds, 3)
        self.assertEqual(len(ledger.effects), 2)
        self.assertEqual(ledger.effects[0]["call_id"], "call-1")
        self.assertEqual(ledger.effects[1]["call_id"], "call-2")
        self.assertEqual([x["call_id"] for x in ledger.tool_exchanges], ["call-1", "call-1", "call-2"])
        self.assertEqual(ledger.requests[0]["url"], "https://api.deepseek.com/v1/chat/completions")
        body = ledger.requests[0]["body"]
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["max_tokens"], adapter.MAX_OUTPUT_TOKENS)
        self.assertNotIn("endpoint", body)
        self.assertNotIn("key_env", body)
        self.assertEqual(ledger.requests[0]["body_sha256"], __import__("hashlib").sha256(
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest())
        second = ledger.requests[1]["body"]["messages"]
        assistant = next(m for m in second if m.get("role") == "assistant" and m.get("tool_calls"))
        self.assertEqual(assistant["content"], "Synthetic step call-1")
        self.assertEqual(assistant["reasoning_content"], "opaque-reason-1")
        self.assertEqual(assistant["tool_calls"][0]["id"], "call-1")
        self.assertEqual(assistant["tool_calls"][0]["function"]["arguments"], '{"key":"sample"}')
        tool = next(m for m in second if m.get("role") == "tool")
        self.assertEqual((tool["tool_call_id"], tool["content"]), ("call-1", "synthetic-value"))

    def test_empty_content_and_reasoning_are_not_coerced_to_none(self):
        empty, result = self.run_scenario("empty-history")
        self.assertEqual(result, "Offline synthetic completion: synthetic-formatted:synthetic-value")
        assistant = next(m for m in empty.requests[1]["body"]["messages"]
                         if m.get("role") == "assistant" and m.get("tool_calls"))
        self.assertEqual(assistant["content"], "")
        self.assertEqual(assistant["reasoning_content"], "")
        self.assertIn("reasoning_content", assistant)

        none, result = self.run_scenario("none-history")
        self.assertEqual(result, "Offline synthetic completion: synthetic-formatted:synthetic-value")
        assistant = next(m for m in none.requests[1]["body"]["messages"]
                         if m.get("role") == "assistant" and m.get("tool_calls"))
        self.assertIsNone(assistant["content"])
        self.assertEqual(assistant["reasoning_content"], "opaque-reason-1")

    def test_whole_tool_batch_and_finish_reason_are_checked_before_effects(self):
        for scenario, code in (("batch-valid-then-invalid", "tool_unknown"),
                               ("invalid-finish", "finish_reason_invalid")):
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertEqual(ledger.effects, [])
                self.assertEqual(ledger.error_code, code)
                self.assertEqual(ledger.transport_calls, 1)

    def test_duplicate_call_id_stops_after_preserving_first_effect(self):
        ledger, result = self.run_scenario("duplicate-call-id")
        self.assertIsNone(result)
        self.assertEqual(ledger.error_code, "tool_call_id_invalid")
        self.assertEqual(ledger.transport_calls, 2)
        self.assertEqual(len(ledger.effects), 1)
        self.assertEqual(ledger.effects[0]["call_id"], "call-1")

    def test_reasoning_replay_requires_exact_model_and_endpoint(self):
        reasoning = SimpleNamespace(origin_model="deepseek-flash", provider_data={"origin_endpoint": "https://api.deepseek.com"})
        context = SimpleNamespace(model="deepseek-flash", base_url="https://api.deepseek.com/v1", reasoning=reasoning)
        self.assertTrue(adapter._same_route_reasoning(context))
        context.base_url = "https://proxy.invalid/v1"
        self.assertFalse(adapter._same_route_reasoning(context))
        context.base_url = "https://api.deepseek.com/v1"
        context.model = "another-model"
        self.assertFalse(adapter._same_route_reasoning(context))
        context.model = "deepseek-flash"
        reasoning.provider_data["origin_endpoint"] = "https://proxy.invalid"
        self.assertFalse(adapter._same_route_reasoning(context))

    def test_response_from_another_model_is_rejected_before_tool_execution(self):
        ledger, result = self.run_scenario("mismatched-response-model")
        self.assertIsNone(result)
        self.assertEqual(ledger.error_code, "response_model_mismatch")
        self.assertEqual(ledger.effects, [])

    def test_missing_or_invalid_usage_makes_aggregate_unknown(self):
        for scenario in ("missing-usage", "invalid-final-usage"):
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertIsNone(ledger.aggregate_input_tokens)
                self.assertIsNone(ledger.aggregate_output_tokens)
                self.assertIsNone(ledger.aggregate_cost_cny)
                self.assertFalse(ledger.usage_complete)
                self.assertEqual(ledger.error_code, "usage_unknown")
        final, _ = self.run_scenario("invalid-final-usage")
        self.assertEqual(len(final.effects), 2)
        self.assertEqual(final.known_input_tokens, 48)

    def test_over_output_or_synthetic_cap_accounts_usage_but_dispatches_no_tools(self):
        for scenario, code in (("over-output", "returned_usage_over_output_limit"),
                               ("over-input", "returned_usage_over_input_limit"),
                               ("over-cap", "returned_usage_over_budget")):
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertEqual(ledger.error_code, code)
                self.assertEqual(ledger.effects, [])
                self.assertGreater(ledger.known_input_tokens, 0)

    def test_request_reservation_includes_synthetic_prior_spend_and_round_limit(self):
        body = {"model": "deepseek-flash", "max_tokens": 128, "messages": [{"role": "user", "content": "synthetic"}]}
        ledger = adapter.Ledger("success", initial_cost_cny=4.99)
        with self.assertRaises(adapter.IntegrationFailure) as budget_error:
            adapter._budget_check(ledger, body)
        self.assertEqual(budget_error.exception.code, "budget_exhausted")
        ledger = adapter.Ledger("success")
        ledger.rounds = adapter.MAX_ROUNDS
        with self.assertRaises(adapter.IntegrationFailure) as round_error:
            adapter._budget_check(ledger, body)
        self.assertEqual(round_error.exception.code, "round_limit")

    def test_request_budget_rejection_happens_before_mock_transport_send(self):
        ledger = adapter.Ledger("success")
        wire = adapter.MockWire(ledger)
        transport = adapter.BudgetedMockTransport(ledger, wire)
        body = json.dumps({"model": "deepseek-flash", "max_tokens": 128,
                           "messages": [{"role": "user", "content": "x" * adapter.MAX_INPUT_TOKENS}]})
        request = adapter.httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions", content=body)
        with self.assertRaises(adapter.IntegrationFailure) as error:
            asyncio.run(transport.handle_async_request(request))
        self.assertEqual(error.exception.code, "input_estimate_limit")
        self.assertEqual(ledger.transport_calls, 0)
        self.assertEqual(ledger.rounds, 0)

    def test_http_transport_failures_never_retry_and_preserve_effects(self):
        scenarios = {
            "http-429": "http_rate_limited", "http-503": "http_unavailable",
            "connect-error": "transport_connect_error", "timeout": "transport_timeout",
        }
        for scenario, code in scenarios.items():
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertEqual(ledger.transport_calls, 1)
                self.assertEqual(ledger.error_code, code)
                self.assertEqual(ledger.effects, [])
                self.assertFalse(ledger.usage_complete)
                self.assertIsNone(ledger.aggregate_cost_cny)

    def test_failure_after_tool_effect_does_not_replay_tool(self):
        # These cases are added to the CLI and exercise the SDK after a tool
        # effect has been recorded in turn one.
        for scenario, code in (("post-tool-429", "http_rate_limited"),
                               ("post-tool-503", "http_unavailable"),
                               ("post-tool-connect-error", "transport_connect_error"),
                               ("post-tool-timeout", "transport_timeout")):
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertEqual(ledger.transport_calls, 2)
                self.assertEqual(ledger.error_code, code)
                self.assertEqual(len(ledger.effects), 1)
                self.assertEqual(ledger.effects[0]["call_id"], "call-1")
                self.assertFalse(ledger.usage_complete)
                self.assertEqual(ledger.known_input_tokens, 20)
                self.assertIsNone(ledger.aggregate_input_tokens)
                self.assertIsNone(ledger.aggregate_cost_cny)

    def test_runner_environment_converter_and_tracing_restore_after_failure(self):
        from agents.models.openai_chatcompletions import Converter
        from agents.mcp.util import MCPUtil
        from agents.tracing import get_trace_provider
        import chi_bench.experiment.agents.openai_agents_runner as upstream
        import chi_bench.experiment.agents.openai_agents_local_tools as tools
        import agents.mcp as agents_mcp

        before = {
            "env": {k: os.environ.get(k) for k in (
                "OPENAI_AGENTS_MODEL", "OPENAI_AGENTS_API_MODE", "OPENAI_AGENTS_MAX_TURNS",
                "OPENAI_AGENTS_REASONING_EFFORT", "OPENAI_AGENTS_MAX_RETRIES", "OPENAI_BASE_URL")},
            "context": upstream._agent_model_context,
            "settings": upstream._build_model_settings,
            "tools": tools.build_local_tools,
            "mcp": agents_mcp.MCPServerStreamableHttp,
            "invoke": MCPUtil.__dict__["invoke_mcp_tool"],
            "to_tool": MCPUtil.__dict__["to_function_tool"],
            "message_converter": Converter.__dict__["message_to_output_items"],
            "history_converter": Converter.__dict__["items_to_messages"],
            "trace": (get_trace_provider()._disabled, get_trace_provider()._manual_disabled,
                      get_trace_provider()._env_disabled),
        }
        self.run_scenario("http-503")
        self.assertIs(upstream._agent_model_context, before["context"])
        self.assertIs(upstream._build_model_settings, before["settings"])
        self.assertIs(tools.build_local_tools, before["tools"])
        self.assertIs(agents_mcp.MCPServerStreamableHttp, before["mcp"])
        self.assertIs(MCPUtil.__dict__["invoke_mcp_tool"], before["invoke"])
        self.assertIs(MCPUtil.__dict__["to_function_tool"], before["to_tool"])
        self.assertIs(Converter.__dict__["message_to_output_items"], before["message_converter"])
        self.assertIs(Converter.__dict__["items_to_messages"], before["history_converter"])
        self.assertEqual((get_trace_provider()._disabled, get_trace_provider()._manual_disabled,
                          get_trace_provider()._env_disabled), before["trace"])
        self.assertEqual({k: os.environ.get(k) for k in before["env"]}, before["env"])

    def test_plan_live_and_evidence_identity(self):
        plan = adapter._plan()
        self.assertEqual(plan["entry"], "chi_bench.experiment.agents.openai_agents_runner.run_agent")
        self.assertFalse(plan["real_api_enabled"])
        self.assertEqual(adapter.main(["live"]), 2)

        ledger, result = self.run_scenario("success")
        evidence = adapter._evidence("test-run", ledger, result, adapter._sdk_identity(), adapter._upstream_identity())
        self.assertEqual(evidence["provenance"], "offline_synthetic_mocktransport_official_runner")
        self.assertIsNone(evidence["accounting"]["real_usage"])
        self.assertIsNone(evidence["accounting"]["real_cost_cny"])
        self.assertIsNone(evidence["outcome"]["official_reward"])
        self.assertEqual(evidence["outcome"]["task_outcome"], "unknown")

    def test_evidence_run_identity_is_exclusive_and_live_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runs"
            with patch.object(adapter, "RUNS_ROOT", root):
                path = adapter._write_evidence("exclusive-1", {"provenance": "synthetic"})
                self.assertTrue(path.is_file())
                with self.assertRaises(FileExistsError):
                    adapter._write_evidence("exclusive-1", {"provenance": "overwrite"})
                untouched = Path(temp) / "live-must-not-create"
                with patch.object(adapter, "RUNS_ROOT", untouched):
                    self.assertEqual(adapter.main(["live"]), 2)
                self.assertFalse(untouched.exists())


if __name__ == "__main__":
    unittest.main()
