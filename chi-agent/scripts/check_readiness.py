#!/usr/bin/env python3
"""
scripts/check_readiness.py — no-model readiness check for chi-agent.

Checks Python, Docker daemon, the upstream vendor clone, and required
environment-variable presence.  Never makes a model call or downloads
restricted content.  Exits 0 only when all required items are satisfied.

Usage:
    python scripts/check_readiness.py
    python scripts/check_readiness.py --json      # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — pinned upstream commit matches project.yaml
# ---------------------------------------------------------------------------
UPSTREAM_COMMIT = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
UPSTREAM_REPO = "https://github.com/actava-ai/chi-bench"
VENDOR_DIR = Path(__file__).parent.parent / "vendor" / "chi-bench"

REQUIRED_ENV_VARS = ["ANTHROPIC_API_KEY"]
OPTIONAL_ENV_VARS = ["OPENAI_API_KEY", "OPENROUTER_API_KEY"]

MIN_PYTHON = (3, 12)

# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python() -> dict:
    ok = sys.version_info >= MIN_PYTHON
    return {
        "check": "python_version",
        "required": True,
        "ok": ok,
        "detail": (
            f"{sys.version} — OK"
            if ok
            else f"{sys.version} — need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
        ),
        "fix": None if ok else f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+",
    }


def check_uv() -> dict:
    found = shutil.which("uv")
    return {
        "check": "uv",
        "required": True,
        "ok": bool(found),
        "detail": f"uv at {found}" if found else "uv not found in PATH",
        "fix": None if found else "curl -LsSf https://astral.sh/uv/install.sh | sh",
    }


def check_docker() -> dict:
    """Check that the Docker CLI exists and the daemon is reachable."""
    cli = shutil.which("docker")
    if not cli:
        return {
            "check": "docker",
            "required": True,
            "ok": False,
            "detail": "docker CLI not found",
            "fix": "Install Docker Desktop: https://docs.docker.com/get-docker/",
        }
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        daemon_ok = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "check": "docker",
            "required": True,
            "ok": False,
            "detail": f"docker info failed: {exc}",
            "fix": "Start Docker Desktop or the Docker daemon.",
        }
    return {
        "check": "docker",
        "required": True,
        "ok": daemon_ok,
        "detail": "Docker daemon reachable" if daemon_ok else result.stderr.strip()[:200],
        "fix": None if daemon_ok else "Start Docker Desktop or the Docker daemon.",
    }


def check_vendor() -> dict:
    """Check that the upstream repo is cloned at the pinned commit."""
    git_dir = VENDOR_DIR / ".git"
    if not git_dir.exists():
        return {
            "check": "upstream_vendor",
            "required": False,
            "ok": False,
            "detail": f"vendor/chi-bench not cloned (expected at {VENDOR_DIR})",
            "fix": (
                f"git clone {UPSTREAM_REPO} {VENDOR_DIR} && "
                f"git -C {VENDOR_DIR} checkout {UPSTREAM_COMMIT}"
            ),
        }
    try:
        result = subprocess.run(
            ["git", "-C", str(VENDOR_DIR), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        actual = result.stdout.strip()
    except Exception as exc:
        return {
            "check": "upstream_vendor",
            "required": False,
            "ok": False,
            "detail": f"git rev-parse failed: {exc}",
            "fix": "Ensure git is available and vendor/chi-bench is a valid clone.",
        }
    ok = actual == UPSTREAM_COMMIT
    return {
        "check": "upstream_vendor",
        "required": False,
        "ok": ok,
        "detail": (
            f"HEAD = {actual} (matches pinned commit)"
            if ok
            else f"HEAD = {actual}, want {UPSTREAM_COMMIT}"
        ),
        "fix": (
            None
            if ok
            else f"git -C {VENDOR_DIR} checkout {UPSTREAM_COMMIT}"
        ),
    }


def check_env_vars() -> list[dict]:
    results = []
    for var in REQUIRED_ENV_VARS:
        present = bool(os.environ.get(var))
        results.append({
            "check": f"env:{var}",
            "required": True,
            "ok": present,
            "detail": (
                f"{var} is set (value not shown)"
                if present
                else f"{var} is not set"
            ),
            # Distinguish presence from proven connectivity.
            "note": (
                "Presence confirmed; actual API connectivity not verified by this script."
                if present
                else None
            ),
            "fix": (
                None
                if present
                else f"export {var}=<your-key>  # or add to .env"
            ),
        })
    for var in OPTIONAL_ENV_VARS:
        present = bool(os.environ.get(var))
        results.append({
            "check": f"env:{var}",
            "required": False,
            "ok": True,  # optional — never blocks readiness
            "detail": (
                f"{var} is set (value not shown)"
                if present
                else f"{var} not set (optional)"
            ),
            "note": "Optional — only required for specific harnesses.",
            "fix": None,
        })
    return results


def check_handbook() -> dict:
    """
    Record handbook access status.
    This check always reports NOT READY unless the user explicitly confirms
    via the HF_HANDBOOK_ACCESS_GRANTED=1 environment variable.
    """
    granted = os.environ.get("HF_HANDBOOK_ACCESS_GRANTED", "").strip() == "1"
    return {
        "check": "handbook_access",
        "required": False,
        "ok": granted,
        "detail": (
            "HF_HANDBOOK_ACCESS_GRANTED=1 is set — treat as user-confirmed, not verified by this script."
            if granted
            else (
                "Managed-Care Operations Handbook access not confirmed. "
                "Apply at https://huggingface.co/datasets/actava/managed-care-operations-handbook "
                "and set HF_HANDBOOK_ACCESS_GRANTED=1 once approved."
            )
        ),
        "note": (
            "Configuration presence does not prove service access. "
            "Real baseline runs require handbook access."
        ),
        "fix": (
            None
            if granted
            else "Complete HuggingFace gated dataset request; set HF_HANDBOOK_ACCESS_GRANTED=1 when approved."
        ),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_checks() -> list[dict]:
    checks: list[dict] = [
        check_python(),
        check_uv(),
        check_docker(),
        check_vendor(),
        check_handbook(),
    ]
    checks.extend(check_env_vars())
    return checks


def summarise(checks: list[dict]) -> tuple[bool, list[str]]:
    """Return (all_required_ok, list_of_failure_messages)."""
    failures = []
    for c in checks:
        if c["required"] and not c["ok"]:
            failures.append(f"  MISSING [{c['check']}]: {c['detail']}")
            if c.get("fix"):
                failures.append(f"    → Fix: {c['fix']}")
    return len(failures) == 0, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="chi-agent readiness check (no model call)")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    checks = run_checks()
    all_ok, failures = summarise(checks)

    if args.json:
        print(json.dumps({"ready": all_ok, "checks": checks}, indent=2))
        sys.exit(0 if all_ok else 1)

    # Human-readable output
    print("=" * 60)
    print("chi-agent readiness check")
    print("=" * 60)
    for c in checks:
        tag = "OK " if c["ok"] else ("REQ" if c["required"] else "OPT")
        print(f"  [{tag}] {c['check']}: {c['detail']}")
        if not c["ok"] and c.get("fix"):
            print(f"        Fix: {c['fix']}")
        if c.get("note"):
            print(f"        Note: {c['note']}")

    print()
    if all_ok:
        print("READY — all required checks passed.")
        print("Note: Handbook access and API connectivity are not proven by this script;")
        print("      confirm separately before starting a real benchmark run.")
    else:
        print("NOT READY — missing required dependencies:")
        for line in failures:
            print(line)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
