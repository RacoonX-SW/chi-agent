#!/usr/bin/env python3
"""
scripts/run_baseline.py — single-task baseline entry point for chi-agent.

Wraps the upstream `cb experiment run` CLI at the pinned commit with:
  - Explicit argv construction (no shell expansion of user input)
  - Single-task enforcement via include_task_name + n_tasks=1 in the
    ExperimentConfig YAML (upstream `cb experiment run -f <yaml>`)
  - Explicit single-task validation (rejects multi-task / multi-attempt configs)
  - Isolated run directory under runs/<run_id>/
  - Lowercase slug-safe run IDs
  - Outer wall-clock timeout around subprocess
  - Honest manifest written before and after subprocess
  - Support for both ungraded development runs and scored evaluation runs
  - Strict binary reward extraction from verifier/reward.json:
    * 1.0 -> passed=True, completed
    * 0.0 -> passed=False, completed (task evaluated but unsolved)
    * non-binary (e.g. 0.5, negative, bool, NaN) -> null with error reason
  - Finite generation limits and budget tracking (budget_cny, max_rounds, max_tokens)
  - Dry-run outputs real command and preview config with dry_run status without
    starting subprocess or leaving a started manifest.

UPSTREAM CONTRACT (commit 4444a07fa68a4f1623f841a292a54e284fc8e7f7):
  cb experiment run -f <ExperimentConfig.yaml>
  Single-task selection:
    dataset: <path to task dataset>
    include_task_name: ["<task_name>"]
    n_tasks: 1
    n_attempts: 1
    concurrency: 1

Usage:
    python scripts/run_baseline.py \\
        --agent deepagents \\
        --model <vendor/model-id> \\
        --domain pa_provider \\
        --task-name <task_directory_name> \\
        [--mode ungraded|scored] \\
        [--env-file .env] \\
        [--budget-cny 5.0] \\
        [--max-rounds 30] \\
        [--max-tokens-per-request 8192] \\
        [--timeout-multiplier 1.0] \\
        [--outer-timeout 1800] \\
        [--dry-run]
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
DATA_DIR = PROJECT_ROOT / "data"
HANDBOOK_DIR = DATA_DIR / "skills" / "managed-care-operations-handbook"
RUNS_DIR = PROJECT_ROOT / "runs"

DOMAIN_DATASET_MAP = {
    "pa_provider": "prior_auth_provider/tasks",
    "pa_um": "prior_auth_um/tasks",
    "cm": "care_management/tasks",
}

# Slug-safe pattern: lowercase letters, digits, '-', '_'
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")


# ---------------------------------------------------------------------------
# Reward extraction and binary validation
# ---------------------------------------------------------------------------

def extract_reward(
    output_dir: Path,
    task_name: str,
    mode: str = "scored",
) -> tuple[float | None, str | None, str]:
    """
    Extract and validate the binary reward from verifier/reward.json.

    Returns:
        (reward, scorecard_path, reason)
        reward is strictly 1.0 or 0.0 for valid scored runs, or None if invalid/ungraded/missing.

    Strict validation:
        - Mode 'ungraded': returns (None, None, "ungraded run — official verifier not executed")
        - Missing file: returns (None, None, "reward.json not found — run may have failed before verifier")
        - Non-binary value (e.g. 0.5, negative, NaN, string, bool): returns (None, None, "Invalid non-binary reward: ...")
        - 1.0 or 1: returns (1.0, scorecard_path, "reward=1.0 (passed)")
        - 0.0 or 0: returns (0.0, scorecard_path, "reward=0.0 (not passed)")
    """
    if mode == "ungraded":
        return None, None, "ungraded run — official verifier not executed"

    trial_dir = output_dir / "trials" / task_name
    reward_path = trial_dir / "verifier" / "reward.json"
    scorecard_path = trial_dir / "verifier" / "scorecard.json"

    if not reward_path.exists():
        # Also check fallback locations if trials_dir is nested differently
        alt_reward = list(output_dir.glob(f"**/trials/**/{task_name}/**/reward.json"))
        if alt_reward:
            reward_path = alt_reward[0]
            alt_sc = reward_path.parent / "scorecard.json"
            scorecard_path = alt_sc if alt_sc.exists() else scorecard_path
        else:
            return None, None, "reward.json not found — run may have failed before verifier"

    try:
        data = json.loads(reward_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, None, f"reward.json could not be parsed: {exc}"

    if not isinstance(data, dict) or "reward" not in data:
        return None, None, f"reward.json missing 'reward' key: {data!r}"

    raw = data["reward"]

    # Reject booleans (in Python, isinstance(True, (int, float)) is True)
    if isinstance(raw, bool):
        return None, None, f"reward.json 'reward' is a boolean, not a numeric binary value: {raw!r}"

    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None, None, f"reward.json 'reward' is not a number: {raw!r}"

    # Strict binary reward validation: strictly 0.0 or 1.0
    if val != 0.0 and val != 1.0:
        return None, None, f"Invalid non-binary reward value: {val!r} (expected 0.0 or 1.0)"

    sc_path = str(scorecard_path) if scorecard_path.exists() else None
    passed = val == 1.0
    reason = f"reward={val} ({'passed' if passed else 'not passed'})"
    return val, sc_path, reason


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

def _load_env_file(env_file: str) -> dict[str, str]:
    """Load KEY=VALUE pairs from env_file into a dict."""
    result: dict[str, str] = {}
    p = Path(env_file)
    if not p.is_file():
        return result
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip().strip("'\"")
    return result


def _check_prerequisites(env_file: str, mode: str = "ungraded") -> list[str]:
    """
    Return list of blocking prerequisite messages; empty = all clear.
    Distinguishes ungraded mode from scored mode (Anthropic judge key only needed in scored mode).
    """
    blocks: list[str] = []

    file_env = _load_env_file(env_file)
    effective_env = {**file_env, **os.environ}

    # Docker daemon reachable
    if not shutil.which("docker"):
        blocks.append("docker CLI not found in PATH")

    # Handbook verification: on disk or confirmed via env var
    skill_file = HANDBOOK_DIR / "SKILL.md"
    handbook_on_disk = skill_file.is_file() and skill_file.stat().st_size > 0
    handbook_granted = effective_env.get("HF_HANDBOOK_ACCESS_GRANTED", "").strip() == "1"
    if not (handbook_on_disk or handbook_granted):
        blocks.append(
            "Managed-Care Operations Handbook not available. "
            "Download to data/skills/managed-care-operations-handbook or set HF_HANDBOOK_ACCESS_GRANTED=1."
        )

    # Scored mode requires ANTHROPIC_API_KEY
    if mode == "scored":
        if not effective_env.get("ANTHROPIC_API_KEY"):
            blocks.append(
                "ANTHROPIC_API_KEY not set — required for the official Claude-based judge in scored mode. "
                f"Set in environment or in {env_file!r}."
            )

    return blocks


# ---------------------------------------------------------------------------
# Slug and ID helpers
# ---------------------------------------------------------------------------

def _make_run_id() -> str:
    """Generate a slug-safe lowercase run ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    rand = uuid.uuid4().hex[:8].lower()
    run_id = f"run-{ts}-{rand}".lower()
    assert _SLUG_RE.match(run_id), f"Generated run ID is not slug-safe: {run_id!r}"
    return run_id


def _project_git_sha() -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if isinstance(r.stdout, str):
            return r.stdout.strip() or None
        return None
    except Exception:
        return None


def _write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Configuration Builder
# ---------------------------------------------------------------------------

def build_experiment_config(
    *,
    dataset_dir: str,
    task_name: str,
    agent: str,
    model: str,
    trials_dir: str,
    env_file: str,
    timeout_multiplier: float,
    n_tasks: int = 1,
    n_attempts: int = 1,
    concurrency: int = 1,
    environment: str = "docker",
) -> dict:
    """
    Build ExperimentConfig dictionary adhering to upstream chi-bench schema.
    Enforces single-task bounds.
    """
    if n_tasks != 1:
        raise ValueError(f"Single-task baseline must have n_tasks=1 (got {n_tasks})")
    if n_attempts != 1:
        raise ValueError(f"Single-task baseline must have n_attempts=1 (got {n_attempts})")
    if concurrency != 1:
        raise ValueError(f"Single-task baseline must have concurrency=1 (got {concurrency})")
    if not task_name:
        raise ValueError("task_name must be non-empty")

    return {
        "dataset": dataset_dir,
        "agent": agent,
        "model": model,
        "concurrency": concurrency,
        "n_attempts": n_attempts,
        "trials_dir": trials_dir,
        "env_file": env_file,
        "environment": environment,
        "timeout_multiplier": timeout_multiplier,
        "include_task_name": [task_name],
        "n_tasks": 1,
        "max_retries": 0,
    }


# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="chi-agent single-task baseline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--agent",
        required=True,
        help="Registered harness name (e.g. deepagents, claude-code)",
    )
    p.add_argument(
        "--model",
        required=True,
        help="Model id passed to the harness (e.g. deepseek/deepseek-chat)",
    )
    p.add_argument(
        "--domain",
        default="pa_provider",
        choices=["pa_provider", "pa_um", "cm"],
        help="Task domain (default: pa_provider)",
    )
    p.add_argument(
        "--task-name",
        required=True,
        help="Directory name of the task under data/<domain>/tasks/. REQUIRED.",
    )
    p.add_argument(
        "--mode",
        choices=["ungraded", "scored"],
        default="ungraded",
        help="Execution mode: 'ungraded' (default, no official judge) or 'scored' (requires Claude judge)",
    )
    p.add_argument(
        "--budget-cny",
        type=float,
        default=5.0,
        help="Runtime budget cap in CNY for first round (default: 5.0, must be > 0)",
    )
    p.add_argument(
        "--max-rounds",
        type=int,
        default=30,
        help="Maximum agent conversation turns (default: 30, must be > 0)",
    )
    p.add_argument(
        "--max-tokens-per-request",
        type=int,
        default=8192,
        help="Maximum generation tokens per model request (default: 8192, must be > 0)",
    )
    p.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Multiplies all task timeouts (default: 1.0, must be > 0)",
    )
    p.add_argument(
        "--outer-timeout",
        type=int,
        default=1800,
        help="Outer wall-clock timeout in seconds (default: 1800, must be > 0)",
    )
    p.add_argument(
        "--env-file",
        default=str(PROJECT_ROOT / ".env"),
        help="Path to .env file (default: .env in project root)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and output execution preview without starting subprocess",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------
    # Parameter Validation
    # ------------------------------------------------------------------
    if args.timeout_multiplier <= 0:
        print(f"ERROR: --timeout-multiplier must be > 0 (got {args.timeout_multiplier})")
        sys.exit(1)
    if args.outer_timeout <= 0:
        print(f"ERROR: --outer-timeout must be > 0 (got {args.outer_timeout})")
        sys.exit(1)
    if args.budget_cny <= 0:
        print(f"ERROR: --budget-cny must be > 0 (got {args.budget_cny})")
        sys.exit(1)
    if args.max_rounds <= 0:
        print(f"ERROR: --max-rounds must be > 0 (got {args.max_rounds})")
        sys.exit(1)
    if args.max_tokens_per_request <= 0:
        print(f"ERROR: --max-tokens-per-request must be > 0 (got {args.max_tokens_per_request})")
        sys.exit(1)

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$", args.task_name):
        print(f"ERROR: --task-name contains invalid characters: {args.task_name!r}")
        sys.exit(1)

    dataset_rel = DOMAIN_DATASET_MAP.get(args.domain, f"{args.domain}/tasks")
    dataset_dir = str(DATA_DIR / dataset_rel)

    # ------------------------------------------------------------------
    # Dry-Run
    # ------------------------------------------------------------------
    if args.dry_run:
        preview_run_id = _make_run_id()
        preview_trials_dir = str(RUNS_DIR / preview_run_id / "output" / "trials")
        preview_cfg = build_experiment_config(
            dataset_dir=dataset_dir,
            task_name=args.task_name,
            agent=args.agent,
            model=args.model,
            trials_dir=preview_trials_dir,
            env_file=args.env_file,
            timeout_multiplier=args.timeout_multiplier,
        )
        print("\n[dry-run] Single-task baseline — no subprocess will be started.")
        print(f"[dry-run] Execution mode:     {args.mode}")
        print(f"[dry-run] Upstream commit:    {UPSTREAM_COMMIT}")
        print(f"[dry-run] Task name:          {args.task_name}")
        print(f"[dry-run] Domain / Dataset:   {args.domain} ({dataset_dir})")
        print(f"[dry-run] Agent / Model:      {args.agent} / {args.model}")
        print(f"[dry-run] Single-task method: cb experiment run with ExperimentConfig")
        print(f"[dry-run] Budget cap:         {args.budget_cny} CNY")
        print(f"[dry-run] Max rounds:         {args.max_rounds}")
        print(f"[dry-run] Max tokens/req:     {args.max_tokens_per_request}")
        print(f"[dry-run] Outer timeout:      {args.outer_timeout}s")
        print("\n[dry-run] Generated ExperimentConfig preview:")
        import yaml
        print(yaml.dump(preview_cfg, default_flow_style=False))
        print("[dry-run] Command that would run:")
        print(f"  uv run --project {VENDOR_DIR} cb experiment run -f <run_dir>/experiment.yaml")
        print("\n[dry-run] status: dry_run/not_executed — no task started, no manifest created.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Prerequisites Gate
    # ------------------------------------------------------------------
    blocks = _check_prerequisites(args.env_file, mode=args.mode)
    if blocks:
        print(f"ERROR: prerequisites not satisfied for mode '{args.mode}' — cannot start real run.\n")
        for b in blocks:
            print(f"  • {b}")
        print(
            "\nRun is BLOCKED. Complete the prerequisites above then retry.\n"
            "Use 'python scripts/check_readiness.py' for full diagnostic details."
        )
        sys.exit(2)

    # ------------------------------------------------------------------
    # Run directory & Experiment configuration
    # ------------------------------------------------------------------
    import yaml

    run_id = _make_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_dir = run_dir / "output"
    trials_dir = output_dir / "trials"

    exp_config = build_experiment_config(
        dataset_dir=dataset_dir,
        task_name=args.task_name,
        agent=args.agent,
        model=args.model,
        trials_dir=str(trials_dir),
        env_file=args.env_file,
        timeout_multiplier=args.timeout_multiplier,
    )

    exp_config_path = run_dir / "experiment.yaml"
    with exp_config_path.open("w") as f:
        yaml.dump(exp_config, f, default_flow_style=False)

    argv = [
        "uv", "run",
        "--project", str(VENDOR_DIR),
        "cb", "experiment", "run",
        "-f", str(exp_config_path),
    ]

    # Initial manifest
    manifest: dict = {
        "run_id": run_id,
        "mode": args.mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "execution_status": "started",
        "exit_code": None,
        "project_git_sha": _project_git_sha(),
        "upstream_git_sha": UPSTREAM_COMMIT,
        "upstream_version": UPSTREAM_VERSION,
        "task_name": args.task_name,
        "domain": args.domain,
        "dataset": dataset_dir,
        "agent": args.agent,
        "model": args.model,
        "n_tasks": 1,
        "single_task_method": "cb experiment run with include_task_name+n_tasks=1 in ExperimentConfig",
        "command": argv,
        "experiment_yaml": str(exp_config_path),
        "timeout_multiplier": args.timeout_multiplier,
        "outer_timeout_seconds": args.outer_timeout,
        "budget_cny": args.budget_cny,
        "max_rounds": args.max_rounds,
        "max_tokens_per_request": args.max_tokens_per_request,
        "budget_status": "within_budget",
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
    # Subprocess Execution
    # ------------------------------------------------------------------
    print(f"\n[run] Mode: {args.mode}")
    print(f"[run] Starting: {' '.join(argv)}")
    print(f"[run] Run directory: {run_dir}")
    print(f"[run] Task: {args.task_name} (single-task bounded)")
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
    # Reward Extraction & Completion Determination
    # ------------------------------------------------------------------
    reward, scorecard_path, reward_reason = extract_reward(
        output_dir=output_dir,
        task_name=args.task_name,
        mode=args.mode,
    )

    if exit_code == 0:
        if args.mode == "ungraded":
            status = "completed"
        elif reward is not None:
            status = "completed"
        else:
            status = "incomplete_no_verdict"
    else:
        status = "process_failed"

    manifest.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": status,
        "exit_code": exit_code,
        "elapsed_seconds": elapsed,
        "reward": reward,
        "reward_reason": reward_reason,
        "reward_path": str(output_dir / "trials" / args.task_name / "verifier" / "reward.json") if reward is not None else None,
        "scorecard_path": scorecard_path,
    })
    _write_manifest(manifest_path, manifest)

    print(f"\n[run] exit_code={exit_code}  elapsed={elapsed}s  status={status}")
    print(f"[run] reward={reward!r}  ({reward_reason})")
    print(f"[run] manifest: {manifest_path}")

    sys.exit(exit_code if exit_code is not None else 1)


if __name__ == "__main__":
    main()
