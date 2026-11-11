#!/usr/bin/env python3
"""
scripts/experiments/run_baseline.py — single-task baseline entry point for chi-agent.

Wraps the upstream `cb experiment run` CLI at the pinned commit with:
  - Explicit argv construction (no shell expansion of user input)
  - Single-task enforcement via include_task_name + n_tasks=1 in the
    ExperimentConfig YAML (upstream `cb experiment run -f <yaml>`)
  - Explicit single-task validation (rejects multi-task / multi-attempt configs)
  - Forwarding finite limits (max_rounds, max_tokens, budget) into agent_kwargs
  - Offline budget decision logic (checks pre-request reservation and flags unknown usage)
  - Absolute env-file resolution ensuring child process in vendor/ loads the same file
  - Strict finite positive numbers validation (rejects NaN, Inf, <=0)
  - Mode enforcement:
    * 'scored': requires Anthropic key, executes with official verifier
    * 'ungraded': real execution blocked in D0 until verified skip-verifier entry is available;
      dry-run and offline checks fully supported
  - Robust verdict extraction:
    * Traverses trials inspecting config.json metadata and task directory names
    * Rejects ambiguous trial directories (multiple matching runs)
    * Strict binary validation: only numeric 0.0 and 1.0 accepted (rejects bool, str, NaN, 0.5)
    * Returns actual read reward/scorecard path

UPSTREAM CONTRACT (commit 4444a07fa68a4f1623f841a292a54e284fc8e7f7):
  cb experiment run -f <ExperimentConfig.yaml>
  Single-task selection:
    dataset: <path to task dataset>
    include_task_name: ["<task_name>"]
    n_tasks: 1
    n_attempts: 1
    concurrency: 1
    agent_kwargs: {max_rounds: ..., max_tokens_per_request: ..., budget_cny: ...}

Usage:
    python -m scripts.experiments.run_baseline \\
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
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from chi_agent.budget_evaluation import evaluate_budget
from scripts.experiments.baseline_gate_policy import evaluate_gate

# ---------------------------------------------------------------------------
# Constants — must match check_readiness.py and project.yaml
# ---------------------------------------------------------------------------
UPSTREAM_COMMIT = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
UPSTREAM_VERSION = "1.1.0"
PROJECT_ROOT = Path(__file__).parents[2]
VENDOR_DIR = PROJECT_ROOT / "vendor" / "chi-bench"
DATA_DIR = PROJECT_ROOT / "data"
HANDBOOK_DIR = DATA_DIR / "skills" / "managed-care-operations-handbook"
RUNS_DIR = PROJECT_ROOT / "runs"

DOMAIN_DATASET_MAP = {
    "pa_provider": "prior_auth_provider/tasks",
    "pa_um": "prior_auth_um/tasks",
    "cm": "care_management/tasks",
}

RUNNER_ENV_VARS = ["DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]
JUDGE_ENV_VARS = ["ANTHROPIC_API_KEY"]

# Slug-safe pattern: lowercase letters, digits, '-', '_'
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")

# ---------------------------------------------------------------------------
# Parameter Validation Helpers
# ---------------------------------------------------------------------------

def _validate_positive_finite(name: str, val: float | int) -> None:
    """Validate that val is a finite positive number. Rejects NaN, Inf, and non-positive numbers."""
    if not (isinstance(val, (int, float)) and math.isfinite(val) and val > 0):
        print(f"ERROR: {name} must be a finite positive number (got {val!r})")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Budget Evaluation
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Reward Extraction & Binary Validation
# ---------------------------------------------------------------------------

def extract_reward(
    output_dir: Path,
    task_name: str,
    mode: str = "scored",
) -> tuple[float | None, str | None, str, str | None]:
    """
    Extract and validate the binary reward from verifier/reward.json.

    Finds candidate trial directories by checking config.json task metadata and
    directory names (handling random suffixes and truncated names).
    Rejects ambiguous results if multiple matching trials are found.
    Strictly verifies numeric binary values (0.0 or 1.0); rejects bool, str, NaN, 0.5.

    Returns:
        (reward, scorecard_path, reason, actual_reward_path)
    """
    if mode == "ungraded":
        return None, None, "ungraded run — official verifier not executed", None

    output_path = Path(output_dir)
    reward_files = list(output_path.glob("**/verifier/reward.json"))

    matching: list[tuple[Path, Path]] = []
    unresolved: list[str] = []
    for rf in reward_files:
        trial_dir = rf.parent.parent

        # 1. Check config.json task metadata if present
        cfg_path = trial_dir / "config.json"
        matched = False
        allow_directory_fallback = not cfg_path.is_file()
        if cfg_path.is_file():
            try:
                cfg_data = json.loads(cfg_path.read_text())
                if not isinstance(cfg_data, dict):
                    raise ValueError("config.json root must be an object")
                task_info = cfg_data.get("task")
                if task_info is None:
                    allow_directory_fallback = True
                elif not isinstance(task_info, dict):
                    raise ValueError("config.json task metadata must be an object")
                else:
                    identity_values = [task_info.get(key) for key in ("path", "id", "name")]
                    identity_values = [value for value in identity_values if value is not None and value != ""]
                    if not identity_values:
                        allow_directory_fallback = True
                    else:
                        t_path, t_id, t_name = (task_info.get(k) for k in ("path", "id", "name"))
                        claims: list[bool] = []
                        if t_path not in (None, ""):
                            claims.append(
                                isinstance(t_path, str)
                                and (Path(t_path).name == task_name or t_path.endswith(f"/{task_name}"))
                            )
                        if t_id not in (None, ""):
                            claims.append(t_id == task_name)
                        if t_name not in (None, ""):
                            claims.append(t_name == task_name)
                        matched = bool(claims) and all(claims)
                        if not matched:
                            unresolved.append(f"{trial_dir}: config.json explicitly identifies a different task")
            except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
                unresolved.append(f"{trial_dir}: invalid config.json task metadata ({exc})")

        # Only metadata-free layouts may use the confirmed task__suffix convention.
        if not matched and allow_directory_fallback:
            d_name = trial_dir.name
            if d_name == task_name or (d_name.startswith(f"{task_name}__") and len(d_name) > len(task_name) + 2):
                matched = True

        if matched:
            matching.append((trial_dir, rf))

    # Reject missing or ambiguous results
    if len(matching) == 0:
        if not reward_files:
            return None, None, "reward.json not found — run may have failed before verifier", None
        detail = "; ".join(unresolved[:3])
        reason = "No reward belongs to the requested task; metadata mismatch/invalid metadata is not overridden by directory names"
        if detail:
            reason += f" ({detail})"
        return None, None, reason, None

    if len(matching) > 1:
        return (
            None,
            None,
            f"Ambiguous trial results: found {len(matching)} matching trial directories for task '{task_name}'",
            None,
        )

    trial_dir, actual_reward_path = matching[0]

    try:
        data = json.loads(actual_reward_path.read_text())
    except (json.JSONDecodeError, OSError, ValueError, OverflowError) as exc:
        return None, None, f"reward.json could not be parsed: {exc}", str(actual_reward_path)

    if not isinstance(data, dict) or "reward" not in data:
        return None, None, f"reward.json missing 'reward' key: {data!r}", str(actual_reward_path)

    raw = data["reward"]

    # Reject booleans (isinstance(True, int) is True in Python)
    if isinstance(raw, bool):
        return None, None, f"reward.json 'reward' is a boolean ({raw!r}), not a numeric binary value", str(actual_reward_path)

    # Reject strings (e.g. {"reward": "1"})
    if isinstance(raw, str):
        return None, None, f"reward.json 'reward' is a string ({raw!r}), not a numeric binary value", str(actual_reward_path)

    if not isinstance(raw, (int, float)):
        return None, None, f"reward.json 'reward' is not a number: {raw!r}", str(actual_reward_path)

    try:
        val = float(raw)
    except (OverflowError, ValueError, TypeError):
        return None, None, "reward.json 'reward' cannot be represented as a finite float", str(actual_reward_path)
    if not math.isfinite(val):
        return None, None, f"reward.json 'reward' is not a finite number: {val!r}", str(actual_reward_path)

    # Strict binary reward validation: strictly 0.0 or 1.0
    if val != 0.0 and val != 1.0:
        return None, None, f"Invalid non-binary reward value: {val!r} (expected 0.0 or 1.0)", str(actual_reward_path)

    scorecard_path = trial_dir / "verifier" / "scorecard.json"
    sc_path = str(scorecard_path) if scorecard_path.is_file() else None
    passed = (val == 1.0)
    reason = f"reward={val} ({'passed' if passed else 'not passed'})"
    return val, sc_path, reason, str(actual_reward_path)


# ---------------------------------------------------------------------------
# Prerequisite & Environment Loading
# ---------------------------------------------------------------------------

def _load_env_file(env_file_path: Path | str) -> dict[str, str]:
    """Load KEY=VALUE pairs from env_file into a dict."""
    result: dict[str, str] = {}
    p = Path(env_file_path).resolve()
    if not p.is_file():
        return result
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip().strip("'\"")
    return result


def _check_prerequisites(
    env_file_path: Path | str,
    mode: str = "ungraded",
    budget_cny: float = 5.0,
    *,
    domain: str | None = None,
    task_name: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> list[str]:
    """
    Return list of blocking prerequisite messages; empty = all clear.
    Validates checkout, dataset, handbook on disk, environment credentials, and mode support.
    """
    blocks: list[str] = []

    p_env = Path(env_file_path).resolve()
    file_env = _load_env_file(p_env)
    # File values override process environment, matching upstream load_dotenv(override=True)
    effective_env = {**os.environ, **file_env}

    # 1. Upstream vendor clone check
    git_dir = VENDOR_DIR / ".git"
    if not git_dir.exists():
        blocks.append(f"vendor/chi-bench not cloned (expected at {VENDOR_DIR})")
    else:
        try:
            r = subprocess.run(
                ["git", "-C", str(VENDOR_DIR), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            actual_sha = r.stdout.strip()
            if actual_sha != UPSTREAM_COMMIT:
                blocks.append(
                    f"vendor/chi-bench commit mismatch: HEAD={actual_sha}, want {UPSTREAM_COMMIT}"
                )
        except Exception as exc:
            blocks.append(f"Could not verify vendor/chi-bench commit: {exc}")

    # Selection, exact provider credentials, handbook revision/content integrity,
    # and execution-mode support are shared with check_readiness.py.
    gate = evaluate_gate(
        mode=mode,
        domain=domain,
        task_name=task_name,
        model=model,
        provider=provider,
        env=effective_env,
        data_dir=DATA_DIR,
        handbook_dir=HANDBOOK_DIR,
        project_config_path=PROJECT_ROOT / "project.yaml",
        source_manifest_path=DATA_DIR / "source-downloads.json",
    )
    blocks.extend(gate["failures"])

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
    max_rounds: int = 30,
    max_tokens_per_request: int = 8192,
    budget_cny: float = 5.0,
    n_tasks: int = 1,
    n_attempts: int = 1,
    concurrency: int = 1,
    environment: str = "docker",
) -> dict:
    """
    Build ExperimentConfig dictionary adhering to upstream chi-bench schema.
    Enforces single-task bounds and forwards agent limits via agent_kwargs.
    """
    if n_tasks != 1:
        raise ValueError(f"Single-task baseline must have n_tasks=1 (got {n_tasks})")
    if n_attempts != 1:
        raise ValueError(f"Single-task baseline must have n_attempts=1 (got {n_attempts})")
    if concurrency != 1:
        raise ValueError(f"Single-task baseline must have concurrency=1 (got {concurrency})")
    if not task_name:
        raise ValueError("task_name must be non-empty")

    # Forward limits into ExperimentConfig agent_kwargs
    agent_kwargs = {
        "max_rounds": str(max_rounds),
        "max_tokens_per_request": str(max_tokens_per_request),
        "budget_cny": str(budget_cny),
    }

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
        "agent_kwargs": agent_kwargs,
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
        help="Execution mode: 'ungraded' (development) or 'scored' (requires Claude judge)",
    )
    p.add_argument(
        "--provider",
        help="Optional provider assertion; must match the known prefix in --model",
    )
    p.add_argument(
        "--budget-cny",
        type=float,
        default=5.0,
        help="Runtime budget cap in CNY for first round (default: 5.0, must be finite positive)",
    )
    p.add_argument(
        "--max-rounds",
        type=int,
        default=30,
        help="Maximum agent conversation turns (default: 30, must be positive integer)",
    )
    p.add_argument(
        "--max-tokens-per-request",
        type=int,
        default=8192,
        help="Maximum generation tokens per model request (default: 8192, must be positive integer)",
    )
    p.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Multiplies all task timeouts (default: 1.0, must be finite positive)",
    )
    p.add_argument(
        "--outer-timeout",
        type=int,
        default=1800,
        help="Outer wall-clock timeout in seconds (default: 1800, must be positive integer)",
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
    # Parameter Validation (R7: Strict finite positive checks)
    # ------------------------------------------------------------------
    _validate_positive_finite("--timeout-multiplier", args.timeout_multiplier)
    _validate_positive_finite("--outer-timeout", args.outer_timeout)
    _validate_positive_finite("--budget-cny", args.budget_cny)
    _validate_positive_finite("--max-rounds", args.max_rounds)
    _validate_positive_finite("--max-tokens-per-request", args.max_tokens_per_request)

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$", args.task_name):
        print(f"ERROR: --task-name contains invalid characters: {args.task_name!r}")
        sys.exit(1)

    # R8: Early absolute resolution of env-file path
    env_file_path = Path(args.env_file).resolve()
    dataset_rel = DOMAIN_DATASET_MAP.get(args.domain, f"{args.domain}/tasks")
    dataset_dir = str(DATA_DIR / dataset_rel)

    # ------------------------------------------------------------------
    # Dry-Run Preview
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
            env_file=str(env_file_path),
            timeout_multiplier=args.timeout_multiplier,
            max_rounds=args.max_rounds,
            max_tokens_per_request=args.max_tokens_per_request,
            budget_cny=args.budget_cny,
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
        print(f"[dry-run] Resolved env file:  {env_file_path}")
        print("\n[dry-run] Generated ExperimentConfig preview:")
        import yaml
        print(yaml.dump(preview_cfg, default_flow_style=False))
        print("[dry-run] Command that would run:")
        print(f"  uv run --project {VENDOR_DIR} cb experiment run -f <run_dir>/experiment.yaml")
        print("\n[dry-run] status: dry_run/not_executed — no task started, no manifest created.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Prerequisites & Budget Gates (R1, R2, R5)
    # ------------------------------------------------------------------
    pre_budget_status, pre_budget_reason = evaluate_budget(
        args.budget_cny, args.max_rounds, args.max_tokens_per_request
    )
    blocks = _check_prerequisites(
        env_file_path,
        mode=args.mode,
        budget_cny=args.budget_cny,
        domain=args.domain,
        task_name=args.task_name,
        model=args.model,
        provider=args.provider,
    )
    if pre_budget_status != "within_budget":
        blocks.append(f"Budget gate: {pre_budget_reason}")
    if blocks:
        # Write blocked manifest to record unsupported/blocked reason if in a run context
        run_id = _make_run_id()
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"

        manifest = {
            "run_id": run_id,
            "mode": args.mode,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "blocked_before_execution",
            "exit_code": 2,
            "project_git_sha": _project_git_sha(),
            "upstream_git_sha": UPSTREAM_COMMIT,
            "upstream_version": UPSTREAM_VERSION,
            "task_name": args.task_name,
            "domain": args.domain,
            "dataset": dataset_dir,
            "agent": args.agent,
            "model": args.model,
            "n_tasks": 1,
            "budget_cny": args.budget_cny,
            "max_rounds": args.max_rounds,
            "max_tokens_per_request": args.max_tokens_per_request,
            "budget_status": pre_budget_status,
            "budget_reason": pre_budget_reason,
            "reward": None,
            "reward_reason": f"Execution blocked: {'; '.join(blocks)}",
            "blocked_prerequisites": blocks,
        }
        _write_manifest(manifest_path, manifest)

        print(f"ERROR: prerequisites / execution gate not satisfied for mode '{args.mode}':\n")
        for b in blocks:
            print(f"  • {b}")
        print(f"\nExecution BLOCKED. Manifest saved to: {manifest_path}")
        sys.exit(2)

    # ------------------------------------------------------------------
    # Run Directory & Experiment Configuration
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
        env_file=str(env_file_path),
        timeout_multiplier=args.timeout_multiplier,
        max_rounds=args.max_rounds,
        max_tokens_per_request=args.max_tokens_per_request,
        budget_cny=args.budget_cny,
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

    # Pre-execution budget status
    init_budget_status, init_budget_reason = pre_budget_status, pre_budget_reason

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
        "budget_status": init_budget_status,
        "budget_reason": init_budget_reason,
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
            "budget_status": "unverified_unknown_usage",
            "budget_reason": "Process timed out without measured token usage",
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
            "budget_status": "unverified_unknown_usage",
            "budget_reason": "Subprocess error without measured token usage",
        })
        _write_manifest(manifest_path, manifest)
        print(f"\n[run] Subprocess error: {exc}")
        sys.exit(4)

    elapsed = round(time.monotonic() - t0, 1)

    # ------------------------------------------------------------------
    # Post-Execution: Reward & Budget Evaluation
    # ------------------------------------------------------------------
    try:
        reward, scorecard_path, reward_reason, actual_reward_path = extract_reward(
            output_dir=output_dir,
            task_name=args.task_name,
            mode=args.mode,
        )
    except Exception as exc:
        # A bad verifier artifact must not strand the run in started state.
        reward, scorecard_path, actual_reward_path = None, None, None
        reward_reason = f"Result collection failed safely: {type(exc).__name__}: {exc}"

    if exit_code == 0:
        if args.mode == "ungraded":
            status = "completed"
        elif reward is not None:
            status = "completed"
        else:
            status = "incomplete_no_verdict"
    else:
        status = "process_failed"

    post_budget_status, post_budget_reason = evaluate_budget(
        args.budget_cny,
        args.max_rounds,
        args.max_tokens_per_request,
    )

    manifest.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": status,
        "exit_code": exit_code,
        "elapsed_seconds": elapsed,
        "reward": reward,
        "reward_reason": reward_reason,
        "reward_path": actual_reward_path,
        "scorecard_path": scorecard_path,
        "budget_status": post_budget_status,
        "budget_reason": post_budget_reason,
    })
    _write_manifest(manifest_path, manifest)

    print(f"\n[run] exit_code={exit_code}  elapsed={elapsed}s  status={status}")
    print(f"[run] reward={reward!r}  ({reward_reason})")
    print(f"[run] manifest: {manifest_path}")

    sys.exit(exit_code if exit_code is not None else 1)


if __name__ == "__main__":
    main()
