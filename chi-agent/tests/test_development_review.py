"""Offline synthetic coverage for local development review."""
import fcntl
import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

import development_review as dr
import live_development as live


@pytest.fixture
def capture(tmp_path):
    root = tmp_path / "inputs"
    folder = root / "c-test"
    folder.mkdir(parents=True)
    c_root = tmp_path / "campaign"
    (c_root / "c-test").mkdir(parents=True)
    (c_root / "runs").mkdir()
    (c_root / "claims").mkdir()
    identity = {"vendor": {"commit": "4444a07fa68a4f1623f841a292a54e284fc8e7f7"}, "synthetic": True}
    exported = {"world_id": "world-test", "target_patient_id": "patient-test", "target_case_id": "case-test"}
    expectations = {"verifier_contract": "contract_v5", "target_patient_id": "patient-test",
                    "target_case_id": "case-test", "task_actor": "provider",
                    "evidence_rubric_items": [{"rubric_key": "synthetic"}]}
    world = {"world_id": "world-test", "patients": [{"id": "patient-test"}],
             "documents": [{"id": "doc-test", "patient_id": "patient-test", "content": "synthetic chart"}]}
    def write(path, obj):
        data = dr._json_bytes(obj)
        path.write_bytes(data)
        return dr._hash(data)
    manifest = {"schema": "chi-development-review-capture-v1", "status": "ready", "run_id": "c-test",
                "task_id": live.TASK_ID, "world_id": "container-test", "shared_world_id": "world-test",
                "execution_identity": identity, "official_reward": None,
                "export_sha256": write(folder / "exported_state.json", exported),
                "expectations_sha256": write(folder / "expectations.json", expectations),
                "shared_world_sha256": write(folder / "shared_world.json", world)}
    digest = write(folder / "manifest.json", manifest)
    orchestration = {"run_id": "c-test", "kind": "c-once", "status": "completed_ungraded", "official_reward": None,
                     "finished_at": "synthetic", "runner": {"exit_code": 0},
                     "cleanup_error_code": None, "persistence_error_code": None,
                     "review_input": {"status": "ready", "manifest_sha256": digest},
                     "world": {"container_id": "container-test", "task_id": live.TASK_ID,
                               "image_id": "sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50"},
                     "cleanup": {"runner_removed": True, "world_removed": True, "network_removed": True}}
    write(c_root / "c-test" / "orchestration.json", orchestration)
    write(c_root / "runs" / "c-test.json", {"schema": "chi-real-provider-run-v1", "campaign_id": live.CAMPAIGN_ID,
                                              "run_id": "c-test", "state": "complete",
                                              "execution_identity": identity, "official_reward": None})
    write(c_root / "claims" / "c-test.json", {"schema": live.CLAIM_SCHEMA, "campaign_id": live.CAMPAIGN_ID,
          "run_id": "c-test", "task_id": live.TASK_ID, "state": "runner_started_once",
          "terminal_status": "completed_ungraded", "finished_at": "synthetic", "execution_identity": identity,
          "official_reward": None})
    return folder, {"input_root": root, "c_root": c_root, "identity": identity}, world


@pytest.fixture
def synthetic_adapter(monkeypatch):
    import chi_bench.verifier.judge.pa_um_adapter as adapter
    from chi_bench.core.scenario import SharedWorldDefinition
    class SyntheticWorld:
        def __init__(self, data):
            self.data = data
        def model_dump(self, mode):
            return self.data
    monkeypatch.setattr(SharedWorldDefinition, "model_validate", lambda value: SyntheticWorld(value))
    monkeypatch.setattr(adapter, "_build_rubrics", lambda _: ({"rubric_id": "provider_pre_submission.evidence.synthetic", "prompt": "synthetic"},))
    monkeypatch.setattr(dr, "_checks", lambda *_: {"synthetic_check": True})


def verdict(passed=True, ref="source_context/chart_slice.json:1"):
    return {"rubric_verdicts": {"provider_pre_submission.evidence.synthetic": {"pass": passed, "explanation": "Synthetic evidence.", "evidence_refs": [ref]}},
            "session_metadata": {"untrusted": "ignored"}}


def response(verdict_body=None, usage=True):
    result = {"model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(verdict_body if verdict_body is not None else verdict()), "reasoning_content": "synthetic"}}]}
    if usage:
        result["usage"] = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                           "prompt_cache_hit_tokens": 30, "prompt_cache_miss_tokens": 70}
    return result


def call(capture, tmp_path, request_handler, review_id="review-1"):
    folder, kwargs, _ = capture
    return dr.review(folder, review_id, review_root=tmp_path / "reviews", _secret="synthetic-secret",
                     _transport=httpx.MockTransport(request_handler), **kwargs)


def test_single_request_inline_and_settled(capture, tmp_path, synthetic_adapter):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert "tools" not in body and "tool_choice" not in body
        assert body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "high"
        assert body["response_format"] == {"type": "json_object"}
        files = json.loads(body["messages"][1]["content"])
        assert "source_context/chart_slice.json" in files
        assert "synthetic chart" in json.dumps(files)
        assert not any(name == "shared_world.json" for name in files)
        return httpx.Response(200, json=response())
    result = call(capture, tmp_path, handler)
    assert result["status"] == "complete" and result["official_reward"] is None
    assert result["verdicts"]["provider_pre_submission.evidence.synthetic"]["pass"] is True and len(seen) == 1
    state = json.loads((tmp_path / "reviews/accounting.json").read_text())
    assert state["pending"] is None and state["input_tokens"] == 100 and state["cache_hit_tokens"] == 30
    assert state["known_estimated_cost_cny"] == "0.00036"
    for name in ("accounting.json", "review-1/claim.json", "review-1/development-review.json", "review-1/provider-response.json"):
        assert "synthetic-secret" not in (tmp_path / "reviews" / name).read_text()


def test_source_chart_missing(capture, synthetic_adapter):
    _, _, world = capture
    world["documents"] = []
    with pytest.raises(dr.ReviewError, match="source_chart_incomplete"):
        dr._build({"world_id": "world-test"}, {"verifier_contract": "contract_v5", "target_patient_id": "patient-test",
                  "evidence_rubric_items": [{"rubric_key": "synthetic"}]}, world)


def test_capture_tamper_and_location(capture, tmp_path):
    folder, kwargs, _ = capture
    (folder / "shared_world.json").write_text("{}")
    with pytest.raises(dr.ReviewError, match="input_provenance_invalid"):
        dr._input(folder, **kwargs)
    with pytest.raises(dr.ReviewError, match="input_location_invalid"):
        dr._input(tmp_path / "elsewhere", **kwargs)


@pytest.mark.parametrize("bad", [verdict("false"), verdict(False, "../secrets:1"), {"rubric_verdicts": {}},
                                  {"rubric_verdicts": {"provider_pre_submission.evidence.synthetic": {"pass": True, "explanation": "", "evidence_refs": []}}}])
def test_invalid_verdict_still_settles(capture, tmp_path, synthetic_adapter, bad):
    result = call(capture, tmp_path, lambda req: httpx.Response(200, json=response(bad)))
    assert result["status"] == "incomplete" and result["safe_error_code"] == "verdicts_invalid"
    state = json.loads((tmp_path / "reviews/accounting.json").read_text())
    assert state["pending"] is None and state["settled_requests"] == 1
    assert call(capture, tmp_path, lambda req: httpx.Response(200, json=response()), "review-2")["status"] == "complete"


def test_missing_usage_blocks_new_attempt(capture, tmp_path, synthetic_adapter):
    result = call(capture, tmp_path, lambda req: httpx.Response(200, json=response(usage=False)))
    assert result["safe_error_code"] == "usage_missing"
    assert json.loads((tmp_path / "reviews/accounting.json").read_text())["pending"]["review_id"] == "review-1"
    with pytest.raises(dr.ReviewError, match="accounting_pending_unknown"):
        call(capture, tmp_path, lambda req: pytest.fail("no request allowed"), "review-2")


def test_timeout_and_http_error_preserve_pending(capture, tmp_path, synthetic_adapter):
    def timeout(request):
        raise httpx.ReadTimeout("sensitive text", request=request)
    result = call(capture, tmp_path, timeout)
    assert result["safe_error_code"] == "provider_timeout"
    assert "sensitive text" not in json.dumps(result)
    assert json.loads((tmp_path / "reviews/accounting.json").read_text())["pending"] is not None


def test_duplicate_and_lock(capture, tmp_path, synthetic_adapter):
    call(capture, tmp_path, lambda req: httpx.Response(200, json=response()))
    with pytest.raises(dr.ReviewError, match="review_id_exists"):
        call(capture, tmp_path, lambda req: pytest.fail("no request allowed"))
    fd = os.open(tmp_path / "reviews/.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(dr.ReviewError, match="review_busy"):
            call(capture, tmp_path, lambda req: pytest.fail("no request allowed"), "review-2")
    finally:
        os.close(fd)


def test_plan_and_deterministic_are_read_only(capture, tmp_path, monkeypatch, synthetic_adapter):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    folder, kwargs, _ = capture
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    assert dr.plan()["credentials_read"] is False
    assert dr.deterministic(folder, **kwargs)["partial_checks"] == {"synthetic_check": True}
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before


def test_http_error_zero_retry_and_no_body_leak(capture, tmp_path, synthetic_adapter):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, text="private provider response")
    result = call(capture, tmp_path, handler)
    assert result["safe_error_code"] == "provider_http_error" and len(calls) == 1
    assert "private provider response" not in json.dumps(result)
    assert json.loads((tmp_path / "reviews/accounting.json").read_text())["pending"] is not None


def test_duplicate_json_verdict_and_nan_rejected_after_settlement(capture, tmp_path, synthetic_adapter):
    raw = '{"rubric_verdicts":{"provider_pre_submission.evidence.synthetic":{"pass":true,"pass":false,"explanation":"x","evidence_refs":["rubrics.json:1"]}}}'
    payload = response()
    payload["choices"][0]["message"]["content"] = raw
    result = call(capture, tmp_path, lambda req: httpx.Response(200, json=payload))
    assert result["safe_error_code"] == "verdicts_invalid"
    assert json.loads((tmp_path / "reviews/accounting.json").read_text())["pending"] is None
    with pytest.raises(dr.ReviewError, match="verdicts_invalid"):
        dr._verdicts('{"rubric_verdicts":{"provider_pre_submission.evidence.synthetic":{"pass":NaN}}}', ["provider_pre_submission.evidence.synthetic"], {})


def test_missing_accounting_does_not_reset_history(capture, tmp_path, synthetic_adapter):
    call(capture, tmp_path, lambda req: httpx.Response(200, json=response()))
    (tmp_path / "reviews/accounting.json").unlink()
    with pytest.raises(dr.ReviewError, match="accounting_missing"):
        call(capture, tmp_path, lambda req: pytest.fail("no request allowed"), "review-2")


def test_actual_world_model_and_adapter_source(monkeypatch):
    import chi_bench.verifier.judge.pa_um_adapter as adapter
    from chi_bench.core.scenario import SharedWorldDefinition
    world = {name: [] for name, field in SharedWorldDefinition.model_fields.items()
             if field.is_required() and getattr(field.annotation, "__origin__", None) is list}
    world.update({"world_id": "world-test", "seed": 1, "generated_at": "2026-01-01T00:00:00Z",
                  "now": "2026-01-01T00:00:00Z",
                  "counts": {"provider_workers": 0, "payer_workers": 0, "patients": 1,
                             "encounters": 0, "documents": 1, "historical_cases": 0, "active_cases": 0},
                  "provider_org": {"id": "p", "name": "Provider", "kind": "provider"},
                  "payer_org": {"id": "q", "name": "Payer", "kind": "payer"},
                  "patients": [{"id": "patient-test", "member_id": "m", "first_name": "Synthetic",
                                "last_name": "Patient", "dob": "2000-01-01", "sex": "unknown"}],
                  "documents": [{"id": "doc-test", "patient_id": "patient-test", "kind": "chart_note",
                                 "title": "Synthetic", "content": "synthetic chart content",
                                 "created_at": "2026-01-01T00:00:00Z"}]})
    SharedWorldDefinition.model_validate(world)
    monkeypatch.setattr(adapter, "_build_rubrics", lambda _: ({"rubric_id": "provider_pre_submission.evidence.synthetic", "prompt": "synthetic"},))
    files, ids, _, _ = dr._build({"world_id": "world-test", "target_case_id": "case-test"},
                                 {"verifier_contract": "contract_v5", "target_patient_id": "patient-test",
                                  "evidence_rubric_items": [{"rubric_key": "synthetic"}]}, world)
    assert ids == ["provider_pre_submission.evidence.synthetic"]
    assert "synthetic chart content" in "".join(files.values())
    assert "source_context/evidence_index.json" in files


def test_overall_deadline_and_bounded_socket_read(capture, tmp_path, synthetic_adapter, monkeypatch):
    moments = iter([0.0, 181.0])
    monkeypatch.setattr(dr, "_now", lambda: next(moments))
    calls = []
    def handler(request):
        calls.append(request)
        assert request.extensions["timeout"]["read"] == 60
        return httpx.Response(200, json=response())
    result = call(capture, tmp_path, handler)
    assert result["safe_error_code"] == "provider_timeout" and len(calls) == 1
    assert json.loads((tmp_path / "reviews/accounting.json").read_text())["pending"] is not None


def test_response_echoing_secret_is_not_saved_but_usage_settles(capture, tmp_path, synthetic_adapter):
    payload = response()
    payload["choices"][0]["message"]["reasoning_content"] = "echo synthetic-secret"
    result = call(capture, tmp_path, lambda req: httpx.Response(200, json=payload))
    assert result["safe_error_code"] == "provider_response_secret"
    state = json.loads((tmp_path / "reviews/accounting.json").read_text())
    assert state["pending"] is None and state["settled_requests"] == 1
    assert not (tmp_path / "reviews/review-1/provider-response.json").exists()
    for item in (tmp_path / "reviews").rglob("*.json"):
        assert "synthetic-secret" not in item.read_text()
