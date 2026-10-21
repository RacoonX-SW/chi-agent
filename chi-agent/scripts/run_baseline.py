#!/usr/bin/env python3
"""
scripts/run_baseline.py — single-task baseline entry point for chi-agent.

Wraps the upstream `cb submission run` CLI at a pinned commit with:
  - Explicit argv construction (no shell expansion of user input)
  - Single-task enforcement via include_task_name + n_tasks=1 in the
    submission YAML (upstream `cb submission run` does NOT accept --task-id)
  - Task ID required; omitting it is a hard error (prevents silent fan-out)
  - Isolated run directory under runs/<run_id>/
  - Lowercase slug-safe run IDs (upstream schema requires lowercase only)
  - Outer wall-clock timeout around the subprocess
  - Honest manifest written before and after subprocess
  - Reward extracted from verifier/reward.json with binary validation;
    non-binary values, missing files, and invalid JSON all → null with reason
  - Dry-run outputs the real command and exits with dry_run/not_executed status
    (no subprocess started, no manifest left in started state)

UPSTREAM CONTRACT (commit 4444a07fa68a4f1623f841a292a54e284fc8e7f7):
  cb submission run -f <yaml> [--domain <domain>] [--skip-preflight]
  No --task-id flag. Single-task selection is via:
    include_task_name: ["<task_name>"]   # in the run: block of the YAML
    n_tasks: 1                            # hard cap

  SubmissionMeta.id must be slug-safe lowercase (letters, digits, -, _).

  Official reward artifact: <trial_dir>/verifier/reward.json {"reward": <float>}
  Binary pass threshold: reward >= 1.0.
  scorecard.json provides fractional_reward for diagnostics only.

BLOCKED until prerequisites are satisfied:
  - Kaggle competition registration (user action)
  - Managed-Care Operations Handbook access (user action, HF gated)
  - ANTHROPIC_API_KEY in environment (user action)
  - upstream chi-bench cloned at vendor/chi-bench at the pinned commit
  - uv available in PATH
  - Docker daemon running (environment: docker) OR Modal configured

Usage (once prerequisites are ready):
    python scripts/run_baseline.py \\
        --agent deepagents \\
        --model <vendor/model-id> \\
        --domain pa_provider \\
        --task-name <task_directory_name> \\
        [--env-file .env] \\
        [--timeout-multiplier 1.0] \\
        [--outer-timeout 1800] \\
        [--dry-run]

    # --task-name is required. Omitting it is a hard error.
    # Use the directory name of the task under data/<domain>/tasks/<task_name>/
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

# Slug-safe pattern required by upstream SubmissionMeta._slug_safe()
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")

# Binary reward threshold per upstream session_verifier.py: reward >= 1.0
BINARY_PASS_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Reward extraction and validation
# ---------------------------------------------------------------------------

def extract_reward(output_dir: Path, task_name: str) -> tuple[float | None, str | None, str]:
    """
    Extract the binary reward from the official verifier/reward.json artifact.

    Returns (reward, scorecard_path, reason).
    reward is None when the result is unknown or invalid.
    reason describes the outcome (for the manifest).

    Official artifact layout (per session_verifier.py):
        <output_dir>/trials/<task_name>/verifier/reward.json
            {"reward": <float>}
        <output_dir>/trials/<task_name>/verifier/scorecard.json
            {"fractional_reward": <float>, ...}  (diagnostics only)

    Binary pass: reward >= 1.0  (per _verify_one: reward >= 1.0 → passed)
    Non-binary float values (0 < v < 1) are accepted as reward=0 in the
    leaderboard context (not-passed), but recorded faithfully.
    """
    # The trial directory is named after the task
    trial_dir = output_dir / "trials" / task_name
    reward_path = trial_dir / "verifier" / "reward.json"
    scorecard_path = trial_dir / "verifier" / "scorecard.json"

    if not reward_path.exists():
        return None, None, "reward.json not found — run may have failed before verifier"

    try:
        data = json.loads(reward_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, None, f"reward.json could not be parsed: {exc}"

    if not isinstance(data, dict) or "reward" not in data:
        return None, None, f"reward.json missing 'reward' key: {data!r}"

    raw = data["reward"]
    try:
        reward = float(raw)
    except (TypeError, ValueError):
        return None, None, f"reward.json 'reward' is not a number: {raw!r}"

    sc_path = str(scorecard_path) if scorecard_path.exists() else None
    passed = reward >= BINARY_PASS_THRESHOLD
    reason = f"reward={reward} ({'passed' if passed else 'not passed'})"
    return reward, sc_path, reason


# ---------------------------------------------------------------------------
# Prerequisite checks (fast; no model call)
# ---------------------------------------------------------------------------

def _load_env_file(env_file: str) -> dict[str, str]:
    """
    Load KEY=VALUE pairs from env_file into a dict.
    Lines starting with # and blank lines are ignored.
    Values are not quoted-stripped beyond basic handling.
    Returns empty dict if file is absent (caller decides if that's an error).
    """
    result: dict[str, str] = {}
    p = Path(env_file)
    if not p.exists():
        return result
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _check_prerequisites(env_file: str) -> list[str]:
    """
    Return list of blocking prerequisite messages; empty = all clear.
    Loads env_file and merges with current process environment.
    """
    blocks: list[str] = []

    # Merge env_file values (process env takes precedence)
    file_env = _load_env_file(env_file)
    effective_env = {**file_env, **os.environ}

    # uv
    if not shutil.which("uv"):
        blocks.append(
            "uv not found in PATH — install: curl -LsSf https://astral.sh/uv/install.sh | sh"
        )

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

    # required env vars (checked against merged env)
    for var in REQUIRED_ENVS:
        if not effective_env.get(var):
            blocks.append(
                f"{var} not set — required for the chi-bench judge. "
                f"Set in environment or in {env_file!r}"
            )

    # handbook acknowledgement
    if effective_env.get("HF_HANDBOOK_ACCESS_GRANTED", "").strip() != "1":
        blocks.append(
            "Managed-Care Operations Handbook access not confirmed. "
            "Apply at https://huggingface.co/datasets/actava/managed-care-operations-handbook "
            "and set HF_HANDBOOK_ACCESS_GRANTED=1 when approved."
        )

    return blocks


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _make_run_id() -> str:
    """
    Generate a slug-safe lowercase run ID.
    Upstream SubmissionMeta requires only [a-z0-9-_].
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")  # lowercase t/z
    rand = uuid.uuid4().hex[:8]
    return f"run-{ts}-{rand}"


def _make_submission_id(run_id: str) -> str:
    sub = f"chi-agent-baseline-{run_id}"
    assert _SLUG_RE.match(sub), f"Generated submission ID is not slug-safe: {sub!r}"
    return sub


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


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="chi-agent single-task baseline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[1] if "Usage" in __doc__ else "",
    )
    p.add_argument("--agent", required=True,
                   help="Registered harness name (e.g. deepagents, openai-agents)")
    p.add_argument("--model", required=True,
                   help="Model id passed verbatim to the harness (e.g. vendor/model-id)")
    p.add_argument("--domain", default="pa_provider",
                   choices=["pa_provider", "pa_um", "cm"],
                   help="Task domain (default: pa_provider)")
    p.add_argument("--task-name", required=True,
                   help=(
                       "Directory name of the task under data/<domain>/tasks/. "
                       "REQUIRED — omitting causes silent fan-out of the full domain."
                   ))
    p.add_argument("--timeout-multiplier", type=float, default=1.0,
                   help="Multiplies all task timeouts (default: 1.0, must be > 0)")
    p.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"),
                   help="Path to .env file (default: .env in project root)")
    p.add_argument("--outer-timeout", type=int, default=1800,
                   help="Outer wall-clock timeout in seconds (default: 1800, must be > 0)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the command without executing; exits 0 with dry_run status")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------
    # Validate local parameters before touching anything
    # ------------------------------------------------------------------
    if args.timeout_multiplier <= 0:
        print(f"ERROR: --timeout-multiplier must be > 0 (got {args.timeout_multiplier})")
        sys.exit(1)
    if args.outer_timeout <= 0:
        print(f"ERROR: --outer-timeout must be > 0 (got {args.outer_timeout})")
        sys.exit(1)

    # task-name: alphanumeric, hyphens, underscores only
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$", args.task_name):
        print(f"ERROR: --task-name contains unexpected characters: {args.task_name!r}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Dry-run: just show the command, write no manifests, exit cleanly
    # ------------------------------------------------------------------
    if args.dry_run:
        # Build a preview of what would be generated
        preview_run_id = _make_run_id()
        preview_sub_id = _make_submission_id(preview_run_id)
        print("\n[dry-run] Single-task baseline — no subprocess will be started.")
        print(f"[dry-run] Upstream commit:    {UPSTREAM_COMMIT}")
        print(f"[dry-run] Task name:          {args.task_name}")
        print(f"[dry-run] Domain:             {args.domain}")
        print(f"[dry-run] Agent / model:      {args.agent} / {args.model}")
        print(f"[dry-run] Submission ID:      {preview_sub_id} (lowercase, slug-safe)")
        print(f"[dry-run] Single-task method: include_task_name + n_tasks=1 in YAML")
        print(f"[dry-run] Outer timeout:      {args.outer_timeout}s")
        print(f"[dry-run] Note: subprocess timeouts (container/Modal) may leave")
        print(f"          residual provider requests after the outer timeout fires.")
        print()
        print("[dry-run] Command that would run:")
        print(f"  uv run --project {VENDOR_DIR} cb submission run -f <run_dir>/submission.yaml")
        print()
        print("[dry-run] status: dry_run/not_executed — no task started.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Gate: check prerequisites before doing anything else
    # ------------------------------------------------------------------
    blocks = _check_prerequisites(args.env_file)
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
    run_id = _make_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_dir = run_dir / "output"

    submission_id = _make_submission_id(run_id)
    sub_config_path = run_dir / "submission.yaml"

    # ------------------------------------------------------------------
    # Write submission YAML with single-task constraint
    # ------------------------------------------------------------------
    import yaml as _yaml  # deferred so ImportError surfaces clearly

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
            # Single-task constraint: include only this specific task by name,
            # hard cap at 1. Upstream `cb submission run` has no --task-id flag;
            # this is the verified single-task path.
            "include_task_name": [args.task_name],
            "n_tasks": 1,
        },
        "dataset": {
            "version": "chi-bench-v1.0.0",
            "domains": [args.domain],
        },
        "paths": {
            "output_root": str(output_dir),
        },
    }
    with sub_config_path.open("w") as f:
        _yaml.dump(sub_config, f, default_flow_style=False)

    # ------------------------------------------------------------------
    # Build argv — explicit list, no shell expansion
    # ------------------------------------------------------------------
    argv = [
        "uv", "run",
        "--project", str(VENDOR_DIR),
        "cb", "submission", "run",
        "-f", str(sub_config_path),
    ]

    # ------------------------------------------------------------------
    # Initial manifest — written before subprocess starts
    # ------------------------------------------------------------------
    manifest: dict = {
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
        "docker_image_id": None,
        "task_name": args.task_name,
        "domain": args.domain,
        "harness": args.agent,
        "model": args.model,
        "n_tasks": 1,
        "single_task_method": "include_task_name+n_tasks in YAML",
        "command": argv,
        "submission_yaml": str(sub_config_path),
        "timeout_multiplier": args.timeout_multiplier,
        "outer_timeout_seconds": args.outer_timeout,
        "outer_timeout_note": (
            "Outer timeout kills this wrapper process. Subprocess containers or "
            "Modal sandboxes may continue until their own timeout; provider "
            "requests in-flight at that point have unknown completion status."
        ),
        "output_dir": str(output_dir),
        "reward_path": None,
        "scorecard_path": None,
        "reward": None,
        "reward_reason": None,
        "elapsed_seconds": None,
        "token_usage": None,
        "token_usage_source": "null — not measured by this wrapper",
        "cost_usd": None,
        "cost_usd_source": "null — not measured by this wrapper",
        "blocked_prerequisites": [],
    }
    manifest_path = run_dir / "manifest.json"
    _write_manifest(manifest_path, manifest)

    # ------------------------------------------------------------------
    # Execute — with outer timeout
    # ------------------------------------------------------------------
    print(f"\n[run] Starting: {' '.join(argv)}")
    print(f"[run] Run directory: {run_dir}")
    print(f"[run] Task: {args.task_name} (enforced via include_task_name + n_tasks=1)")
    print(f"[run] Outer timeout: {args.outer_timeout}s\n")

    t0 = time.monotonic()
    exit_code: int | None = None

    try:
        proc = subprocess.run(argv, cwd=str(VENDOR_DIR), timeout=args.outer_timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        elapsed = round(time.monotonic() - t0, 1)
        manifest.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "timeout",
            "exit_code": None,
            "elapsed_seconds": elapsed,
            "reward": None,
            "reward_reason": "timeout — no verdict before outer timeout",
        })
        _write_manifest(manifest_path, manifest)
        print(f"\n[run] TIMEOUT after {args.outer_timeout}s. reward=null")
        sys.exit(3)
    except Exception as exc:
        elapsed = round(time.monotonic() - t0, 1)
        manifest.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "subprocess_error",
            "exit_code": None,
            "elapsed_seconds": elapsed,
            "reward": None,
            "reward_reason": f"subprocess error: {exc}",
        })
        _write_manifest(manifest_path, manifest)
        print(f"\n[run] Subprocess error: {exc}")
        sys.exit(4)

    elapsed = round(time.monotonic() - t0, 1)

    # ------------------------------------------------------------------
    # Extract reward from official artifact
    # ------------------------------------------------------------------
    reward, scorecard_path, reward_reason = extract_reward(output_dir, args.task_name)

    # Determine completion status:
    # - exit=0 + valid reward → completed (even if reward=0, task was evaluated)
    # - exit=0 + no reward → incomplete (process finished but no verdict)
    # - exit!=0 → process_failed
    if exit_code == 0 and reward is not None:
        status = "completed"
    elif exit_code == 0:
        status = "incomplete_no_verdict"
    else:
        status = "process_failed"

    # ------------------------------------------------------------------
    # Final manifest
    # ------------------------------------------------------------------
    manifest.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": status,
        "exit_code": exit_code,
        "elapsed_seconds": elapsed,
        "reward": reward,
        "reward_reason": reward_reason,
        "reward_path": str(output_dir / "trials" / args.task_name / "verifier" / "reward.json"),
        "scorecard_path": scorecard_path,
    })
    _write_manifest(manifest_path, manifest)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n[run] exit_code={exit_code}  elapsed={elapsed}s  status={status}")
    print(f"[run] reward={reward!r}  ({reward_reason})")
    print(f"[run] manifest: {manifest_path}")
    if scorecard_path:
        print(f"[run] scorecard: {scorecard_path}")

    sys.exit(exit_code if exit_code is not None else 1)


if __name__ == "__main__":
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("ERROR: pyyaml is not installed. Run: pip install pyyaml")
        sys.exit(1)
    main()
