"""Generate a frozen role-resource manifest and hand it to the original preflight.

The tool is package-external. It never imports project runtime modules, never
reads credentials, and never scans a task directory as "public" by default: each
file is classified explicitly, unknown files fail, and hidden initialisation data
(expectations) stays `world_only`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

ROLE_MAP = {
    "prior_auth_provider": ("provider", "provider"),
    "prior_auth_um": ("payer", "payer"),
    "care_management": ("care_manager", "cm"),
}
PA_PAYER_WORLD = "prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json"
PA_PROVIDER_WORLD = "prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json"
PA_WORLDS = (PA_PAYER_WORLD, PA_PROVIDER_WORLD)
CM_WORLD = "care_management/shared/worlds/healthverse-cm-curated25-v1.json"
CM_REF = "care_management/shared/tool_reference.md"
PRIMARY_WORLD = {"provider": PA_PROVIDER_WORLD, "payer": PA_PAYER_WORLD, "cm": CM_WORLD}
VISIBILITY = {"public", "world_only"}


class ManifestError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _check(path: Path, root: Path) -> Path:
    """Reject symlinks, escapes and non-regular files under the dataset root."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise ManifestError("manifest_symlink")
    resolved = candidate.resolve(strict=False)
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ManifestError("manifest_path_escape")
    for parent in [candidate, *candidate.parents]:
        if parent == root_resolved:
            break
        if parent.is_symlink():
            raise ManifestError("manifest_symlink")
    if not candidate.is_file():
        raise ManifestError("manifest_file_missing")
    return candidate


def _entry(path: Path, root: Path, visibility: str) -> dict:
    if visibility not in VISIBILITY:
        raise ManifestError("manifest_visibility_invalid")
    checked = _check(path, root)
    content = checked.read_bytes()
    return {
        "path": checked.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "visibility": visibility,
    }


def build_manifest(dataset: Path, family: str, task_id: str, revision: str | None = None) -> dict:
    dataset = Path(dataset)
    if family not in ROLE_MAP:
        raise ManifestError("manifest_family_invalid")
    actor, role = ROLE_MAP[family]
    task_path = f"{family}/tasks/{task_id}"
    task = dataset / task_path
    if task.is_symlink() or not task.is_dir():
        raise ManifestError("manifest_task_missing")
    files = []
    if role == "cm":
        if not (dataset / CM_REF).is_file():
            raise ManifestError("manifest_reference_missing")
        world_paths = (CM_WORLD,)
        task_files = ("instruction.md", "task.toml", "fixtures/manifest.json",
                      "fixtures/expectations.json")
    else:
        # Both PA worlds stay in the frozen file list (preflight requires the
        # pair), but only the role's own world may be the primary `world`.
        world_paths = PA_WORLDS
        task_files = ("instruction.md", "task.toml", "tool_reference.md",
                      "fixtures/manifest.json", "fixtures/expectations.json")
    for world in world_paths:
        files.append(_entry(dataset / world, dataset, "world_only"))
    public = {"instruction.md"}
    if role != "cm":
        public.add("tool_reference.md")
    for relative in task_files:
        files.append(_entry(task / relative, dataset,
                            "public" if relative in public else "world_only"))
    request_dir = task / "fixtures/request"
    if role == "payer":
        if request_dir.is_symlink() or not request_dir.is_dir():
            raise ManifestError("manifest_request_missing")
        pdfs = sorted(request_dir.glob("*.pdf"))
        if len(pdfs) != 4:
            raise ManifestError("manifest_request_count")
        for pdf in pdfs:
            files.append(_entry(pdf, dataset, "public"))
    else:
        if request_dir.exists():
            raise ManifestError("manifest_request_unexpected")
    if role == "cm":
        files.append(_entry(dataset / CM_REF, dataset, "public"))
    _reject_unexpected(task, dataset, files)
    primary_world = PRIMARY_WORLD[role]
    if primary_world not in {item["path"] for item in files}:
        raise ManifestError("manifest_world_missing")
    manifest = {
        "schema": "chi-role-resources-v1",
        "actor": actor,
        "family": family,
        "role": role,
        "revision": revision or _revision(dataset),
        "task_id": task_id,
        "task_path": task_path,
        "instruction_path": f"{task_path}/instruction.md",
        "tool_reference_path": CM_REF if role == "cm" else f"{task_path}/tool_reference.md",
        "world": {"path": primary_world,
                  "sha256": next(item["sha256"] for item in files if item["path"] == primary_world),
                  "source": "shared"},
        "files": sorted(files, key=lambda item: item["path"]),
    }
    return manifest


def _reject_unexpected(task: Path, dataset: Path, files: list[dict]) -> None:
    known = {dataset / item["path"] for item in files}
    for path in task.rglob("*"):
        if path.is_symlink():
            raise ManifestError("manifest_symlink")
        if path.is_file() and path not in known:
            raise ManifestError("manifest_unexpected_file")


def _revision(dataset: Path) -> str:
    source = dataset / "REVISION"
    if source.is_file():
        value = source.read_text(encoding="ascii").strip()
        if len(value) == 40:
            return value
    for candidate in ("revision.txt", "REVISION.txt"):
        path = dataset / candidate
        if path.is_file():
            value = path.read_text(encoding="ascii").strip()
            if len(value) == 40:
                return value
    raise ManifestError("manifest_revision_missing")


def write_manifest(manifest: dict, output: Path, dataset: Path,
                   *, preflight=None) -> str:
    """Write once (O_EXCL), then run the original preflight on the written file."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ManifestError("manifest_output_exists")
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    directory = output.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".manifest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        digest = hashlib.sha256(payload).hexdigest()
        if preflight is not None:
            preflight(dataset, Path(temp), digest)
        # Atomic no-overwrite commit: link(2) fails with EEXIST if any file or
        # symlink appeared after the early check, so a racing writer can never be
        # replaced. A second exists() call would still be racy.
        try:
            os.link(temp, output)
        except FileExistsError:
            raise ManifestError("manifest_output_exists") from None
        except OSError:
            raise ManifestError("manifest_write_failed") from None
        os.unlink(temp)
        _fsync_dir(directory)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    return digest


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _preflight_import():
    import role_resource_preflight  # package-external checker
    return role_resource_preflight.validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a frozen role-resource manifest")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--family", required=True, choices=sorted(ROLE_MAP))
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", help="40-hex dataset revision when the tree has no REVISION file")
    parser.add_argument("--no-preflight", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.dataset, args.family, args.task_id, args.revision)
        digest = write_manifest(manifest, args.output, args.dataset,
                                preflight=None if args.no_preflight else _preflight_import())
    except ManifestError as exc:
        print(json.dumps({"status": "refused", "code": exc.code}, sort_keys=True))
        return 1
    except ValueError as exc:
        print(json.dumps({"status": "preflight_failed", "code": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "written", "manifest_sha256": digest,
                      "files": len(manifest["files"]), "task_id": manifest["task_id"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
