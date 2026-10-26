"""Tests for the optional fixed-SDK / official-runner integration layer."""

from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

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

    def test_not_found_tool_effect_consumes_id_and_prevents_duplicate(self):
        ledger, result = self.run_scenario("not-found-then-duplicate")
        self.assertIsNone(result)
        self.assertEqual(ledger.transport_calls, 2)
        self.assertEqual(ledger.error_code, "tool_call_id_invalid")
        self.assertEqual(ledger.validated_call_ids, {"call-1"})
        self.assertEqual(ledger.effects, [{
            "tool": "synthetic_lookup", "call_id": "call-1", "result": "synthetic-key-not-found",
        }])

    def test_call_id_shape_and_tool_batch_validation(self):
        scenarios = {
            "invalid-call-id": "tool_call_id_invalid",
            "batch-duplicate-id": "tool_call_id_invalid",
            "invalid-call-type": "tool_batch_invalid",
            "invalid-call-json": "tool_arguments_invalid",
            "invalid-call-argument-type": "tool_arguments_invalid",
            "batch-valid-then-invalid": "tool_unknown",
        }
        for scenario, code in scenarios.items():
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertEqual(ledger.error_code, code)
                self.assertEqual(ledger.effects, [])
                self.assertEqual(ledger.validated_call_ids, set())

    def test_final_assistant_requires_nonblank_content_and_reasoning(self):
        for scenario, code in (
            ("final-no-reasoning", "reasoning_missing"),
            ("final-invalid-reasoning", "reasoning_missing"),
            ("final-content-none", "final_content_invalid"),
            ("final-content-empty", "final_content_invalid"),
            ("final-content-whitespace", "final_content_invalid"),
            ("final-content-absent", "final_content_invalid"),
            ("finish-length", "finish_reason_invalid"),
            ("finish-content-filter", "finish_reason_invalid"),
        ):
            with self.subTest(scenario=scenario):
                ledger, result = self.run_scenario(scenario)
                self.assertIsNone(result)
                self.assertEqual(ledger.error_code, code)
                self.assertEqual(len(ledger.effects), 2)

    def test_huge_usage_is_unknown_without_overflow_or_fake_aggregate(self):
        ledger, result = self.run_scenario("huge-usage")
        self.assertIsNone(result)
        self.assertEqual(ledger.error_code, "usage_unknown")
        self.assertFalse(ledger.usage_complete)
        self.assertEqual(ledger.known_input_tokens, 0)
        self.assertEqual(ledger.known_cost_cny, 0.0)
        self.assertIsNone(ledger.aggregate_input_tokens)
        self.assertIsNone(ledger.aggregate_cost_cny)

    def test_unknown_or_invalid_ledger_blocks_before_transport(self):
        request_body = {"model": "deepseek-flash", "max_tokens": 128,
                        "messages": [{"role": "user", "content": "synthetic"}]}
        bad_states = (
            ("unknown", lambda ledger: adapter._mark_unknown_usage(ledger), "usage_unknown"),
            ("bool_prior", lambda ledger: setattr(ledger, "initial_cost_cny", True), "accounting_state_invalid"),
            ("nan_cost", lambda ledger: setattr(ledger, "known_cost_cny", math.nan), "accounting_state_invalid"),
            ("huge_cost", lambda ledger: setattr(ledger, "known_cost_cny", 10**400), "accounting_state_invalid"),
            ("missing_source", lambda ledger: setattr(ledger, "prior_cost_source", ""), "accounting_state_invalid"),
        )
        for name, mutate, code in bad_states:
            with self.subTest(state=name):
                ledger = adapter.Ledger("success")
                mutate(ledger)
                transport = adapter.BudgetedMockTransport(ledger, adapter.MockWire(ledger))
                request = adapter.httpx.Request(
                    "POST", "https://api.deepseek.com/v1/chat/completions",
                    content=json.dumps(request_body),
                )
                with self.assertRaises(adapter.IntegrationFailure) as error:
                    asyncio.run(transport.handle_async_request(request))
                self.assertEqual(error.exception.code, code)
                self.assertEqual(ledger.transport_calls, 0)
                self.assertEqual(ledger.rounds, 0)

    def test_failure_during_async_openai_setup_restores_every_scoped_change(self):
        from agents.models.openai_chatcompletions import Converter
        from agents.mcp.util import MCPUtil
        from agents.tracing import get_trace_provider
        import chi_bench.experiment.agents.openai_agents_runner as upstream
        import chi_bench.experiment.agents.openai_agents_local_tools as tools
        import agents.mcp as agents_mcp
        import openai

        vendor_path = str(adapter.VENDOR_SRC)
        while vendor_path in __import__("sys").path:
            __import__("sys").path.remove(vendor_path)
        sys_path_before = list(__import__("sys").path)
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
        with patch.object(openai, "AsyncOpenAI", side_effect=RuntimeError("secret-like diagnostic")):
            ledger, result = self.run_scenario("success")
        self.assertIsNone(result)
        self.assertEqual(ledger.error_code, "offline_setup_failed")
        self.assertEqual(ledger.transport_calls, 0)
        self.assertEqual(__import__("sys").path, sys_path_before)
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

    def test_cleanup_failure_is_recorded_without_overwriting_primary_error(self):
        import openai

        async def fail_close(_client):
            raise RuntimeError("sensitive close diagnostic")

        with patch.object(openai.AsyncOpenAI, "close", fail_close):
            failed, result = self.run_scenario("http-503")
            self.assertIsNone(result)
            self.assertEqual(failed.error_code, "http_unavailable")
            self.assertEqual(failed.cleanup_error_code, "cleanup_failed")
            failed_evidence = adapter._evidence(
                "cleanup-primary", failed, result, adapter._sdk_identity(), adapter._upstream_identity()
            )
            self.assertEqual(failed_evidence["outcome"]["safe_error_code"], "http_unavailable")
            self.assertEqual(failed_evidence["outcome"]["safe_cleanup_error_code"], "cleanup_failed")
            self.assertNotIn("sensitive close diagnostic", json.dumps(failed_evidence))

            succeeded, result = self.run_scenario("success")
        self.assertIsNone(result)
        self.assertEqual(succeeded.error_code, "cleanup_failed")
        self.assertEqual(succeeded.cleanup_error_code, "cleanup_failed")
        success_evidence = adapter._evidence(
            "cleanup-only", succeeded, result, adapter._sdk_identity(), adapter._upstream_identity()
        )
        self.assertEqual(success_evidence["outcome"]["safe_error_code"], "cleanup_failed")
        self.assertEqual(success_evidence["outcome"]["safe_cleanup_error_code"], "cleanup_failed")
        self.assertEqual(success_evidence["outcome"]["status"], "incomplete")

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
        accounting = evidence["accounting"]
        for key in ("synthetic_input_price_usd_per_million", "synthetic_output_price_usd_per_million",
                    "synthetic_usd_to_cny", "pricing_version", "pricing_source", "fx_rate_source",
                    "synthetic_prior_spend_cny", "synthetic_prior_spend_source", "budget_aggregate_cost_cny"):
            self.assertIn(key, accounting)
        recomputed = accounting["synthetic_prior_spend_cny"] + (
            (accounting["aggregate_usage"]["input_tokens"] * accounting["synthetic_input_price_usd_per_million"]
             + accounting["aggregate_usage"]["output_tokens"] * accounting["synthetic_output_price_usd_per_million"])
            / 1_000_000 * accounting["synthetic_usd_to_cny"]
        )
        self.assertAlmostEqual(accounting["budget_aggregate_cost_cny"], recomputed)

    def test_evidence_run_identity_is_exclusive_and_live_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runs"
            with patch.object(adapter, "RUNS_ROOT", root):
                path = adapter._write_evidence("exclusive-1", {"provenance": "synthetic"})
                self.assertTrue(path.is_file())
                with self.assertRaises(adapter.IntegrationFailure):
                    adapter._write_evidence("exclusive-1", {"provenance": "overwrite"})
                untouched = Path(temp) / "live-must-not-create"
                with patch.object(adapter, "RUNS_ROOT", untouched):
                    self.assertEqual(adapter.main(["live"]), 2)
                self.assertFalse(untouched.exists())

    def test_offline_id_is_reserved_before_runner_and_collisions_preserve_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runs"
            with patch.object(adapter, "RUNS_ROOT", root), patch.object(adapter, "_run_offline", new=AsyncMock()) as runner:
                self.assertEqual(adapter.main(["offline", "--run-id", "../unsafe"]), 2)
                runner.assert_not_awaited()
                self.assertFalse(root.exists())

                root.mkdir()
                existing = root / "duplicate.json"
                existing.write_bytes(b"preserve-exactly")
                self.assertEqual(adapter.main(["offline", "--run-id", "duplicate"]), 2)
                runner.assert_not_awaited()
                self.assertEqual(existing.read_bytes(), b"preserve-exactly")

                reservation = adapter._reserve_evidence("concurrent")
                with self.assertRaises(adapter.IntegrationFailure) as error:
                    adapter._reserve_evidence("concurrent")
                self.assertEqual(error.exception.code, "run_id_exists")
                reservation.close()

    def test_async_openai_init_failure_leaves_safe_terminal_evidence(self):
        import openai
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runs"
            with patch.object(adapter, "RUNS_ROOT", root), patch.object(
                openai, "AsyncOpenAI", side_effect=RuntimeError("secret-like diagnostic")
            ):
                self.assertEqual(adapter.main(["offline", "--run-id", "init-failure"]), 1)
            evidence = json.loads((root / "init-failure.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["outcome"]["status"], "incomplete")
            self.assertEqual(evidence["outcome"]["safe_error_code"], "offline_setup_failed")
            self.assertNotIn("secret-like diagnostic", json.dumps(evidence))


if __name__ == "__main__":
    unittest.main()
