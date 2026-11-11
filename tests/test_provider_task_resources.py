import contextlib
import hashlib
import json

import pytest

import a_environment
import live_development as live
import provider_task_resources as resources


def test_frozen_resource_verification_and_tampering(tmp_path, monkeypatch):
    revision, world_id = "synthetic-revision", "synthetic-world"
    world_sha = "a" * 64
    task_ids = ("synthetic-provider-one", "synthetic-provider-two")
    monkeypatch.setattr(resources, "REVISION", revision)
    monkeypatch.setattr(resources, "WORLD_ID", world_id)
    monkeypatch.setattr(resources, "WORLD_SHA256", world_sha)
    task_files = {}
    manifest_files = {}
    target = tmp_path / "data/provider-baseline" / revision
    target.mkdir(parents=True)
    for task_id in task_ids:
        contents = {
            "instruction.md": b"Synthetic instruction\n",
            "tool_reference.md": b"Synthetic reference\n",
            "task.toml": b'task = "synthetic"\n',
            "fixtures/manifest.json": json.dumps({"task_id": task_id, "world_id": world_id,
                                                   "task_actor": "provider", "payer_mode": "agent"}).encode(),
            "fixtures/expectations.json": json.dumps({"verifier_contract": "contract_v5",
                                                       "task_actor": "provider"}).encode(),
        }
        task_files[task_id] = {}
        for name, payload in contents.items():
            relative = f"prior_auth_provider/tasks/{task_id}/{name}"
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            task_files[task_id][name] = (len(payload), digest)
            manifest_files[relative] = {"size": len(payload), "sha256": digest}
    monkeypatch.setattr(resources, "TASK_FILES", task_files)
    (target / "resource-manifest.json").write_text(json.dumps({
        "schema": "chi-provider-baseline-resources-v1", "dataset": "actava/chi-bench",
        "revision": revision, "tasks": list(task_ids), "files": manifest_files,
    }))
    for task_id in task_ids:
        path, identity = resources.verify(tmp_path, task_id)
        assert identity["task_id"] == task_id
        assert identity["world_sha256"] == world_sha
        (path / "instruction.md").write_text("tampered")
        with pytest.raises(ValueError):
            resources.verify(tmp_path, task_id)
    with pytest.raises(ValueError):
        resources.verify(tmp_path, "../../unknown")


def test_explicit_cli_and_cross_task_claim(tmp_path):
    ids = list(resources.TASK_FILES)
    with pytest.raises(SystemExit):
        live._parser().parse_args(["c-run", "--run-id", "one"])
    with pytest.raises(SystemExit):
        live._parser().parse_args(["c-run", "--run-id", "one", "--task-id", live.TASK_ID])
    args = live._parser().parse_args(["c-run", "--run-id", "one", "--task-id", ids[0]])
    assert args.task_id == ids[0]
    b = {"execution_identity": {"source": "test"}, "profile_sha256": "digest"}
    live._claim_c_once(tmp_path, "one", b, k=True, task_id=ids[0], resource_identity=resources.identity(ids[0]))
    with pytest.raises(live.LiveFailure):
        live._transition_c_claim(tmp_path, "one", "runner_started_once", execution_identity=b["execution_identity"],
                                 profile_sha256="digest", k=True, task_id=ids[1])
    live._transition_c_claim(tmp_path, "one", "runner_started_once", execution_identity=b["execution_identity"],
                             profile_sha256="digest", k=True, task_id=ids[0])


def test_quiescence_requires_confirmed_exit(monkeypatch):
    monkeypatch.setattr(a_environment, "_api_timeout", lambda *args: contextlib.nullcontext())
    class Runner:
        attrs = {"State": {"Status": "exited", "ExitCode": 137}}
        stopped = False
        def stop(self, timeout): self.stopped = True
        def reload(self): pass
    runner = Runner()
    record = {}
    assert live._runner_quiescent(runner, object(), record)
    assert runner.stopped and record["exit_code"] == 137
    runner.attrs = {"State": {"Status": "running", "ExitCode": 0}}
    assert not live._runner_quiescent(runner, object(), {})
