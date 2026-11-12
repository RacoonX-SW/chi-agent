"""Offline protocol and fail-closed tests for the A-stage MCP probe."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scripts.experiments.probe_official_tools as probe  # noqa: E402


def live_schema():
    return {
        "type": "object",
        "properties": {
            "status": {
                "anyOf": [
                    {"type": "string", "enum": sorted(probe.CASE_STATUSES)},
                    {"type": "null"},
                ]
            }
        },
        "required": [],
    }


def tool(name=probe.ALLOWED_TOOL, schema=None):
    return SimpleNamespace(name=name, inputSchema=live_schema() if schema is None else schema)


class FakeTransport:
    def __init__(self):
        self.exited = False

    async def __aenter__(self):
        return (object(), object(), lambda: "session")

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True


class FakeSession:
    def __init__(self, *, tools=None, result=None, hang_phase=None, exit_group_mode=None):
        self.tools = [tool()] if tools is None else tools
        self.result = SimpleNamespace(
            isError=False,
            structuredContent={"items": []},
        ) if result is None else result
        self.hang_phase = hang_phase
        self.exit_group_mode = exit_group_mode
        self.events = []
        self.call_count = 0
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        if self.exit_group_mode == "probe_only" and exc is not None:
            raise ExceptionGroup("synthetic SDK wrapper", [exc])
        if self.exit_group_mode == "mixed" and exc is not None:
            raise ExceptionGroup("synthetic SDK wrapper and cleanup error", [exc, RuntimeError("cleanup failed")])
        if self.exit_group_mode == "base_mixed" and exc is not None:
            raise BaseExceptionGroup(
                "synthetic SDK wrapper and cancellation",
                [exc, asyncio.CancelledError("cancelled during cleanup")],
            )

    async def initialize(self):
        self.events.append("initialize")
        if self.hang_phase == "initialize":
            await asyncio.sleep(60)
        return SimpleNamespace(
            serverInfo=SimpleNamespace(name="synthetic-server", version="0"),
            protocolVersion="2024-11-05",
        )

    async def list_tools(self):
        self.events.append("list_tools")
        if self.hang_phase == "list_tools":
            await asyncio.sleep(60)
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, *, arguments):
        self.events.append("call_tool")
        self.call_count += 1
        self.called_name = name
        self.arguments = arguments
        if self.hang_phase == "call_tool":
            await asyncio.sleep(60)
        return self.result


class AToolsProbeTests(unittest.TestCase):
    def run_probe(self, *, session=None, phase_timeout_sec=0.5):
        temporary = tempfile.TemporaryDirectory()
        evidence = Path(temporary.name)
        transport = FakeTransport()
        session = session or FakeSession()

        @asynccontextmanager
        async def transport_factory(endpoint):
            self.assertEqual(endpoint, probe.ALLOWED_ENDPOINT)
            async with transport as streams:
                yield streams

        class SessionContext:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return await session.__aexit__(exc_type, exc, tb)

        summary = asyncio.run(
            probe.execute_probe(
                endpoint=probe.ALLOWED_ENDPOINT,
                evidence_dir=evidence,
                phase_timeout_sec=phase_timeout_sec,
                transport_factory=transport_factory,
                session_factory=lambda *_streams: SessionContext(),
            )
        )
        return temporary, evidence, transport, session, summary

    def test_success_runs_initialize_list_and_exactly_one_empty_list_call(self):
        temp, evidence, transport, session, summary = self.run_probe()
        try:
            self.assertEqual(session.events, ["initialize", "list_tools", "call_tool"])
            self.assertEqual(session.call_count, 1)
            self.assertEqual(session.called_name, "cases.list_cases")
            self.assertEqual(session.arguments, {})
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["items_count"], 0)
            self.assertTrue(summary["empty_items"])
            self.assertTrue(summary["call_invoked"])
            self.assertTrue(summary["call_response_received"])
            self.assertEqual(summary["call_result_status"], "valid")
            self.assertEqual(summary["business_effect"], "none_expected_read_only")
            self.assertEqual(summary["audit_effect"], "expected_from_successful_handler")
            self.assertEqual(summary["model_calls"], 0)
            self.assertEqual(summary["tool_retries"], 0)
            self.assertTrue((evidence / "mcp-schema.json").is_file())
            self.assertTrue((evidence / "mcp-response.json").is_file())
            self.assertTrue((evidence / "summary.json").is_file())
        finally:
            temp.cleanup()

    def test_missing_target_tool_fails_without_any_call(self):
        temp, _, transport, session, summary = self.run_probe(
            session=FakeSession(tools=[tool("auth.submit_authorization")])
        )
        try:
            self.assertEqual(session.call_count, 0)
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["phase"], "schema_validation")
            self.assertFalse(summary["call_invoked"])
            self.assertEqual(summary["audit_effect"], "not_attempted")
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
        finally:
            temp.cleanup()

    def test_dangerous_tool_name_is_rejected_by_local_policy(self):
        for name in (
            "auth.submit_authorization",
            "docs.upload_evidence",
            "unknown.delete_everything",
        ):
            with self.subTest(name=name), self.assertRaises(probe.ProbeFailure):
                probe.authorize_tool(name, {probe.ALLOWED_TOOL, name})

    def test_missing_or_changed_schema_fails_before_tool_call(self):
        cases = [
            SimpleNamespace(name=probe.ALLOWED_TOOL),
            tool(schema={"type": "object", "properties": {}, "required": []}),
            tool(schema={"type": "object", "properties": {"status": {"type": "string"}}, "required": []}),
            tool(schema={"type": "object", "properties": {"status": live_schema()["properties"]["status"], "other": {"type": "string"}}, "required": []}),
            tool(schema={"type": "object", "properties": live_schema()["properties"], "required": ["status"]}),
            tool(schema={"type": "object", "properties": live_schema()["properties"], "required": None}),
            tool(schema={"type": "object", "properties": live_schema()["properties"], "minProperties": 1}),
            tool(schema={"type": "object", "properties": live_schema()["properties"], "not": {}}),
            tool(schema={
                "type": "object",
                "properties": {"status": {"type": "string", "enum": sorted(probe.CASE_STATUSES)}},
            }),
            tool(schema={
                "type": "object",
                "properties": {
                    "status": {
                        **live_schema()["properties"]["status"],
                        "default": "submitted",
                    }
                },
            }),
        ]
        for item in cases:
            with self.subTest(schema=getattr(item, "inputSchema", None)):
                temp, _, transport, session, summary = self.run_probe(session=FakeSession(tools=[item]))
                try:
                    self.assertEqual(session.call_count, 0)
                    self.assertEqual(summary["status"], "failed")
                    self.assertEqual(summary["phase"], "schema_validation")
                    self.assertFalse(summary["call_invoked"])
                    self.assertEqual(summary["audit_effect"], "not_attempted")
                    self.assertTrue(session.exited)
                    self.assertTrue(transport.exited)
                finally:
                    temp.cleanup()

    def test_call_timeout_closes_session_and_transport_without_retry(self):
        temp, _, transport, session, summary = self.run_probe(
            session=FakeSession(hang_phase="call_tool"), phase_timeout_sec=0.01
        )
        try:
            self.assertEqual(session.call_count, 1)
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["phase"], "call_tool")
            self.assertEqual(summary["tool_retries"], 0)
            self.assertTrue(summary["call_invoked"])
            self.assertFalse(summary["call_response_received"])
            self.assertEqual(summary["call_result_status"], "unknown")
            self.assertEqual(summary["business_effect"], "unknown")
            self.assertEqual(summary["audit_effect"], "unknown")
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
        finally:
            temp.cleanup()

    def test_initialize_timeout_also_closes_resources(self):
        temp, _, transport, session, summary = self.run_probe(
            session=FakeSession(hang_phase="initialize"), phase_timeout_sec=0.01
        )
        try:
            self.assertEqual(session.call_count, 0)
            self.assertEqual(summary["phase"], "initialize")
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
        finally:
            temp.cleanup()

    def test_mcp_error_and_invalid_result_shape_never_report_success(self):
        for result in (
            SimpleNamespace(isError=True, structuredContent={"items": []}),
            SimpleNamespace(isError=False, structuredContent={"not_items": []}),
            SimpleNamespace(isError=False, structuredContent={"items": ["not-an-object"]}),
            SimpleNamespace(isError=False, structuredContent=None, content=[]),
        ):
            with self.subTest(result=result):
                temp, _, _, session, summary = self.run_probe(session=FakeSession(result=result))
                try:
                    self.assertEqual(session.call_count, 1)
                    self.assertEqual(summary["status"], "failed")
                    self.assertEqual(summary["phase"], "response_validation")
                    self.assertTrue(summary["call_response_received"])
                    self.assertEqual(summary["audit_effect"], "unknown")
                finally:
                    temp.cleanup()

    def test_raw_response_is_only_in_private_file_not_summary(self):
        patient_detail = {"patient_name": "Synthetic Person", "patient_id": "SYNTHETIC-1"}
        temp, evidence, _, session, summary = self.run_probe(
            session=FakeSession(
                result=SimpleNamespace(isError=False, structuredContent={"items": [patient_detail]})
            )
        )
        try:
            serialized_summary = json.dumps(summary)
            raw = (evidence / "mcp-response.json").read_text(encoding="utf-8")
            self.assertNotIn("Synthetic Person", serialized_summary)
            self.assertIn("Synthetic Person", raw)
            self.assertEqual(summary["items_count"], 1)
        finally:
            temp.cleanup()

    def test_exception_group_preserves_single_nested_timeout(self):
        temp, _, transport, session, summary = self.run_probe(
            session=FakeSession(hang_phase="call_tool", exit_group_mode="probe_only"),
            phase_timeout_sec=0.01,
        )
        try:
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["phase"], "call_tool")
            self.assertIn("timed out", summary["reason"])
            self.assertEqual(summary["error_type"], "TimeoutError")
            self.assertEqual(summary["nested_probe_failures"][0]["phase"], "call_tool")
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
        finally:
            temp.cleanup()

    def test_mixed_exception_group_keeps_generic_and_nested_cleanup_information(self):
        temp, _, transport, session, summary = self.run_probe(
            session=FakeSession(hang_phase="call_tool", exit_group_mode="mixed"),
            phase_timeout_sec=0.01,
        )
        try:
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["phase"], "call_tool")
            self.assertEqual(summary["error_type"], "ExceptionGroup")
            self.assertEqual(summary["reason"], "MCP transport failed")
            self.assertIn("timed out", summary["nested_probe_failures"][0]["reason"])
            self.assertEqual(
                summary["exception_group_member_types"], ["ProbeFailure", "RuntimeError"]
            )
            self.assertTrue(summary["call_invoked"])
            self.assertFalse(summary["call_response_received"])
            self.assertEqual(summary["call_result_status"], "unknown")
            self.assertEqual(summary["audit_effect"], "unknown")
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
        finally:
            temp.cleanup()

    def test_base_exception_group_is_preserved_without_swallowing_cancellation(self):
        temp, _, transport, session, summary = self.run_probe(
            session=FakeSession(hang_phase="call_tool", exit_group_mode="base_mixed"),
            phase_timeout_sec=0.01,
        )
        try:
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["error_type"], "BaseExceptionGroup")
            self.assertIn("timed out", summary["nested_probe_failures"][0]["reason"])
            self.assertEqual(
                summary["exception_group_member_types"], ["CancelledError", "ProbeFailure"]
            )
            self.assertTrue(session.exited)
            self.assertTrue(transport.exited)
        finally:
            temp.cleanup()

    def test_cli_rejects_non_local_endpoint_and_unmapped_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            for argv in (
                ["--endpoint", "http://example.com/mcp", "--output-dir", str(probe.ALLOWED_OUTPUT_DIR)],
                ["--endpoint", probe.ALLOWED_ENDPOINT, "--output-dir", td],
            ):
                with self.subTest(argv=argv):
                    self.assertEqual(probe.main(argv), 2)


if __name__ == "__main__":
    unittest.main()
