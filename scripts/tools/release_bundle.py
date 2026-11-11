"""Final-candidate release wrapper and clean-room verification for Go CHI.

The inner ``package/`` is the existing Go bundle, whose manifest already binds
every distributed file. This wrapper adds a release manifest, a checksum list,
a source commit and an optional caller-owned supply plan check. It never starts
a model, world or Trial.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from chi_agent.bundle import MANIFEST_NAME, PACKAGE_FILES, BundleFailure, build_bundle, validate_bundle
from chi_agent.delivery import DeliveryError, check_plan, validate_plan

SCHEMA = "chi-go-release-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
RELEASE_MANIFEST = "release-manifest.json"
SUMS = "SHA256SUMS"
PLAN = "supply-plan.example.json"
TOP_LEVEL = {RELEASE_MANIFEST, SUMS, PLAN, "package"}
BLOCKED_TOP = {".env", "data", "vendor", "runs", "tests", "reviews", "openspec", "docs"}


class ReleaseError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.as_posix())


def _source_commit(source_root: Path, supplied: str | None) -> str:
    if supplied is not None:
        if type(supplied) is not str or not COMMIT.fullmatch(supplied):
            raise ReleaseError("release_source_commit_invalid")
        return supplied
    try:
        value = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                               check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise ReleaseError("release_source_commit_missing") from None
    if not COMMIT.fullmatch(value):
        raise ReleaseError("release_source_commit_invalid")
    return value


def _sums(root: Path) -> bytes:
    lines = []
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if relative == SUMS:
            continue
        lines.append(f"{_sha(path)}  {relative}\n")
    return "".join(lines).encode("utf-8")


def build_release(target, *, source_root, source_commit=None) -> dict:
    target = Path(target)
    source_root = Path(source_root)
    if target.exists() or target.is_symlink():
        raise ReleaseError("release_target_exists")
    commit = _source_commit(source_root, source_commit)
    try:
        target.mkdir(mode=0o700)
        identity = build_bundle(target / "package", source_root=source_root)
        package_files = {relative: item["sha256"] for relative, item in identity.files.items()}
        manifest = {
            "schema": SCHEMA,
            "source_commit": commit,
            "bundle_manifest_sha256": identity.manifest_sha256,
            "bundle_entry_config_sha256": identity.entry_config_sha256,
            "bundle_files": package_files,
            "dependency_locks": {
                "model": package_files["requirements-model.lock"],
                "pdf": package_files["requirements-pdf.lock"],
            },
            "allowed_top_level": sorted(TOP_LEVEL),
            "notes": [
                "inner package/ is validated by its own bundle-manifest.json",
                "SHA256SUMS binds the release wrapper files",
                "no source checkout, data, vendor, tests, runs, credentials or trajectories",
            ],
        }
        (target / RELEASE_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (target / PLAN).write_text(json.dumps({
            "schema": "chi-go-delivery-plan-v1",
            "note": "Replace placeholders with caller-supplied paths and hashes before check_plan",
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (target / SUMS).write_bytes(_sums(target))
        return {"status": "built", "root": str(target), "source_commit": commit,
                "bundle_manifest_sha256": identity.manifest_sha256,
                "release_manifest_sha256": _sha(target / RELEASE_MANIFEST)}
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def verify_release(root, plan=None) -> dict:
    root = Path(root)
    try:
        if root.is_symlink() or not root.is_dir():
            raise ReleaseError("release_root_invalid")
        entries = {path.name for path in root.iterdir()}
        if entries != TOP_LEVEL or any(path.is_symlink() for path in root.iterdir()):
            raise ReleaseError("release_layout_invalid")
        if any(name in BLOCKED_TOP for name in entries):
            raise ReleaseError("release_forbidden_content")
        manifest = json.loads((root / RELEASE_MANIFEST).read_text(encoding="utf-8"))
        required = {"schema", "source_commit", "bundle_manifest_sha256",
                    "bundle_entry_config_sha256", "bundle_files", "dependency_locks",
                    "allowed_top_level", "notes"}
        if (type(manifest) is not dict or set(manifest) != required
                or manifest.get("schema") != SCHEMA
                or type(manifest.get("source_commit")) is not str
                or not COMMIT.fullmatch(manifest["source_commit"])):
            raise ReleaseError("release_manifest_invalid")
        package = root / "package"
        try:
            identity = validate_bundle(package)
        except BundleFailure:
            raise ReleaseError("release_bundle_identity_invalid") from None
        if (identity.manifest_sha256 != manifest["bundle_manifest_sha256"]
                or identity.entry_config_sha256 != manifest["bundle_entry_config_sha256"]):
            raise ReleaseError("release_bundle_identity_invalid")
        present = {path.relative_to(package).as_posix() for path in _files(package)}
        expected = set(identity.files) | {MANIFEST_NAME}
        if present != expected:
            raise ReleaseError("release_package_content_invalid")
        if manifest["bundle_files"] != {relative: identity.files[relative]["sha256"]
                                        for relative in identity.files}:
            raise ReleaseError("release_bundle_files_invalid")
        if manifest["dependency_locks"] != {
                "model": identity.files["requirements-model.lock"]["sha256"],
                "pdf": identity.files["requirements-pdf.lock"]["sha256"]}:
            raise ReleaseError("release_dependency_locks_invalid")
        expected_sums = _sums(root)
        if (root / SUMS).read_bytes() != expected_sums:
            raise ReleaseError("release_checksum_invalid")
        plan_report = None
        if plan is not None:
            plan_report = check_plan(plan)
            if Path(plan["bundle"]["root"]).resolve() != package.resolve():
                raise ReleaseError("release_plan_bundle_mismatch")
        return {"status": "valid", "source_commit": manifest["source_commit"],
                "bundle_manifest_sha256": identity.manifest_sha256,
                "release_manifest_sha256": _sha(root / RELEASE_MANIFEST),
                "files": len(present), "plan_checked": plan_report is not None,
                "note": "offline release verification only; no model/world/Trial started"}
    except (ReleaseError, BundleFailure, DeliveryError, OSError, ValueError, KeyError) as exc:
        code = getattr(exc, "code", "release_invalid")
        raise ReleaseError(code) from None


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build or verify a Go CHI release wrapper")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--target", required=True)
    build.add_argument("--source-root", required=True)
    build.add_argument("--source-commit")
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--plan")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            print(json.dumps(build_release(args.target, source_root=args.source_root,
                                           source_commit=args.source_commit), sort_keys=True))
        else:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else None
            if plan is not None:
                validate_plan(plan)
            print(json.dumps(verify_release(args.root, plan), sort_keys=True))
        return 0
    except (ReleaseError, DeliveryError, OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "code": getattr(exc, "code", "release_invalid")},
                         sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
