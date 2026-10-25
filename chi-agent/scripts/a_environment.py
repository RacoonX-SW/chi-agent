"""Prepare and run the fixed CHI-Bench A-stage tool environment.

All Docker and Hugging Face operations are intended to run inside the A
controller container. The official task container receives no model, judge,
FHIR, or Hugging Face credentials and has no external network route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from contextlib import contextmanager

UPSTREAM_SHA = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
DATASET_REVISION = "5ce88104df2a91e057619eb70fb51f56fc5949eb"
TASK_ID = "pa_t018_t018_o001_p01_new_referral_provider"
IMAGE_TAG_PREFIX = "chi-agent-a-world"
RESOURCE_LABEL = "org.chi-agent.a-environment"
PROBE_CONTAINER_PATH = "/tmp/a_tools_probe.py"
API_TIMEOUT_SEC = 30
RUN_TIMEOUT_SEC = 900
STARTUP_TIMEOUT_SEC = 180
PROBE_TIMEOUT_SEC = 45
CLEANUP_TIMEOUT_SEC = 30
DATASET_MANIFEST_NAME = ".a-environment-data-manifest.json"
TASK_PATH = f"prior_auth_provider/tasks/{TASK_ID}"
WORLD_FILES = (
    "prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json",
    "prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json",
)
TASK_FILES = (
    f"{TASK_PATH}/instruction.md",
    f"{TASK_PATH}/task.toml",
    f"{TASK_PATH}/tool_reference.md",
    f"{TASK_PATH}/fixtures/manifest.json",
    f"{TASK_PATH}/fixtures/expectations.json",
)
MODEL_OR_JUDGE_ENV = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
    "HF_TOKEN",
    "CHI_BENCH_FHIR_URL",
)


class AEnvironmentError(RuntimeError):
    pass


def _docker():
    try:
        import docker
    except ImportError as exc:  # pragma: no cover - exercised in controller image
        raise AEnvironmentError("Docker SDK is missing in the A controller image") from exc
    client = docker.from_env(timeout=API_TIMEOUT_SEC)
    client.api.timeout = API_TIMEOUT_SEC
    return client


def _root() -> Path:
    value = os.environ.get("A_PROJECT_ROOT")
    root = Path(value) if value else Path(__file__).resolve().parents[1]
    if not root.is_absolute() or not root.is_dir():
        raise AEnvironmentError("A_PROJECT_ROOT must be an existing absolute controller path")
    return root


def _daemon_path(root: Path, local_path: Path) -> str:
    """Translate a controller-container path to the Docker host's bind path."""
    host_root = os.environ.get("HOST_PROJECT_ROOT")
    if not host_root or not Path(host_root).is_absolute():
        raise AEnvironmentError("HOST_PROJECT_ROOT must map to an absolute host path")
    try:
        relative = local_path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise AEnvironmentError("bind mount source must be inside the project directory") from exc
    return str(Path(host_root) / relative)


def _approved_probe_script(root: Path, probe_script: Path) -> Path:
    """Accept only the fixed, reviewed A-stage read-only probe entrypoint."""
    expected = (root / "scripts" / "a_tools_probe.py").resolve()
    supplied = Path(probe_script).resolve()
    if supplied != expected or not supplied.is_file():
        raise AEnvironmentError("probe script must be the fixed A-stage read-only entrypoint")
    return supplied


def _run_dir(root: Path, run_id: str, *, create: bool = False) -> Path:
    _validate_run_id(run_id)
    path = root / "runs" / "a-environment" / run_id
    if create:
        path.mkdir(parents=True, exist_ok=False)
    elif not path.is_dir():
        raise AEnvironmentError("run directory is missing; start this run before probing")
    return path


def _validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}", run_id):
        raise AEnvironmentError("run id must contain only letters, digits, '_' or '-' (max 48 chars)")


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_paths(checkout: Path) -> list[Path]:
    paths = [checkout / name for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE")]
    for directory in ("src", "docker"):
        paths.extend(
            path for path in (checkout / directory).rglob("*")
            if path.is_file() and not path.is_symlink()
        )
    return sorted(paths, key=lambda item: item.relative_to(checkout).as_posix())


def _source_manifest(checkout: Path) -> dict[str, Any]:
    files = _source_paths(checkout)
    if any(not path.is_file() for path in files):
        raise AEnvironmentError("official build source is incomplete")
    records = {
        path.relative_to(checkout).as_posix(): {"sha256": _sha256(path), "size": path.stat().st_size}
        for path in files
    }
    blob = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"upstream_sha": UPSTREAM_SHA, "files": records, "tree_sha256": hashlib.sha256(blob).hexdigest()}


def _dataset_dir(root: Path) -> Path:
    return root / "data" / "a-environment" / f"download-{DATASET_REVISION}"


def _dataset_manifest(source: Path) -> dict[str, Any]:
    manifest_path = source / DATASET_MANIFEST_NAME
    if not manifest_path.is_file():
        raise AEnvironmentError("pinned task data has no integrity manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise AEnvironmentError("pinned task data integrity manifest is unreadable") from None
    if manifest.get("revision") != DATASET_REVISION:
        raise AEnvironmentError("task data revision does not match the A-stage pin")
    records = manifest.get("files")
    expected_paths = set(WORLD_FILES + TASK_FILES)
    if not isinstance(records, dict) or set(records) != expected_paths:
        raise AEnvironmentError("task data file inventory does not match the allowlist")
    for relative, expected in records.items():
        path = source / relative
        if not path.is_file() or path.stat().st_size != expected.get("size") or _sha256(path) != expected.get("sha256"):
            raise AEnvironmentError("pinned task data failed its recorded integrity check")
    return manifest


def _verify_checkout(root: Path) -> Path:
    checkout = root / "vendor" / "chi-bench"
    head_path = checkout / ".git"
    if not head_path.exists():
        raise AEnvironmentError("fixed official checkout is missing from vendor/chi-bench")
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.stdout.strip() != UPSTREAM_SHA:
        raise AEnvironmentError("official checkout SHA does not match the A-stage pin")
    status = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
        timeout=API_TIMEOUT_SEC,
    )
    if status.stdout.strip():
        raise AEnvironmentError("official checkout has modified or untracked files")
    for required in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "src", "docker"):
        if not (checkout / required).exists():
            raise AEnvironmentError("official checkout is missing a build input")
    return checkout


def download_data(root: Path, *, use_local_hf_auth: bool = False) -> Path:
    """Download only the selected task's runtime payload at the pinned revision."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - exercised in controller image
        raise AEnvironmentError("huggingface_hub is missing in the A controller image") from exc

    destination = _dataset_dir(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        # Reuse only a directory created by this exact fixed-data workflow.
        _dataset_manifest(destination)
        return destination
    auth_home = "/hf-auth" if use_local_hf_auth else None
    if auth_home:
        os.environ["HF_HOME"] = auth_home
    try:
        snapshot_download(
            repo_id="actava/chi-bench",
            repo_type="dataset",
            revision=DATASET_REVISION,
            local_dir=str(destination),
            allow_patterns=[*WORLD_FILES, *TASK_FILES],
            max_workers=4,
        )
    except Exception as exc:
        # Do not echo exception strings: hub errors can include request URLs.
        raise AEnvironmentError(
            "pinned task data download failed; retry anonymously or use --use-local-hf-auth"
        ) from exc

    if any(not (destination / item).is_file() for item in (*WORLD_FILES, *TASK_FILES)):
        raise AEnvironmentError("pinned task data is incomplete; check the A-stage download logs")
    records = {
        relative: {"sha256": _sha256(destination / relative), "size": (destination / relative).stat().st_size}
        for relative in (*WORLD_FILES, *TASK_FILES)
    }
    _safe_write_json(
        destination / DATASET_MANIFEST_NAME,
        {
            "dataset": "actava/chi-bench",
            "revision": DATASET_REVISION,
            "full_dataset_download": False,
            "task_id": TASK_ID,
            "allowlisted_file_count": len(records),
            "files": records,
        },
    )
    return destination


def _verify_handbook(root: Path) -> dict[str, Any]:
    identity_path = root / "data" / "source-downloads.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        record = next(
            item for item in identity["sources"]
            if item.get("repo") == "actava/managed-care-operations-handbook"
        )
    except (OSError, KeyError, StopIteration, json.JSONDecodeError):
        raise AEnvironmentError("approved handbook identity record is unavailable") from None
    if record.get("commit") != "f1210b294904792541116852f6074df8b84d89dd":
        raise AEnvironmentError("handbook revision does not match the approved local copy")
    files = record.get("files")
    if not isinstance(files, list) or len(files) != 1292:
        raise AEnvironmentError("approved handbook inventory does not match its verified manifest")
    base = root / "data" / "skills"
    total = 0
    for item in files:
        relative = item.get("path")
        expected_sha = item.get("sha256")
        expected_size = item.get("bytes")
        if not isinstance(relative, str) or not isinstance(expected_sha, str):
            raise AEnvironmentError("approved handbook manifest has an invalid file record")
        path = base / relative
        if not path.is_file() or path.stat().st_size != expected_size or _sha256(path) != expected_sha:
            raise AEnvironmentError("approved handbook failed its recorded integrity check")
        total += expected_size
    if total != record.get("verified_bytes"):
        raise AEnvironmentError("approved handbook byte count differs from its verified manifest")
    return {
        "dataset": record["repo"],
        "revision": record["commit"],
        "file_count": len(files),
        "bytes": total,
    }


def prepare_build_context(root: Path) -> Path:
    """Create the minimal official Docker build context for this one task."""
    checkout = _verify_checkout(root)
    source = _dataset_dir(root)
    skill = root / "data" / "skills" / "managed-care-operations-handbook"
    data_identity = _dataset_manifest(source)
    handbook_identity = _verify_handbook(root)
    source_identity = _source_manifest(checkout)

    context = root / "data" / "a-environment" / "build-context"
    if context.exists():
        owner_marker = context / ".a-environment-build-context"
        if not owner_marker.is_file() or owner_marker.read_text(encoding="ascii").strip() != source_identity["tree_sha256"]:
            raise AEnvironmentError("refusing to replace a build-context directory not created by this script")
        shutil.rmtree(context)
    context.mkdir(parents=True)
    (context / ".a-environment-build-context").write_text(source_identity["tree_sha256"] + "\n", encoding="ascii")
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE"):
        shutil.copy2(checkout / name, context / name)
    shutil.copytree(checkout / "src", context / "src")
    shutil.copytree(checkout / "docker", context / "docker")

    data = context / "data"
    for domain in (
        "prior_auth_provider/shared/worlds",
        "prior_auth_provider/tasks",
        "prior_auth_um/tasks",
        "care_management/shared/worlds",
        "care_management/tasks",
        "prior_auth_e2e/worlds",
        "prior_auth_e2e/tasks",
        "marathon",
    ):
        directory = data / domain
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".a-stage-placeholder").write_text("not part of this task build\n", encoding="ascii")
    for rel in WORLD_FILES:
        shutil.copy2(source / rel, data / rel)
    selected_task = data / TASK_PATH
    selected_task.mkdir(parents=True)
    for rel in TASK_FILES:
        destination = data / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, destination)
    shutil.copytree(skill, data / "skills" / "managed-care-operations-handbook")
    # The fixed official Dockerfile's shared CM tool-reference COPY is
    # unconditional. The selected PA task replaces this default at startup;
    # using its public reference here keeps the minimal build context complete.
    cm_default = data / "care_management" / "shared" / "tool_reference.md"
    shutil.copy2(source / f"{TASK_PATH}/tool_reference.md", cm_default)

    # Refuse accidental credentials or project env files in the build context.
    forbidden_names = {".env", ".env.local", ".env.production"}
    if any(path.name in forbidden_names for path in context.rglob("*")):
        raise AEnvironmentError("build context unexpectedly contains an environment file")
    copied_identity = _source_manifest(context)
    if copied_identity["tree_sha256"] != source_identity["tree_sha256"]:
        raise AEnvironmentError("official source changed while preparing the build context")
    _safe_write_json(
        context / ".a-environment-identities.json",
        {"upstream": source_identity, "dataset": data_identity, "handbook": handbook_identity},
    )
    return context


def _dockerfile(context: Path) -> None:
    dockerfile = context / "docker" / "Dockerfile"
    if not dockerfile.is_file():
        raise AEnvironmentError("official Dockerfile is missing from build context")


def build_image(root: Path, run_id: str) -> tuple[str, str]:
    _validate_run_id(run_id)
    context = prepare_build_context(root)
    _dockerfile(context)
    client = _docker()
    try:
        return _build_image(root, run_id, client=client, deadline=time.monotonic() + RUN_TIMEOUT_SEC, context=context)
    finally:
        client.close()


def _build_image(root: Path, run_id: str, *, client, deadline: float, context: Path | None = None) -> tuple[str, str]:
    context = context or prepare_build_context(root)
    _dockerfile(context)
    tag = f"{IMAGE_TAG_PREFIX}:{run_id}"
    try:
        with _api_timeout(client, deadline):
            client.images.get(tag)
    except Exception as exc:
        if getattr(exc, "status_code", None) != 404:
            raise
    else:
        raise AEnvironmentError("refusing to replace an image tag from an existing A-stage run")
    with _api_timeout(client, deadline):
        image, stream = client.images.build(path=str(context), dockerfile="docker/Dockerfile", tag=tag, rm=True)
    # Consume bounded Engine progress without forwarding command output.
    progress = iter(stream)
    while True:
        try:
            with _api_timeout(client, deadline):
                next(progress)
        except StopIteration:
            break
    if not image.attrs.get("Id"):
        with _api_timeout(client, deadline):
            image.reload()
    if not image.attrs.get("Id"):
        raise AEnvironmentError("Docker build completed without an image identity")
    return tag, image.attrs["Id"]


def _resource_labels(run_id: str) -> dict[str, str]:
    return {RESOURCE_LABEL: "1", f"{RESOURCE_LABEL}.run-id": run_id}


def _task_environment() -> dict[str, str]:
    """Explicit environment allowlist for official task startup."""
    environment = {
        "CHI_BENCH_TASK_ID": TASK_ID,
        "CHI_BENCH_TASKS_ROOT": "/opt/chi-bench/tasks",
        "CHI_BENCH_RUNTIME_DIR": "/tmp/chi-bench-runtime",
        "CHI_BENCH_WORLDS_DIR": "/opt/chi-bench/worlds",
        "CHI_BENCH_WORKSPACE_ROOT": "/logs/artifacts/workspaces",
        "CHI_BENCH_RAW_ROOT": "/srv/chi-bench/raw",
        "CHI_BENCH_PAYER_MODE": "agent",
        "IS_SANDBOX": "1",
    }
    if set(environment).intersection(MODEL_OR_JUDGE_ENV):
        raise AEnvironmentError("task environment allowlist includes a credential or external backend")
    return environment


def _get_owned(client, resource_type: str, name: str, run_id: str):
    try:
        resource = getattr(client, resource_type).get(name)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise
    labels = resource.attrs.get("Config", {}).get("Labels", {}) if resource_type == "containers" else resource.attrs.get("Labels", {})
    if labels.get(RESOURCE_LABEL) != "1" or labels.get(f"{RESOURCE_LABEL}.run-id") != run_id:
        raise AEnvironmentError(f"refusing to operate on unowned Docker resource {name}")
    return resource


@contextmanager
def _api_timeout(client, deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("A-stage overall deadline expired")
    api = client.api
    previous = getattr(api, "timeout", API_TIMEOUT_SEC)
    api.timeout = min(API_TIMEOUT_SEC, remaining)
    try:
        yield
    finally:
        api.timeout = previous


def _check_resource_slots(client, run_id: str, *, deadline: float | None = None) -> None:
    _validate_run_id(run_id)
    until = deadline or (time.monotonic() + API_TIMEOUT_SEC)
    with _api_timeout(client, until):
        container = _get_owned(client, "containers", f"chi-agent-a-world-{run_id}", run_id)
    if container:
        raise AEnvironmentError("an A-stage task container already exists for this run id")
    with _api_timeout(client, until):
        network = _get_owned(client, "networks", f"chi-agent-a-net-{run_id}", run_id)
    if network:
        raise AEnvironmentError("an A-stage network already exists for this run id")


def _container(client, run_id: str, *, deadline: float | None = None):
    name = f"chi-agent-a-world-{run_id}"
    with _api_timeout(client, deadline or (time.monotonic() + API_TIMEOUT_SEC)):
        container = _get_owned(client, "containers", name, run_id)
    if not container:
        raise AEnvironmentError("A-stage task container is not running")
    return container


def _capture_logs(container, run_dir: Path, client, deadline: float | None = None) -> bool:
    try:
        until = deadline or (time.monotonic() + API_TIMEOUT_SEC)
        with _api_timeout(client, until):
            output = container.logs(stdout=True, stderr=True, timestamps=True)
        (run_dir / "container.log").write_bytes(output or b"")
        return True
    except Exception as exc:
        _safe_write_json(run_dir / "container-log-error.json", {"error_type": type(exc).__name__})
        return False


def _persist_report(root: Path, run_id: str, report: dict[str, Any], run_dir: Path | None) -> Path:
    if run_dir is not None and run_dir.is_dir():
        target = run_dir / "stage-result.json"
    else:
        failures = root / "runs" / "a-environment" / "failures"
        failures.mkdir(parents=True, exist_ok=True)
        target = failures / f"{run_id}-{uuid.uuid4().hex[:12]}.json"
    _safe_write_json(target, report)
    return target


def _startup_probe_command() -> list[str]:
    # The official entrypoint finishes only after all MCP initialize probes,
    # then execs its default `sleep infinity`. Match the full argv exactly.
    check = (
        "import os,pathlib,sys\n"
        "ready=False\n"
        "for p in pathlib.Path('/proc').iterdir():\n"
        " try:\n"
        "  if not p.name.isdigit(): continue\n"
        "  raw=(p/'cmdline').read_bytes().split(b'\\0'); argv=[x for x in raw if x]\n"
        "  if len(argv)==2 and pathlib.Path(os.fsdecode(argv[0])).name=='sleep' and argv[1]==b'infinity': ready=True; break\n"
        " except (OSError,PermissionError): pass\n"
        "print('A_WORLD_READY' if ready else 'A_WORLD_NOT_READY')\n"
        "sys.exit(0 if ready else 1)\n"
    )
    return ["python", "-c", check]


def wait_world(container, timeout_s: int = STARTUP_TIMEOUT_SEC, *, deadline: float | None = None) -> float:
    client = container.client
    started = time.monotonic()
    end = min(started + timeout_s, deadline or started + timeout_s)
    while time.monotonic() < end:
        try:
            with _api_timeout(client, end):
                container.reload()
                if container.status != "running":
                    raise AEnvironmentError("official entrypoint exited before MCP startup completed")
                code, output = container.exec_run(_startup_probe_command(), demux=False)
        except TimeoutError:
            if time.monotonic() >= end:
                break
            continue
        if code == 0 and b"A_WORLD_READY" in (output or b""):
            return time.monotonic() - started
        time.sleep(min(1.0, max(0.0, end - time.monotonic())))
    raise AEnvironmentError("official entrypoint did not reach its default sleep command before timeout")


def _verify_mount_identity(container, identity: dict[str, Any], probe_script: Path | None, *, deadline: float) -> None:
    client = container.client
    checks = [("/logs/artifacts/mount-check.txt", identity["mount_check_sha256"])]
    if probe_script:
        checks.append((PROBE_CONTAINER_PATH, identity["probe_sha256"]))
    code_template = (
        "import hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
        "sys.exit(0 if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2] else 1)"
    )
    for path, expected in checks:
        with _api_timeout(client, deadline):
            code, _ = container.exec_run(["python", "-c", code_template, path, expected], demux=True)
        if code != 0:
            raise AEnvironmentError("Docker host/controller bind mount identity check failed")


def _runtime_identity(client, container, image, network, root: Path, run_dir: Path,
                      identity: dict[str, Any], *, deadline: float) -> dict[str, Any]:
    with _api_timeout(client, deadline):
        container.reload()
        image.reload()
        network.reload()
        version_code, version_output = container.exec_run(["python", "--version"], demux=True)
    stdout, stderr = version_output if isinstance(version_output, tuple) else (version_output, b"")
    python_version = ((stdout or b"") + (stderr or b"")).decode("ascii", errors="replace").strip()
    if version_code != 0 or not re.fullmatch(r"Python 3\.12(?:\.\d+)?", python_version):
        raise AEnvironmentError("task container is not running the official Python 3.12 target")
    env_pairs = [item.split("=", 1) for item in container.attrs.get("Config", {}).get("Env", [])]
    env_names = {pair[0] for pair in env_pairs if pair}
    if env_names.intersection(MODEL_OR_JUDGE_ENV):
        raise AEnvironmentError("task container inherited a model, judge, HF, or FHIR credential")
    if not network.attrs.get("Internal", False):
        raise AEnvironmentError("task network is not Docker-internal")
    attached_networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
    if set(attached_networks) != {identity["network"]}:
        raise AEnvironmentError("task container is attached to an unexpected Docker network")
    port_bindings = container.attrs.get("HostConfig", {}).get("PortBindings") or {}
    if any(bindings for bindings in port_bindings.values()):
        raise AEnvironmentError("task container unexpectedly publishes a host port")
    mounts = {item.get("Destination"): item for item in container.attrs.get("Mounts", [])}
    expected_mounts = {"/logs/artifacts"}
    if identity.get("probe_sha256"):
        expected_mounts.add(PROBE_CONTAINER_PATH)
    if set(mounts) != expected_mounts or not mounts["/logs/artifacts"].get("RW", False):
        raise AEnvironmentError("task container has an unexpected mount layout")
    if PROBE_CONTAINER_PATH in mounts and mounts[PROBE_CONTAINER_PATH].get("RW", True):
        raise AEnvironmentError("MCP probe script mount is not read-only")
    details = {
        **identity,
        "task_python": python_version,
        "image_id": image.attrs.get("Id"),
        "image_os": image.attrs.get("Os"),
        "image_architecture": image.attrs.get("Architecture"),
        "image_repo_digests": image.attrs.get("RepoDigests") or [],
        "network_internal": bool(network.attrs.get("Internal")),
        "published_ports": "none",
        "container_environment_keys": sorted(env_names),
        "mount_destinations": sorted(mounts),
        "mount_check_sha256": identity["mount_check_sha256"],
        "probe_sha256": identity.get("probe_sha256"),
    }
    _safe_write_json(run_dir / "run-identity.json", details)
    return details


def start_world(root: Path, run_id: str, *, probe_script: Path | None = None, client=None,
                run_dir: Path | None = None, deadline: float | None = None) -> dict[str, Any]:
    """Start the official default sleep command; no runner or judge is launched."""
    own_client = client is None
    _validate_run_id(run_id)
    if probe_script is not None:
        probe_script = _approved_probe_script(root, probe_script)
    client = client or _docker()
    deadline = deadline or (time.monotonic() + RUN_TIMEOUT_SEC)
    tag = f"{IMAGE_TAG_PREFIX}:{run_id}"
    container_name = f"chi-agent-a-world-{run_id}"
    network_name = f"chi-agent-a-net-{run_id}"
    labels = _resource_labels(run_id)
    network = container = None
    try:
        _check_resource_slots(client, run_id, deadline=deadline)
        with _api_timeout(client, deadline):
            image = client.images.get(tag)
        if run_dir is None:
            run_dir = _run_dir(root, run_id, create=True)
        elif run_dir != root / "runs" / "a-environment" / run_id or not run_dir.is_dir():
            raise AEnvironmentError("run directory identity is invalid")
        marker = uuid.uuid4().hex
        (run_dir / "mount-check.txt").write_text(marker, encoding="ascii")
        volumes: dict[str, dict[str, str]] = {
            _daemon_path(root, run_dir): {"bind": "/logs/artifacts", "mode": "rw"},
        }
        if probe_script:
            if not probe_script.is_file():
                raise AEnvironmentError("the approved A-stage MCP probe script is missing")
            volumes[_daemon_path(root, probe_script)] = {"bind": PROBE_CONTAINER_PATH, "mode": "ro"}
        with _api_timeout(client, deadline):
            network = client.networks.create(network_name, driver="bridge", internal=True, labels=labels)
            container = client.containers.create(
                image=image.id,
                name=container_name,
                command=["sleep", "infinity"],
                environment=_task_environment(),
                labels=labels,
                volumes=volumes,
                network=network_name,
                detach=True,
                stdin_open=False,
                tty=False,
            )
            container.start()
        identity = {
            "run_id": run_id,
            "image": tag,
            "image_id": image.id,
            "container": container_name,
            "container_id": container.id,
            "network": network_name,
            "network_id": network.id,
            "task_id": TASK_ID,
            "mount_check_sha256": hashlib.sha256(marker.encode("ascii")).hexdigest(),
            "probe_sha256": _sha256(probe_script) if probe_script else None,
            "task_environment_keys": sorted(_task_environment()),
            "agent_started": False,
            "runner_started": False,
            "judge_started": False,
            "model_calls": 0,
        }
        _safe_write_json(run_dir / "run-identity.json", identity)
        return identity
    except Exception as exc:
        if run_dir is not None and run_dir.is_dir():
            if container is not None:
                _capture_logs(container, run_dir, client)
            partial = {"phase": "start", "status": "failed", "error_type": type(exc).__name__}
            removed = {"container_removed": False, "network_removed": False}
            cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT_SEC
            if container is not None:
                try:
                    with _api_timeout(client, cleanup_deadline):
                        container.remove(force=True)
                    removed["container_removed"] = True
                except Exception as cleanup_exc:
                    partial["container_cleanup_error_type"] = type(cleanup_exc).__name__
            if network is not None:
                try:
                    with _api_timeout(client, cleanup_deadline):
                        network.remove()
                    removed["network_removed"] = True
                except Exception as cleanup_exc:
                    partial["network_cleanup_error_type"] = type(cleanup_exc).__name__
            partial["cleanup"] = removed
            _persist_report(root, run_id, partial, run_dir)
        raise
    finally:
        if own_client:
            client.close()


def _run_probe_command(container, run_dir: Path, *, deadline: float) -> int:
    client = container.client
    command = [
        "python", PROBE_CONTAINER_PATH,
        "--endpoint", "http://127.0.0.1:8020/mcp",
        "--output-dir", "/logs/artifacts/probe",
        "--phase-timeout-sec", "6",
    ]
    chunks_out: list[bytes] = []
    chunks_err: list[bytes] = []
    exec_id = None
    try:
        with _api_timeout(client, deadline):
            exec_id = client.api.exec_create(container.id, command, stdout=True, stderr=True)["Id"]
            stream = client.api.exec_start(exec_id, detach=False, tty=False, stream=True, demux=True)
            for out, err in stream:
                if time.monotonic() >= deadline:
                    raise TimeoutError("A-stage MCP probe exceeded its overall deadline")
                if out:
                    chunks_out.append(out)
                if err:
                    chunks_err.append(err)
            detail = client.api.exec_inspect(exec_id)
    except Exception as exc:
        (run_dir / "probe.stdout.bin").write_bytes(b"".join(chunks_out))
        (run_dir / "probe.stderr.bin").write_bytes(b"".join(chunks_err))
        _safe_write_json(
            run_dir / "probe-status.json",
            {"exit_code": None, "exec_id_created": exec_id is not None, "error_type": type(exc).__name__,
             "tool": "cases.list_cases", "arguments": {},
             "read_only_policy": "fixed_allowlisted_read_only_tool",
             "probe_summary_path": "/logs/artifacts/probe/summary.json"},
        )
        raise AEnvironmentError("Docker exec did not produce a definitive MCP probe result") from None
    (run_dir / "probe.stdout.bin").write_bytes(b"".join(chunks_out))
    (run_dir / "probe.stderr.bin").write_bytes(b"".join(chunks_err))
    exit_code = detail.get("ExitCode")
    _safe_write_json(
        run_dir / "probe-status.json",
        {"exit_code": exit_code, "tool": "cases.list_cases", "arguments": {},
         "read_only_policy": "fixed_allowlisted_read_only_tool",
         "probe_summary_path": "/logs/artifacts/probe/summary.json"},
    )
    if type(exit_code) is not int:
        raise AEnvironmentError("Docker exec returned an unknown MCP probe exit code")
    return exit_code


def probe_world(root: Path, run_id: str, probe_script: Path, *, client=None,
                deadline: float | None = None) -> int:
    own_client = client is None
    probe_script = _approved_probe_script(root, probe_script)
    client = client or _docker()
    _validate_run_id(run_id)
    deadline = deadline or (time.monotonic() + PROBE_TIMEOUT_SEC)
    run_dir = _run_dir(root, run_id)
    container = _container(client, run_id, deadline=deadline)
    try:
        readiness_sec = wait_world(container, min(STARTUP_TIMEOUT_SEC, max(1, int(deadline - time.monotonic()))), deadline=deadline)
        if not probe_script.is_file():
            raise AEnvironmentError("the approved A-stage MCP probe script is missing")
        identity = json.loads((run_dir / "run-identity.json").read_text(encoding="utf-8"))
        current_probe_sha256 = _sha256(probe_script)
        if not identity.get("probe_sha256") or identity["probe_sha256"] != current_probe_sha256:
            raise AEnvironmentError("the approved A-stage MCP probe changed after world startup")
        with _api_timeout(client, deadline):
            image = client.images.get(identity["image_id"])
            network = client.networks.get(identity["network"])
        _verify_mount_identity(container, identity, probe_script, deadline=deadline)
        details = _runtime_identity(client, container, image, network, root, run_dir, identity, deadline=deadline)
        details["startup_readiness_seconds"] = round(readiness_sec, 3)
        _safe_write_json(run_dir / "run-identity.json", details)
        return _run_probe_command(container, run_dir, deadline=min(deadline, time.monotonic() + PROBE_TIMEOUT_SEC))
    finally:
        if own_client:
            client.close()


def cleanup(client, run_id: str, *, deadline: float | None = None) -> dict[str, Any]:
    """Remove only the preflight-validated resources for this run id."""
    _validate_run_id(run_id)
    deadline = deadline or (time.monotonic() + CLEANUP_TIMEOUT_SEC)
    with _api_timeout(client, deadline):
        container = _get_owned(client, "containers", f"chi-agent-a-world-{run_id}", run_id)
    with _api_timeout(client, deadline):
        network = _get_owned(client, "networks", f"chi-agent-a-net-{run_id}", run_id)
    result: dict[str, Any] = {"container_removed": False, "network_removed": False}
    if container:
        try:
            with _api_timeout(client, deadline):
                container.remove(force=True)
            result["container_removed"] = True
        except Exception as exc:
            result["container_cleanup_error_type"] = type(exc).__name__
    if network:
        try:
            with _api_timeout(client, deadline):
                network.remove()
            result["network_removed"] = True
        except Exception as exc:
            result["network_cleanup_error_type"] = type(exc).__name__
    return result


def run_probe(root: Path, run_id: str, probe_script: Path, *, use_local_hf_auth: bool = False) -> int:
    """Run as a transaction, preserving diagnostics and removing only this invocation's resources."""
    run_id = run_id.strip()
    _validate_run_id(run_id)
    probe_script = _approved_probe_script(root, probe_script)
    deadline = time.monotonic() + RUN_TIMEOUT_SEC
    client = None
    started = False
    run_dir: Path | None = None
    phase = "preflight"
    report: dict[str, Any] = {"run_id": run_id, "status": "failed", "phase": phase}
    failure: Exception | None = None
    try:
        client = _docker()
        # Reject collisions before creating evidence or entering a finally path.
        _check_resource_slots(client, run_id, deadline=deadline)
        if (root / "runs" / "a-environment" / run_id).exists():
            raise AEnvironmentError("run id already has evidence; choose a new run id")
        run_dir = _run_dir(root, run_id, create=True)
        phase = "build"
        tag = f"{IMAGE_TAG_PREFIX}:{run_id}"
        try:
            with _api_timeout(client, deadline):
                client.images.get(tag)
        except Exception as exc:
            if getattr(exc, "status_code", None) != 404:
                raise
            _build_image(root, run_id, client=client, deadline=deadline)
        phase = "start"
        identity = start_world(root, run_id, probe_script=probe_script, client=client, run_dir=run_dir, deadline=deadline)
        started = True
        report["image_id"] = identity["image_id"]
        phase = "readiness_and_probe"
        exit_code = probe_world(root, run_id, probe_script, client=client, deadline=deadline)
        if exit_code != 0:
            raise AEnvironmentError("read-only MCP probe returned a nonzero exit code")
        report.update({"status": "success", "phase": "complete", "probe_exit_code": exit_code})
    except Exception as exc:
        failure = exc
        report.update({"status": "failed", "phase": phase, "error_type": type(exc).__name__})
        if run_dir is not None:
            previous_report = run_dir / "stage-result.json"
            if previous_report.is_file():
                try:
                    startup_report = json.loads(previous_report.read_text(encoding="utf-8"))
                    if startup_report.get("phase") == "start":
                        report["partial_start_cleanup"] = startup_report.get("cleanup")
                        if startup_report.get("cleanup_error_type"):
                            report["partial_start_cleanup_error_type"] = startup_report["cleanup_error_type"]
                except (OSError, json.JSONDecodeError):
                    report["partial_start_report_unreadable"] = True
        if started and run_dir is not None:
            try:
                container = _container(client, run_id, deadline=time.monotonic() + API_TIMEOUT_SEC)
                _capture_logs(container, run_dir, client)
            except Exception as log_exc:
                report["log_capture_error_type"] = type(log_exc).__name__
    finally:
        if started and client is not None:
            try:
                report["cleanup"] = cleanup(client, run_id, deadline=time.monotonic() + CLEANUP_TIMEOUT_SEC)
                if any(key.endswith("cleanup_error_type") for key in report["cleanup"]):
                    if failure is None:
                        failure = AEnvironmentError("resource cleanup failed")
                        report.update({"status": "failed", "phase": "cleanup", "error_type": "CleanupError"})
            except Exception as exc:
                report["cleanup"] = {"error_type": type(exc).__name__}
                if failure is None:
                    failure = exc
                    report.update({"status": "failed", "phase": "cleanup", "error_type": type(exc).__name__})
            if run_dir is not None:
                _persist_report(root, run_id, report, run_dir)
        elif run_dir is not None:
            # start_world owns partial-create cleanup; preserve its result and
            # write this transaction's final phase separately.
            _persist_report(root, run_id, report, run_dir)
        elif failure is not None:
            _persist_report(root, run_id, report, None)
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                report["client_close_error_type"] = type(exc).__name__
                if failure is None:
                    failure = exc
                    report.update({"status": "failed", "phase": "client_close", "error_type": type(exc).__name__})
                _persist_report(root, run_id, report, run_dir)
    if failure is not None:
        raise AEnvironmentError(f"A-stage {report['phase']} failed ({report.get('error_type', type(failure).__name__)})") from None
    return int(report.get("probe_exit_code", 2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare and verify the CHI-Bench A environment")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    download = sub.add_parser("download-data")
    download.add_argument("--use-local-hf-auth", action="store_true")
    build = sub.add_parser("build-image")
    build.add_argument("--run-id", default=uuid.uuid4().hex[:12])
    start = sub.add_parser("start")
    start.add_argument("--run-id", required=True)
    start.add_argument("--probe-script", type=Path)
    probe = sub.add_parser("probe")
    probe.add_argument("--run-id", required=True)
    probe.add_argument("--probe-script", type=Path, required=True)
    run = sub.add_parser("run-probe")
    run.add_argument("--run-id", default=uuid.uuid4().hex[:12])
    run.add_argument("--probe-script", type=Path, required=True)
    run.add_argument("--use-local-hf-auth", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("--run-id", required=True)
    stop = sub.add_parser("stop")
    stop.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        root = _root()
        if args.command == "check":
            checkout = _verify_checkout(root)
            print(f"upstream_sha={UPSTREAM_SHA} path={checkout.relative_to(root)}")
            return 0
        if args.command == "download-data":
            download_data(root, use_local_hf_auth=args.use_local_hf_auth)
            print(f"dataset_revision={DATASET_REVISION} selected_task={TASK_ID}")
            return 0
        if args.command == "build-image":
            tag, image_id = build_image(root, args.run_id)
            print(f"image={tag} image_id={image_id}")
            return 0
        if args.command == "start":
            identity = start_world(root, args.run_id, probe_script=args.probe_script)
            print(f"container={identity['container']} network={identity['network']} ports=none")
            return 0
        if args.command == "probe":
            client = _docker()
            run_dir = None
            report: dict[str, Any] = {"run_id": args.run_id, "status": "failed", "phase": "probe"}
            try:
                code = probe_world(root, args.run_id, args.probe_script, client=client)
                run_dir = _run_dir(root, args.run_id)
                report.update({"status": "success" if code == 0 else "failed", "probe_exit_code": code})
                return code
            except Exception as exc:
                report["error_type"] = type(exc).__name__
                try:
                    run_dir = _run_dir(root, args.run_id)
                    container = _container(client, args.run_id, deadline=time.monotonic() + API_TIMEOUT_SEC)
                    _capture_logs(container, run_dir, client)
                except Exception as log_exc:
                    report["log_capture_error_type"] = type(log_exc).__name__
                raise AEnvironmentError(f"A-stage probe failed ({type(exc).__name__})") from None
            finally:
                if run_dir is not None:
                    _persist_report(root, args.run_id, report, run_dir)
                client.close()
        if args.command == "run-probe":
            code = run_probe(root, args.run_id, args.probe_script, use_local_hf_auth=args.use_local_hf_auth)
            print(f"probe_exit_code={code} runtime_resources=cleaned logs=runs/a-environment/{args.run_id}/")
            return code
        client = _docker()
        try:
            if args.command == "stop":
                result = cleanup(client, args.run_id)
                print(f"container_removed={result['container_removed']} network_removed={result['network_removed']}")
                return 2 if any(key.endswith("cleanup_error_type") for key in result) else 0
            if args.command == "status":
                container = _get_owned(client, "containers", f"chi-agent-a-world-{args.run_id}", args.run_id)
                network = _get_owned(client, "networks", f"chi-agent-a-net-{args.run_id}", args.run_id)
                print(f"container={container.status if container else 'absent'} network={'present' if network else 'absent'}")
                return 0
        finally:
            client.close()
        return 2
    except AEnvironmentError as exc:
        print(f"a_environment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by container CLI
    raise SystemExit(main())
