#!/usr/bin/env python3
"""
scripts/run_baseline.py — single-task baseline entry point for chi-agent.

Wraps the upstream `cb submission run` CLI at a pinned commit with:
  - Explicit argv construction (no shell expansion of user input)
  - Isolated run directory under runs/<run_id>/
  - Hard task count = 1 and configurable timeout multiplier
  - Honest manifest written before and after the subprocess
  - Reward and usage retained as null when absent or unknown

BLOCKED until prerequisites are satisfied:
  - Kaggle competition registration
  - Managed-Care Operations Handbook access (HuggingFace gated dataset)
  - ANTHROPIC_API_KEY in environment
  - upstream chi-bench cloned at vendor/chi-bench at the pinned commit
  - `uv` available (chi-bench uses uv for its CLI)
  - Docker daemon running (environment: docker) OR Modal configured

Usage (once prerequisites are ready):
    python scripts/run_baseline.py \\
        --agent deepagents \\
        --model <vendor/model-id> \\
        --domain pa_provider \\
        --task-id <task_id> \\
        --timeout-multiplier 1.0

Run with --dry-run to print the command that would be executed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — must match check_readiness.py and project.yaml
# ---------------------------------------------------------------------------
UPSTREAM_COMMIT = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
UPSTREAM_VERSION = "1.1.0"
PROJECT_ROOT = Path(__file__).parent.parent
VENDOR_DIR = PROJECT_ROOT / "vendor" / "chi-bench"
RUNS_DIR = PROJECT_ROOT / "runs"

REQUIRED_ENVS = ["ANTHROPIC_API_KEY"]


# ---------------------------------------------------------------------------
# Prerequisite checks (fast; no model call)
# ---------------------------------------------------------------------------

def _check_prerequisites() -> list[str]:
    """Return list of blocking prerequisite messages, empty = all clear."""
    blocks: list[str] = []

    # uv
    if not shutil.which("uv"):
        blocks.append("uv not found in PATH — install: curl -LsSf https://astral.sh/uv/install.sh | sh")

    # vendor clone at pinned commit
    git_dir = VENDOR_DIR / ".git"
    if not git_dir.exists():
        blocks.append(
            f"vendor/chi-bench not cloned — run: "
            f"git clone https://github.com/actava-ai/chi-bench {VENDOR_DIR} "
            f"&& git -C {VENDOR_DIR} checkout {UPSTREAM_COMMIT}"
        )
    else:
        try:
            r = subprocess.run(
                ["git", "-C", str(VENDOR_DIR), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            actual = r.stdout.strip()
            if actual != UPSTREAM_COMMIT:
                blocks.append(
                    f"vendor/chi-bench HEAD={actual}, want {UPSTREAM_COMMIT} — "
                    f"run: git -C {VENDOR_DIR} checkout {UPSTREAM_COMMIT}"
                )
        except Exception as exc:
            blocks.append(f"Could not verify vendor commit: {exc}")

    # required env vars
    for var in REQUIRED_ENVS:
        if not os.environ.get(var):
            blocks.append(f"{var} not set — required for the chi-bench judge")

    # handbook acknowledgement
    if os.environ.get("HF_HANDBOOK_ACCESS_GRANTED", "").strip() != "1":
        blocks.append(
            "Managed-Care Operations Handbook access not confirmed. "
            "Apply at https://huggingface.co/datasets/actava/managed-care-operations-handbook "
            "and set HF_HANDBOOK_ACCESS_GRANTED=1 when approved."
        )

    return blocks


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def _project_git_sha() -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def _write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    print(f"[manifest] written to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="chi-agent single-task baseline runner")
    p.add_argument("--agent", required=True,
                   help="Registered harness name (e.g. deepagents, openai-agents)")
    p.add_argument("--model", required=True,
                   help="Model id passed verbatim to the harness (e.g. vendor/model-id)")
    p.add_argument("--domain", default="pa_provider",
                   choices=["pa_provider", "pa_um", "cm"],
                   help="Task domain (default: pa_provider)")
    p.add_argument("--task-id", default=None,
                   help="Specific task id (optional; runs the first available task if omitted)")
    p.add_argument("--timeout-multiplier", type=float, default=1.0,
                   help="Multiplies all task timeouts (default: 1.0)")
    p.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"),
                   help="Path to .env file passed to chi-bench (default: .env)")
    p.add_argument("--outer-timeout", type=int, default=1800,
                   help="Outer wall-clock timeout in seconds (default: 1800)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the command without executing it")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------
    # Gate: check prerequisites before doing anything
    # ------------------------------------------------------------------
    blocks = _check_prerequisites()
    if blocks:
        print("ERROR: prerequisites not satisfied — cannot start a real run.\n")
        for b in blocks:
            print(f"  • {b}")
        print(
            "\nThis run is BLOCKED. Complete the above prerequisites then retry.\n"
            "Use scripts/check_readiness.py for a full readiness report."
        )
        sys.exit(2)

    # ------------------------------------------------------------------
    # Set up isolated run directory
    # ------------------------------------------------------------------
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Submission config written into the run directory so each run is isolated
    submission_id = f"chi-agent-baseline-{run_id}"
    sub_config_path = run_dir / "submission.yaml"
    sub_config = {
        "schema": "chi-bench/submission/v1",
        "submission": {
            "id": submission_id,
            "team": "chi-agent",
            "contact": "",
            "agent": args.agent,
            "model": args.model,
            "notes": f"Single-task baseline. run_id={run_id}",
        },
        "run": {
            "environment": "docker",
            "n_attempts": 1,
            "concurrency": 1,
            "max_retries": 0,
            "timeout_multiplier": args.timeout_multiplier,
            "env_file": args.env_file,
        },
        "dataset": {
            "version": "chi-bench-v1.0.0",
            "domains": [args.domain],
        },
        "paths": {
            "output_root": str(run_dir / "output"),
        },
    }
    import yaml as _yaml  # noqa: E402 — deferred so import errors surface clearly
    with sub_config_path.open("w") as f:
        _yaml.dump(sub_config, f, default_flow_style=False)

    # ------------------------------------------------------------------
    # Build argv for upstream CLI — no shell expansion of user input
    # ------------------------------------------------------------------
    argv = [
        "uv", "run",
        "--project", str(VENDOR_DIR),
        "cb", "submission", "run",
        "-f", str(sub_config_path),
    ]
    if args.task_id:
        # Validate task_id format before passing (alphanumeric + hyphens/underscores only)
        if not all(c.isalnum() or c in "-_" for c in args.task_id):
            print(f"ERROR: --task-id contains unexpected characters: {args.task_id!r}")
            sys.exit(1)
        argv.extend(["--task-id", args.task_id])

    # ------------------------------------------------------------------
    # Initial manifest — before subprocess starts
    # ------------------------------------------------------------------
    manifest = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "execution_status": "started",
        "exit_code": None,
        "project_git_sha": _project_git_sha(),
        "upstream_git_sha": UPSTREAM_COMMIT,
        "upstream_version": UPSTREAM_VERSION,
        "upstream_repo": "https://github.com/actava-ai/chi-bench",
        "data_version": "chi-bench-v1.0.0",
        "docker_image_id": None,   # populated post-run if available
        "task_id": args.task_id,
        "domain": args.domain,
        "harness": args.agent,
        "model": args.model,
        "n_tasks": 1,
        "command": argv,
        "timeout_multiplier": args.timeout_multiplier,
        "outer_timeout_seconds": args.outer_timeout,
        "output_dir": str(run_dir / "output"),
        "scorecard_path": None,
        "reward": None,            # set after run; null if unavailable
        "elapsed_seconds": None,
        "token_usage": None,       # null — source not yet available
        "token_usage_source": None,
        "cost_usd": None,          # null — source not yet available
        "cost_usd_source": None,
        "blocked_prerequisites": [],
    }
    manifest_path = run_dir / "manifest.json"
    _write_manifest(manifest_path, manifest)

    if args.dry_run:
        print("\n[dry-run] Would execute:")
        print("  " + " ".join(argv))
        print(f"\n[dry-run] Run directory: {run_dir}")
        print("[dry-run] No subprocess was started.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Execute — with outer timeout
    # ------------------------------------------------------------------
    print(f"\n[run] Starting: {' '.join(argv)}")
    print(f"[run] Directory: {run_dir}")
    print(f"[run] Outer timeout: {args.outer_timeout}s\n")

    t0 = time.monotonic()
    exit_code: int | None = None
    try:
        proc = subprocess.run(
            argv,
            cwd=str(VENDOR_DIR),
            timeout=args.outer_timeout,
        )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        manifest["execution_status"] = "timeout"
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest["elapsed_seconds"] = round(time.monotonic() - t0, 1)
        manifest["exit_code"] = None
        manifest["reward"] = None
        _write_manifest(manifest_path, manifest)
        print(f"\n[run] TIMEOUT after {args.outer_timeout}s.")
        print("[run] reward=null (no valid verdict before timeout)")
        sys.exit(3)
    except Exception as exc:
        manifest["execution_status"] = "subprocess_error"
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest["elapsed_seconds"] = round(time.monotonic() - t0, 1)
        manifest["exit_code"] = None
        manifest["reward"] = None
        _write_manifest(manifest_path, manifest)
        print(f"\n[run] Subprocess error: {exc}")
        sys.exit(4)

    elapsed = round(time.monotonic() - t0, 1)

    # ------------------------------------------------------------------
    # Collect verdict from scorecard (best-effort)
    # ------------------------------------------------------------------
    reward: float | None = None
    scorecard_path: str | None = None

    output_dir = run_dir / "output"
    # chi-bench writes scorecards under output_root/submissions/<id>/packet/...
    # Search for any scorecard JSON to avoid hard-coding paths that may change.
    scorecard_candidates = list(output_dir.rglob("scorecard*.json")) if output_dir.exists() else []
    if scorecard_candidates:
        scorecard_path = str(scorecard_candidates[0])
        try:
            with open(scorecard_path) as f:
                sc = json.load(f)
            # chi-bench scorecard schema: top-level "reward" or nested
            reward = sc.get("reward")
        except Exception:
            reward = None  # parse failure → reward stays null

    # ------------------------------------------------------------------
    # Final manifest
    # ------------------------------------------------------------------
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["execution_status"] = "completed" if exit_code == 0 else "process_failed"
    manifest["exit_code"] = exit_code
    manifest["elapsed_seconds"] = elapsed
    manifest["reward"] = reward
    manifest["scorecard_path"] = scorecard_path
    # token_usage and cost_usd remain null — no trusted source available from this wrapper
    manifest["token_usage_source"] = "null — not measured by this wrapper"
    manifest["cost_usd_source"] = "null — not measured by this wrapper"
    _write_manifest(manifest_path, manifest)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n[run] exit_code={exit_code}  elapsed={elapsed}s")
    print(f"[run] reward={reward!r}  (null means no valid official verdict was found)")
    print(f"[run] manifest: {manifest_path}")
    if scorecard_path:
        print(f"[run] scorecard: {scorecard_path}")

    if reward is None and exit_code == 0:
        print("[run] WARNING: process exited 0 but no reward found in scorecard — run may be incomplete.")

    sys.exit(exit_code if exit_code is not None else 1)


if __name__ == "__main__":
    # Defer yaml import so an informative error is shown if pyyaml is absent
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("ERROR: pyyaml is not installed. Run: pip install pyyaml")
        sys.exit(1)
    main()
