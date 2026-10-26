#!/usr/bin/env python3
"""Dedicated, offline-preparation entry for the identified evaluation bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).absolute().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))

from evaluation_bundle import BundleFailure, BundleIdentity, _read_regular_bounded, validate_bundle
from b_execution_policy import PolicyFailure, ExecutionPolicy, is_validated_policy, make_evaluation_policy
from b_provider_profile import ProfileFailure, ProviderProfile, load_profile
from b_live_preflight import PreparationFailure, _policy_summary, _profile_summary, _rehearse, _source_and_sdk


ENTRY_CONFIG_PATH = ROOT / "profiles" / "evaluation-entry.json"
ENTRY_RUNTIME_SOURCE_FILES = (
    "scripts/evaluation_entry.py", "scripts/evaluation_bundle.py", "scripts/b_live_preflight.py",
    "scripts/b_execution_policy.py", "scripts/b_provider_profile.py", "scripts/b_provider_transport.py",
    "scripts/model_runner_adapter.py", "scripts/b_model_adapter.py",
    "profiles/evaluation-entry.json", "profiles/deepseek-flash-prepared.json",
)
ENTRY_CONFIG_EXPECTED = {
    "schema": "chi-evaluation-entry-config-v1",
    "entry_id": "identified-evaluation-record-only-v1",
    "execution_scope": "evaluation_rehearsal",
    "policy_mode": "record_only",
    "hard_cap_cny": None,
    "provider_profile_id": "deepseek-flash-prepared-2026-10-26-v1",
    "status": "identified_offline_preparation",
    "real_api_enabled": False,
    "actual_calls_authorized": False,
}
MAX_CONFIG_BYTES = 16_384
SAFE_REHEARSE_SCENARIOS = (
    "evaluation-over-five", "success", "missing-usage", "invalid-final-usage", "http-429",
    "http-503", "connect-error", "timeout", "post-tool-503",
)


class EntryFailure(Exception):
    def __init__(self, code: str, phase: str = "preflight"):
        super().__init__(code)
        self.code = code
        self.phase = phase


@dataclass(frozen=True)
class EntryContext:
    bundle: BundleIdentity
    config_sha256: str
    policy: ExecutionPolicy
    profile: ProviderProfile


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _same_typed_value(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_typed_value(actual[key], expected[key]) for key in expected)
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_typed_value(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _load_context() -> EntryContext:
    try:
        bundle = validate_bundle(ROOT)
    except BundleFailure as exc:
        raise EntryFailure(exc.code) from None
    try:
        raw_bytes = _read_regular_bounded(
            ENTRY_CONFIG_PATH, MAX_CONFIG_BYTES, "evaluation_entry_config_invalid")
        data = json.loads(raw_bytes, object_pairs_hook=_unique_object,
                          parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise EntryFailure("evaluation_entry_config_invalid") from None
    if not _same_typed_value(data, ENTRY_CONFIG_EXPECTED):
        raise EntryFailure("evaluation_entry_config_invalid")
    config_sha = hashlib.sha256(raw_bytes).hexdigest()
    if config_sha != bundle.entry_config_sha256:
        raise EntryFailure("evaluation_entry_config_digest_mismatch")
    try:
        policy = make_evaluation_policy("record_only")
    except PolicyFailure as exc:
        raise EntryFailure(exc.code) from None
    if (not is_validated_policy(policy) or policy.scope != "evaluation_rehearsal"
            or policy.mode != "record_only" or policy.hard_cap_cny is not None):
        raise EntryFailure("evaluation_policy_invalid")
    try:
        profile = load_profile()
    except ProfileFailure as exc:
        raise EntryFailure(exc.code) from None
    if profile.raw.get("profile_id") != ENTRY_CONFIG_EXPECTED["provider_profile_id"]:
        raise EntryFailure("evaluation_provider_profile_mismatch")
    return EntryContext(bundle, config_sha, policy, profile)


def _runtime_identity() -> dict[str, Any]:
    try:
        source, sdk = _source_and_sdk(ENTRY_RUNTIME_SOURCE_FILES)
        return {"status": "verified_for_offline_integration", "sdk": sdk, "source": source}
    except PreparationFailure as exc:
        return {"status": "unavailable", "sdk": None, "source": None,
                "safe_error_code": exc.code}


def _safe_output_root(value: Path, bundle_root: Path) -> Path:
    value = Path(value)
    if ".." in value.parts:
        raise EntryFailure("evaluation_output_path_invalid")
    try:
        absolute = __import__("evaluation_bundle")._check_components(
            value, "evaluation_output_path_invalid")
    except BundleFailure:
        raise EntryFailure("evaluation_output_path_invalid") from None
    bundle_root = Path(bundle_root)
    try:
        absolute.relative_to(bundle_root)
        raise EntryFailure("evaluation_output_path_invalid")
    except ValueError:
        pass
    try:
        bundle_root.relative_to(absolute)
    except ValueError:
        return absolute
    raise EntryFailure("evaluation_output_path_invalid")


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


def _read_only_report(mode: str, context: EntryContext) -> dict[str, Any]:
    identity = _runtime_identity()
    technical_ready = identity["status"] == "verified_for_offline_integration"
    return {
        "mode": mode,
        "entry": {"entry_id": ENTRY_CONFIG_EXPECTED["entry_id"],
                  "config_sha256": context.config_sha256,
                  "bundle_id": context.bundle.bundle_id,
                  "bundle_manifest_sha256": context.bundle.manifest_sha256,
                  "identity_is_not_signature_or_authorization": True},
        "execution_policy": _policy_summary(context.policy),
        "profile": _profile_summary(context.profile),
        "identity": identity,
        "technical_ready": technical_ready,
        "readiness": "identified_offline_preparation" if technical_ready else "optional_runtime_unavailable",
        "authorization": {"execution_paused": True, "actual_calls_authorized": False,
                           "authentication": "unverified", "official_task_world": False, "grading": False},
        "accounting": {"mode": "record_only", "hard_cap_cny": None,
                       "real_usage": None, "real_cost_cny": None, "official_reward": None},
        "side_effects": {"files_written": False, "client_created": False,
                         "http_transport_created": False, "credentials_read": False,
                         "ledger_or_claim_created": False},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "preflight", "rehearse", "live"), default="plan")
    parser.add_argument("--evaluation-id")
    parser.add_argument("--task-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--scenario", choices=SAFE_REHEARSE_SCENARIOS, default="evaluation-over-five")
    args = parser.parse_args(argv)

    # No config, package, profile, credentials, SDK client, ledger or claim is
    # inspected on this permanently paused path.
    if args.mode == "live":
        _print({"mode": "live", "status": "rejected", "safe_error_code": "real_execution_paused",
                "credentials_read": False, "config_read": False, "bundle_read": False,
                "client_created": False, "transport_created": False, "ledger_or_claim_created": False})
        return 2

    try:
        context = _load_context()
        if args.mode in {"plan", "preflight"}:
            report = _read_only_report("read_only_" + args.mode, context)
            _print(report)
            if args.mode == "preflight":
                return 0 if report["technical_ready"] else 1
            return 0
        if not all((args.evaluation_id, args.task_id, args.attempt_id, args.run_id, args.output_root)):
            raise EntryFailure("evaluation_identity_and_output_root_required")
        output_root = _safe_output_root(args.output_root, context.bundle.root)
        identity = _runtime_identity()
        if identity["status"] != "verified_for_offline_integration":
            raise EntryFailure(identity["safe_error_code"])
        import asyncio

        journal, ledger, result = asyncio.run(_rehearse(
            args.scenario, args.run_id, policy=context.policy,
            evaluation_id=args.evaluation_id, task_id=args.task_id, attempt_id=args.attempt_id,
            output_root=output_root, application_files=ENTRY_RUNTIME_SOURCE_FILES,
            execution_identity_sha256=context.bundle.manifest_sha256,
        ))
        success = ledger.error_code is None and result is not None
        _print({"mode": "identified_evaluation_entry_rehearsal",
                "status": "complete" if success else "incomplete",
                "evidence": str(journal.run_path), "transport_send_count": ledger.transport_calls,
                "evaluation_identity": {"evaluation_id": args.evaluation_id, "task_id": args.task_id,
                                         "attempt_id": args.attempt_id, "run_id_is_output_label_only": True},
                "execution_policy": _policy_summary(context.policy),
                "entry_identity": {"bundle_manifest_sha256": context.bundle.manifest_sha256,
                                   "config_sha256": context.config_sha256},
                "safe_error_code": ledger.error_code, "cleanup_error_code": ledger.cleanup_error_code,
                "real_usage": None, "real_cost_cny": None, "official_reward": None})
        return 0 if success else 1
    except (BundleFailure, EntryFailure, PolicyFailure, ProfileFailure, PreparationFailure) as exc:
        _print({"status": "blocked" if getattr(exc, "phase", "preflight") == "preflight" else "incomplete",
                "safe_error_code": getattr(exc, "code", "evaluation_entry_failed"),
                "credentials_read": False, "real_usage": None, "real_cost_cny": None,
                "official_reward": None})
        return 2 if getattr(exc, "phase", "preflight") == "preflight" else 1


if __name__ == "__main__":
    raise SystemExit(main())
