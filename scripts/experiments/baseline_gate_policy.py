"""Shared deterministic selection and evidence gate for D0 real modes.

This module never connects to a model, judge, task service, or Docker daemon.
It only inspects selected local task files, declared source manifests, and
credential presence (never credential values).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


DOMAIN_DIRS = {
    "pa_provider": "prior_auth_provider",
    "pa_um": "prior_auth_um",
    "cm": "care_management",
}

MODEL_PREFIX_ENV = {
    "deepseek": ("DEEPSEEK_API_KEY",),
    "gemini": ("GEMINI_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}

DOMAIN_HANDBOOK_FILES = {
    "pa_provider": "references/provider-pa/SKILL.md",
    "pa_um": "references/payer-um/SKILL.md",
    "cm": "references/care-manager/SKILL.md",
}

TASK_REQUIRED_FILES = ("instruction.md", "task.toml", "tool_reference.md")
HANDBOOK_REPO = "actava/managed-care-operations-handbook"
BENCHMARK_REPO = "actava/chi-bench"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def infer_provider(model: str | None) -> str | None:
    """Infer only providers with an explicit, known model namespace."""
    if not isinstance(model, str) or "/" not in model:
        return None
    prefix = model.split("/", 1)[0].strip().lower()
    return prefix if prefix in MODEL_PREFIX_ENV else None


def _load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError, UnicodeError) as exc:
        return None, f"Cannot read {path.name}: {type(exc).__name__}"


def _hash_matches(path: Path, expected_bytes: Any, expected_hash: Any) -> bool:
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
        return False
    if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(expected_hash):
        return False
    try:
        if not path.is_file() or path.stat().st_size != expected_bytes:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected_hash
    except OSError:
        return False


def _source_for(sources: Any, repo: str) -> dict[str, Any] | None:
    if not isinstance(sources, list):
        return None
    found = [entry for entry in sources if isinstance(entry, dict) and entry.get("repo") == repo]
    return found[0] if len(found) == 1 else None


def _manifest_file_map(entry: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    files = entry.get("files")
    if not isinstance(files, list) or not files:
        return None
    mapping: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict):
            return None
        rel = item.get("path")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            return None
        if rel in mapping:
            return None
        size = item.get("bytes")
        digest = item.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            return None
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            return None
        mapping[rel] = item
    declared_count = entry.get("verified_file_count")
    if isinstance(declared_count, bool) or declared_count != len(mapping):
        return None
    byte_total = sum(item["bytes"] for item in mapping.values())
    declared_bytes = entry.get("verified_bytes")
    if isinstance(declared_bytes, bool) or not isinstance(declared_bytes, int) or byte_total != declared_bytes:
        return None
    return mapping


def _verify_listed_files(
    *, root: Path, file_map: dict[str, dict[str, Any]], required_paths: set[str] | None = None
) -> list[str]:
    failures: list[str] = []
    paths = sorted(file_map if required_paths is None else required_paths)
    for rel in paths:
        record = file_map.get(rel)
        if record is None:
            failures.append(f"Source manifest does not list required file: {rel}")
            continue
        if not _hash_matches(root / rel, record.get("bytes"), record.get("sha256")):
            failures.append(f"File missing or integrity mismatch: {rel}")
    return failures


def _project_handbook(project_config_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        config = yaml.safe_load(project_config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError, UnicodeError) as exc:
        return None, f"Cannot read project.yaml handbook declaration: {type(exc).__name__}"
    handbook = config.get("handbook") if isinstance(config, dict) else None
    if not isinstance(handbook, dict):
        return None, "project.yaml has no valid handbook declaration"
    if handbook.get("dataset") != HANDBOOK_REPO:
        return None, "project.yaml handbook repository does not match the expected source"
    revision = handbook.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        return None, "project.yaml handbook revision is missing"
    return handbook, None


def evaluate_gate(
    *,
    mode: str,
    domain: str | None,
    task_name: str | None,
    model: str | None,
    env: dict[str, str],
    data_dir: Path | str,
    handbook_dir: Path | str,
    project_config_path: Path | str,
    source_manifest_path: Path | str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return shared selection/evidence blockers for readiness and execution."""
    data_dir = Path(data_dir)
    handbook_dir = Path(handbook_dir)
    project_config_path = Path(project_config_path)
    source_manifest_path = Path(source_manifest_path)
    failures: list[str] = []
    evidence: dict[str, Any] = {"mode": mode, "domain": domain, "task_name": task_name}

    inferred_provider = infer_provider(model)
    evidence["model"] = model
    evidence["provider"] = inferred_provider
    if not domain or not task_name or not model:
        failures.append("Real-mode selection incomplete: domain, task-name, and model are required")
    if task_name and not _TASK_NAME_RE.fullmatch(task_name):
        failures.append("Selected task name contains invalid path characters")
    if domain not in DOMAIN_DIRS:
        failures.append(f"Unsupported or missing domain: {domain!r}")
    if inferred_provider is None:
        failures.append(f"Unknown model provider prefix; cannot select a credential safely: {model!r}")
    if provider:
        evidence["explicit_provider"] = provider
        if inferred_provider is None or provider.strip().lower() != inferred_provider:
            failures.append("Explicit provider does not match the known provider prefix in --model")

    if domain in DOMAIN_DIRS and task_name and _TASK_NAME_RE.fullmatch(task_name):
        task_parent = data_dir / DOMAIN_DIRS[domain] / "tasks"
        task_dir = task_parent / task_name
        evidence["task_path"] = str(task_dir)
        if not task_dir.is_dir() or task_dir.resolve().parent != task_parent.resolve():
            failures.append(f"Selected task directory is missing: {task_dir}")
        else:
            missing = [name for name in TASK_REQUIRED_FILES if not (task_dir / name).is_file()]
            if missing:
                failures.append(f"Selected task is incomplete; missing files: {', '.join(missing)}")

    if inferred_provider is not None:
        key_names = MODEL_PREFIX_ENV[inferred_provider]
        configured = [name for name in key_names if bool((env.get(name) or "").strip())]
        evidence["runner_credential"] = {
            "provider": inferred_provider,
            "environment_names": list(key_names),
            "configured": bool(configured),
            "connectivity_verified": False,
        }
        if not configured:
            failures.append(
                f"No credential configured for selected provider {inferred_provider}; expected one of {', '.join(key_names)}"
            )

    # Validate selected task files against the source download record. This
    # intentionally supports only files evidenced by the local manifest.
    manifest, manifest_error = _load_json(source_manifest_path)
    sources = manifest.get("sources") if isinstance(manifest, dict) else None
    bench_entry = _source_for(sources, BENCHMARK_REPO)
    if bench_entry is None:
        failures.append("source-downloads.json has no unique CHI-Bench source record")
    elif domain in DOMAIN_DIRS and task_name and _TASK_NAME_RE.fullmatch(task_name):
        bench_files = _manifest_file_map(bench_entry)
        if bench_files is None:
            failures.append("CHI-Bench source manifest file inventory is incomplete or malformed")
        else:
            task_rel = f"{DOMAIN_DIRS[domain]}/tasks/{task_name}"
            required_task_paths = {f"{task_rel}/{name}" for name in TASK_REQUIRED_FILES}
            task_root = data_dir
            failures.extend(_verify_listed_files(root=task_root, file_map=bench_files, required_paths=required_task_paths))
            evidence["benchmark_source_commit"] = bench_entry.get("commit")
            evidence["benchmark_download_scope"] = bench_entry.get("download_scope")

    if manifest_error:
        failures.append(manifest_error)

    # Check the pinned handbook revision, full manifest inventory, and the
    # root plus selected-domain references. No handbook text is read.
    handbook_decl, handbook_error = _project_handbook(project_config_path)
    if handbook_error:
        failures.append(handbook_error)
    else:
        evidence["handbook"] = {
            "repo": handbook_decl.get("dataset"),
            "revision": handbook_decl.get("revision"),
            "connectivity_verified": False,
        }
        hand_entry = _source_for(sources, handbook_decl.get("dataset"))
        if hand_entry is None:
            failures.append("source-downloads.json has no unique handbook source record")
        else:
            if hand_entry.get("commit") != handbook_decl.get("revision"):
                failures.append("Handbook source commit does not match project.yaml revision")
            file_map = _manifest_file_map(hand_entry)
            if file_map is None:
                failures.append("Handbook source manifest inventory is incomplete or malformed")
            else:
                if hand_entry.get("download_scope") != "full_snapshot":
                    failures.append("Handbook source record does not declare a full snapshot")
                source_root = handbook_dir.parent
                failures.extend(_verify_listed_files(root=source_root, file_map=file_map))
                required = {f"{handbook_dir.name}/SKILL.md"}
                if domain in DOMAIN_HANDBOOK_FILES:
                    required.add(f"{handbook_dir.name}/{DOMAIN_HANDBOOK_FILES[domain]}")
                failures.extend(_verify_listed_files(root=source_root, file_map=file_map, required_paths=required))
                evidence["handbook_manifest_files"] = len(file_map)

    # Mode support is intentionally shared: R1 has no verified ungraded CLI;
    # OAuth/Claude Code is known but remains unverified and never passes.
    if mode == "ungraded":
        evidence["mode_support"] = "unsupported_unverified_entrypoint"
        failures.append(
            "Ungraded real execution is currently unsupported by the fixed upstream entry point "
            "(no verified skip-judge mechanism)"
        )
    elif mode == "scored":
        evidence["mode_support"] = "scored_configured_only"
        api_key = bool((env.get("ANTHROPIC_API_KEY") or "").strip())
        oauth_present = any(bool((env.get(name) or "").strip()) for name in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"))
        evidence["judge_auth"] = {
            "api_key_configured": api_key,
            "claude_code_or_oauth_configured_unverified": oauth_present,
            "authentication_verified": False,
        }
        if not api_key:
            if oauth_present:
                failures.append("Claude Code/OAuth judge credentials are present but that path is unverified")
            else:
                failures.append("Scored mode requires configured ANTHROPIC_API_KEY; OAuth is known but unverified")
    else:
        evidence["mode_support"] = "unknown"
        failures.append(f"Unsupported real execution mode: {mode!r}")

    # De-duplicate without reordering diagnostics.
    failures = list(dict.fromkeys(failures))
    return {"ready": not failures, "failures": failures, "evidence": evidence}
