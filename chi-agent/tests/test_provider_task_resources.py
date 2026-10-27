import contextlib
import json
import shutil
from pathlib import Path

import pytest

import a_environment
import live_development as live
import provider_task_resources as resources


def test_frozen_resource_verification_and_tampering(tmp_path):
    source = live.ROOT / "data/provider-baseline" / resources.REVISION
    target = tmp_path / "data/provider-baseline" / resources.REVISION
    target.mkdir(parents=True)
    shutil.copyfile(source / "resource-manifest.json", target / "resource-manifest.json")
    for task_id in resources.TASK_FILES:
        relative = Path("prior_auth_provider/tasks") / task_id
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source / relative, target / relative)
        path, identity = resources.verify(tmp_path, task_id)
        assert identity["task_id"] == task_id
        assert identity["world_sha256"] == resources.WORLD_SHA256
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
