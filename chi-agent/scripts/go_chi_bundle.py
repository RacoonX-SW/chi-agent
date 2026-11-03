"""Build and verify a clean, allowlisted Go CHI evaluation bundle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "bundle-manifest.json"
INCOMPLETE_NAME = ".bundle-incomplete"
MANIFEST_SCHEMA = "chi-go-evaluation-bundle-v1"
CONFIG_PATH = "profiles/go-chi-entry.json"
MAX_FILE_BYTES = 16 * 1024 * 1024

# Destination path -> repository source path. This list is the entire package
# input boundary; no directory walk of the project or vendor tree is used.
PACKAGE_FILES: dict[str, str] = {
    "scripts/go_chi_entry.py": "scripts/go_chi_entry.py",
    "scripts/go_chi_evidence.py": "scripts/go_chi_evidence.py",
    "scripts/go_chi_bundle.py": "scripts/go_chi_bundle.py",
    "scripts/go_chi_contract.py": "scripts/go_chi_contract.py",
    "scripts/go_chi_context.py": "scripts/go_chi_context.py",
    "scripts/go_chi_recovery.py": "scripts/go_chi_recovery.py",
    "scripts/go_chi_guidance.py": "scripts/go_chi_guidance.py",
    "scripts/go_chi_guard.py": "scripts/go_chi_guard.py",
    "scripts/go_chi_search.py": "scripts/go_chi_search.py",
    "scripts/go_chi_state.py": "scripts/go_chi_state.py",
    "scripts/go_chi_auxiliary.py": "scripts/go_chi_auxiliary.py",
    "scripts/go_chi_inspect.py": "scripts/go_chi_inspect.py",
    "scripts/go_chi_harness.py": "scripts/go_chi_harness.py",
    "scripts/go_chi_journal.py": "scripts/go_chi_journal.py",
    "scripts/go_chi_summary.py": "scripts/go_chi_summary.py",
    "scripts/go_chi_local.py": "scripts/go_chi_local.py",
    "scripts/go_chi_policy.py": "scripts/go_chi_policy.py",
    "scripts/go_chi_mcp.py": "scripts/go_chi_mcp.py",
    "scripts/go_chi_resources.py": "scripts/go_chi_resources.py",
    "scripts/go_chi_runtime.py": "scripts/go_chi_runtime.py",
    "scripts/go_chi_tools.py": "scripts/go_chi_tools.py",
    "scripts/evaluation_bundle.py": "scripts/evaluation_bundle.py",
    "scripts/b_execution_policy.py": "scripts/b_execution_policy.py",
    "scripts/b_provider_profile.py": "scripts/b_provider_profile.py",
    "scripts/b_provider_transport.py": "scripts/b_provider_transport.py",
    "scripts/model_runner_adapter.py": "scripts/model_runner_adapter.py",
    "scripts/budget_evaluation.py": "scripts/budget_evaluation.py",
    "scripts/b_model_adapter.py": "scripts/b_model_adapter.py",
    "scripts/opencode_go_provider.py": "scripts/opencode_go_provider.py",
    "scripts/patient_identity_binding.py": "scripts/patient_identity_binding.py",
    "scripts/payer_evidence.py": "scripts/payer_evidence.py",
    "scripts/pdf_resource_reader.py": "scripts/pdf_resource_reader.py",
    "scripts/referral_field_guidance.py": "scripts/referral_field_guidance.py",
    "scripts/request_budget.py": "scripts/request_budget.py",
    "scripts/install_model_dependencies.sh": "scripts/install_model_dependencies.sh",
    "profiles/go-chi-entry.json": "profiles/go-chi-entry.json",
    "profiles/opencode-go-deepseek.json": "profiles/opencode-go-deepseek.json",
    "requirements-model.lock": "requirements-model.lock",
    "requirements-pdf.lock": "requirements-pdf.lock",
    "RUN_CHI_GO.md": "docs/go-chi-entry-runbook.md",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BundleFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BundleIdentity:
    root: Path
    bundle_id: str
    manifest_sha256: str
    entry_config_sha256: str
    files: dict[str, dict[str, Any]]


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except Exception:
        raise BundleFailure("bundle_manifest_invalid") from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _lexical_absolute(path: Path, code: str) -> Path:
    path = Path(path)
    if ".." in path.parts:
        raise BundleFailure(code)
    return Path(os.path.abspath(path))


def _check_components(path: Path, code: str, *, final_may_be_missing: bool = True) -> Path:
    absolute = _lexical_absolute(path, code)
    current = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:], start=1):
        current /= part
        try:
            details = current.lstat()
        except FileNotFoundError:
            if not final_may_be_missing and index == len(absolute.parts) - 1:
                raise BundleFailure(code) from None
            continue
        except OSError:
            raise BundleFailure(code) from None
        if stat.S_ISLNK(details.st_mode):
            raise BundleFailure(code)
        if index < len(absolute.parts) - 1 and not stat.S_ISDIR(details.st_mode):
            raise BundleFailure(code)
    return absolute


def _read_allowlisted_source(source_root: Path, source_relative: str) -> bytes:
    path = _check_components(source_root / source_relative, "bundle_source_invalid",
                             final_may_be_missing=False)
    try:
        return _read_regular_bounded(path, MAX_FILE_BYTES, "bundle_source_invalid")
    except Exception:
        raise BundleFailure("bundle_source_invalid") from None


def _read_regular_bounded(path: Path, limit: int, code: str, *, expected_size: int | None = None,
                          size_mismatch_code: str | None = None) -> bytes:
    """Read a regular no-follow file with a hard byte bound and stable size checks."""
    fd = None
    try:
        path_details = os.lstat(path)
        if not stat.S_ISREG(path_details.st_mode) or path_details.st_size > limit:
            raise ValueError
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit
                or before.st_dev != path_details.st_dev or before.st_ino != path_details.st_ino):
            raise ValueError
        if expected_size is not None and before.st_size != expected_size:
            raise BundleFailure(size_mismatch_code or code)
        bound = limit if expected_size is None else expected_size
        with os.fdopen(fd, "rb") as handle:
            fd = None
            payload = handle.read(bound + 1)
            after = os.fstat(handle.fileno())
        if (len(payload) > bound or (expected_size is not None and len(payload) != expected_size)
                or before.st_dev != after.st_dev or before.st_ino != after.st_ino
                or after.st_size != before.st_size):
            raise BundleFailure(size_mismatch_code or code)
        return payload
    except BundleFailure:
        raise
    except Exception:
        raise BundleFailure(code) from None
    finally:
        if fd is not None:
            os.close(fd)


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        raise BundleFailure("bundle_write_failed") from None


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        raise BundleFailure("bundle_write_failed") from None


def _tree_allowlist() -> tuple[set[str], set[str]]:
    files = set(PACKAGE_FILES) | {MANIFEST_NAME}
    dirs = {"vendor", "vendor/chi-bench"}
    for name in PACKAGE_FILES:
        parent = Path(name).parent
        while str(parent) not in {".", ""}:
            dirs.add(parent.as_posix())
            parent = parent.parent
    return files, dirs


def _check_tree(root: Path) -> None:
    incomplete = root / INCOMPLETE_NAME
    try:
        incomplete.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise BundleFailure("bundle_tree_invalid") from None
    else:
        raise BundleFailure("bundle_incomplete")
    expected_files, expected_dirs = _tree_allowlist()
    found_files: set[str] = set()
    found_dirs: set[str] = set()
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(root)
        for dirname in list(directories):
            child = current_path / dirname
            rel = (relative_current / dirname).as_posix()
            if child.is_symlink() or not child.is_dir():
                raise BundleFailure("bundle_tree_invalid")
            if rel == "vendor":
                found_dirs.add(rel)
                continue
            if rel == "vendor/chi-bench":
                # This is an empty mount point in the bundle; an independently
                # mounted pinned vendor checkout may be present at runtime.
                directories.remove(dirname)
                if rel in expected_dirs:
                    found_dirs.add(rel)
                continue
            if rel.startswith("vendor/"):
                raise BundleFailure("bundle_tree_invalid")
            found_dirs.add(rel)
        for filename in filenames:
            child = current_path / filename
            rel = (relative_current / filename).as_posix()
            if child.is_symlink() or not child.is_file():
                raise BundleFailure("bundle_tree_invalid")
            found_files.add(rel)
    if found_files != expected_files or found_dirs != expected_dirs:
        raise BundleFailure("bundle_tree_invalid")


def _manifest_digest(manifest: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


def build_bundle(target: Path, *, source_root: Path = ROOT) -> BundleIdentity:
    """Create a new directory package; a failed target stays incomplete and reserved."""
    source_root = _check_components(Path(source_root), "bundle_source_invalid", final_may_be_missing=False)
    if not source_root.is_dir():
        raise BundleFailure("bundle_source_invalid")
    target = _lexical_absolute(Path(target), "bundle_target_invalid")
    _check_components(target.parent, "bundle_target_invalid", final_may_be_missing=False)
    if not target.parent.is_dir():
        raise BundleFailure("bundle_target_invalid")
    if target.exists() or target.is_symlink():
        raise BundleFailure("bundle_target_exists")
    try:
        target.mkdir(mode=0o700)
        _fsync_dir(target.parent)
    except FileExistsError:
        raise BundleFailure("bundle_target_exists") from None
    except Exception:
        raise BundleFailure("bundle_write_failed") from None

    entries: dict[str, dict[str, Any]] = {}
    try:
        _write_exclusive(target / INCOMPLETE_NAME, b"bundle build in progress\n")
        _fsync_dir(target)
        for relative, source_relative in PACKAGE_FILES.items():
            payload = _read_allowlisted_source(source_root, source_relative)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_exclusive(destination, payload)
            _fsync_dir(destination.parent)
            entries[relative] = {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}

        (target / "vendor" / "chi-bench").mkdir(parents=True, exist_ok=True)
        _fsync_dir(target / "vendor")
        config = entries.get(CONFIG_PATH)
        if config is None:
            raise BundleFailure("bundle_source_invalid")
        unsigned = {
            "schema": MANIFEST_SCHEMA,
            "bundle_id": "go-chi-evaluation-record-only-v1",
            "files": entries,
            "entry_config_sha256": config["sha256"],
            "identity_is_not_signature_or_authorization": True,
        }
        manifest = {**unsigned, "manifest_sha256": _manifest_digest(unsigned)}
        _write_exclusive(target / MANIFEST_NAME, _canonical(manifest) + b"\n")
        _fsync_dir(target)
        # Removing this marker is the publication commit. All package files
        # and the manifest have already been fsynced. Any earlier failure
        # leaves the reserved target visibly incomplete and unverifiable.
        (target / INCOMPLETE_NAME).unlink()
        return BundleIdentity(root=target, bundle_id=manifest["bundle_id"],
                              manifest_sha256=manifest["manifest_sha256"],
                              entry_config_sha256=manifest["entry_config_sha256"], files=entries)
    except BundleFailure:
        try:
            manifest_path = target / MANIFEST_NAME
            if manifest_path.exists() and not manifest_path.is_symlink():
                manifest_path.unlink()
                _fsync_dir(target)
        except Exception:
            pass
        raise
    except Exception:
        try:
            manifest_path = target / MANIFEST_NAME
            if manifest_path.exists() and not manifest_path.is_symlink():
                manifest_path.unlink()
                _fsync_dir(target)
        except Exception:
            pass
        raise BundleFailure("bundle_write_failed") from None


def validate_bundle(root: Path) -> BundleIdentity:
    root = _check_components(Path(root), "bundle_path_invalid", final_may_be_missing=False)
    if not root.is_dir():
        raise BundleFailure("bundle_path_invalid")
    _check_tree(root)
    manifest_path = root / MANIFEST_NAME
    _check_components(manifest_path, "bundle_manifest_invalid", final_may_be_missing=False)
    try:
        manifest_bytes = _read_regular_bounded(manifest_path, 1_048_576, "bundle_manifest_invalid")
        manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise BundleFailure("bundle_manifest_invalid") from None
    required = {"schema", "bundle_id", "files", "entry_config_sha256",
                "identity_is_not_signature_or_authorization", "manifest_sha256"}
    if (type(manifest) is not dict or set(manifest) != required
            or manifest.get("schema") != MANIFEST_SCHEMA
            or manifest.get("bundle_id") != "go-chi-evaluation-record-only-v1"
            or manifest.get("identity_is_not_signature_or_authorization") is not True
            or not isinstance(manifest.get("files"), dict)
            or set(manifest["files"]) != set(PACKAGE_FILES)
            or not isinstance(manifest.get("entry_config_sha256"), str)
            or not SHA256_RE.fullmatch(manifest["entry_config_sha256"])
            or type(manifest.get("manifest_sha256")) is not str
            or not SHA256_RE.fullmatch(manifest["manifest_sha256"])
            or _manifest_digest(manifest) != manifest["manifest_sha256"]):
        raise BundleFailure("bundle_manifest_invalid")
    for relative in PACKAGE_FILES:
        item = manifest["files"].get(relative)
        if (type(item) is not dict or set(item) != {"sha256", "size"}
                or type(item.get("sha256")) is not str or not SHA256_RE.fullmatch(item["sha256"])
                or type(item.get("size")) is not int or not 0 <= item["size"] <= MAX_FILE_BYTES):
            raise BundleFailure("bundle_manifest_invalid")
        path = _check_components(root / relative, "bundle_file_invalid", final_may_be_missing=False)
        payload = _read_regular_bounded(path, MAX_FILE_BYTES, "bundle_file_invalid",
                                        expected_size=item["size"],
                                        size_mismatch_code="bundle_file_digest_mismatch")
        if len(payload) != item["size"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise BundleFailure("bundle_file_digest_mismatch")
    if manifest["entry_config_sha256"] != manifest["files"][CONFIG_PATH]["sha256"]:
        raise BundleFailure("bundle_manifest_invalid")
    return BundleIdentity(root=root, bundle_id=manifest["bundle_id"],
                          manifest_sha256=manifest["manifest_sha256"],
                          entry_config_sha256=manifest["entry_config_sha256"], files=manifest["files"])


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--target", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        identity = build_bundle(args.target) if args.command == "build" else validate_bundle(args.root)
        print(json.dumps({"status": "complete", "bundle_id": identity.bundle_id,
                          "bundle_root": str(identity.root), "manifest_sha256": identity.manifest_sha256,
                          "entry_config_sha256": identity.entry_config_sha256,
                          "file_count": len(identity.files)}, indent=2, sort_keys=True))
        return 0
    except BundleFailure as exc:
        print(json.dumps({"status": "rejected", "safe_error_code": exc.code,
                          "identity_is_not_authorization": True}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
