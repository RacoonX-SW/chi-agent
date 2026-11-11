import json
import asyncio
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

import patient_identity_binding as pib


class Journal:
    def __init__(self): self.run_doc = {}
    def _persist(self): pass


def result(value):
    return SimpleNamespace(isError=False, structuredContent=value, content=[])


def observations():
    guard = pib.PatientBinding("The patient has a 90 day treatment trial.", Journal())
    patients = [{"id": "P1", "dob": "1970-01-01", "sex": "male"},
                {"id": "P2", "dob": "1971-05-01", "sex": "male"},
                {"id": "P3", "dob": "1985-01-01", "sex": "female"}]
    roster = {"items": patients, "total": len(patients)}
    guard.observe("r1", "chart.search_patients", {}, result(roster))
    exchanges = [{"call_id": "r1", "result": json.dumps(roster)}]
    for pid, dob, duration in (("P1", "1970-01-01", "90 day"), ("P2", "1971-05-01", "30 day")):
        chart = {"patient": {"id": pid, "dob": dob, "sex": "male"},
                 "conditions": ["same diagnosis"],
                 "orders": [{"id": "O" + pid, "patient_id": pid}],
                 "summaries": [duration + " treatment trial", {"id": "D" + pid, "patient_id": pid, "case_id": None}]}
        guard.observe("c" + pid, "chart.get_patient_chart_by_patient", {"patient_id": pid}, result(chart))
        exchanges.append({"call_id": "c" + pid, "result": json.dumps(chart)})
    return guard, exchanges


def verdict(status="unique_match"):
    return json.dumps({"status": status, "selected_patient_id": "P1",
                       "matches": ["P1"], "mismatches": ["P2", "P3"], "unknown": [],
                       "evidence": [{"instruction_quote": "90 day treatment trial",
                                     "chart_quote": "90 day treatment trial"}]})


def test_cohort_requires_full_unfiltered_roster_and_observed_charts():
    guard, history = observations()
    assert "P1" in guard.confirmation_input("P1", history)
    with pytest.raises(pib.Refusal, match="P2"):
        guard.confirmation_input("P1", history[:-1])
    assert guard.confirmations == 0
    filtered = pib.PatientBinding("instruction", Journal())
    filtered.observe("f", "chart.search_patients", {"patient_id": "P1"}, result({"items": [{"id": "P1"}], "total": 1}))
    assert filtered.roster is None
    partial = pib.PatientBinding("instruction", Journal())
    partial.observe("f", "chart.search_patients", {}, result({"items": [{"id": "P1"}], "total": 2}))
    assert partial.roster is None


def test_unique_match_citations_and_candidate_coverage():
    guard, history = observations()
    guard.confirmation_input("P1", history)
    fake = json.loads(verdict())
    fake["evidence"][0]["chart_quote"] = "fabricated"
    assert guard.assess("P1", json.dumps(fake))["reason"] == "evidence_invalid"
    fake = json.loads(verdict())
    fake["mismatches"].remove("P3")
    fake["unknown"].append("P3")
    assert guard.assess("P1", json.dumps(fake)) == {"status": "needs_observation", "reason": "unresolved_candidates", "unknown_ids": ["P3"]}
    assert guard.assess("P1", verdict("ambiguous"))["status"] == "ambiguous"
    assert guard.bound is None
    guard.confirmations = 2
    with pytest.raises(pib.Refusal, match="confirmation_unavailable"):
        guard.confirmation_input("P1", history)
    guard.confirmations = 0
    assert guard.assess("P1", verdict())["status"] == "unique_match"
    assert guard.bound == "P1"
    with pytest.raises(pib.Refusal): guard.confirmation_input("P2", history)


def test_partition_coverage_and_feedback_with_large_roster():
    guard, history = observations()
    items = guard.roster["items"]
    items.extend({"id": f"P{i}", "dob": "1985-01-01", "sex": "female"} for i in range(4, 66))
    guard.roster["value"]["total"] = len(items)
    guard.roster["text"] = json.dumps(guard.roster["value"])
    history[0]["result"] = guard.roster["text"]
    evidence = json.loads(guard.confirmation_input("P1", history))
    assert evidence["expected_count"] == 65
    assert evidence["required_candidate_ids"] == [f"P{i}" for i in range(1, 66)]
    candidate = json.loads(verdict())
    candidate["mismatches"] = [f"P{i}" for i in range(2, 9)]
    result = guard.assess("P1", json.dumps(candidate))
    assert result == {"status": "invalid", "reason": "candidate_coverage_incomplete", "expected_count": 65,
                      "actual_count": 8, "expected_ids": sorted(f"P{i}" for i in range(1, 66)),
                      "actual_ids": sorted(f"P{i}" for i in range(1, 9)),
                      "missing_ids": sorted(f"P{i}" for i in range(9, 66)), "unexpected_ids": []}
    candidate["mismatches"] = [f"P{i}" for i in range(2, 66)]
    candidate["unknown"] = ["P2"]
    assert guard.assess("P1", json.dumps(candidate))["reason"] == "candidate_partition_duplicate"
    candidate["mismatches"].remove("P2")
    assert guard.assess("P1", json.dumps(candidate))["unknown_ids"] == ["P2"]
    candidate["unknown"] = []
    candidate["mismatches"].append("P2")
    candidate["selected_patient_id"] = "P2"
    assert guard.assess("P1", json.dumps(candidate)) == {"status": "mismatch", "reason": "selected_candidate_mismatch"}
    assert guard.bound is None
    candidate["selected_patient_id"] = "P1"
    candidate["evidence"][0]["chart_quote"] = "not present"
    assert guard.assess("P1", json.dumps(candidate))["reason"] == "evidence_invalid"
    assert guard.assess("P1", '{"status":"unique_match","status":"unique_match"}')["reason"] == "confirmation_format_invalid"
    assert guard.bound is None


def test_cross_patient_orders_cases_forms_documents_and_conflicting_result():
    guard, history = observations()
    guard.confirmation_input("P1", history)
    guard.assess("P1", verdict())
    guard.check("cases.create_from_order", {"patient_id": "P1", "source_order_id": "OP1"})
    for args in ({"patient_id": "P2"}, {"patient_id": "P1", "source_order_id": "OP2"},
                 {"patient_id": "P1", "source_order_id": "forged"}):
        with pytest.raises(pib.Refusal): guard.check("cases.create_from_order", args)
    case = {"case": {"id": "C1", "patient_id": "P1", "service_request_id": "OP1"},
            "patient": {"id": "P1"}, "service_request": {"id": "OP1", "patient_id": "P1"}}
    guard.observe("create", "cases.create_from_order", {"patient_id": "P1", "source_order_id": "OP1"}, result(case))
    guard.observe("forms", "forms.list_required_forms", {"case_id": "C1"}, result({"items": [{"form_id": "SHARED-FORM"}]}))
    guard.check("forms.save_form_response", {"case_id": "C1", "form_id": "SHARED-FORM"})
    guard.cases["C2"] = "P1"
    with pytest.raises(pib.Refusal):
        guard.check("forms.save_form_response", {"case_id": "C2", "form_id": "SHARED-FORM"})
    guard.check("docs.create_submission_bundle", {"case_id": "C1", "document_ids": ["DP1"]})
    for name, args in (("forms.save_form_response", {"case_id": "C1", "form_id": "forged"}),
                       ("auth.submit_authorization", {"case_id": "C3"}),
                       ("docs.create_submission_bundle", {"case_id": "C1", "document_ids": ["forged"]}),
                       ("docs.create_submission_bundle", {"case_id": "C1", "document_ids": ["DP2"]}),
                       ("new.unknown", {"case_id": "C1"})):
        with pytest.raises(pib.Refusal): guard.check(name, args)
    bad = dict(case, service_request={"id": "OP2", "patient_id": "P2"})
    with pytest.raises(RuntimeError): guard.observe("bad", "cases.get_case", {"case_id": "C1"}, result(bad))
    with pytest.raises(pib.Refusal): guard.check("cases.create_from_order", {"patient_id": "P1"})


@pytest.mark.parametrize("first_result", ["ambiguous", "length", "empty", "invalid_json"])
def test_confirm_uses_guarded_shared_budget_and_two_attempt_limit(tmp_path, first_result):
    import httpx
    from openai import AsyncOpenAI
    import b_provider_profile as profiles
    import b_provider_transport as transport
    import b_execution_policy as policies
    import live_development as live
    import model_runner_adapter as adapter
    from test_live_development import _adopt_synthetic_history
    import contextvars

    async def run():
        profile = profiles.load_profile(today=datetime.date(2026, 10, 26))
        _adopt_synthetic_history(tmp_path, tmp_path)
        journal = live.RealDevelopmentJournal(tmp_path, "confirmation", profile=profile,
                                               policy=policies.load_real_development_policy())
        journal.start_dispatch = lambda **_kw: None
        journal.finish_dispatch = lambda **_kw: None
        guard, history = observations()
        guard.journal = journal
        ledger = adapter.Ledger("synthetic")
        class Lower(httpx.AsyncBaseTransport):
            calls = 0
            async def handle_async_request(self, request):
                self.calls += 1
                body = json.loads(request.content)
                assert body.get("tools", []) == []
                assert body["max_tokens"] == pib.CONFIRM_MAX_OUTPUT_TOKENS
                if self.calls == 1:
                    content = {"ambiguous": verdict("ambiguous"), "length": None, "empty": "", "invalid_json": "not-json"}[first_result]
                    finish = "length" if first_result == "length" else "stop"
                else:
                    content, finish = verdict(), "stop"
                return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 1,
                    "model": profile.model, "choices": [{"index": 0, "finish_reason": finish,
                    "message": {"role": "assistant", "content": content, "reasoning_content": "test"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}, request=request)
        lower = Lower()
        context = contextvars.ContextVar("confirmation-test", default=None)
        guarded = transport.GuardedTransport(profile=profile, journal=journal, lower=lower, ledger=ledger,
                   cap_cny=None, validate_response=lambda _value: None, allowed_tool_names=set(),
                   confirmation_context=context.get)
        client = AsyncOpenAI(api_key="synthetic", base_url=profile.endpoint + "/v1",
                             http_client=httpx.AsyncClient(transport=guarded), max_retries=0)
        schemas = {}
        tools = live._live_tools("c-once", tmp_path, tmp_path, journal, schemas, ledger, binding=guard,
                                 binding_lock=asyncio.Lock(), openai_client=client, profile=profile, exchanges=history,
                                 request_context=context)
        confirm = next(tool for tool in tools if tool.name == "local-confirm-patient")
        for index in range(2):
            args = {"patient_id": "P1", "instruction_quote": "90 day treatment trial",
                    "chart_quote": "90 day treatment trial"}
            ledger.pending_calls.append({"call_id": f"confirm{index}", "tool": confirm.name, "arguments": args})
            answer = await confirm.on_invoke_tool(None, json.dumps(args))
            if index == 0:
                expected = {"ambiguous": "semantic_ambiguous", "length": "confirmation_output_truncated",
                            "empty": "confirmation_empty", "invalid_json": "confirmation_format_invalid"}[first_result]
                assert json.loads(answer)["reason"] == expected
                assert guard.bound is None and ledger.error_code is None
            else:
                assert json.loads(answer)["status"] == "unique_match"
        assert guard.bound == "P1"
        assert lower.calls == ledger.rounds == guard.confirmations == 2
        assert all(entry["status"] == "settled" for entry in journal.run_doc["requests"])
        assert journal.run_doc["requests"][0]["response_metadata"]["finish_reason"] == ("length" if first_result == "length" else "stop")
        assert journal.state["pending"] is None
        with pytest.raises(pib.Refusal): guard.confirmation_input("P1", history)
        await client.close()
        journal.close()
    asyncio.run(run())


def test_batch_confirmation_cannot_race_other_tools():
    import live_development as live
    import model_runner_adapter as adapter
    guard, _ = observations()
    ledger = adapter.Ledger("synthetic")
    class Recorder:
        def record_validated_dispatches(self, _items): pass
    profile = SimpleNamespace(raw={"response_model": "synthetic"})
    schema = {"type": "object", "properties": {"patient_id": {"type": "string"}},
              "required": ["patient_id"], "additionalProperties": False}
    def call(call_id, name):
        return {"id": call_id, "type": "function", "function": {"name": name, "arguments": '{"patient_id":"P1"}'}}
    response = {"model": "synthetic", "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "reasoning_content": "test", "content": None,
        "tool_calls": [call("a", "local-confirm-patient"), call("b", "chart__list_candidate_orders")]}}]}
    with pytest.raises(live.LiveFailure, match="patient_confirmation_batch_invalid"):
        live._validate_live_response(response, ledger, profile,
            {"local-confirm-patient": schema, "chart__list_candidate_orders": schema},
            {"local-confirm-patient", "chart__list_candidate_orders"}, Recorder(),
            {"chart__list_candidate_orders": "chart.list_candidate_orders"}, binding=guard)
    assert ledger.pending_calls == []


def test_dispatch_serializes_and_refuses_cross_patient_before_backend():
    import contextvars
    import hashlib
    import live_development as live
    guard, history = observations()
    guard.confirmation_input("P1", history)
    guard.assess("P1", verdict())
    class Recorder(Journal):
        def __init__(self): super().__init__(); self.run_doc["tool_dispatches"] = []
        def start_dispatch(self, *, call_id, **_kw):
            next(x for x in self.run_doc["tool_dispatches"] if x["call_id"] == call_id)["state"] = "started"
        def finish_dispatch(self, *, call_id, result, error=False):
            next(x for x in self.run_doc["tool_dispatches"] if x["call_id"] == call_id)["state"] = "unknown" if error else "returned"
    recorder = Recorder()
    guard.journal = recorder
    class FakeUtil:
        count = 0
        @classmethod
        async def invoke_mcp_tool(cls, server, tool, context, input_json, *, meta=None):
            cls.count += 1
            return "backend called"
    official = SimpleNamespace(_install_oversize_output_patch=lambda _path: None)
    name = "cases.create_from_order"
    model_name = "cases__create_from_order"
    args = [{"patient_id": "P2"}, {"patient_id": "P1"}]
    for index, item in enumerate(args):
        digest = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        recorder.run_doc["tool_dispatches"].append({"call_id": str(index), "state": "validated", "raw_name": name,
                                                    "model_name": model_name, "arguments_sha256": digest})
    async def run():
        live._install_dispatch_recorder(official, FakeUtil, recorder, guard, asyncio.Lock(),
                                        contextvars.ContextVar("test-mcp", default=None))
        official._install_oversize_output_patch(None)
        return await asyncio.gather(*(FakeUtil.invoke_mcp_tool(None, SimpleNamespace(name=name), None, json.dumps(item))
                                      for item in args))
    results = asyncio.run(run())
    assert results[0].startswith("REFUSED:")
    assert results[1] == "backend called"
    assert FakeUtil.count == 1


@pytest.mark.parametrize("mode", ["success", "mixed_confirmation", "length_then_success", "wrong_role", "function_call", "claim_done", "exhausted_after_confirmation", "exhausted_main_only", "guidance_a", "guidance_b"])
def test_official_runner_synthetic_patient_flow(tmp_path, monkeypatch, mode):
    from argparse import Namespace
    import httpx
    from mcp.types import CallToolResult, TextContent, Tool
    import live_development as live
    from test_live_development import FakeMCP, _adopt_synthetic_history, _call, _completion

    root = tmp_path / "budget"
    root.mkdir()
    _adopt_synthetic_history(root, root)
    identity = live._execution_identity(k=True)
    profile = live.load_profile()
    live._claim_c_once(root, "flow", {"execution_identity": identity, "profile_sha256": profile.sha256}, k=True)
    instruction = tmp_path / "instruction.md"
    instruction.write_text("The patient has a 90 day treatment trial.")
    roster = {"items": [{"id": "P1", "dob": "1970-01-01", "sex": "male"},
                        {"id": "P2", "dob": "1971-05-01", "sex": "male"}], "total": 2}
    charts = {pid: {"patient": {"id": pid, "dob": dob, "sex": "male"},
                    "summaries": [duration + " treatment trial"], "orders": []}
              for pid, dob, duration in (("P1", "1970-01-01", "90 day"), ("P2", "1971-05-01", "30 day"))}
    case = {"case": {"id": "C1", "patient_id": "P1", "service_request_id": "O1"},
            "patient": {"id": "P1"}, "service_request": {"id": "O1", "patient_id": "P1"}}
    schemas = {
        "chart.search_patients": {"type": "object", "properties": {}, "additionalProperties": False},
        "chart.get_patient_chart_by_patient": {"type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"], "additionalProperties": False},
        "cases.create_from_order": {"type": "object", "properties": {"patient_id": {"type": "string"}, "site_of_service": {"type": "string", "enum": ["synthetic_a", "synthetic_b"]}}, "required": ["patient_id"], "additionalProperties": False},
        "auth.submit_authorization": {"type": "object", "properties": {"case_id": {"type": "string"}, "channel": {"type": "string"}}, "required": ["case_id", "channel"], "additionalProperties": False},
        "forms.list_required_forms": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"], "additionalProperties": False},
        "forms.save_form_response": {"type": "object", "properties": {"case_id": {"type": "string"}, "form_id": {"type": "string"}}, "required": ["case_id", "form_id"], "additionalProperties": False},
    }
    backend = []
    class MCP(FakeMCP):
        async def list_tools(self, *_args, **_kwargs):
            return [Tool(name=name, description="synthetic", inputSchema=schema) for name, schema in schemas.items()]
        async def call_tool(self, name, arguments, **_kwargs):
            backend.append((name, arguments))
            if name == "chart.search_patients": value = roster
            elif name == "chart.get_patient_chart_by_patient": value = charts[arguments["patient_id"]]
            elif name == "cases.create_from_order": value = case
            elif name == "auth.submit_authorization": value = {"case": case["case"]}
            elif name == "forms.list_required_forms": value = {"items": [{"form_id": "F1"}]}
            elif name == "forms.save_form_response": value = {"saved_responses": [{"case_id": "C1"}]}
            else: raise AssertionError(name)
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(value))])
    payload = json.dumps({"status": "unique_match", "selected_patient_id": "P1", "matches": ["P1"],
        "mismatches": ["P2"], "unknown": [],
        "evidence": [{"instruction_quote": "90 day treatment trial", "chart_quote": "90 day treatment trial"}]})
    responses = [
        _completion(calls=[_call("search", "chart__search_patients", {}),
                           _call("blocked", "cases__create_from_order", {"patient_id": "P2"})]),
        _completion(calls=[_call("chart1", "chart__get_patient_chart_by_patient", {"patient_id": "P1"}),
                           _call("chart2", "chart__get_patient_chart_by_patient", {"patient_id": "P2"})]),
        _completion(calls=[_call("confirm", "local-confirm-patient", {"patient_id": "P1", "instruction_quote": "90 day treatment trial", "chart_quote": "90 day treatment trial"})]
                    + ([_call("race", "cases__create_from_order", {"patient_id": "P1"})] if mode == "mixed_confirmation" else [])),
        _completion(text=payload),
        _completion(calls=[_call("create", "cases__create_from_order", {"patient_id": "P1"})]),
        _completion(calls=[_call("forms", "forms__list_required_forms", {"case_id": "C1"})]),
        _completion(calls=[_call("save", "forms__save_form_response", {"case_id": "C1", "form_id": "F1"})]),
        _completion(text="Completed synthetic task."),
    ]
    if mode == "length_then_success":
        truncated = _completion(text=None)
        truncated["choices"][0]["finish_reason"] = "length"
        responses[3:4] = [truncated,
            _completion(calls=[_call("confirm_again", "local-confirm-patient", {"patient_id": "P1",
                "instruction_quote": "90 day treatment trial", "chart_quote": "90 day treatment trial"})]),
            _completion(text=payload)]
    elif mode == "claim_done":
        responses[-1:] = [_completion(calls=[_call("claim", "local-claim_done", {})]),
                          _completion(text="Completed synthetic task.")]
    elif mode == "exhausted_after_confirmation":
        responses[4:] = [_completion(calls=[_call(f"sleep{index}", "local-sleep", {"seconds": 0})]) for index in range(46)]
    elif mode == "exhausted_main_only":
        responses[:] = [_completion(calls=[_call(f"sleep{index}", "local-sleep", {"seconds": 0})]) for index in range(50)]
    elif mode in {"guidance_a", "guidance_b"}:
        site = "synthetic_a" if mode == "guidance_a" else "synthetic_b"
        responses[4] = _completion(calls=[_call("create", "cases__create_from_order", {"patient_id": "P1", "site_of_service": site})])
        responses[-1:] = [_completion(calls=[_call("submit", "auth__submit_authorization", {"case_id": "C1", "channel": "synthetic_channel"})]),
                          _completion(text="Completed synthetic task.")]
    elif mode in {"wrong_role", "function_call"}:
        invalid = _completion(text=payload)
        message = invalid["choices"][0]["message"]
        if mode == "wrong_role":
            message["role"] = "user"
        else:
            message["function_call"] = {"name": "synthetic", "arguments": "{}"}
        responses[3:] = [invalid, _completion(text="No patient was confirmed.")]
    wire = []
    def reply(request):
        body = json.loads(request.content)
        wire.append(body)
        if (len(wire) == 4 and mode != "exhausted_main_only") or (mode == "length_then_success" and len(wire) == 6):
            assert body.get("tools", []) == []
        if len(wire) > 4:
            assert not any(payload in str(item.get("content")) for item in body["messages"])
        return httpx.Response(200, json=responses.pop(0), request=request)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-only")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_kw: httpx.MockTransport(reply))
    monkeypatch.setattr("agents.mcp.MCPServerStreamableHttp", lambda *_a, **_kw: MCP(backend))
    args = Namespace(kind="c-once", run_id="flow", budget_root=root, logs_dir=tmp_path / "logs",
                     instruction_file=instruction, mcp_url="http://example.invalid/mcp", k_development=True,
                     _test_context=live._MOCK_ORCHESTRATION_TEST)
    status = asyncio.run(live._worker_run(args))
    journal = json.loads((root / "runs/flow.json").read_text())
    if mode == "exhausted_main_only":
        assert status == 1 and len(wire) == 50 and not responses
        assert journal["primary_error_code"] == "provider_request_limit_reached"
        assert all(entry["status"] == "settled" for entry in journal["requests"])
        assert json.loads((root / "accounting.json").read_text())["pending"] is None
        assert not backend
        return
    assert any(event.get("event") == "refusal" and event.get("call_id") == "blocked"
               for event in journal["patient_binding_events"])
    if mode == "mixed_confirmation":
        assert status == 1
        assert len(wire) == 3
        assert all(name not in {"cases.create_from_order", "forms.save_form_response"} for name, _ in backend)
        assert not any(event.get("purpose") == "patient_confirmation" for event in journal["patient_binding_events"])
        return
    if mode in {"wrong_role", "function_call"}:
        assert status == 0 and len(wire) == 5 and not responses
        assert all(name not in {"cases.create_from_order", "forms.save_form_response"} for name, _ in backend)
        assert not any(event.get("event") == "patient_bound" for event in journal["patient_binding_events"])
        assert any(event.get("event") == "confirmation_result" and event.get("result", {}).get("reason") == "confirmation_format_invalid"
                   for event in journal["patient_binding_events"])
        assert journal["requests"][3]["status"] == "settled"
        assert json.loads((root / "accounting.json").read_text())["pending"] is None
        return
    if mode == "exhausted_after_confirmation":
        assert status == 1 and len(wire) == 50 and not responses
        assert journal["primary_error_code"] == "provider_request_limit_reached"
        assert all(entry["status"] == "settled" for entry in journal["requests"])
        assert len(journal["requests"]) == 50
        assert sum(entry.get("purpose") == "patient_confirmation" for entry in journal["requests"]) == 1
        assert json.loads((root / "accounting.json").read_text())["pending"] is None
        assert all(name not in {"cases.create_from_order", "forms.save_form_response"} for name, _ in backend)
        return
    assert status == 0, (tmp_path / "logs/run_log.txt").read_text()
    assert not responses and len(wire) == (10 if mode == "length_then_success" else 9 if mode in {"claim_done", "guidance_a", "guidance_b"} else 8)
    expected_backend = ["chart.search_patients", "chart.get_patient_chart_by_patient", "chart.get_patient_chart_by_patient",
                        "cases.create_from_order", "forms.list_required_forms", "forms.save_form_response"]
    if mode in {"guidance_a", "guidance_b"}:
        expected_backend.append("auth.submit_authorization")
    assert [name for name, _ in backend] == expected_backend
    assert all(entry["status"] == "settled" for entry in journal["requests"])
    assert len(journal["requests"]) == len(wire)
    import request_budget
    for index, body in enumerate(wire, 1):
        request_entry = journal["requests"][index - 1]
        system_text = body["messages"][0]["content"]
        if request_entry.get("purpose") == "patient_confirmation":
            assert system_text == pib.PROMPT and "request_budget_feedback" not in request_entry
        else:
            suffix, record = request_budget.feedback(index - 1, mode == "claim_done" and index == len(wire))
            assert system_text.endswith(suffix) and system_text.count("<runtime_request_budget ") == 1
            assert sum(message.get("role") == "system" for message in body["messages"]) == 1
            assert all("<runtime_request_budget " not in str(message.get("content"))
                       for message in body["messages"] if message.get("role") == "tool")
            assert request_entry["request_budget_feedback"] == record
    assert "max_turns=50" in (tmp_path / "logs/run_log.txt").read_text()
    if mode in {"guidance_a", "guidance_b"}:
        import referral_field_guidance as guidance
        recorded = journal["referral_field_guidance"]
        assert recorded["version"] == guidance.VERSION and recorded["guidance_sha256"] == guidance.GUIDANCE_SHA256
        assert set(recorded["tools"]) == set(guidance.GUIDANCE)
        for request in wire:
            if not request.get("tools"):
                assert guidance.MARKER not in json.dumps(request)
                continue
            by_name = {tool["function"]["name"]: tool["function"] for tool in request["tools"]}
            for raw_name, text in guidance.GUIDANCE.items():
                function = by_name[raw_name.replace(".", "__")]
                assert function["description"] == "synthetic\n\n" + guidance.MARKER + "\n" + text
                assert function["description"].count(guidance.MARKER) == 1
                assert function["parameters"] == schemas[raw_name]
                assert recorded["tools"][raw_name]["original_description_sha256"] == guidance.sha256("synthetic")
                assert recorded["tools"][raw_name]["appended_description_sha256"] == guidance.sha256(function["description"])
            assert by_name["chart__search_patients"]["description"] == "synthetic"
        create_args = next(args for name, args in backend if name == "cases.create_from_order")
        assert create_args["site_of_service"] == ("synthetic_a" if mode == "guidance_a" else "synthetic_b")
        assert next(args for name, args in backend if name == "auth.submit_authorization") == {"case_id": "C1", "channel": "synthetic_channel"}
    if mode == "length_then_success":
        assert journal["requests"][3]["response_metadata"]["finish_reason"] == "length"
        assert any(event.get("event") == "confirmation_result" and event.get("result", {}).get("reason") == "confirmation_output_truncated"
                   for event in journal["patient_binding_events"])
    assert any(event.get("purpose") == "patient_confirmation" and event.get("provider_round") == 4
               for event in journal["patient_binding_events"])
    assert json.loads((root / "accounting.json").read_text())["pending"] is None
