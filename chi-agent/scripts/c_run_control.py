"""Offline stage-C lifecycle controller.

This module does not execute the official benchmark. ``plan`` is read-only,
``rehearse`` uses only an in-memory synthetic backend, and ``live`` is disabled.
The exclusive claim and evidence files are local control records, not proof of a
real task attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import time
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from run_baseline import build_experiment_config, evaluate_budget

TASK_ID = "pa_t018_t018_o001_p01_new_referral_provider"
DOMAIN = "pa_provider"
UPSTREAM_SHA = "4444a07fa68a4f1623f841a292a54e284fc8e7f7"
UPSTREAM_VERSION = "1.1.0"
CAMPAIGN_ID = "bootstrap-baseline-c"
CAP_CNY = 5.0
MAX_ROUNDS = 30
MAX_OUTPUT_TOKENS = 8192
MAX_TASK_SECONDS = 900
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SCENARIOS = frozenset({"success", "runner-rejection", "timeout", "partial-create", "cleanup-failure", "unknown-budget", "missing-usage"})


class ControlError(ValueError):
    pass


class LiveExecutionDisabled(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _positive_int(name: str, value: Any, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
        raise ControlError(f"{name} must be an integer from 1 to {ceiling}")
    return value


def _safe_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ControlError(f"{name} must be a lowercase slug of at most 64 characters")
    return value


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    agent: str
    model: str
    dataset_dir: str = "/synthetic/public-task-dataset"
    env_file: str = "/synthetic/no-env-file"
    max_rounds: int = MAX_ROUNDS
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    max_input_tokens: int = 8192
    timeout_seconds: int = MAX_TASK_SECONDS
    attempts: int = 1
    concurrency: int = 1
    retries: int = 0

    def validate(self) -> None:
        _safe_id("run_id", self.run_id)
        if not isinstance(self.agent, str) or not self.agent.strip():
            raise ControlError("agent must be explicitly provided")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ControlError("model must be explicitly provided")
        if self.dataset_dir != "/synthetic/public-task-dataset" or self.env_file != "/synthetic/no-env-file":
            raise ControlError("offline rehearsal accepts only the fixed synthetic paths")
        _positive_int("max_rounds", self.max_rounds, MAX_ROUNDS)
        _positive_int("max_output_tokens", self.max_output_tokens, MAX_OUTPUT_TOKENS)
        _positive_int("max_input_tokens", self.max_input_tokens, 1_000_000)
        _positive_int("timeout_seconds", self.timeout_seconds, MAX_TASK_SECONDS)
        if self.attempts != 1 or isinstance(self.attempts, bool):
            raise ControlError("attempts must equal 1")
        if self.concurrency != 1 or isinstance(self.concurrency, bool):
            raise ControlError("concurrency must equal 1")
        if self.retries != 0 or isinstance(self.retries, bool):
            raise ControlError("retries must equal 0")


@dataclass(frozen=True)
class BudgetEvidence:
    prior_b_spend_cny: float | None
    prior_b_source: str | None
    input_price_usd_per_million: float | None
    output_price_usd_per_million: float | None
    pricing_version: str | None
    usd_to_cny: float | None
    fx_source: str | None

    def evaluate(self, spec: RunSpec) -> tuple[str, str]:
        return evaluate_budget(
            CAP_CNY,
            spec.max_rounds,
            spec.max_output_tokens,
            cumulative_cost_cny=self.prior_b_spend_cny,
            input_price_usd_per_million=self.input_price_usd_per_million,
            output_price_usd_per_million=self.output_price_usd_per_million,
            max_input_tokens_per_request=spec.max_input_tokens,
            usd_to_cny=self.usd_to_cny,
            pricing_version=self.pricing_version,
            fx_rate_source=self.fx_source,
        )


@dataclass(frozen=True)
class OwnedHandle:
    resource_id: str
    owned: bool


class OwnedHandleError(RuntimeError):
    def __init__(self, handle: OwnedHandle | None = None):
        super().__init__("synthetic world creation failed")
        self.handle = handle


@dataclass(frozen=True)
class BackendResult:
    exit_code: int
    usage: dict[str, int] | None
    synthetic_cost_cny: float | None
    synthetic_cost_source: str | None
    known_prefix_usage: dict[str, int] | None = None


class Backend(Protocol):
    def create_world(self, spec: RunSpec) -> OwnedHandle: ...
    def run_once(self, handle: OwnedHandle, spec: RunSpec) -> BackendResult: ...
    def cleanup(self, handle: OwnedHandle) -> None: ...


class SyntheticBackend:
    """Tiny in-memory fixture backend; it has no external service hooks."""

    def __init__(self, scenario: str = "success") -> None:
        if scenario not in _SCENARIOS:
            raise ControlError("unknown synthetic scenario")
        self.scenario = scenario
        self.calls: list[str] = []

    def create_world(self, spec: RunSpec) -> OwnedHandle:
        self.calls.append("create_world")
        if self.scenario == "partial-create":
            raise OwnedHandleError(OwnedHandle(f"synthetic-{spec.run_id}", True))
        return OwnedHandle(f"synthetic-{spec.run_id}", True)

    def run_once(self, handle: OwnedHandle, spec: RunSpec) -> BackendResult:
        self.calls.append("run_once")
        if self.scenario == "timeout":
            raise TimeoutError("synthetic timeout")
        if self.scenario == "missing-usage":
            return BackendResult(0, None, None, None, {"input_tokens": 0, "output_tokens": 0})
        if self.scenario == "runner-rejection":
            return BackendResult(1, {"input_tokens": 10, "output_tokens": 5}, 0.000108, "fixed-local-fixture-v1")
        return BackendResult(0, {"input_tokens": 10, "output_tokens": 5}, 0.000108, "fixed-local-fixture-v1")

    def cleanup(self, handle: OwnedHandle) -> None:
        self.calls.append("cleanup")
        if self.scenario == "cleanup-failure":
            raise RuntimeError("synthetic cleanup failure")


def _scope_key(namespace: str) -> str:
    raw = f"{CAMPAIGN_ID}\0{TASK_ID}\0{UPSTREAM_SHA}".encode()
    return f"{namespace}-{hashlib.sha256(raw).hexdigest()}"


def _experiment_config(spec: RunSpec) -> dict[str, Any]:
    return build_experiment_config(
        dataset_dir=spec.dataset_dir,
        task_name=TASK_ID,
        agent=spec.agent,
        model=spec.model,
        trials_dir=f"/synthetic/trials/{spec.run_id}",
        env_file=spec.env_file,
        timeout_multiplier=1.0,
        max_rounds=spec.max_rounds,
        max_tokens_per_request=spec.max_output_tokens,
        budget_cny=CAP_CNY,
        n_tasks=1,
        n_attempts=spec.attempts,
        concurrency=spec.concurrency,
    )


def _candidate(spec: RunSpec) -> dict[str, str]:
    return {"agent": spec.agent, "model": spec.model, "selection_status": "configured_unverified"}


def _requested_limits(spec: RunSpec) -> dict[str, Any]:
    return {
        "max_rounds": spec.max_rounds,
        "max_input_tokens": spec.max_input_tokens,
        "max_output_tokens": spec.max_output_tokens,
        "task_timeout_seconds": spec.timeout_seconds,
        "attempts": 1,
        "concurrency": 1,
        "retries": 0,
        "enforcement_status": "configured_unverified",
    }


def _budget_record(budget: BudgetEvidence) -> dict[str, Any]:
    return {
        "prior_b_spend_cny": budget.prior_b_spend_cny,
        "prior_b_source": budget.prior_b_source,
        "input_price_usd_per_million": budget.input_price_usd_per_million,
        "output_price_usd_per_million": budget.output_price_usd_per_million,
        "pricing_version": budget.pricing_version,
        "usd_to_cny": budget.usd_to_cny,
        "fx_source": budget.fx_source,
        "provenance": "synthetic_fixture_only",
    }


def _real_unknown(reason: str) -> dict[str, Any]:
    return {"real_provider_usage": None, "real_provider_cost_cny": None,
            "real_shared_budget": {"status": "unknown", "reason": reason}, "official_reward": None,
            "task_success": "unknown"}


def plan(spec: RunSpec, budget: BudgetEvidence | None = None) -> dict[str, Any]:
    """Return a pure preview; never inspect or mutate filesystem/claim state."""
    spec.validate()
    budget_status, budget_reason = budget.evaluate(spec) if budget else (
        "unverified_unknown_usage", "prior B spend, pricing and conversion evidence were not supplied"
    )
    return {
        "status": "planned",
        "provenance": "offline_plan",
        "task_id": TASK_ID,
        "domain": DOMAIN,
        "candidate": _candidate(spec),
        "requested_limits": _requested_limits(spec),
        "experiment_config": _experiment_config(spec),
        "budget_preflight": {"status": budget_status, "reason": budget_reason, "cap_cny": CAP_CNY},
        **_real_unknown("offline planning has no verified real B spend or billing evidence"),
    }


def _safe_output_root(root: Path) -> Path:
    candidate = root.expanduser()
    if not candidate.is_absolute():
        raise ControlError("output root must be absolute")
    return candidate


def _ensure_directory(path: Path) -> None:
    """Create a directory tree without following an existing symlink."""
    if not path.is_absolute():
        raise ControlError("evidence directory must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir()
            except FileExistsError:
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                    raise ControlError("evidence path contains a non-directory or symlink")
        else:
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ControlError("evidence path contains a non-directory or symlink")


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _synthetic_budget() -> BudgetEvidence:
    return BudgetEvidence(0.25, "fixed-local-synthetic-fixture-v1", 1.0, 1.0, "fixed-local-synthetic-fixture-v1", 7.2, "fixed-local-synthetic-fixture-v1")


def _priced_cost(usage: dict[str, int] | None, budget: BudgetEvidence) -> float | None:
    if not _valid_usage(usage):
        return None
    if any(value is None for value in (
        budget.input_price_usd_per_million,
        budget.output_price_usd_per_million,
        budget.usd_to_cny,
    )):
        return None
    return (
        usage["input_tokens"] * float(budget.input_price_usd_per_million)
        + usage["output_tokens"] * float(budget.output_price_usd_per_million)
    ) / 1_000_000 * float(budget.usd_to_cny)


def _synthetic_accounting(result: BackendResult, budget: BudgetEvidence) -> dict[str, Any]:
    known_prefix = result.known_prefix_usage if _valid_usage(result.known_prefix_usage) else None
    prefix_cost = _priced_cost(known_prefix, budget)
    prior = budget.prior_b_spend_cny if budget.prior_b_spend_cny is not None else None
    known_prefix_total = prior + prefix_cost if prior is not None and prefix_cost is not None else None
    valid_usage = _valid_usage(result.usage)
    measured_cost = _priced_cost(result.usage, budget)
    reported_cost = result.synthetic_cost_cny
    cost_matches = (
        measured_cost is not None
        and reported_cost is not None
        and math.isclose(float(reported_cost), measured_cost, rel_tol=1e-9, abs_tol=1e-12)
        and isinstance(result.synthetic_cost_source, str)
        and bool(result.synthetic_cost_source.strip())
    )
    complete = valid_usage and cost_matches and prior is not None
    return {
        "provenance": "synthetic_fixture_only",
        "status": "complete" if complete else "incomplete_unknown",
        "synthetic_usage": result.usage if valid_usage else None,
        "synthetic_total_cost_cny": prior + float(reported_cost) if complete else None,
        "synthetic_known_prefix_usage": known_prefix,
        "synthetic_known_prefix_cost_cny": known_prefix_total,
        "synthetic_cost_source": result.synthetic_cost_source if complete else None,
        "real_usage": None,
        "real_cost_cny": None,
    }


def rehearse(
    spec: RunSpec,
    *,
    root: Path,
    backend: Backend | None = None,
    scenario: str = "success",
    budget: BudgetEvidence | None = None,
) -> dict[str, Any]:
    """Run one explicitly synthetic lifecycle, retaining claim and evidence."""
    spec.validate()
    backend = backend or SyntheticBackend(scenario)
    budget = budget or (_synthetic_budget() if scenario not in {"unknown-budget"} else BudgetEvidence(None, None, None, None, None, None, None))
    budget_status, budget_reason = budget.evaluate(spec)
    output_root = _safe_output_root(root)
    run_dir = output_root / "runs" / spec.run_id
    if os.path.lexists(run_dir):
        raise ControlError("run identity already has evidence; refusing overwrite")
    _ensure_directory(output_root)
    _ensure_directory(run_dir.parent)
    if budget_status != "within_budget":
        run_dir.mkdir(exist_ok=False)
        result = {
            "schema_version": 1,
            "provenance": "synthetic_rehearsal",
            "run_id": spec.run_id,
            "status": "preflight_blocked",
            "phase": "preflight",
            "budget_preflight": {"status": budget_status, "reason": budget_reason, "cap_cny": CAP_CNY},
            "candidate": _candidate(spec),
            "synthetic_budget": _budget_record(budget),
            "synthetic_accounting": {
                "status": "incomplete_unknown",
                "synthetic_usage": None,
                "synthetic_total_cost_cny": None,
                "synthetic_known_prefix_usage": None,
                "synthetic_known_prefix_cost_cny": None,
                "real_usage": None,
                "real_cost_cny": None,
            },
            **_real_unknown("synthetic fixture accounting is isolated from real B/C spend"),
            "attempt_claimed": False,
        }
        _atomic_json(run_dir / "manifest.json", result)
        return result

    run_dir.mkdir(parents=False, exist_ok=False)
    claims_dir = output_root / "claims" / "synthetic"
    _ensure_directory(claims_dir)
    claim_path = claims_dir / f"{_scope_key('synthetic')}.json"
    claim = {
        "namespace": "synthetic",
        "scope_id": _scope_key("synthetic"),
        "campaign_id": CAMPAIGN_ID,
        "task_id": TASK_ID,
        "upstream_sha": UPSTREAM_SHA,
        "run_id": spec.run_id,
        "status": "started",
        "claimed_at": _utc_now(),
        "replay_allowed": False,
    }
    try:
        _write_new_json(claim_path, claim)
    except FileExistsError:
        result = {
            "schema_version": 1,
            "provenance": "synthetic_rehearsal",
            "run_id": spec.run_id,
            "status": "claim_conflict",
            "phase": "claim",
            "claim_path": str(claim_path),
            "attempt_claimed": False,
            **_real_unknown("claim conflict did not access real B/C budget"),
        }
        _atomic_json(run_dir / "manifest.json", result)
        return result

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "provenance": "synthetic_rehearsal",
        "namespace": "synthetic",
        "run_id": spec.run_id,
        "scope_id": claim["scope_id"],
        "campaign_id": CAMPAIGN_ID,
        "task_id": TASK_ID,
        "project_sha": _project_sha(),
        "project_sha_source": "read-only git metadata unavailable in this controller",
        "upstream_sha": UPSTREAM_SHA,
        "upstream_version": UPSTREAM_VERSION,
        "candidate": _candidate(spec),
        "requested_limits": _requested_limits(spec),
        "limit_enforcement": "configured_unverified",
        "experiment_config": _experiment_config(spec),
        "config_sha256": hashlib.sha256(json.dumps(_experiment_config(spec), sort_keys=True).encode()).hexdigest(),
        "status": "started",
        "phase": "world_creation",
        "started_at": _utc_now(),
        "claim_path": str(claim_path),
        "attempt_claimed": True,
        "budget_preflight": {"status": budget_status, "reason": budget_reason, "cap_cny": CAP_CNY},
        "synthetic_budget": _budget_record(budget),
        **_real_unknown("synthetic fixture accounting is isolated from real B/C spend"),
        "real_usage_source": None,
        "resource_ids_owned": [],
        "cleanup": {"attempted": False, "status": "not_started"},
        "primary_error": None,
        "cleanup_error": None,
        "replay_allowed": False,
    }
    manifest_path = run_dir / "manifest.json"
    _atomic_json(manifest_path, manifest)
    handle: OwnedHandle | None = None
    terminal = "rehearsal_failed"
    primary_error: dict[str, str] | None = None
    started = time.monotonic()
    try:
        manifest["phase"] = "world_creation"
        _atomic_json(manifest_path, manifest)
        try:
            handle = backend.create_world(spec)
        except OwnedHandleError as exc:
            handle = exc.handle
            raise
        if not isinstance(handle, OwnedHandle) or not handle.owned:
            raise ControlError("backend did not return a confirmed owned handle")
        manifest["resource_ids_owned"] = [handle.resource_id]
        manifest["phase"] = "runner"
        _atomic_json(manifest_path, manifest)
        result = backend.run_once(handle, spec)
        if not isinstance(result, BackendResult):
            raise ControlError("backend result has an invalid shape")
        if isinstance(result.exit_code, bool) or not isinstance(result.exit_code, int):
            raise ControlError("backend exit code has an invalid shape")
        if result.synthetic_cost_cny is not None and (
            isinstance(result.synthetic_cost_cny, bool)
            or not isinstance(result.synthetic_cost_cny, (int, float))
            or not math.isfinite(float(result.synthetic_cost_cny))
            or result.synthetic_cost_cny < 0
            or not isinstance(result.synthetic_cost_source, str)
            or not result.synthetic_cost_source.strip()
        ):
            raise ControlError("synthetic cost evidence has an invalid shape")
        accounting = _synthetic_accounting(result, budget)
        manifest["synthetic_accounting"] = accounting
        if result.exit_code != 0:
            terminal = "runner_rejected"
            primary_error = {"phase": "runner", "error_type": "NonzeroExit"}
        elif accounting["status"] != "complete":
            terminal = "accounting_unknown"
            primary_error = {"phase": "accounting", "error_type": "MissingOrInvalidUsage"}
        else:
            terminal = "rehearsal_completed"
        manifest["synthetic_result"] = {
            "exit_code": result.exit_code,
            "usage": result.usage if _valid_usage(result.usage) else None,
            "known_prefix_usage": result.known_prefix_usage if _valid_usage(result.known_prefix_usage) else None,
            "synthetic_cost_cny": result.synthetic_cost_cny,
            "synthetic_cost_source": result.synthetic_cost_source,
        }
    except TimeoutError as exc:
        terminal = "timeout"
        primary_error = {"phase": manifest["phase"], "error_type": type(exc).__name__}
    except Exception as exc:
        if manifest["phase"] == "world_creation":
            terminal = "world_creation_failed"
        else:
            terminal = "runner_failed"
        primary_error = {"phase": manifest["phase"], "error_type": type(exc).__name__}
    finally:
        if handle is not None and handle.owned:
            manifest["cleanup"] = {"attempted": True, "status": "started"}
            _atomic_json(manifest_path, manifest)
            try:
                backend.cleanup(handle)
                manifest["cleanup"] = {"attempted": True, "status": "succeeded"}
            except Exception as exc:
                manifest["cleanup"] = {"attempted": True, "status": "failed"}
                manifest["cleanup_error"] = {"error_type": type(exc).__name__}
                if terminal == "rehearsal_completed":
                    terminal = "cleanup_failed"
        elif handle is not None:
            manifest["cleanup"] = {"attempted": False, "status": "foreign_handle_not_removed"}
        else:
            manifest["cleanup"] = {"attempted": False, "status": "resource_state_unknown" if primary_error else "not_created"}
        manifest["elapsed_seconds"] = round(time.monotonic() - started, 3)
        manifest["finished_at"] = _utc_now()
        manifest["status"] = terminal
        manifest["phase"] = "cleanup" if manifest["cleanup"]["attempted"] else manifest["phase"]
        manifest["primary_error"] = primary_error
        _atomic_json(manifest_path, manifest)
        claim["status"] = terminal
        claim["finished_at"] = manifest["finished_at"]
        _atomic_json(claim_path, claim)
    return manifest


def _valid_usage(usage: Any) -> bool:
    return isinstance(usage, dict) and all(
        key in usage and isinstance(usage[key], int) and not isinstance(usage[key], bool) and usage[key] >= 0
        for key in ("input_tokens", "output_tokens")
    )


def _project_sha() -> str | None:
    # Avoid reporting a symbolic ref name as if it were a commit SHA.
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline C single-attempt lifecycle controller")
    parser.add_argument("mode", choices=("plan", "rehearse", "live"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--scenario", choices=sorted(_SCENARIOS), default="success")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        spec = RunSpec(args.run_id, args.agent, args.model)
        if args.mode == "plan":
            print(json.dumps(plan(spec), indent=2, sort_keys=True))
            return 0
        if args.mode == "live":
            raise LiveExecutionDisabled("live execution is disabled: no verified B transport, ungraded runner or runtime authorization")
        result = rehearse(spec, root=Path(__file__).resolve().parents[1] / "runs" / "c-control", scenario=args.scenario)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] in {"rehearsal_completed", "preflight_blocked", "claim_conflict"} else 1
    except LiveExecutionDisabled as exc:
        print(json.dumps({"status": "live_disabled", "reason": str(exc), "attempt_claimed": False}, sort_keys=True))
        return 2
    except (ControlError, OSError) as exc:
        print(json.dumps({"status": "rejected", "error_type": type(exc).__name__}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
