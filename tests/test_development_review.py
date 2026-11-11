"""Offline synthetic coverage for local development review."""
import fcntl
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scripts.development.review_run as dr
import scripts.development.run_development_legacy as live


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


def test_failed_new_task_review_requires_settled_provenance(capture, monkeypatch):
    import scripts.development.provider_task_resources as resources
    folder, kwargs, _ = capture
    c_root = kwargs["c_root"]
    task = next(iter(resources.TASK_FILES))
    resource = {"task_id": task, "world_id": "world-test",
                "world_sha256": dr._hash((folder / "shared_world.json").read_bytes()),
                "files": {"fixtures/expectations.json": {"sha256": dr._hash((folder / "expectations.json").read_bytes())}}}
    monkeypatch.setattr(resources, "identity", lambda value: resource if value == task else (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(live, "_validate_accounting_state", lambda *args, **kw: None)
    monkeypatch.setattr(live, "_validate_k_provenance", lambda *args: None)
    def read(path): return json.loads(path.read_text())
    def write(path, obj): path.write_bytes(dr._json_bytes(obj))
    manifest = read(folder / "manifest.json")
    manifest.update(task_id=task, task_resource_identity=resource)
    write(folder / "manifest.json", manifest)
    orch_path = c_root / "c-test/orchestration.json"
    orch = read(orch_path)
    orch.update(status="runner_failed", primary_error_code="runner_nonzero_exit", task_resource_identity=resource)
    orch["world"]["task_id"] = task
    orch["runner"] = {"exit_code": 1, "quiescent": True}
    orch["review_input"]["manifest_sha256"] = dr._hash((folder / "manifest.json").read_bytes())
    write(orch_path, orch)
    claim_path = c_root / "claims/c-test.json"
    claim = read(claim_path)
    claim.update(task_id=task, task_resource_identity=resource, terminal_status="runner_failed", primary_error_code="runner_nonzero_exit")
    write(claim_path, claim)
    run_path = c_root / "runs/c-test.json"
    run = read(run_path)
    run.update(task_id=task, task_resource_identity=resource, state="incomplete", real_usage={"input_tokens": 2, "output_tokens": 1},
               estimated_cost_cny="0.1", requests=[{"status": "settled", "usage_provenance": "provider_response_usage",
                                                    "input_tokens": 2, "output_tokens": 1, "estimated_cost_cny": "0.1"}])
    write(run_path, run)
    accounting = {"schema": live.K_ACCOUNTING_SCHEMA, "execution_identity": kwargs["identity"], "pending": None,
                  "usage_complete": True, "known_input_tokens": 2, "known_output_tokens": 1, "known_settled_cost_cny": "0.1"}
    write(c_root / "accounting.json", accounting)
    write(c_root / "controller-state.json", {"state": "clean"})
    assert dr._input(folder, **kwargs)[0]["task_id"] == task
    accounting["pending"] = {"status": "unknown"}
    write(c_root / "accounting.json", accounting)
    with pytest.raises(dr.ReviewError): dr._input(folder, **kwargs)
    accounting["pending"] = None
    write(c_root / "accounting.json", accounting)
    run["requests"][0]["status"] = "unknown"
    write(run_path, run)
    with pytest.raises(dr.ReviewError): dr._input(folder, **kwargs)


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
        plan = dr.plan()
        assert body["max_tokens"] == plan["max_output_tokens"] == 32768
        claim = json.loads((tmp_path / "reviews/review-1/claim.json").read_text())
        settings = claim["identity"]["review_settings"]
        assert settings == {"max_output_tokens": 32768, "timeout_seconds": 360, "read_timeout_seconds": 60}
        assert plan["timeout_seconds"] == settings["timeout_seconds"]
        assert plan["read_timeout_seconds"] == settings["read_timeout_seconds"]
        pending = json.loads((tmp_path / "reviews/accounting.json").read_text())["pending"]
        profile = dr.load_profile()
        expected = (Decimal(profile.input_reserve_tokens) * profile.input_price
                    + Decimal(body["max_tokens"]) * profile.output_price) / Decimal(1_000_000)
        assert Decimal(pending["reserve_upper_cost_cny"]) == expected == Decimal("2.359296")
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


def test_audit_journal_bound_is_separate_from_inline_input(capture):
    folder, kwargs, _ = capture
    journal = kwargs["c_root"] / "runs" / "c-test.json"
    run = json.loads(journal.read_text())
    run["synthetic_audit_evidence"] = "x" * (3 * 1024 * 1024)
    journal.write_bytes(dr._json_bytes(run))
    assert dr._input(folder, **kwargs)[0]["run_id"] == "c-test"
    assert dr.MAX_INPUT == 2 * 1024 * 1024
    run["execution_identity"] = {"synthetic": "wrong"}
    journal.write_bytes(dr._json_bytes(run))
    with pytest.raises(dr.ReviewError, match="input_provenance_invalid"):
        dr._input(folder, **kwargs)
    run["execution_identity"] = kwargs["identity"]
    run["synthetic_audit_evidence"] = "x" * dr.MAX_AUDIT_JOURNAL
    journal.write_bytes(dr._json_bytes(run))
    with pytest.raises(dr.ReviewError, match="input_invalid"):
        dr._input(folder, **kwargs)


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
    moments = iter([0.0, 361.0])
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


def test_read_fifo_rejected_without_blocking(tmp_path):
    import subprocess
    import sys
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    proc = subprocess.run([sys.executable, "-c", "import sys; "
                           "from scripts.development import review_run as d; "
                           "\ntry: d._read(d.Path(sys.argv[1]),100)\nexcept d.ReviewError: sys.exit(0)\nsys.exit(1)",
                           str(fifo)], timeout=3, capture_output=True)
    assert proc.returncode == 0


def test_ancestor_symlinks_rejected(capture, tmp_path, synthetic_adapter):
    folder, kwargs, _ = capture
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path, target_is_directory=True)
    linked_folder = linked / "inputs" / folder.name
    linked_kwargs = dict(kwargs, input_root=linked / "inputs")
    with pytest.raises(dr.ReviewError, match="input_location_invalid"):
        dr._input(linked_folder, **linked_kwargs)
    with pytest.raises(dr.ReviewError, match="review_root_invalid"):
        dr.review(folder, "symlink-test", review_root=linked / "reviews", _secret="synthetic-secret",
                  _transport=httpx.MockTransport(lambda req: pytest.fail("no request")), **kwargs)
    assert not (tmp_path / "reviews").exists()


def test_receipt_durable_before_aggregate_and_missing_receipt_blocks(capture, tmp_path, synthetic_adapter):
    class Crash(BaseException):
        pass
    root = tmp_path / "reviews"
    atomic = live._atomic_json
    def crash_after_settlement(path, value, **kwargs):
        atomic(path, value, **kwargs)
        if path == root / "accounting.json" and value.get("settled_requests") == 1:
            raise Crash()
    with patch.object(live, "_atomic_json", side_effect=crash_after_settlement):
        with pytest.raises(Crash):
            call(capture, tmp_path, lambda req: httpx.Response(200, json=response()))
    receipt = json.loads((root / "review-1/settlement.json").read_text())
    assert receipt["usage"]["prompt_tokens"] == 100
    assert json.loads((root / "accounting.json").read_text())["pending"] is None
    assert call(capture, tmp_path, lambda req: httpx.Response(200, json=response()), "review-2")["status"] == "complete"
    (root / "review-1/settlement.json").unlink()
    with pytest.raises(dr.ReviewError, match="accounting_invalid"):
        call(capture, tmp_path, lambda req: pytest.fail("no request"), "review-3")


def test_crash_after_receipt_preserves_pending(capture, tmp_path, synthetic_adapter):
    class Crash(BaseException):
        pass
    root = tmp_path / "reviews"
    atomic = live._atomic_json
    def crash_after_receipt(path, value, **kwargs):
        atomic(path, value, **kwargs)
        if path.name == "settlement.json":
            raise Crash()
    with patch.object(live, "_atomic_json", side_effect=crash_after_receipt):
        with pytest.raises(Crash):
            call(capture, tmp_path, lambda req: httpx.Response(200, json=response()))
    assert (root / "review-1/settlement.json").is_file()
    assert json.loads((root / "accounting.json").read_text())["pending"] is not None
    with pytest.raises(dr.ReviewError, match="accounting_pending_unknown"):
        call(capture, tmp_path, lambda req: pytest.fail("no request"), "review-2")


def test_modified_settlement_is_rejected(capture, tmp_path, synthetic_adapter):
    call(capture, tmp_path, lambda req: httpx.Response(200, json=response()))
    path = tmp_path / "reviews/review-1/settlement.json"
    receipt = json.loads(path.read_text())
    receipt["usage"]["completion_tokens"] = 21
    path.write_text(json.dumps(receipt))
    with pytest.raises(dr.ReviewError, match="accounting_invalid"):
        call(capture, tmp_path, lambda req: pytest.fail("no request"), "review-2")


def test_length_response_settles_and_new_id_continues_with_prior_receipt(capture, tmp_path, synthetic_adapter):
    payload = response()
    payload["choices"][0]["finish_reason"] = "length"
    payload["choices"][0]["message"]["content"] = ""
    result = call(capture, tmp_path, lambda req: httpx.Response(200, json=payload))
    assert result["status"] == "incomplete" and result["safe_error_code"] == "provider_response_invalid"
    root = tmp_path / "reviews"
    state = json.loads((root / "accounting.json").read_text())
    assert state["pending"] is None and state["settled_requests"] == 1
    assert (root / "review-1/settlement.json").is_file()
    # Prior receipts predate review_settings. Preserve their semantics while
    # checking that their matching identities and usage remain reconcilable.
    receipt_path = root / "review-1/settlement.json"
    claim_path = root / "review-1/claim.json"
    receipt = json.loads(receipt_path.read_text())
    claim = json.loads(claim_path.read_text())
    del receipt["identity"]["review_settings"]
    del claim["identity"]["review_settings"]
    receipt_path.write_text(json.dumps(receipt))
    claim_path.write_text(json.dumps(claim))
    result = call(capture, tmp_path, lambda req: httpx.Response(200, json=response()), "review-2")
    assert result["status"] == "complete"
    state = json.loads((root / "accounting.json").read_text())
    assert state["settled_requests"] == 2 and state["pending"] is None
