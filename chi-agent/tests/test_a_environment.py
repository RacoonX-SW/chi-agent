from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import a_environment as a  # noqa: E402


def _fixture_tree(root: Path) -> tuple[Path, Path]:
    checkout = root / "vendor" / "chi-bench"
    (checkout / ".git").mkdir(parents=True)
    for name, content in {
        "pyproject.toml": "[project]\nname='fixture'\n",
        "uv.lock": "version = 1\n",
        "README.md": "synthetic README\n",
        "LICENSE": "synthetic license\n",
    }.items():
        (checkout / name).write_text(content)
    (checkout / "src" / "chi_bench").mkdir(parents=True)
    (checkout / "src" / "chi_bench" / "__init__.py").write_text("# synthetic source\n")
    (checkout / "docker" / "shims" / "healthverse").mkdir(parents=True)
    (checkout / "docker" / "shims" / "healthverse" / "__init__.py").write_text("# synthetic shim\n")
    (checkout / "docker" / "Dockerfile").write_text("FROM python:3.12-slim\n")
    (checkout / "docker" / "entrypoint.sh").write_text("#!/bin/sh\nexec \"$@\"\n")

    data = a._dataset_dir(root)
    records = {}
    for rel in (*a.WORLD_FILES, *a.TASK_FILES):
        file = data / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"synthetic {rel}\n")
        records[rel] = {"sha256": a._sha256(file), "size": file.stat().st_size}
    a._safe_write_json(
        data / a.DATASET_MANIFEST_NAME,
        {"dataset": "synthetic", "revision": a.DATASET_REVISION,
         "allowlisted_file_count": len(records), "files": records},
    )
    handbook = root / "data" / "skills" / "managed-care-operations-handbook"
    handbook.mkdir(parents=True)
    (handbook / "SKILL.md").write_text("synthetic handbook\n")
    return checkout, data


def _probe_script(root: Path) -> Path:
    path = root / "scripts" / "a_tools_probe.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# synthetic reviewed probe\n")
    return path


def test_task_environment_is_an_explicit_credential_free_allowlist(monkeypatch) -> None:
    for name in a.MODEL_OR_JUDGE_ENV:
        monkeypatch.setenv(name, "synthetic-secret-sentinel")
    env = a._task_environment()
    assert env["CHI_BENCH_TASK_ID"] == a.TASK_ID
    assert not set(env).intersection(a.MODEL_OR_JUDGE_ENV)
    assert "CHI_BENCH_FHIR_URL" not in env


def test_daemon_mount_path_translates_and_rejects_outside_source(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "runs" / "probe.py"
    source.parent.mkdir()
    source.write_text("pass\n")
    monkeypatch.setenv("HOST_PROJECT_ROOT", "/Users/example/chi-agent")
    assert a._daemon_path(root, source) == "/Users/example/chi-agent/runs/probe.py"
    with pytest.raises(a.AEnvironmentError, match="inside the project"):
        a._daemon_path(root, tmp_path / "outside")


def test_run_directory_rejects_reuse_and_path_traversal(tmp_path: Path) -> None:
    first = a._run_dir(tmp_path, "run-1", create=True)
    with pytest.raises(FileExistsError):
        a._run_dir(tmp_path, "run-1", create=True)
    with pytest.raises(a.AEnvironmentError, match="run id"):
        a._run_dir(tmp_path, "../other")
    assert first.is_dir()


def test_build_context_uses_verified_synthetic_inputs_and_excludes_other_payloads(
    monkeypatch, tmp_path: Path
) -> None:
    checkout, _ = _fixture_tree(tmp_path)
    monkeypatch.setattr(a, "_verify_checkout", lambda root: checkout)
    monkeypatch.setattr(a, "_verify_handbook", lambda root: {"file_count": 1, "revision": "synthetic"})
    context = a.prepare_build_context(tmp_path)
    task = context / "data" / a.TASK_PATH
    assert (context / "README.md").is_file()
    assert (context / "LICENSE").is_file()
    assert (task / "fixtures" / "expectations.json").is_file()  # synthetic fixture only
    assert not (task / "solution").exists()
    assert not (task / "tests").exists()
    assert not (task / "fixtures" / "judge").exists()
    assert not any(path.name.startswith(".env") for path in context.rglob("*"))
    assert json.loads((context / ".a-environment-identities.json").read_text())["dataset"]["allowlisted_file_count"] == 7


def test_dataset_manifest_detects_changed_payload(tmp_path: Path) -> None:
    _, data = _fixture_tree(tmp_path)
    assert a._dataset_manifest(data)["revision"] == a.DATASET_REVISION
    (data / a.TASK_FILES[0]).write_text("mutated\n")
    with pytest.raises(a.AEnvironmentError, match="integrity"):
        a._dataset_manifest(data)


def test_source_tree_identity_changes_when_build_input_changes(tmp_path: Path) -> None:
    checkout, _ = _fixture_tree(tmp_path)
    before = a._source_manifest(checkout)["tree_sha256"]
    (checkout / "README.md").write_text("changed synthetic README\n")
    assert a._source_manifest(checkout)["tree_sha256"] != before


def test_checkout_rejects_dirty_or_untracked_source(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "vendor" / "chi-bench"
    checkout.mkdir(parents=True)
    (checkout / ".git").mkdir()

    def fake_run(argv, **kwargs):
        if "rev-parse" in argv:
            return SimpleNamespace(stdout=a.UPSTREAM_SHA + "\n")
        return SimpleNamespace(stdout="?? src/untracked.py\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(a.AEnvironmentError, match="modified or untracked"):
        a._verify_checkout(tmp_path)


class _Resource:
    def __init__(self, name: str, labels: dict[str, str], removals: list[str], log_path: Path | None = None):
        self.name = name
        self.id = f"id-{name}"
        self.attrs = {"Config": {"Labels": labels}, "Labels": labels}
        self.removals = removals
        self.log_path = log_path
        self.status = "running"
        self.client = SimpleNamespace(api=SimpleNamespace(timeout=30))

    def remove(self, **kwargs):
        if self.log_path is not None:
            assert self.log_path.exists(), "container logs must be persisted before removal"
        self.removals.append(self.name)

    def logs(self, **kwargs):
        return b"synthetic safe startup log"

    def reload(self):
        return None


def _not_found(_name):
    exc = RuntimeError("not found")
    exc.status_code = 404
    raise exc


def test_run_probe_collision_preserves_existing_container_network_and_evidence(tmp_path: Path) -> None:
    run_id = "previous-run"
    removals: list[str] = []
    labels = a._resource_labels(run_id)
    old_container = _Resource("previous-container", labels, removals)
    old_network = _Resource("previous-network", labels, removals)
    client = SimpleNamespace(
        images=SimpleNamespace(get=lambda _: SimpleNamespace(id="image")),
        containers=SimpleNamespace(get=lambda name: old_container if name.endswith(run_id) else _not_found(name)),
        networks=SimpleNamespace(get=lambda name: old_network if name.endswith(run_id) else _not_found(name)),
        api=SimpleNamespace(timeout=30),
        close=lambda: None,
    )
    old_dir = tmp_path / "runs" / "a-environment" / run_id
    old_dir.mkdir(parents=True)
    (old_dir / "prior-evidence.json").write_text("preserve\n")
    probe_script = _probe_script(tmp_path)
    with patch.object(a, "_docker", return_value=client):
        with pytest.raises(a.AEnvironmentError, match="preflight failed"):
            a.run_probe(tmp_path, run_id, probe_script)
    assert removals == []
    assert (old_dir / "prior-evidence.json").read_text() == "preserve\n"
    assert list((tmp_path / "runs" / "a-environment" / "failures").glob(f"{run_id}-*.json"))


def test_cleanup_preflights_foreign_network_before_removing_owned_container() -> None:
    removals: list[str] = []
    run_id = "run-7"
    container = _Resource("owned-container", a._resource_labels(run_id), removals)
    network = _Resource("foreign-network", {}, removals)
    client = SimpleNamespace(
        containers=SimpleNamespace(get=lambda _: container),
        networks=SimpleNamespace(get=lambda _: network),
        api=SimpleNamespace(timeout=30),
    )
    with pytest.raises(a.AEnvironmentError, match="unowned"):
        a.cleanup(client, run_id)
    assert removals == []


class _ReadinessContainer(_Resource):
    def __init__(self, responses):
        super().__init__("world", {}, [])
        self.responses = iter(responses)
        self.commands = []

    def exec_run(self, command, **kwargs):
        self.commands.append(command)
        return next(self.responses)


def test_wait_world_requires_exact_official_sleep_infinity_command() -> None:
    source = a._startup_probe_command()[2]
    compile(source, "<readiness-check>", "exec")
    assert "len(argv)==2" in source
    assert "pathlib.Path(os.fsdecode(argv[0])).name=='sleep'" in source
    assert "argv[1]==b'infinity'" in source
    assert "A_WORLD_READY" in source
    container = _ReadinessContainer([(1, b"A_WORLD_NOT_READY"), (0, b"A_WORLD_READY")])
    with patch.object(a.time, "sleep", return_value=None):
        assert a.wait_world(container, timeout_s=1) >= 0
    assert len(container.commands) == 2


def test_wait_world_fails_when_mcp_startup_never_reaches_sleep() -> None:
    container = _ReadinessContainer([(1, b"A_WORLD_NOT_READY")] * 10)
    with pytest.raises(a.AEnvironmentError, match="did not reach"):
        a.wait_world(container, timeout_s=0.01)


class _ExecAPI:
    def __init__(self, exit_code, chunks=(), delay=0.0):
        self.timeout = 30
        self.exit_code = exit_code
        self.chunks = chunks
        self.delay = delay

    def exec_create(self, *_args, **_kwargs):
        return {"Id": "synthetic-exec"}

    def exec_start(self, *_args, **_kwargs):
        def generate():
            for item in self.chunks:
                if self.delay:
                    time.sleep(self.delay)
                yield item
        return generate()

    def exec_inspect(self, _exec_id):
        return {"ExitCode": self.exit_code}


def test_probe_unknown_exit_code_is_recorded_as_inconclusive_and_fails(tmp_path: Path) -> None:
    container = SimpleNamespace(id="container", client=SimpleNamespace(api=_ExecAPI(None, [(b"", b"")])))
    with pytest.raises(a.AEnvironmentError, match="unknown MCP probe exit code"):
        a._run_probe_command(container, tmp_path, deadline=time.monotonic() + 1)
    status = json.loads((tmp_path / "probe-status.json").read_text())
    assert status["exit_code"] is None
    assert status["probe_summary_path"] == "/logs/artifacts/probe/summary.json"
    assert status["read_only_policy"] == "fixed_allowlisted_read_only_tool"
    assert "audit_read_record_expected" not in status
    assert "changed_world" not in status


def test_probe_boolean_exit_code_is_not_accepted_as_integer_success(tmp_path: Path) -> None:
    container = SimpleNamespace(id="container", client=SimpleNamespace(api=_ExecAPI(False, [(b"", b"")])))
    with pytest.raises(a.AEnvironmentError, match="unknown MCP probe exit code"):
        a._run_probe_command(container, tmp_path, deadline=time.monotonic() + 1)
    status = json.loads((tmp_path / "probe-status.json").read_text())
    assert status["exit_code"] is False


def test_probe_stream_timeout_is_recorded_and_never_maps_to_success(tmp_path: Path) -> None:
    api = _ExecAPI(0, [(b"late", b"")], delay=0.02)
    container = SimpleNamespace(id="container", client=SimpleNamespace(api=api))
    with pytest.raises(a.AEnvironmentError, match="definitive MCP probe result"):
        a._run_probe_command(container, tmp_path, deadline=time.monotonic() + 0.005)
    status = json.loads((tmp_path / "probe-status.json").read_text())
    assert status["exit_code"] is None
    assert status["error_type"] == "TimeoutError"


def test_run_probe_failure_persists_logs_and_cleanup_result_before_removal(tmp_path: Path) -> None:
    run_id = "synthetic-failure"
    removals: list[str] = []
    run_dir = tmp_path / "runs" / "a-environment" / run_id
    live_container = _Resource("world", a._resource_labels(run_id), removals, run_dir / "container.log")
    network = _Resource("network", a._resource_labels(run_id), removals)
    client = SimpleNamespace(
        images=SimpleNamespace(get=lambda _: SimpleNamespace(id="image-id")),
        containers=SimpleNamespace(get=lambda name: live_container if name.endswith(run_id) else _not_found(name)),
        networks=SimpleNamespace(get=lambda name: network if name.endswith(run_id) else _not_found(name)),
        api=SimpleNamespace(timeout=30),
        close=lambda: None,
    )

    def fake_start(_root, _run_id, **kwargs):
        a._safe_write_json(kwargs["run_dir"] / "run-identity.json", {"image_id": "image-id"})
        return {"image_id": "image-id"}

    with (
        patch.object(a, "_docker", return_value=client),
        patch.object(a, "_check_resource_slots", return_value=None),
        patch.object(a, "start_world", side_effect=fake_start),
        patch.object(a, "probe_world", side_effect=a.AEnvironmentError("synthetic failure")),
        patch.object(a, "_container", return_value=live_container),
    ):
        with pytest.raises(a.AEnvironmentError, match="readiness_and_probe failed"):
            a.run_probe(tmp_path, run_id, _probe_script(tmp_path))
    result = json.loads((run_dir / "stage-result.json").read_text())
    assert result["phase"] == "readiness_and_probe"
    assert result["error_type"] == "AEnvironmentError"
    assert result["cleanup"] == {"container_removed": True, "network_removed": True}
    assert (run_dir / "container.log").read_bytes() == b"synthetic safe startup log"
    assert removals == ["world", "network"]


def test_partial_start_failure_captures_logs_and_cleans_only_created_resources(
    tmp_path: Path, monkeypatch
) -> None:
    run_id = "synthetic-start-failure"
    monkeypatch.setenv("HOST_PROJECT_ROOT", "/host/chi-agent")
    removed: list[str] = []
    run_dir = tmp_path / "runs" / "a-environment" / run_id
    network = _Resource("new-network", a._resource_labels(run_id), removed)
    container = _Resource("new-container", a._resource_labels(run_id), removed, run_dir / "container.log")

    class Networks:
        def get(self, name):
            return _not_found(name)

        def create(self, *_args, **_kwargs):
            return network

    class Containers:
        def get(self, name):
            return _not_found(name)

        def create(self, *_args, **_kwargs):
            return container

    container.start = lambda: (_ for _ in ()).throw(RuntimeError("synthetic start failure"))
    client = SimpleNamespace(
        images=SimpleNamespace(get=lambda _tag: SimpleNamespace(id="synthetic-image")),
        containers=Containers(),
        networks=Networks(),
        api=SimpleNamespace(timeout=30),
        close=lambda: None,
    )
    with pytest.raises(RuntimeError, match="synthetic start failure"):
        a.start_world(tmp_path, run_id, client=client)
    assert removed == ["new-container", "new-network"]
    assert (run_dir / "container.log").read_bytes() == b"synthetic safe startup log"
    report = json.loads((run_dir / "stage-result.json").read_text())
    assert report["phase"] == "start"
    assert report["error_type"] == "RuntimeError"
    assert report["cleanup"] == {"container_removed": True, "network_removed": True}


def test_run_probe_preserves_partial_start_cleanup_diagnostics(tmp_path: Path) -> None:
    run_id = "synthetic-partial-start"
    client = SimpleNamespace(
        images=SimpleNamespace(get=lambda _: SimpleNamespace(id="image-id")),
        api=SimpleNamespace(timeout=30),
        close=lambda: None,
    )

    def failed_start(_root, _run_id, **kwargs):
        run_dir = kwargs["run_dir"]
        a._safe_write_json(
            run_dir / "stage-result.json",
            {"phase": "start", "status": "failed", "cleanup": {"container_removed": False,
             "network_removed": True}},
        )
        raise RuntimeError("synthetic startup failure")

    with (
        patch.object(a, "_docker", return_value=client),
        patch.object(a, "_check_resource_slots", return_value=None),
        patch.object(a, "start_world", side_effect=failed_start),
    ):
        with pytest.raises(a.AEnvironmentError, match="start failed"):
            a.run_probe(tmp_path, run_id, _probe_script(tmp_path))
    report = json.loads((tmp_path / "runs" / "a-environment" / run_id / "stage-result.json").read_text())
    assert report["phase"] == "start"
    assert report["partial_start_cleanup"] == {"container_removed": False, "network_removed": True}


def test_probe_requires_fixed_script_and_matching_startup_hash(tmp_path: Path) -> None:
    approved = _probe_script(tmp_path)
    other = tmp_path / "scripts" / "arbitrary.py"
    other.write_text("# not reviewed\n")
    with pytest.raises(a.AEnvironmentError, match="fixed A-stage"):
        a._approved_probe_script(tmp_path, other)

    run_id = "probe-hash-check"
    run_dir = a._run_dir(tmp_path, run_id, create=True)
    a._safe_write_json(run_dir / "run-identity.json", {"probe_sha256": "stale-hash"})
    container = SimpleNamespace(id="world", reload=lambda: None)
    client = SimpleNamespace(close=lambda: None)
    with (
        patch.object(a, "_docker", return_value=client),
        patch.object(a, "_container", return_value=container),
        patch.object(a, "wait_world", return_value=0.0),
    ):
        with pytest.raises(a.AEnvironmentError, match="changed after world startup"):
            a.probe_world(tmp_path, run_id, approved, client=client)
