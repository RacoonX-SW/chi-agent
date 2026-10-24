#!/usr/bin/env python3
"""
scripts/check_readiness.py — no-model readiness check for chi-agent.

Checks prerequisites per mode (offline, tools, ungraded, scored).
Never makes a model call or downloads restricted content.
Distinguishes credential presence from connectivity.
Verifies handbook presence on disk (authorization flag alone does not prove files).
Offline mode does not require Docker socket or external services.

Usage:
    python scripts/check_readiness.py
    python scripts/check_readiness.py --mode offline
    python scripts/check_readiness.py --mode ungraded
    python scripts/check_readiness.py --mode scored
    python scripts/check_readiness.py --json
    python scripts/check_readiness.py --env-file .env
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
PROJECT_ROOT = Path(__file__).parent.parent
VENDOR_DIR = PROJECT_ROOT / "vendor" / "chi-bench"
DATA_DIR = PROJECT_ROOT / "data"
HANDBOOK_DIR = DATA_DIR / "skills" / "managed-care-operations-handbook"

MIN_PYTHON = (3, 12)

# Runner keys for candidate models (DeepSeek, Gemini, etc.)
RUNNER_ENV_VARS = ["DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]
JUDGE_ENV_VARS = ["ANTHROPIC_API_KEY"]


def load_env_file(env_file_path: Path | str | None) -> dict[str, str]:
    """Load KEY=VALUE pairs from an env file without overriding existing process env."""
    res: dict[str, str] = {}
    if not env_file_path:
        return res
    p = Path(env_file_path).resolve()
    if not p.is_file():
        return res
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        res[k.strip()] = v.strip().strip("'\"")
    return res


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python() -> dict:
    ok = sys.version_info >= MIN_PYTHON
    return {
        "check": "python_version",
        "category": "runtime",
        "ok": ok,
        "detail": (
            f"{sys.version.split()[0]} — OK"
            if ok
            else f"{sys.version.split()[0]} — need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
        ),
        "fix": None if ok else f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+",
    }


def check_uv() -> dict:
    found = shutil.which("uv")
    return {
        "check": "uv",
        "category": "tooling",
        "ok": bool(found),
        "detail": f"uv at {found}" if found else "uv not found in PATH",
        "fix": None if found else "curl -LsSf https://astral.sh/uv/install.sh | sh",
    }


def check_git() -> dict:
    found = shutil.which("git")
    return {
        "check": "git",
        "category": "tooling",
        "ok": bool(found),
        "detail": f"git at {found}" if found else "git not found in PATH",
        "fix": None if found else "Install git",
    }


def check_docker() -> dict:
    """Check that the Docker CLI exists and the daemon is reachable."""
    cli = shutil.which("docker")
    if not cli:
        return {
            "check": "docker",
            "category": "environment",
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
            "category": "environment",
            "ok": False,
            "detail": f"docker info failed: {exc}",
            "fix": "Start Docker Desktop or the Docker daemon.",
        }
    return {
        "check": "docker",
        "category": "environment",
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
            "category": "upstream",
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
            "category": "upstream",
            "ok": False,
            "detail": f"git rev-parse failed: {exc}",
            "fix": "Ensure git is available and vendor/chi-bench is a valid clone.",
        }
    ok = actual == UPSTREAM_COMMIT
    return {
        "check": "upstream_vendor",
        "category": "upstream",
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


def check_dataset() -> dict:
    """Check that local task data is available."""
    task_dir = DATA_DIR / "prior_auth_provider" / "tasks"
    ok = task_dir.is_dir() and any(task_dir.iterdir())
    return {
        "check": "task_dataset",
        "category": "data",
        "ok": ok,
        "detail": (
            f"Public provider tasks found at {task_dir}"
            if ok
            else f"Task dataset missing at {task_dir}"
        ),
        "fix": None if ok else "Download public tasks to data/prior_auth_provider/tasks",
    }


def check_handbook(env: dict[str, str] | None = None) -> dict:
    """
    Check handbook status.
    Requires actual downloaded files on disk; an authorization flag alone
    (e.g. HF_HANDBOOK_ACCESS_GRANTED=1) does NOT prove downloaded handbook.
    """
    if env is None:
        env = os.environ  # type: ignore[assignment]
    skill_file = HANDBOOK_DIR / "SKILL.md"
    on_disk = skill_file.is_file() and skill_file.stat().st_size > 0
    granted_flag = (env.get("HF_HANDBOOK_ACCESS_GRANTED") or "").strip() == "1"

    if on_disk:
        detail = f"Handbook verified on disk at {HANDBOOK_DIR} (SKILL.md present)"
        note = "Local handbook files present and verified."
        fix = None
    elif granted_flag:
        detail = (
            "HF_HANDBOOK_ACCESS_GRANTED=1 is set, but handbook files are not downloaded on disk. "
            f"Expected SKILL.md under {HANDBOOK_DIR}."
        )
        note = "Authorization flag alone is not a downloaded/versioned handbook."
        fix = f"Download handbook to {HANDBOOK_DIR}"
    else:
        detail = (
            f"Managed-Care Operations Handbook not found on disk at {HANDBOOK_DIR}. "
            "Apply at https://huggingface.co/datasets/actava/managed-care-operations-handbook "
            "and download files."
        )
        note = "Required for medical task context in real agent execution."
        fix = f"Download handbook to {HANDBOOK_DIR}"

    return {
        "check": "handbook_access",
        "category": "data",
        "ok": on_disk,
        "detail": detail,
        "note": note,
        "fix": fix,
    }


def check_credentials(env: dict[str, str] | None = None) -> dict[str, dict]:
    """Inspect presence of runner and judge credentials without exposing values."""
    if env is None:
        env = os.environ  # type: ignore[assignment]
    res = {}
    for var in RUNNER_ENV_VARS + JUDGE_ENV_VARS:
        present = bool(env.get(var))
        res[var] = {
            "check": f"env:{var}",
            "category": "secrets",
            "ok": present,
            "detail": (
                f"{var} is set (value not shown)"
                if present
                else f"{var} is not set"
            ),
            "note": (
                "Presence confirmed; actual API connectivity not verified by this script."
                if present
                else None
            ),
            "fix": None if present else f"export {var}=<your-key>  # or add to .env",
        }
    return res


# ---------------------------------------------------------------------------
# Mode Evaluation
# ---------------------------------------------------------------------------

def evaluate_modes(env: dict[str, str] | None = None) -> dict:
    """
    Evaluate readiness for distinct modes:
      - offline: python, git, uv (does NOT require docker socket, keys, or dataset)
      - tools: offline + docker daemon + vendor checkout
      - ungraded: tools + task dataset + handbook on disk + at least 1 runner credential
      - scored: ungraded + judge credential (ANTHROPIC_API_KEY)
    """
    if env is None:
        env = os.environ  # type: ignore[assignment]

    py_chk = check_python()
    uv_chk = check_uv()
    git_chk = check_git()
    docker_chk = check_docker()
    vendor_chk = check_vendor()
    data_chk = check_dataset()
    handbook_chk = check_handbook(env)
    creds = check_credentials(env)

    # Mode 1: Offline checks (container, unit tests, config validation)
    # R4: Does NOT require docker daemon/socket, vendor checkout, or API keys.
    offline_required = [py_chk, git_chk, uv_chk]
    offline_failures = [c["detail"] for c in offline_required if not c["ok"]]
    offline_ready = len(offline_failures) == 0

    # Mode 2: Tools integration
    tools_failures = []
    if not docker_chk["ok"]:
        tools_failures.append(docker_chk["detail"])
    if not vendor_chk["ok"]:
        tools_failures.append(vendor_chk["detail"])
    tools_ready = len(tools_failures) == 0

    # Mode 3: Ungraded execution (runs task with candidate model, no official judge)
    # R5: Requires docker daemon, upstream vendor checkout, task dataset, handbook on disk,
    # and at least one candidate runner key.
    runner_key_present = any(creds[var]["ok"] for var in RUNNER_ENV_VARS)
    ungraded_failures = []
    if not docker_chk["ok"]:
        ungraded_failures.append("Docker daemon must be reachable for containerized execution.")
    if not vendor_chk["ok"]:
        ungraded_failures.append(vendor_chk["detail"])
    if not data_chk["ok"]:
        ungraded_failures.append(data_chk["detail"])
    if not handbook_chk["ok"]:
        ungraded_failures.append(handbook_chk["detail"])
    if not runner_key_present:
        ungraded_failures.append(
            f"No candidate runner API key found. Set at least one of: {', '.join(RUNNER_ENV_VARS)}"
        )
    ungraded_ready = len(ungraded_failures) == 0

    # Mode 4: Scored execution (requires Anthropic judge key)
    scored_failures = list(ungraded_failures)
    anthropic_ok = creds["ANTHROPIC_API_KEY"]["ok"]
    if not anthropic_ok:
        scored_failures.append(
            "ANTHROPIC_API_KEY is not set — required for the official Claude judge."
        )
    scored_ready = ungraded_ready and anthropic_ok

    all_checks = [
        py_chk,
        uv_chk,
        git_chk,
        docker_chk,
        vendor_chk,
        data_chk,
        handbook_chk,
    ] + list(creds.values())

    return {
        "offline": {
            "ready": offline_ready,
            "failures": offline_failures,
            "required_checks": ["python_version", "git", "uv"],
        },
        "tools": {
            "ready": tools_ready,
            "failures": tools_failures,
            "required_checks": ["docker", "upstream_vendor"],
        },
        "ungraded": {
            "ready": ungraded_ready,
            "failures": ungraded_failures,
            "required_checks": ["docker", "upstream_vendor", "task_dataset", "handbook_access", "runner_api_key"],
        },
        "scored": {
            "ready": scored_ready,
            "failures": scored_failures,
            "required_checks": ["docker", "upstream_vendor", "task_dataset", "handbook_access", "runner_api_key", "env:ANTHROPIC_API_KEY"],
        },
        "all_checks": all_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="chi-agent readiness check (no model call)")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--mode",
        choices=["offline", "tools", "ungraded", "scored", "all"],
        default="all",
        help="Readiness mode to evaluate (default: all)",
    )
    parser.add_argument(
        "--env-file",
        default=str(PROJECT_ROOT / ".env"),
        help="Path to .env file to load credentials from",
    )
    args = parser.parse_args()

    # Load env file and merge with process env
    file_env = load_env_file(args.env_file)
    effective_env = {**os.environ, **file_env}

    report = evaluate_modes(effective_env)

    target_mode = args.mode
    if target_mode == "all":
        is_ready = report["offline"]["ready"]
    else:
        is_ready = report[target_mode]["ready"]

    if args.json:
        out = {
            "mode": target_mode,
            "ready": is_ready,
            "modes": {
                k: {"ready": v["ready"], "failures": v["failures"]}
                for k, v in report.items()
                if k != "all_checks"
            },
            "checks": report["all_checks"],
        }
        print(json.dumps(out, indent=2))
        sys.exit(0 if is_ready else 1)

    print("=" * 65)
    print(f"chi-agent readiness check (Mode: {target_mode})")
    print("=" * 65)

    print("\n--- Individual Checks ---")
    for c in report["all_checks"]:
        tag = "OK " if c["ok"] else "FAIL"
        print(f"  [{tag}] {c['check']:<24}: {c['detail']}")
        if not c["ok"] and c.get("fix"):
            print(f"         → Fix: {c['fix']}")
        if c.get("note"):
            print(f"         → Note: {c['note']}")

    print("\n--- Mode Summary ---")
    for mode_name in ["offline", "tools", "ungraded", "scored"]:
        m_info = report[mode_name]
        status = "READY" if m_info["ready"] else "NOT READY"
        print(f"  [{status:<9}] {mode_name.upper():<10}")
        if not m_info["ready"]:
            for f in m_info["failures"]:
                print(f"              - {f}")

    print("\n" + "=" * 65)
    if is_ready:
        print(f"STATUS: READY for mode '{target_mode}'.")
        print("Note: Credential presence does not prove model connectivity.")
    else:
        print(f"STATUS: NOT READY for mode '{target_mode}'.")
    print("=" * 65)

    sys.exit(0 if is_ready else 1)


if __name__ == "__main__":
    main()
