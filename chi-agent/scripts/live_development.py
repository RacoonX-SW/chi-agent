#!/usr/bin/env python3
"""Bounded real-provider development smoke and one ungraded CHI task attempt.

The read-only commands do not read credentials or create state.  Real commands
are deliberately separated from the evaluation entrypoint and keep all real
accounting in a campaign-wide namespace that is independent of rehearsals.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import tarfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from b_execution_policy import load_local_policy, load_real_development_policy
from b_live_preflight import _profile_summary, _source_and_sdk, build_plan
from b_provider_profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "pa_t018_t018_o001_p01_new_referral_provider"
CAMPAIGN_ID = "real-b-c-ungraded-first-campaign"
ACCOUNTING_SCHEMA = "chi-real-b-c-accounting-v1"
CLAIM_SCHEMA = "chi-real-c-once-claim-v1"
B_SUCCESS_SCHEMA = "chi-real-b-smoke-success-v1"
_MOCK_ORCHESTRATION_TEST = object()
CLAIM_FILE = "c-once-claim.json"
REAL_ROOT_RELATIVE = Path("runs/real-b-c")
K_ROOT_RELATIVE = Path("runs/real-c-development")
K_ACCOUNTING_SCHEMA = "chi-real-c-development-accounting-v1"
WORKSPACE_CONTAINER_ROOT = Path("/logs/artifacts/workspaces")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
SAFE_ERROR_RE = re.compile(r"^[a-z0-9_]{1,64}$")


class LiveFailure(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _workspace_path(workspace_root: Path, value: Any, *, allow_directory: bool = False) -> Path | None:
    """Return only case/provider/shared paths beneath the task workspace root."""
    if type(value) is not str or ".." in Path(value).parts:
        return None
    candidate = Path(value)
    try:
        relative = candidate.relative_to(workspace_root)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) < (2 if allow_directory else 3) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", parts[0]):
        return None
    if parts[1] not in {"provider", "shared"}:
        return None
    cursor = workspace_root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None
    return candidate


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _fsync_parent(path: Path) -> None:
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _atomic_json(path: Path, value: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (_json(value) + "\n").encode("utf-8")
    if exclusive:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_parent(path)
        return
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_parent(path)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink():
            raise ValueError()
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys,
                           parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise LiveFailure("real_accounting_invalid") from None
    if type(value) is not dict:
        raise LiveFailure("real_accounting_invalid")
    return value


def _validate_accounting_state(state: dict[str, Any], *, profile: Any,
                               execution_identity: dict[str, Any] | None) -> str | None:
    """Validate every persistent budget invariant without changing the journal."""
    required = {"schema", "campaign_id", "namespace", "currency", "cap_cny", "prior_spend_cny",
                "prior_source", "known_settled_cost_cny", "known_input_tokens", "known_output_tokens",
                "usage_complete", "pending", "profile_sha256", "execution_identity", "created_at"}
    is_k = state.get("schema") == K_ACCOUNTING_SCHEMA
    if is_k:
        required |= {"adoption_sha256", "source_transitions"}
    if set(state) != required or state.get("schema") not in {ACCOUNTING_SCHEMA, K_ACCOUNTING_SCHEMA} \
            or state.get("campaign_id") != CAMPAIGN_ID:
        return "real_accounting_invalid"
    if (state.get("namespace") != "real_provider_usage_estimated_cost" or state.get("currency") != "CNY"
            or state.get("cap_cny") != (None if is_k else "5") or type(state.get("prior_source")) is not str
            or not state["prior_source"].strip() or type(state.get("created_at")) is not str
            or not state["created_at"].strip()):
        return "real_accounting_invalid"
    for key in ("prior_spend_cny", "known_settled_cost_cny"):
        value = state.get(key)
        if type(value) is not str:
            return "real_accounting_invalid"
        try:
            amount = Decimal(value)
        except Exception:
            return "real_accounting_invalid"
        if not amount.is_finite() or amount < 0:
            return "real_accounting_invalid"
    if not is_k and Decimal(state["prior_spend_cny"]) + Decimal(state["known_settled_cost_cny"]) > Decimal("5"):
        return "real_accounting_invalid"
    try:
        datetime.fromisoformat(state["created_at"].replace("Z", "+00:00"))
    except ValueError:
        return "real_accounting_invalid"
    for key in ("known_input_tokens", "known_output_tokens"):
        value = state.get(key)
        if type(value) is not int or not 0 <= value <= 10**12:
            return "real_accounting_invalid"
    if type(state.get("usage_complete")) is not bool:
        return "real_accounting_invalid"
    digest = state.get("profile_sha256")
    if digest is not None and (type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        return "real_accounting_invalid"
    identity = state.get("execution_identity")
    if type(identity) is not dict:
        return "real_accounting_invalid"
    if execution_identity is not None and identity != execution_identity:
        return "real_execution_identity_mismatch"
    if digest is not None and digest != profile.sha256:
        return "real_profile_mismatch"
    pending = state.get("pending")
    if pending is not None:
        if type(pending) is not dict:
            return "real_accounting_invalid"
        pending_keys = {"run_id", "round", "status", "input_reserve_tokens", "output_reserve_tokens",
                        "reserve_upper_cost_cny", "cumulative_upper_cost_cny", "request_sha256",
                        "request_wire_bytes", "route", "model", "reserve_basis"}
        confirmation = is_k and type(pending) is dict and pending.get("purpose") == "patient_confirmation"
        if confirmation:
            from patient_identity_binding import CONFIRM_MAX_OUTPUT_TOKENS
            pending_keys.add("purpose")
            output_valid = type(pending.get("output_reserve_tokens")) is int and pending["output_reserve_tokens"] == CONFIRM_MAX_OUTPUT_TOKENS
            wire_limit = 8 * 1024 * 1024
        else:
            output_valid = type(pending.get("output_reserve_tokens")) is int and 1 <= pending["output_reserve_tokens"] <= profile.max_output_tokens
            wire_limit = 1_048_576
        if (type(pending) is not dict or set(pending) != pending_keys
                or type(pending.get("run_id")) is not str or ID_RE.fullmatch(pending["run_id"]) is None
                or type(pending.get("round")) is not int or pending["round"] < 1
                or pending.get("status") not in {"pending", "unknown"}
                or type(pending.get("input_reserve_tokens")) is not int
                or pending.get("input_reserve_tokens") != profile.input_reserve_tokens
                or not output_valid
                or type(pending.get("request_wire_bytes")) is not int
                or not 1 <= pending["request_wire_bytes"] <= wire_limit
                or type(pending.get("request_sha256")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", pending["request_sha256"]) is None
                or pending.get("route") != profile.endpoint + "/v1/chat/completions"
                or pending.get("model") != profile.model
                or pending.get("reserve_basis") != "documented_peak_price_and_context_ceiling_not_tokenizer_measured"):
            return "real_accounting_invalid"
        for key in ("reserve_upper_cost_cny", "cumulative_upper_cost_cny"):
            value = pending.get(key)
            if type(value) is not str:
                return "real_accounting_invalid"
            try:
                amount = Decimal(value)
            except Exception:
                return "real_accounting_invalid"
            if not amount.is_finite() or amount < 0:
                return "real_accounting_invalid"
        reserve = ((Decimal(pending["input_reserve_tokens"]) * profile.input_price
                    + Decimal(pending["output_reserve_tokens"]) * profile.output_price)
                   / Decimal(1_000_000))
        expected_cumulative = Decimal(state["prior_spend_cny"]) + Decimal(state["known_settled_cost_cny"]) + reserve
        if (Decimal(pending["reserve_upper_cost_cny"]) != reserve
                or Decimal(pending["cumulative_upper_cost_cny"]) != expected_cumulative
                or (not is_k and expected_cumulative > Decimal("5"))
                or state.get("profile_sha256") != profile.sha256):
            return "real_accounting_invalid"
    elif state.get("usage_complete") is not True:
        return "real_accounting_invalid"
    return None


def _execution_identity(*, k: bool = False) -> dict[str, Any]:
    profile = load_profile()
    policy = load_real_development_policy() if k else load_local_policy()
    import model_runner_adapter as adapter
    upstream = adapter._upstream_identity()
    try:
        sdk = adapter._sdk_identity()
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code != "optional_sdk_layer_unavailable" and exc.__class__.__name__ != "PackageNotFoundError":
            raise LiveFailure("sdk_identity_unavailable") from None
        # The controller image need not contain the optional SDK. Bind the
        # expected versions from the hashed lock; the isolated runner verifies
        # these actual versions again before creating the provider client.
        lock_text = (ROOT / "requirements-model.lock").read_text(encoding="utf-8")
        expected = {"openai-agents": "0.13.6", "openai": "2.36.0", "httpx": "0.28.1"}
        if any(not re.search(rf"^{re.escape(name)}=={re.escape(version)}\s", lock_text, re.M)
               for name, version in expected.items()):
            raise LiveFailure("sdk_lock_identity_mismatch") from None
        sdk = expected
    files = ("scripts/live_development.py", "scripts/b_provider_transport.py",
             "scripts/pdf_resource_reader.py",
             "scripts/model_runner_adapter.py", "scripts/b_provider_profile.py",
             "scripts/a_environment.py", "scripts/b_execution_policy.py",
             "scripts/b_live_preflight.py", "scripts/b_model_adapter.py",
             "profiles/deepseek-flash-prepared.json", "profiles/local-development-policy.json",
             "requirements-model.lock")
    if k:
        files += ("requirements-pdf.lock", "scripts/provider_task_resources.py", "scripts/patient_identity_binding.py",
                  "scripts/request_budget.py", "scripts/referral_field_guidance.py")
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    identity = {"vendor": upstream, "sdk": sdk, "application_files_sha256": hashes,
                "profile_sha256": profile.sha256, "policy_sha256": policy.sha256}
    if k:
        try:
            from pdf_resource_reader import dependency_identity
            identity["pdf_dependency"] = dependency_identity(ROOT / "requirements-pdf.lock")
        except Exception:
            raise LiveFailure("pdf_dependency_unavailable_or_mismatch") from None
    return identity


def initialize_real_accounting(root: Path, *, prior_source: str,
                               execution_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create the one authorized first-campaign zero-prior record, once only."""
    if type(prior_source) is not str or not prior_source.strip() or len(prior_source) > 160:
        raise LiveFailure("real_prior_source_invalid")
    execution_identity = execution_identity or _execution_identity()
    state = {
        "schema": ACCOUNTING_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "namespace": "real_provider_usage_estimated_cost",
        "currency": "CNY",
        "cap_cny": "5",
        "prior_spend_cny": "0",
        "prior_source": prior_source.strip(),
        "known_settled_cost_cny": "0",
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "usage_complete": True,
        "pending": None,
        "profile_sha256": None,
        "execution_identity": execution_identity,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _atomic_json(root / "accounting.json", state, exclusive=True)
    except FileExistsError:
        raise LiveFailure("real_accounting_already_initialized") from None
    except Exception:
        raise LiveFailure("real_accounting_initialize_failed") from None
    return state


def _validate_b_receipt(root: Path, receipt: dict[str, Any], profile: Any,
                        identity: dict[str, Any]) -> None:
    if (receipt.get("schema") != B_SUCCESS_SCHEMA or receipt.get("status") != "success"
            or receipt.get("campaign_id") != CAMPAIGN_ID or receipt.get("task_id") != TASK_ID
            or receipt.get("profile_sha256") != profile.sha256
            or receipt.get("execution_identity") != identity or receipt.get("official_reward") is not None):
        raise LiveFailure("real_b_success_evidence_mismatch")
    run_id = receipt.get("run_id")
    if type(run_id) is not str or ID_RE.fullmatch(run_id) is None:
        raise LiveFailure("real_b_success_evidence_invalid")
    run_path = root / "runs" / f"{run_id}.json"
    run = _read_json(run_path)
    logs = root / run_id / "runner-logs"
    if (run.get("schema") != "chi-real-provider-run-v1" or run.get("campaign_id") != CAMPAIGN_ID
            or run.get("state") != "complete" or run.get("execution_identity") != identity
            or run.get("profile_sha256") != profile.sha256 or run.get("real_usage") != receipt.get("usage")
            or run.get("estimated_cost_cny") != receipt.get("estimated_cost_cny")):
        raise LiveFailure("real_b_success_evidence_mismatch")
    files = [(run_path, "run_journal_sha256"), (logs / "run_result.json", "runner_result_sha256"),
             (logs / "run_output.txt", "run_output_sha256"), (logs / "trace.jsonl", "trace_sha256"),
             (logs / "run_log.txt", "run_log_sha256")]
    for path, key in files:
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != receipt.get(key):
            raise LiveFailure("real_b_success_evidence_mismatch")


def adopt_prior(old_root: Path, root: Path, *, _test_context: Any = None) -> None:
    """Import verified terminal J evidence once, without altering predecessor bytes."""
    import fcntl
    if _test_context is not _MOCK_ORCHESTRATION_TEST and (
            old_root.resolve() != (ROOT / REAL_ROOT_RELATIVE).resolve()
            or root.resolve() != (ROOT / K_ROOT_RELATIVE).resolve()):
        raise LiveFailure("real_budget_root_mismatch")
    if old_root.is_symlink() or root.is_symlink() or not old_root.is_dir():
        raise LiveFailure("real_accounting_invalid")
    root.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(old_root / ".real-accounting.lock", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LiveFailure("real_accounting_busy_or_pending") from None
        state_path = old_root / "accounting.json"
        receipt_path = old_root / "b-success.json"
        claim_path = old_root / CLAIM_FILE
        state, receipt, claim = (_read_json(path) for path in (state_path, receipt_path, claim_path))
        profile = load_profile()
        code = _validate_accounting_state(state, profile=profile, execution_identity=None)
        if code or state.get("schema") != ACCOUNTING_SCHEMA or state.get("pending") is not None or not state.get("usage_complete"):
            raise LiveFailure(code or "real_accounting_pending_unknown")
        _validate_b_receipt(old_root, receipt, profile, state["execution_identity"])
        claim_run = claim.get("run_id")
        if (claim.get("schema") != CLAIM_SCHEMA or claim.get("campaign_id") != CAMPAIGN_ID
                or claim.get("task_id") != TASK_ID or type(claim_run) is not str
                or ID_RE.fullmatch(claim_run) is None or claim.get("execution_identity") != state["execution_identity"]
                or claim.get("profile_sha256") != profile.sha256 or claim.get("official_reward") is not None
                or claim.get("replay_allowed") is not False or not claim.get("finished_at")
                or claim.get("state") != "failed_or_uncertain_claim_retained" or claim.get("terminal_status") != "failed"
                or claim.get("cleanup_error_code") is not None
                or claim.get("b_success_sha256") != hashlib.sha256(_json(receipt).encode()).hexdigest()):
            raise LiveFailure("prior_claim_invalid")
        orchestration = _read_json(old_root / claim_run / "orchestration.json")
        cleanup = orchestration.get("cleanup")
        world = orchestration.get("world")
        if (orchestration.get("run_id") != claim_run or orchestration.get("status") != claim.get("terminal_status")
                or not orchestration.get("finished_at") or orchestration.get("cleanup_error_code") is not None
                or orchestration.get("persistence_error_code") is not None or type(cleanup) is not dict
                or type(world) is not dict or world.get("logs_captured") is not True
                or cleanup.get("world_removed") is not True or cleanup.get("network_removed") is not True
                or "runner" in orchestration):
            raise LiveFailure("prior_claim_invalid")
        usage = receipt.get("usage")
        if (type(usage) is not dict or usage != {"input_tokens": state["known_input_tokens"], "output_tokens": state["known_output_tokens"]}
                or Decimal(receipt["estimated_cost_cny"]) != Decimal(state["known_settled_cost_cny"])
                or Decimal(state["prior_spend_cny"]) + Decimal(state["known_settled_cost_cny"]) <= 0):
            raise LiveFailure("prior_usage_inconsistent")
        provenance = {"schema": "chi-real-prior-adoption-v1", "old_execution_identity": state["execution_identity"],
                      "source_files_sha256": {str(path.relative_to(old_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                              for path in (state_path, receipt_path, claim_path, old_root / claim_run / "orchestration.json")},
                      "prior_usage": usage, "prior_estimated_cost_cny": str(Decimal(state["prior_spend_cny"]) + Decimal(state["known_settled_cost_cny"]))}
        new_state = {**state, "schema": K_ACCOUNTING_SCHEMA, "cap_cny": None,
                     "prior_spend_cny": provenance["prior_estimated_cost_cny"], "known_settled_cost_cny": "0",
                     "prior_source": "adopted_j_campaign:adoption.json"}
        _atomic_json(root / "adoption.json", provenance, exclusive=True)
        new_state["adoption_sha256"] = hashlib.sha256((root / "adoption.json").read_bytes()).hexdigest()
        new_state["source_transitions"] = []
        _atomic_json(root / "accounting.json", new_state, exclusive=True)
    except FileExistsError:
        raise LiveFailure("real_accounting_already_initialized") from None
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _validate_k_provenance(root: Path, state: dict[str, Any]) -> None:
    """Verify self-contained adoption and source history before any paid work."""
    try:
        adoption_path = root / "adoption.json"
        adoption = _read_json(adoption_path)
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        if adoption.get("schema") != "chi-real-prior-adoption-v1" or digest(adoption_path) != state.get("adoption_sha256"):
            raise ValueError()
        usage = adoption.get("prior_usage")
        hashes = adoption.get("source_files_sha256")
        if (type(usage) is not dict or set(usage) != {"input_tokens", "output_tokens"}
                or any(type(usage[x]) is not int or usage[x] < 0 for x in usage)
                or any(state[f"known_{x}"] < usage[x] for x in usage)
                or state.get("prior_source") != "adopted_j_campaign:adoption.json"
                or Decimal(state["prior_spend_cny"]) != Decimal(adoption["prior_estimated_cost_cny"])
                or Decimal(state["prior_spend_cny"]) <= 0 or type(hashes) is not dict or len(hashes) != 4
                or any(type(h) is not str or re.fullmatch(r"[0-9a-f]{64}", h) is None for h in hashes.values())):
            raise ValueError()
        identity = adoption["old_execution_identity"]
        minimum_cost = Decimal("0")
        minimum_input, minimum_output = usage["input_tokens"], usage["output_tokens"]
        chain = state["source_transitions"]
        if type(identity) is not dict or type(chain) is not list:
            raise ValueError()
        seen = set()
        for entry in chain:
            if (type(entry) is not dict or set(entry) != {"previous_accounting_sha256", "sha256"}
                    or any(type(entry[x]) is not str or re.fullmatch(r"[0-9a-f]{64}", entry[x]) is None for x in entry)):
                raise ValueError()
            key = entry["previous_accounting_sha256"]
            if key in seen:
                raise ValueError()
            seen.add(key)
            path = root / "source-transitions" / f"{key}.json"
            record = _read_json(path)
            if (digest(path) != entry["sha256"] or record.get("schema") != "chi-real-source-transition-v1"
                    or record.get("previous_accounting_sha256") != key or record.get("before") != identity
                    or type(record.get("after")) is not dict or type(record.get("reason")) is not str
                    or not record["reason"].strip()):
                raise ValueError()
            snapshot = record.get("accounting_snapshot")
            if (type(snapshot) is not dict or set(snapshot) != {"known_settled_cost_cny", "known_input_tokens", "known_output_tokens"}
                    or type(snapshot["known_settled_cost_cny"]) is not str
                    or type(snapshot["known_input_tokens"]) is not int or type(snapshot["known_output_tokens"]) is not int
                    or not Decimal(snapshot["known_settled_cost_cny"]).is_finite()
                    or Decimal(snapshot["known_settled_cost_cny"]) < minimum_cost
                    or snapshot["known_input_tokens"] < minimum_input or snapshot["known_output_tokens"] < minimum_output):
                raise ValueError()
            minimum_cost = Decimal(snapshot["known_settled_cost_cny"])
            minimum_input, minimum_output = snapshot["known_input_tokens"], snapshot["known_output_tokens"]
            receipt_id, receipt_hash = record.get("previous_b_receipt_run_id"), record.get("previous_b_receipt_sha256")
            if receipt_hash is not None:
                if type(receipt_id) is not str or ID_RE.fullmatch(receipt_id) is None:
                    raise ValueError()
                receipt_path = root / "b-receipts" / f"{receipt_id}.json"
                if receipt_path.is_symlink() or digest(receipt_path) != receipt_hash:
                    raise ValueError()
            elif receipt_id is not None:
                raise ValueError()
            identity = record["after"]
        if (identity != state["execution_identity"] or Decimal(state["known_settled_cost_cny"]) < minimum_cost
                or state["known_input_tokens"] < minimum_input or state["known_output_tokens"] < minimum_output):
            raise ValueError()
    except Exception:
        raise LiveFailure("real_provenance_invalid") from None


def rebind_source(root: Path, reason: str) -> None:
    import fcntl
    if type(reason) is not str or not reason.strip() or len(reason) > 300:
        raise LiveFailure("source_transition_reason_invalid")
    lock_fd = os.open(root / ".real-accounting.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LiveFailure("real_accounting_busy_or_pending") from None
        path = root / "accounting.json"
        state = _read_json(path)
        code = _validate_accounting_state(state, profile=load_profile(), execution_identity=None)
        if code or state.get("schema") != K_ACCOUNTING_SCHEMA or state.get("pending") is not None or not state.get("usage_complete"):
            raise LiveFailure(code or "real_accounting_pending_unknown")
        _validate_k_provenance(root, state)
        before = state["execution_identity"]
        after = _execution_identity(k=True)
        if before == after:
            raise LiveFailure("source_transition_unchanged")
        receipt_path = root / "b-success.json"
        receipt_hash = None
        receipt_id = None
        if receipt_path.exists():
            receipt = _read_json(receipt_path)
            _validate_b_receipt(root, receipt, load_profile(), before)
            receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            receipt_id = receipt["run_id"]
            archive = root / "b-receipts" / f"{receipt['run_id']}.json"
            _atomic_json(archive, receipt, exclusive=True)
        old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {"schema": "chi-real-source-transition-v1", "before": before, "after": after,
                  "reason": reason.strip(), "previous_accounting_sha256": old_hash,
                  "previous_b_receipt_sha256": receipt_hash, "previous_b_receipt_run_id": receipt_id,
                  "accounting_snapshot": {key: state[key] for key in
                                          ("known_settled_cost_cny", "known_input_tokens", "known_output_tokens")},
                  "timestamp": datetime.now(timezone.utc).isoformat()}
        transition_path = root / "source-transitions" / f"{old_hash}.json"
        _atomic_json(transition_path, record, exclusive=True)
        if receipt_hash is not None:
            receipt_path.unlink()
            _fsync_parent(receipt_path)
        state["execution_identity"] = after
        state["source_transitions"].append({"previous_accounting_sha256": old_hash,
                                            "sha256": hashlib.sha256(transition_path.read_bytes()).hexdigest()})
        _atomic_json(path, state)
    except FileExistsError:
        raise LiveFailure("source_transition_incomplete_or_exists") from None
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _check_k_attempts_clean(root: Path) -> None:
    claims = root / "claims"
    if claims.is_symlink():
        raise LiveFailure("prior_cleanup_unverified")
    if not claims.exists():
        return
    for path in claims.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise LiveFailure("prior_cleanup_unverified")
        claim = _read_json(path)
        run_id = claim.get("run_id")
        if type(run_id) is not str or ID_RE.fullmatch(run_id) is None or path.name != f"{run_id}.json":
            raise LiveFailure("prior_cleanup_unverified")
        run = _read_json(root / run_id / "orchestration.json")
        cleanup = run.get("cleanup")
        if (claim.get("schema") != CLAIM_SCHEMA or not claim.get("finished_at")
                or claim.get("cleanup_error_code") is not None or not run.get("finished_at")
                or claim.get("terminal_status") != run.get("status")
                or run.get("cleanup_error_code") is not None or run.get("persistence_error_code") is not None
                or type(cleanup) is not dict
                or ("runner" in run and cleanup.get("runner_removed") is not True)
                or ("world" in run and "container_id" in run["world"] and cleanup.get("world_removed") is not True)
                or ("world" in run and "network_id" in run["world"] and cleanup.get("network_removed") is not True)):
            raise LiveFailure("prior_cleanup_unverified")


def _k_locked(root: Path, operation: Any) -> Any:
    import fcntl
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / ".controller.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LiveFailure("controller_busy") from None
        _check_k_attempts_clean(root)
        gate = root / "controller-state.json"
        if gate.exists() and _read_json(gate).get("state") != "clean":
            raise LiveFailure("prior_cleanup_unverified")
        return operation()
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _k_run(kind: str, run_id: str, root: Path, task_id: str = TASK_ID) -> dict[str, Any]:
    if kind == "c-once" and task_id != TASK_ID:
        from provider_task_resources import verify
        try:
            verify(ROOT, task_id)
        except Exception:
            raise LiveFailure("official_task_resources_invalid") from None
    if ((root / run_id).exists() or (root / run_id).is_symlink()
            or (root / "runs" / f"{run_id}.json").exists()
            or (root / "claims" / f"{run_id}.json").exists()):
        raise LiveFailure("run_id_exists")
    state = _read_json(root / "accounting.json")
    profile = load_profile()
    identity = _execution_identity(k=True)
    code = _validate_accounting_state(state, profile=profile, execution_identity=identity)
    if code:
        raise LiveFailure(code)
    if state.get("schema") != K_ACCOUNTING_SCHEMA or state.get("pending") is not None or state.get("usage_complete") is not True:
        raise LiveFailure("real_accounting_pending_unknown")
    _validate_k_provenance(root, state)
    receipt_path = root / "b-success.json"
    if kind == "b-smoke" and receipt_path.exists():
        raise LiveFailure("real_b_smoke_already_succeeded")
    if kind == "c-once":
        _validate_b_receipt(root, _read_json(receipt_path), profile, identity)
    try:
        credential = _model_key()
    except LiveFailure as exc:
        _atomic_json(root / "pre-resource-failures" / f"{run_id}.json",
                     {"schema": "chi-real-pre-resource-failure-v1", "run_id": run_id,
                      "error_code": exc.code, "resources_created": False,
                      "timestamp": datetime.now(timezone.utc).isoformat()}, exclusive=True)
        raise
    gate = root / "controller-state.json"
    armed = False
    def arm_gate() -> None:
        nonlocal armed
        _atomic_json(gate, {"schema": "chi-real-controller-state-v1", "state": "active", "run_id": run_id})
        armed = True
    try:
        result = _orchestrate(kind, run_id, root, k=True, _credential=credential, _before_resources=arm_gate, task_id=task_id)
    except Exception as exc:
        if not armed:
            code = getattr(exc, "code", "pre_resource_failure")
            _atomic_json(root / "pre-resource-failures" / f"{run_id}.json",
                         {"schema": "chi-real-pre-resource-failure-v1", "run_id": run_id,
                          "error_code": code if SAFE_ERROR_RE.fullmatch(code) else "pre_resource_failure",
                          "resources_created": False, "timestamp": datetime.now(timezone.utc).isoformat()}, exclusive=True)
        raise
    if not armed:
        raise LiveFailure("controller_gate_not_armed")
    clean = result.get("cleanup_error_code") is None and result.get("persistence_error_code") is None
    _atomic_json(gate, {"schema": "chi-real-controller-state-v1", "state": "clean" if clean else "blocked",
                        "run_id": run_id, "status": result.get("status")})
    return result


class RealDevelopmentJournal:
    """Real-only persistent accounting; never reads or writes synthetic journals."""

    def __init__(self, root: Path, run_id: str, *, profile: Any, policy: Any):
        import fcntl

        if not isinstance(run_id, str) or ID_RE.fullmatch(run_id) is None:
            raise LiveFailure("run_id_invalid")
        is_k = policy.scope == "real_development" and policy.mode == "record_only" and policy.hard_cap_cny is None
        if not is_k and (policy.scope != "local_development" or policy.hard_cap_cny != Decimal("5")):
            raise LiveFailure("execution_policy_invalid")
        self.root = root
        self.run_id = run_id
        self.profile = profile
        self.policy = policy
        self.cap_cny = None if is_k else Decimal("5")
        self.state_path = root / "accounting.json"
        self.run_path = root / "runs" / f"{run_id}.json"
        self.lock_path = root / ".real-accounting.lock"
        self.closed = False
        self._lock_owned = False
        self.lock_fd: int | None = None
        root.mkdir(parents=True, exist_ok=True)
        self.lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock_fd)
            self.lock_fd = None
            raise LiveFailure("real_accounting_busy_or_pending") from None
        self._lock_owned = True
        try:
            self.state = _read_json(self.state_path)
            if self.state.get("schema") != (K_ACCOUNTING_SCHEMA if is_k else ACCOUNTING_SCHEMA):
                raise LiveFailure("real_accounting_invalid")
            actual_identity = _execution_identity(k=True) if is_k else _execution_identity()
            if self.state.get("execution_identity") != actual_identity:
                raise LiveFailure("real_execution_identity_mismatch")
            self._validate_state(actual_identity)
            if is_k:
                _validate_k_provenance(root, self.state)
            if self.state.get("pending") is not None or self.state.get("usage_complete") is not True:
                raise LiveFailure("real_accounting_pending_unknown")
            if self.state.get("profile_sha256") not in {None, profile.sha256}:
                raise LiveFailure("real_profile_mismatch")
            if self.run_path.exists() or self.run_path.is_symlink():
                raise LiveFailure("run_id_exists")
            self.run_path.parent.mkdir(parents=True, exist_ok=True)
            self.run_doc = {
                "schema": "chi-real-provider-run-v1", "campaign_id": CAMPAIGN_ID,
                "namespace": "real_provider_usage_estimated_cost", "run_id": run_id,
                "state": "prepared", "profile_sha256": profile.sha256,
                "policy_sha256": policy.sha256, "execution_identity": actual_identity,
                "requests": [], "tool_effects": [],
                "tool_history": [], "official_reward": None,
                "real_usage": {"input_tokens": 0, "output_tokens": 0},
                "estimated_cost_cny": "0",
                "known_prefix_usage": {"input_tokens": 0, "output_tokens": 0},
                "known_prefix_estimated_cost_cny": "0",
                "campaign_usage_snapshot": {"input_tokens": self.state["known_input_tokens"],
                                             "output_tokens": self.state["known_output_tokens"]},
                "campaign_estimated_cost_cny_snapshot": str(self.cumulative_spend) if is_k else self.state["known_settled_cost_cny"],
            }
            _atomic_json(self.run_path, self.run_doc, exclusive=True)
        except Exception:
            self.close()
            raise

    def _validate_state(self, expected_identity: dict[str, Any] | None = None) -> None:
        code = _validate_accounting_state(
            self.state, profile=self.profile, execution_identity=expected_identity)
        if code is not None:
            raise LiveFailure(code)

    def _require_active_lock(self) -> None:
        if self.closed or not self._lock_owned or self.lock_fd is None:
            from b_provider_transport import GuardFailure
            raise GuardFailure("journal_lock_not_owned", "persistence")

    @property
    def cumulative_spend(self) -> Decimal:
        return Decimal(self.state["prior_spend_cny"]) + Decimal(self.state["known_settled_cost_cny"])

    def _persist(self) -> None:
        self._require_active_lock()
        _atomic_json(self.state_path, self.state)
        _atomic_json(self.run_path, self.run_doc)

    def reserve(self, profile: Any, request: Any, body: dict[str, Any], raw: bytes,
                max_output: int, round_number: int, *, purpose: str | None = None,
                budget_feedback: dict | None = None) -> Decimal:
        from b_provider_transport import GuardFailure
        self._require_active_lock()
        fresh = _read_json(self.state_path)
        if self.cap_cny is None:
            try:
                _validate_k_provenance(self.root, fresh)
            except LiveFailure:
                raise GuardFailure("real_provenance_invalid", "request_guard") from None
        if fresh != self.state or fresh.get("pending") is not None or fresh.get("usage_complete") is not True:
            raise GuardFailure("real_accounting_pending_unknown", "request_guard")
        if profile.sha256 != self.profile.sha256:
            raise GuardFailure("real_profile_mismatch", "request_guard")
        if purpose is not None:
            from patient_identity_binding import CONFIRM_MAX_OUTPUT_TOKENS
            if (purpose != "patient_confirmation" or self.policy.scope != "real_development"
                    or type(max_output) is not int or max_output != CONFIRM_MAX_OUTPUT_TOKENS):
                raise GuardFailure("confirmation_policy_invalid", "request_guard")
        elif type(max_output) is not int or not 1 <= max_output <= profile.max_output_tokens:
            raise GuardFailure("output_limit", "request_guard")
        if budget_feedback is not None:
            from request_budget import feedback, claim_recorded
            try:
                _, expected_feedback = feedback(round_number - 1, claim_recorded(self))
                if (self.policy.scope != "real_development" or self.run_doc.get("run_kind") != "c-once"
                        or purpose is not None or budget_feedback != expected_feedback):
                    raise ValueError
            except Exception:
                raise GuardFailure("request_budget_feedback_invalid", "request_guard") from None
        reserve = (Decimal(profile.input_reserve_tokens) * profile.input_price
                   + Decimal(max_output) * profile.output_price) / Decimal(1_000_000)
        if self.cap_cny is not None and self.cumulative_spend + reserve > self.cap_cny:
            raise GuardFailure("budget_exhausted", "request_guard")
        self.state["profile_sha256"] = profile.sha256
        entry = {"round": round_number, "status": "pending", "input_reserve_tokens": profile.input_reserve_tokens,
                 "output_reserve_tokens": max_output, "reserve_upper_cost_cny": str(reserve),
                 "cumulative_upper_cost_cny": str(self.cumulative_spend + reserve),
                 "request_sha256": hashlib.sha256(raw).hexdigest(), "request_wire_bytes": len(raw),
                 "route": str(request.url), "model": body["model"],
                 "reserve_basis": "documented_peak_price_and_context_ceiling_not_tokenizer_measured"}
        if purpose is not None:
            entry["purpose"] = purpose
        self.state["pending"] = {"run_id": self.run_id, **entry}
        if budget_feedback is not None:
            entry["request_budget_feedback"] = budget_feedback
        self.state["usage_complete"] = False
        self.run_doc["requests"].append(entry)
        self.run_doc["state"] = "pending"
        try:
            self._persist()
        except Exception:
            from b_provider_transport import GuardFailure
            raise GuardFailure("journal_write_failed", "request_guard") from None
        return reserve

    def settle(self, actual_cost: Decimal, incoming: int, outgoing: int, *, response_metadata: dict | None = None) -> bool:
        from b_provider_transport import GuardFailure
        self._require_active_lock()
        pending = self.state.get("pending")
        if not isinstance(pending, dict) or pending.get("run_id") != self.run_id:
            raise GuardFailure("journal_pending_missing", "response_accounting")
        reserve = Decimal(pending["reserve_upper_cost_cny"])
        within = actual_cost <= reserve
        entry = self.run_doc["requests"][-1]
        if pending.get("purpose") == "patient_confirmation":
            if (type(response_metadata) is not dict or set(response_metadata) != {"purpose", "round", "request_sha256", "finish_reason", "content_present"}
                    or response_metadata.get("purpose") != "patient_confirmation"
                    or response_metadata.get("round") != pending["round"]
                    or response_metadata.get("request_sha256") != pending["request_sha256"]
                    or response_metadata.get("finish_reason") not in {"stop", "length", "other"}
                    or type(response_metadata.get("content_present")) is not bool):
                raise GuardFailure("confirmation_metadata_invalid", "response_accounting")
            entry["response_metadata"] = response_metadata
        elif response_metadata is not None:
            raise GuardFailure("confirmation_metadata_invalid", "response_accounting")
        entry.update({"status": "settled" if within else "settled_over_reserve",
                      "usage_provenance": "provider_response_usage",
                      "input_tokens": incoming, "output_tokens": outgoing,
                      "estimated_cost_cny": str(actual_cost),
                      "known_aggregate_estimated_cost_cny": str(self.cumulative_spend + actual_cost),
                      "reserve_comparison": "within" if within else "exceeded"})
        if response_metadata is not None:
            # Durable per-request settlement precedes clearing aggregate pending.
            _atomic_json(self.run_path, self.run_doc)
        self.state["known_settled_cost_cny"] = str(Decimal(self.state["known_settled_cost_cny"]) + actual_cost)
        self.state["known_input_tokens"] += incoming
        self.state["known_output_tokens"] += outgoing
        run_usage = self.run_doc.setdefault("real_usage", {"input_tokens": 0, "output_tokens": 0})
        run_usage["input_tokens"] += incoming
        run_usage["output_tokens"] += outgoing
        known_prefix_usage = self.run_doc.setdefault(
            "known_prefix_usage", {"input_tokens": 0, "output_tokens": 0})
        known_prefix_usage["input_tokens"] += incoming
        known_prefix_usage["output_tokens"] += outgoing
        known_prefix_cost = Decimal(self.run_doc.get("known_prefix_estimated_cost_cny", "0")) + actual_cost
        self.run_doc["known_prefix_estimated_cost_cny"] = str(known_prefix_cost)
        self.run_doc["estimated_cost_cny"] = str(known_prefix_cost)
        self.run_doc["campaign_usage_snapshot"] = {
            "input_tokens": self.state["known_input_tokens"],
            "output_tokens": self.state["known_output_tokens"],
        }
        self.run_doc["campaign_estimated_cost_cny_snapshot"] = (str(self.cumulative_spend)
            if self.cap_cny is None else self.state["known_settled_cost_cny"])
        self.state["pending"] = None
        self.state["usage_complete"] = True
        self.run_doc["state"] = "settled"
        self._persist()
        return within

    def mark_unknown(self, code: str) -> None:
        self._require_active_lock()
        if self.state.get("pending") is not None:
            self.state["pending"]["status"] = "unknown"
        self.state["usage_complete"] = False
        self.run_doc["state"] = "unknown"
        self.run_doc["primary_error_code"] = code if SAFE_ERROR_RE.fullmatch(code) else "request_unknown"
        if self.run_doc["requests"]:
            self.run_doc["requests"][-1]["status"] = "unknown"
            self.run_doc["requests"][-1]["reason_code"] = self.run_doc["primary_error_code"]
        try:
            self._persist()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"

    def mark_error(self, code: str) -> None:
        self._require_active_lock()
        self.run_doc["primary_error_code"] = code if SAFE_ERROR_RE.fullmatch(code) else "request_failed"
        if self.state.get("pending") is None:
            self.run_doc["state"] = "incomplete"
        self._persist()

    def record_effect(self, effect: dict[str, Any]) -> None:
        if type(effect) is not dict or set(effect) != {"tool", "call_id", "result"}:
            from b_provider_transport import GuardFailure
            raise GuardFailure("tool_effect_invalid", "tool_execution")
        self.run_doc["tool_effects"].append(effect)
        self._persist()

    def record_history(self, exchanges: list[dict[str, Any]]) -> None:
        self.run_doc["tool_history"] = exchanges
        self.run_doc["mcp_tool_effects"] = exchanges
        self._persist()

    def record_validated_dispatches(self, calls: list[dict[str, Any]]) -> None:
        self._require_active_lock()
        existing = self.run_doc.setdefault("tool_dispatches", [])
        existing.extend(calls)
        self._persist()

    def start_dispatch(self, *, call_id: str, model_name: str, raw_name: str, arguments: dict[str, Any]) -> None:
        self._require_active_lock()
        digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        for entry in self.run_doc.get("tool_dispatches", []):
            if (entry.get("call_id") == call_id and entry.get("state") == "validated"
                    and entry.get("model_name") == model_name and entry.get("arguments_sha256") == digest):
                entry["state"] = "started"
                entry["started_at"] = datetime.now(timezone.utc).isoformat()
                self._persist()
                return
        raise LiveFailure("tool_dispatch_identity_mismatch")

    def finish_dispatch(self, *, call_id: str, result: Any, error: bool = False) -> None:
        self._require_active_lock()
        entries = self.run_doc.get("tool_dispatches", [])
        entry = next((item for item in entries if item.get("call_id") == call_id), None)
        if entry is None or entry.get("state") != "started":
            raise LiveFailure("tool_dispatch_state_invalid")
        if error:
            entry["state"] = "unknown"
            entry["reason_code"] = "tool_dispatch_failed_or_timed_out"
        else:
            safe = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            entry.update({"state": "returned", "result_sha256": hashlib.sha256(safe.encode()).hexdigest(),
                          "result_chars": len(safe), "returned_at": datetime.now(timezone.utc).isoformat()})
        self._persist()

    def finalize(self, *, status: str, primary_error: str | None = None,
                 cleanup_error: str | None = None, reward: None = None) -> None:
        self._require_active_lock()
        unresolved = [item for item in self.run_doc.get("tool_dispatches", [])
                      if item.get("state") in {"started", "unknown"}]
        for item in unresolved:
            item["state"] = "unknown"
            item["reason_code"] = "dispatch_started_without_definitive_return"
        if unresolved:
            if primary_error is None:
                primary_error = "tool_effect_unknown"
            status = "incomplete"
        usage_complete = self.state.get("usage_complete") is True
        known_prefix_usage = dict(self.run_doc.get(
            "known_prefix_usage", self.run_doc.get("real_usage", {"input_tokens": 0, "output_tokens": 0})))
        known_prefix_cost = str(self.run_doc.get(
            "known_prefix_estimated_cost_cny", self.run_doc.get("estimated_cost_cny", "0")))
        self.run_doc.update({"state": status, "primary_error_code": primary_error,
                             "cleanup_error_code": cleanup_error, "official_reward": reward,
                             "real_usage": known_prefix_usage if usage_complete else None,
                             "estimated_cost_cny": known_prefix_cost if usage_complete else None,
                             "known_prefix_usage": known_prefix_usage,
                             "known_prefix_estimated_cost_cny": known_prefix_cost,
                             "campaign_usage": {"input_tokens": self.state["known_input_tokens"],
                                                "output_tokens": self.state["known_output_tokens"]}
                             if usage_complete else None,
                             "campaign_estimated_cost_cny": str(self.cumulative_spend if self.cap_cny is None else Decimal(self.state["known_settled_cost_cny"]))
                             if usage_complete else None,
                             "campaign_known_prefix_usage": {"input_tokens": self.state["known_input_tokens"],
                                                             "output_tokens": self.state["known_output_tokens"]},
                             "campaign_known_prefix_estimated_cost_cny": str(self.cumulative_spend if self.cap_cny is None else Decimal(self.state["known_settled_cost_cny"])),
                             "prior_spend_cny": self.state["prior_spend_cny"],
                             "prior_source": self.state["prior_source"]})
        self._persist()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.lock_fd is not None:
            try:
                import fcntl
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self.lock_fd)
            self.lock_fd = None
            self._lock_owned = False


def build_read_only_plan() -> dict[str, Any]:
    base = build_plan()
    base["entrypoint"] = "scripts/live_development.py"
    base["scope"] = {"real_provider": "DeepSeek profile only", "official_world": "one selected task, ungraded",
                     "grading": False, "automatic_retry": False}
    base["authorization"] = {"local_real_b_c_scope_explicitly_authorized": True,
                              "commands_executed": False, "credentials_read": False,
                              "authentication_verified": False, "http_transport_created": False,
                              "docker_client_created": False, "official_world_started": False,
                              "real_claim_created": False, "grading_authorized": False}
    base["budget"]["real_state_path"] = str(REAL_ROOT_RELATIVE / "accounting.json")
    base["budget"]["prior_spend"] = "unknown_until_real_campaign_journal_exists"
    return base


def _budget_preflight(root: Path, *, profile: Any | None = None,
                      execution_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    path = root / "accounting.json"
    if not path.is_file():
        return {"status": "unknown", "real_aggregate_cost_cny": None,
                "source": None, "safe_error_code": "real_accounting_missing"}
    try:
        state = _read_json(path)
        profile = profile or load_profile()
        execution_identity = execution_identity or _execution_identity()
    except Exception as exc:
        return {"status": "invalid", "real_aggregate_cost_cny": None,
                "source": None, "safe_error_code": getattr(exc, "code", "real_execution_identity_unavailable")}
    code = _validate_accounting_state(state, profile=profile, execution_identity=execution_identity)
    if code is not None:
        return {"status": "invalid", "real_aggregate_cost_cny": None,
                "source": None, "safe_error_code": code}
    if state.get("pending") is not None or state.get("usage_complete") is not True:
        return {"status": "unknown", "real_aggregate_cost_cny": None,
                "source": state.get("prior_source"), "safe_error_code": "real_accounting_pending_unknown"}
    prior = Decimal(state["prior_spend_cny"])
    settled = Decimal(state["known_settled_cost_cny"])
    if state.get("schema") == ACCOUNTING_SCHEMA and prior + settled > Decimal("5"):
        return {"status": "invalid", "real_aggregate_cost_cny": None,
                "source": None, "safe_error_code": "real_accounting_invalid"}
    return {"status": "known", "prior_spend_cny": state["prior_spend_cny"],
            "settled_estimated_cost_cny": state["known_settled_cost_cny"],
            "source": state["prior_source"], "real_aggregate_cost_cny": None,
            "known_aggregate_estimated_cost_cny": str(prior + settled)}


def build_preflight(root: Path) -> dict[str, Any]:
    profile = load_profile()
    actual_identity = None
    try:
        actual_identity = _execution_identity()
        identity = {"status": "verified", **actual_identity}
    except Exception as exc:
        identity = {"status": "unavailable", "safe_error_code": getattr(exc, "code", "source_or_sdk_identity_unavailable"),
                    "source": None, "sdk": None}
    budget = _budget_preflight(root, profile=profile, execution_identity=actual_identity)
    reserve = (Decimal(profile.input_reserve_tokens) * profile.input_price
               + Decimal(profile.max_output_tokens) * profile.output_price) / Decimal(1_000_000)
    remaining = (Decimal("5") - Decimal(budget["prior_spend_cny"]) - Decimal(budget["settled_estimated_cost_cny"])
                 if budget.get("status") == "known" else None)
    return {"mode": "read_only_preflight", "profile": _profile_summary(profile),
            "identity": identity, "budget": {**budget, "scope": "shared_real_B_C", "cap_cny": "5",
                                              "next_request_reserve_upper_cny": str(reserve),
                                              "remaining_estimated_cny": str(remaining) if remaining is not None else None,
                                              "can_reserve_one_max_request": remaining is not None and remaining >= reserve},
            "authorization": {"local_real_b_c_scope_explicitly_authorized": True,
                              "commands_executed": False, "credentials_read": False,
                              "authentication_verified": False, "official_world_started": False,
                              "grading_authorized": False},
            "readiness": "technical_only_not_authorized"}


def _claim_c_once(root: Path, run_id: str, b_success: dict[str, Any], *, k: bool = False,
                  task_id: str = TASK_ID, resource_identity: dict | None = None) -> Path:
    claim = root / "claims" / f"{run_id}.json" if k else root / CLAIM_FILE
    record = {"schema": CLAIM_SCHEMA, "campaign_id": CAMPAIGN_ID, "task_id": task_id,
              "run_id": run_id, "state": "claimed_before_world_creation", "replay_allowed": False,
              "official_reward": None, "b_success_sha256": hashlib.sha256(_json(b_success).encode()).hexdigest(),
              "execution_identity": b_success.get("execution_identity"),
              "profile_sha256": b_success.get("profile_sha256"),
              "claimed_at": datetime.now(timezone.utc).isoformat()}
    if resource_identity is not None:
        record["task_resource_identity"] = resource_identity
    try:
        _atomic_json(claim, record, exclusive=True)
    except FileExistsError:
        raise LiveFailure("real_c_attempt_already_claimed") from None
    except Exception:
        raise LiveFailure("real_c_claim_persist_failed") from None
    return claim


def _transition_c_claim(root: Path, run_id: str, state: str, *,
                        execution_identity: dict[str, Any], profile_sha256: str, k: bool = False,
                        task_id: str = TASK_ID) -> None:
    import fcntl

    path = root / "claims" / f"{run_id}.json" if k else root / CLAIM_FILE
    lock = os.open(root / ".c-claim.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = _read_json(path)
        if record.get("schema") != CLAIM_SCHEMA or record.get("campaign_id") != CAMPAIGN_ID \
                or record.get("task_id") != task_id or record.get("run_id") != run_id \
                or record.get("execution_identity") != execution_identity \
                or record.get("profile_sha256") != profile_sha256 \
                or record.get("state") != "claimed_before_world_creation":
            raise LiveFailure("real_c_claim_transition_invalid")
        if k and task_id != TASK_ID:
            from provider_task_resources import identity
            if record.get("task_resource_identity") != identity(task_id):
                raise LiveFailure("real_c_claim_transition_invalid")
        record["state"] = state
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(path, record)
    finally:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            os.close(lock)


def _copy_projection(root: Path, run_id: str, *, output_parent: Path | None = None,
                     task_id: str = TASK_ID) -> Path:
    import shutil
    from a_environment import _verify_handbook

    if task_id != TASK_ID:
        from provider_task_resources import verify
        try:
            source, _ = verify(root, task_id)
        except Exception:
            raise LiveFailure("official_task_projection_unavailable") from None
    else:
        source = None
    dataset = root / "data" / "a-environment" / "download-5ce88104df2a91e057619eb70fb51f56fc5949eb"
    if source is None:
        try:
            manifest = json.loads((dataset / ".a-environment-data-manifest.json").read_text(encoding="utf-8"))
            if manifest.get("revision") != "5ce88104df2a91e057619eb70fb51f56fc5949eb":
                raise ValueError
            records = manifest.get("files")
            public_relatives = (f"prior_auth_provider/tasks/{TASK_ID}/instruction.md",
                                f"prior_auth_provider/tasks/{TASK_ID}/tool_reference.md")
            if not isinstance(records, dict) or not set(public_relatives).issubset(records):
                raise ValueError
            from a_environment import _sha256
            for relative in public_relatives:
                path = dataset / relative
                expected = records[relative]
                if (path.is_symlink() or not path.is_file() or path.stat().st_size != expected.get("size")
                        or _sha256(path) != expected.get("sha256")):
                    raise ValueError
        except Exception:
            raise LiveFailure("official_task_projection_unavailable") from None
        source = dataset / "prior_auth_provider" / "tasks" / TASK_ID
    output = (output_parent if output_parent is not None else _projection_run_dir(run_id)) / "projection"
    output.mkdir(parents=True, exist_ok=False)
    for filename in ("instruction.md", "tool_reference.md"):
        path = source / filename
        if not path.is_file() or path.is_symlink():
            raise LiveFailure("official_task_projection_unavailable")
        shutil.copyfile(path, output / filename)
    for alias in ("healthverse-task-assets", "chi-bench-task-assets"):
        alias_dir = output / alias
        alias_dir.mkdir()
        shutil.copyfile(output / "tool_reference.md", alias_dir / "tool_reference.md")
    try:
        _verify_handbook(root)
    except Exception:
        raise LiveFailure("authorized_handbook_projection_unavailable") from None
    handbook_source = root / "data" / "skills" / "managed-care-operations-handbook"
    for item in handbook_source.rglob("*"):
        if item.is_symlink():
            raise LiveFailure("authorized_handbook_projection_invalid")
    handbook = output / "workspace" / "skills" / "managed-care-operations-handbook"
    shutil.copytree(handbook_source, handbook, symlinks=True)
    return output


def _model_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        path = ROOT / ".env"
        if path.is_file() and not path.is_symlink():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    name, sep, value = line.partition("=")
                    if sep and name.strip() == "DEEPSEEK_API_KEY":
                        key = value.strip().strip("\"'")
                        break
            except Exception:
                key = None
    if not isinstance(key, str) or not key.strip():
        raise LiveFailure("provider_credential_missing")
    return key.strip()


def _official_world_run_dir(run_id: str) -> Path:
    return ROOT / "runs" / "a-environment" / run_id


def _projection_run_dir(run_id: str) -> Path:
    return ROOT / REAL_ROOT_RELATIVE / run_id


def _capture_review_input(world: Any, capture_root: Path, run_id: str,
                          execution_identity: dict[str, Any], task_id: str = TASK_ID,
                          resource_identity: dict | None = None) -> dict[str, Any]:
    """Capture only the stopped runner's owned world, never participant outputs."""
    from a_environment import _api_timeout
    from b_provider_transport import _reject_symlink_ancestors
    limit = 16 * 1024 * 1024
    deadline = time.monotonic() + 60
    try:
        if ID_RE.fullmatch(run_id) is None:
            raise ValueError
        _reject_symlink_ancestors(capture_root, "review_input_capture_failed")
        program = (
            "import sys,urllib.request; "
            "r=urllib.request.urlopen('http://127.0.0.1:8023/export',timeout=20); "
            "b=r.read(16777217); "
            "sys.exit(2) if len(b)>16777216 else sys.stdout.buffer.write(b)"
        )
        with _api_timeout(world.client, deadline):
            code, exported = world.exec_run(["python", "-c", program], demux=False)
        if time.monotonic() > deadline:
            raise TimeoutError
        if code != 0 or not isinstance(exported, bytes) or len(exported) > limit:
            raise ValueError
        def parse(raw: bytes) -> dict[str, Any]:
            value = json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                               parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
            if type(value) is not dict:
                raise ValueError
            return value

        def archive_file(path: str, name: str, maximum: int) -> bytes:
            chunks = bytearray()
            archive = None
            try:
                with _api_timeout(world.client, deadline):
                    archive, _ = world.get_archive(path)
                    for chunk in archive:
                        if time.monotonic() > deadline:
                            raise TimeoutError
                        chunks.extend(chunk)
                        if len(chunks) > maximum + 1024 * 1024:
                            raise ValueError
                    if time.monotonic() > deadline:
                        raise TimeoutError
            finally:
                if archive is not None and callable(getattr(archive, "close", None)):
                    archive.close()
            with tarfile.open(fileobj=io.BytesIO(chunks), mode="r:*") as tar:
                members = tar.getmembers()
                if len(members) != 1 or members[0].name != name or not members[0].isfile() or members[0].size > maximum:
                    raise ValueError
                handle = tar.extractfile(members[0])
                if handle is None:
                    raise ValueError
                payload = handle.read(maximum + 1)
            if len(payload) > maximum:
                raise ValueError
            parse(payload)
            return payload

        export_data = parse(exported)
        shared_world_id = export_data.get("world_id")
        if type(shared_world_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", shared_world_id) is None:
            raise ValueError
        expectations = archive_file(f"/opt/chi-bench/tasks/{task_id}/fixtures/expectations.json", "expectations.json", limit)
        world_filename = f"{shared_world_id}.json"
        shared_world = archive_file(f"/opt/chi-bench/worlds/{world_filename}", world_filename, 64 * 1024 * 1024)
        if resource_identity is not None and (shared_world_id != resource_identity["world_id"]
                or hashlib.sha256(shared_world).hexdigest() != resource_identity["world_sha256"]
                or hashlib.sha256(expectations).hexdigest() != resource_identity["files"]["fixtures/expectations.json"]["sha256"]):
            raise ValueError
        capture_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _reject_symlink_ancestors(capture_root, "review_input_capture_failed")
        target = capture_root / run_id
        target.mkdir(mode=0o700, exist_ok=False)
        for name, payload in (("exported_state.json", exported), ("expectations.json", expectations),
                              ("shared_world.json", shared_world)):
            fd = os.open(target / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        manifest = {"schema": "chi-development-review-capture-v1", "status": "ready",
                    "run_id": run_id, "task_id": task_id, "world_id": world.id,
                    "shared_world_id": shared_world_id,
                    "execution_identity": execution_identity,
                    "export_sha256": hashlib.sha256(exported).hexdigest(),
                    "expectations_sha256": hashlib.sha256(expectations).hexdigest(),
                    "shared_world_sha256": hashlib.sha256(shared_world).hexdigest(),
                    "official_reward": None}
        if resource_identity is not None:
            manifest["task_resource_identity"] = resource_identity
        _atomic_json(target / "manifest.json", manifest, exclusive=True)
        return {"status": "ready", "manifest_sha256": hashlib.sha256((target / "manifest.json").read_bytes()).hexdigest()}
    except Exception:
        return {"status": "unavailable", "safe_error_code": "review_input_capture_failed"}


def _runner_quiescent(runner: Any, client: Any, record: dict[str, Any]) -> bool:
    if type(record.get("exit_code")) is int:
        return True
    try:
        from a_environment import _api_timeout
        with _api_timeout(client, time.monotonic() + 30):
            runner.stop(timeout=10)
            runner.reload()
        state = runner.attrs.get("State", {})
        if state.get("Status") not in {"exited", "dead"} or type(state.get("ExitCode")) is not int:
            return False
        record["exit_code"] = state["ExitCode"]
        return True
    except Exception:
        return False


def _orchestrate(kind: str, run_id: str, budget_root: Path, *, _test_context: Any = None,
                 k: bool = False, _credential: str | None = None,
                 _before_resources: Any = None, task_id: str = TASK_ID) -> dict[str, Any]:
    """Create an isolated runner; only C owns an official task world."""
    from a_environment import (
        AEnvironmentError, _capture_logs,
        _check_resource_slots, _daemon_path, _docker, _resource_labels,
        _task_environment, wait_world,
    )

    if k and _test_context is not _MOCK_ORCHESTRATION_TEST and not callable(_before_resources):
        raise LiveFailure("controller_lock_required")

    task_directory = None
    resource_identity = None
    if k and kind == "c-once" and task_id != TASK_ID:
        from provider_task_resources import verify
        try:
            task_directory, resource_identity = verify(ROOT, task_id)
        except Exception:
            raise LiveFailure("official_task_resources_invalid") from None

    if budget_root.resolve() != (ROOT / (K_ROOT_RELATIVE if k else REAL_ROOT_RELATIVE)).resolve():
        approved_test_root = (ROOT / REAL_ROOT_RELATIVE / "impl").resolve()
        if (_test_context is not _MOCK_ORCHESTRATION_TEST
                or approved_test_root not in budget_root.resolve().parents):
            raise LiveFailure("real_budget_root_mismatch")
    profile = load_profile()
    execution_identity = _execution_identity(k=True) if k else _execution_identity()
    state = _budget_preflight(budget_root, profile=profile, execution_identity=execution_identity)
    if state.get("status") != "known" or not state.get("settled_estimated_cost_cny"):
        raise LiveFailure(state.get("safe_error_code", "real_budget_unknown"))
    # A known accounting record is required before any provider or Docker side effect.
    current = _read_json(budget_root / "accounting.json")
    if current.get("schema") != (K_ACCOUNTING_SCHEMA if k else ACCOUNTING_SCHEMA):
        raise LiveFailure("real_accounting_invalid")
    if k:
        _validate_k_provenance(budget_root, current)
    if current.get("pending") is not None or current.get("usage_complete") is not True:
        raise LiveFailure("real_accounting_pending_unknown")
    if current.get("execution_identity") != execution_identity:
        raise LiveFailure("real_execution_identity_mismatch")
    if current.get("profile_sha256") not in {None, profile.sha256}:
        raise LiveFailure("real_profile_mismatch")
    sdk = execution_identity["sdk"]
    b_success = None
    if kind == "c-once":
        b_success = _read_json(budget_root / "b-success.json")
        if (b_success.get("schema") != B_SUCCESS_SCHEMA or b_success.get("status") != "success"
                or b_success.get("campaign_id") != CAMPAIGN_ID or b_success.get("task_id") != TASK_ID
                or b_success.get("profile_sha256") != profile.sha256
                or b_success.get("execution_identity") != execution_identity
                or b_success.get("official_reward") is not None):
            raise LiveFailure("real_b_success_evidence_mismatch")
        b_run_id = b_success.get("run_id")
        if not isinstance(b_run_id, str) or ID_RE.fullmatch(b_run_id) is None:
            raise LiveFailure("real_b_success_evidence_invalid")
        b_run_path = budget_root / "runs" / f"{b_run_id}.json"
        b_run = _read_json(b_run_path)
        b_logs = budget_root / b_run_id / "runner-logs"
        if (b_run.get("schema") != "chi-real-provider-run-v1" or b_run.get("campaign_id") != CAMPAIGN_ID
                or b_run.get("state") != "complete" or b_run.get("execution_identity") != execution_identity
                or b_run.get("profile_sha256") != profile.sha256
                or b_run.get("real_usage") != b_success.get("usage")
                or b_run.get("estimated_cost_cny") != b_success.get("estimated_cost_cny")
                or hashlib.sha256(b_run_path.read_bytes()).hexdigest() != b_success.get("run_journal_sha256")
                or not (b_logs / "run_result.json").is_file()
                or hashlib.sha256((b_logs / "run_result.json").read_bytes()).hexdigest() != b_success.get("runner_result_sha256")
                or not (b_logs / "run_output.txt").is_file()
                or hashlib.sha256((b_logs / "run_output.txt").read_bytes()).hexdigest() != b_success.get("run_output_sha256")
                or not (b_logs / "trace.jsonl").is_file()
                or hashlib.sha256((b_logs / "trace.jsonl").read_bytes()).hexdigest() != b_success.get("trace_sha256")
                or not (b_logs / "run_log.txt").is_file()
                or hashlib.sha256((b_logs / "run_log.txt").read_bytes()).hexdigest() != b_success.get("run_log_sha256")):
            raise LiveFailure("real_b_success_evidence_mismatch")
        reserve = (Decimal(profile.input_reserve_tokens) * profile.input_price
                   + Decimal(profile.max_output_tokens) * profile.output_price) / Decimal(1_000_000)
        remaining = None if k else Decimal(current["cap_cny"]) - Decimal(current["prior_spend_cny"]) - Decimal(current["known_settled_cost_cny"])
        if current.get("usage_complete") is not True or (remaining is not None and remaining < reserve):
            raise LiveFailure("budget_insufficient_for_c_once")
    elif (budget_root / "b-success.json").exists():
        raise LiveFailure("real_b_smoke_already_succeeded")
    secret = _credential if _credential is not None else _model_key()
    run_dir = budget_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    projection = None
    claim_path = None
    client = None
    world = None
    runner = None
    tasknet = None
    a_run_dir = None
    network_create_started = False
    world_create_started = False
    runner_create_started = False
    result: dict[str, Any] = {"schema": "chi-real-b-c-orchestration-v1", "run_id": run_id,
                              "campaign_id": CAMPAIGN_ID, "kind": kind, "status": "failed",
                              "official_reward": None, "primary_error_code": None,
                              "cleanup_error_code": None, "cleanup": {"attempted": False}}
    if resource_identity is not None:
        result["task_resource_identity"] = resource_identity
    orchestration_path = run_dir / "orchestration.json"

    def persist_orchestration() -> None:
        try:
            _atomic_json(orchestration_path, result)
        except Exception:
            raise LiveFailure("orchestration_evidence_write_failed") from None

    persist_orchestration()
    deadline = time.monotonic() + 1100
    workspace_mount = None
    world_image = None
    sdk_volume = os.environ.get("CHI_MODEL_DEPS_VOLUME", "chi-h-root-model-deps-20261027-v1")
    pdf_volume = "chi-k-pdf-deps-20261027-v1"
    if _before_resources is not None:
        _before_resources()
    try:
        if kind == "c-once":
            projection = (_copy_projection(ROOT, run_id, output_parent=run_dir, task_id=task_id) if k
                          else _copy_projection(ROOT, run_id))
            result["projection_files"] = ["instruction.md", "tool_reference.md",
                                          "healthverse-task-assets/tool_reference.md",
                                          "chi-bench-task-assets/tool_reference.md",
                                          "workspace/skills/managed-care-operations-handbook/<verified full tree>"]
            persist_orchestration()
        client = _docker()
        controller_image = client.images.get("chi-agent-a-control:latest")
        if controller_image.id != "sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3":
            raise LiveFailure("controller_image_identity_mismatch")
        runner_image = client.images.get("chi-agent-dev:latest")
        if runner_image.id != "sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3":
            raise LiveFailure("runner_image_identity_mismatch")
        client.volumes.get(sdk_volume)
        if k:
            client.volumes.get(pdf_volume)
        world_id = run_id
        task_net_name = f"chi-agent-a-net-{world_id}"
        if kind == "c-once":
            _check_resource_slots(client, world_id, deadline=deadline)
            a_run_dir = _official_world_run_dir(world_id)
            if a_run_dir.exists() or a_run_dir.is_symlink():
                raise LiveFailure("official_world_run_id_exists")
            world_image = client.images.get("chi-agent-a-world:py312-review-20261025-01")
            if world_image.id != "sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50":
                raise LiveFailure("world_image_identity_mismatch")
            runner_name = f"chi-agent-real-runner-{run_id}"
            try:
                client.containers.get(runner_name)
            except Exception as exc:
                if getattr(exc, "status_code", None) != 404:
                    raise LiveFailure("runner_resource_preflight_failed") from None
            else:
                raise LiveFailure("runner_resource_already_exists")
            claim_path = _claim_c_once(budget_root, run_id, b_success or {}, k=k, task_id=task_id,
                                       resource_identity=resource_identity)
            result["c_claim_path"] = str(claim_path.relative_to(ROOT))
            persist_orchestration()
            a_run_dir.mkdir(parents=True, exist_ok=False)
            workspace_mount = a_run_dir / "workspaces"
            workspace_mount.mkdir()
            network_create_started = True
            tasknet = client.networks.create(task_net_name, driver="bridge", internal=True,
                                             labels=_resource_labels(world_id))
            network_create_started = False
            result["world"] = {"network": tasknet.name, "network_id": tasknet.id,
                               "network_internal": True, "credentials_added": False}
            persist_orchestration()
            world_create_started = True
            world_volumes = {_daemon_path(ROOT, a_run_dir): {"bind": "/logs/artifacts", "mode": "rw"}}
            if task_directory is not None:
                world_volumes[_daemon_path(ROOT, task_directory)] = {"bind": f"/opt/chi-bench/tasks/{task_id}", "mode": "ro"}
            task_environment = _task_environment()
            task_environment["CHI_BENCH_TASK_ID"] = task_id
            world = client.containers.create(
                image=world_image.id, name=f"chi-agent-a-world-{world_id}", command=["sleep", "infinity"],
                environment=task_environment, labels=_resource_labels(world_id),
                volumes=world_volumes,
                network=task_net_name, detach=True, stdin_open=False, tty=False,
            )
            world_create_started = False
            result["world"].update({"container": world.name, "container_id": world.id,
                                   "image_id": world_image.id, "task_id": task_id,
                                   "agent_started": False, "runner_started": False, "judge_started": False})
            persist_orchestration()
            world.start()
            ready_seconds = wait_world(world, deadline=deadline)
            result["world"]["readiness_seconds"] = round(ready_seconds, 3)
            mcp_url = f"http://{world.name}:8020/mcp"
            instruction_file = projection / "instruction.md"
        else:
            mcp_url = "http://127.0.0.1:9/unused-mcp-for-b-smoke"
            instruction_file = run_dir / "b-smoke-instruction.md"
            instruction_file.write_text(
                "Use smoke_lookup once to look up CHI-Bench. Then pass its exact result to "
                "smoke_transform. After both tool results, provide a short final confirmation.\n",
                encoding="utf-8",
            )
        runner_name = f"chi-agent-real-runner-{run_id}"
        runner_network = "bridge"
        if k and kind == "c-once":
            from request_budget import MAX_REQUESTS
            runner_max_turns = str(MAX_REQUESTS)
        else:
            runner_max_turns = "6" if kind == "b-smoke" else str(profile.max_rounds)
        volumes = {
            _daemon_path(ROOT, ROOT / "scripts"): {"bind": "/participant/scripts", "mode": "ro"},
            _daemon_path(ROOT, ROOT / "vendor" / "chi-bench"): {"bind": "/participant/vendor/chi-bench", "mode": "ro"},
            _daemon_path(ROOT, ROOT / "profiles"): {"bind": "/participant/profiles", "mode": "ro"},
            _daemon_path(ROOT, ROOT / "requirements-model.lock"): {"bind": "/participant/requirements-model.lock", "mode": "ro"},
            _daemon_path(ROOT, run_dir): {"bind": "/participant/run", "mode": "rw"},
            _daemon_path(ROOT, budget_root): {"bind": "/participant/real-budget", "mode": "rw"},
        }
        if k:
            volumes[_daemon_path(ROOT, ROOT / "requirements-pdf.lock")] = {"bind": "/participant/requirements-pdf.lock", "mode": "ro"}
        if projection is not None:
            volumes[_daemon_path(ROOT, projection)] = {"bind": "/participant/projection", "mode": "ro"}
            volumes[_daemon_path(ROOT, projection / "healthverse-task-assets" / "tool_reference.md")] = {
                "bind": "/opt/healthverse-task-assets/tool_reference.md", "mode": "ro"}
            volumes[_daemon_path(ROOT, projection / "chi-bench-task-assets" / "tool_reference.md")] = {
                "bind": "/opt/chi-bench-task-assets/tool_reference.md", "mode": "ro"}
            volumes[_daemon_path(ROOT, projection / "workspace" / "skills" / "managed-care-operations-handbook")] = {
                "bind": "/workspace/skills/managed-care-operations-handbook", "mode": "ro"}
            if kind == "c-once":
                volumes[_daemon_path(ROOT, a_run_dir)] = {"bind": "/logs/artifacts", "mode": "rw"}
        runner_create_started = True
        runner = client.containers.create(
            image=runner_image.id, name=runner_name,
            command=["/opt/venv/bin/python", "/participant/scripts/live_development.py", "worker",
                     "--kind", kind, "--run-id", run_id, "--budget-root", "/participant/real-budget",
                     "--logs-dir", "/participant/run/runner-logs", "--instruction-file",
                     ("/participant/projection/instruction.md" if projection is not None else "/participant/run/b-smoke-instruction.md"),
                     "--mcp-url", mcp_url] + (["--k-development", "--task-id", task_id] if k and kind == "c-once" else (["--k-development"] if k else [])),
            environment={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ("/pdf-deps:" if k else "") + "/model-deps:/participant/vendor/chi-bench/src",
                         "OPENAI_AGENTS_MODEL": profile.model, "OPENAI_AGENTS_API_MODE": "chat_completions",
                         "OPENAI_AGENTS_MAX_TURNS": runner_max_turns,
                         "OPENAI_AGENTS_REASONING_EFFORT": "high", "OPENAI_AGENTS_MAX_RETRIES": "0",
                         "DEEPSEEK_API_KEY": secret},
            volumes={**volumes, sdk_volume: {"bind": "/model-deps", "mode": "ro"},
                     **({pdf_volume: {"bind": "/pdf-deps", "mode": "ro"}} if k else {})},
            network=runner_network, detach=True, stdin_open=False, tty=False,
            read_only=True, tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"], pids_limit=256,
            labels={"org.chi-agent.real-development": "1", "org.chi-agent.real-development.run-id": run_id},
        )
        runner_create_started = False
        result["controller"] = {"image": "chi-agent-a-control:latest", "image_id": controller_image.id}
        result["runner"] = {"container": runner_name, "container_id": runner.id,
                            "image": "chi-agent-dev:latest", "image_id": runner_image.id, "sdk_volume": sdk_volume,
                            "sdk": sdk, "credentials_in_world": False,
                            "docker_socket_mounted": False, "patient_fixture_projection": False,
                            "judge_enabled": False, "started": False}
        if k:
            result["runner"]["pdf_volume"] = pdf_volume
            result["runner"]["pdf_dependency"] = execution_identity["pdf_dependency"]
        persist_orchestration()
        if tasknet is not None:
            tasknet.connect(runner)
        runner.start()
        result["runner"]["started"] = True
        if kind == "c-once":
            result["world"]["runner_started"] = True
        persist_orchestration()
        wait_result = runner.wait(timeout=max(1, int(deadline - time.monotonic())))
        exit_code = wait_result.get("StatusCode") if isinstance(wait_result, dict) else None
        result["runner"]["exit_code"] = exit_code
        result["status"] = "completed_ungraded" if kind == "c-once" and exit_code == 0 else \
                            "smoke_completed" if kind == "b-smoke" and exit_code == 0 else "runner_failed"
        if exit_code != 0:
            result["primary_error_code"] = "runner_nonzero_exit"
    except Exception as exc:
        result["exception_type"] = type(exc).__name__
        if isinstance(exc, OSError):
            result["exception_errno"] = exc.errno
            result["exception_file_basename"] = Path(exc.filename).name if exc.filename else None
        result["primary_error_code"] = getattr(exc, "code", "orchestration_failed") if SAFE_ERROR_RE.fullmatch(
            getattr(exc, "code", "orchestration_failed")) else "orchestration_failed"
        if network_create_started or world_create_started or runner_create_started:
            result["cleanup_error_code"] = "partial_resource_ownership_unknown"
            result["partial_resource_ownership_unknown"] = True
        if kind == "c-once" and claim_path is not None:
            try:
                record = _read_json(claim_path)
                record["state"] = "failed_or_uncertain_claim_retained"
                record["primary_error_code"] = result["primary_error_code"]
                _atomic_json(claim_path, record)
            except Exception:
                result["persistence_error_code"] = "claim_evidence_persist_failed"
    finally:
        if k and kind == "c-once" and world is not None and runner is not None and result.get("runner", {}).get("started"):
            quiescent = _runner_quiescent(runner, client, result["runner"])
            result["runner"]["quiescent"] = quiescent
            if quiescent:
                result["review_input"] = _capture_review_input(
                    world, ROOT / "runs" / "development-review-inputs", run_id, execution_identity,
                    task_id, resource_identity)
            else:
                result["review_input"] = {"status": "unavailable", "safe_error_code": "runner_quiescence_unverified"}
        if world is not None and client is not None and kind == "c-once":
            try:
                result["world"]["logs_captured"] = _capture_logs(
                    world, _official_world_run_dir(run_id), client,
                    deadline=time.monotonic() + 30,
                )
                if result["world"]["logs_captured"] is not True:
                    result["cleanup_error_code"] = result.get("cleanup_error_code") or "world_log_capture_failed"
            except Exception as exc:
                result["world"]["log_capture_error_type"] = type(exc).__name__
                result["cleanup_error_code"] = result.get("cleanup_error_code") or "world_log_capture_failed"
        if runner is not None:
            try:
                runner.remove(force=True)
                result.setdefault("cleanup", {})["runner_removed"] = True
            except Exception as exc:
                result["cleanup_error_code"] = "runner_cleanup_failed"
                result.setdefault("cleanup", {})["runner_cleanup_error_type"] = type(exc).__name__
        # Remove only the exact handles returned by create() in this invocation.
        # A preflight name/label collision is never a license to clean by run-id.
        if world is not None:
            result.setdefault("cleanup", {})["attempted"] = True
            try:
                world.remove(force=True)
                result["cleanup"]["world_removed"] = True
            except Exception as exc:
                result["cleanup_error_code"] = "world_cleanup_failed"
                result["cleanup"]["world_cleanup_error_type"] = type(exc).__name__
        if tasknet is not None:
            result.setdefault("cleanup", {})["attempted"] = True
            try:
                tasknet.remove()
                result["cleanup"]["network_removed"] = True
            except Exception as exc:
                result["cleanup_error_code"] = result.get("cleanup_error_code") or "world_cleanup_failed"
                result["cleanup"]["network_cleanup_error_type"] = type(exc).__name__
        if client is not None:
            try:
                client.close()
            except Exception:
                result["cleanup_error_code"] = result.get("cleanup_error_code") or "docker_client_close_failed"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["official_reward"] = None
        result["credentials_logged"] = False
        if result.get("cleanup_error_code") and result["status"] in {"completed_ungraded", "smoke_completed"}:
            result["status"] = "cleanup_failed"
        if result["status"] not in {"completed_ungraded", "smoke_completed"}:
            run_path = budget_root / "runs" / f"{run_id}.json"
            if run_path.is_file() and not run_path.is_symlink():
                try:
                    run_doc = _read_json(run_path)
                    if run_doc.get("state") == "complete":
                        run_doc["state"] = "incomplete"
                        run_doc["cleanup_error_code"] = result.get("cleanup_error_code")
                        run_doc["orchestration_status"] = result["status"]
                        _atomic_json(run_path, run_doc)
                except Exception:
                    result["cleanup_error_code"] = result.get("cleanup_error_code") or "run_document_reconciliation_failed"
                    result["status"] = "evidence_write_failed"
        if kind == "b-smoke" and result["status"] != "smoke_completed":
            receipt = budget_root / "b-success.json"
            if receipt.exists():
                try:
                    receipt.unlink()
                    _fsync_parent(receipt)
                    result["b_success_receipt_revoked"] = True
                except Exception:
                    result["cleanup_error_code"] = result.get("cleanup_error_code") or "b_success_receipt_revocation_failed"
                    result["status"] = "cleanup_failed"
        if claim_path is not None:
            try:
                claim = _read_json(claim_path)
                claim["terminal_status"] = result["status"]
                claim["primary_error_code"] = result.get("primary_error_code")
                claim["cleanup_error_code"] = result.get("cleanup_error_code")
                claim["official_reward"] = None
                claim["finished_at"] = result["finished_at"]
                _atomic_json(claim_path, claim)
            except Exception:
                result["persistence_error_code"] = result.get("persistence_error_code") or "c_claim_finalization_failed"
                if result["status"] == "completed_ungraded":
                    result["status"] = "evidence_write_failed"
        try:
            persist_orchestration()
        except Exception:
            result["persistence_error_code"] = result.get("persistence_error_code") or "orchestration_evidence_write_failed"
            result["status"] = "evidence_write_failed"
    return result


def _strict_tool_arguments(schema: dict[str, Any], arguments: Any) -> bool:
    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(arguments)
        return True
    except Exception:
        return False


def _tool_schema(tool: Any) -> tuple[str, dict[str, Any]] | None:
    name = getattr(tool, "name", None)
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    if not isinstance(name, str) or not isinstance(schema, dict):
        return None
    return name, schema


def _apply_referral_guidance(function_tool: Any, raw_name: str, journal: RealDevelopmentJournal) -> Any:
    from referral_field_guidance import VERSION, GUIDANCE_SHA256, append_description
    try:
        applied = append_description(raw_name, function_tool.description)
    except ValueError:
        raise LiveFailure("referral_guidance_description_invalid") from None
    if applied is None:
        return function_tool
    description, details = applied
    recorded = journal.run_doc.setdefault("referral_field_guidance", {
        "version": VERSION, "guidance_sha256": GUIDANCE_SHA256, "tools": {}})
    if (recorded.get("version") != VERSION or recorded.get("guidance_sha256") != GUIDANCE_SHA256
            or (raw_name in recorded["tools"] and recorded["tools"][raw_name] != details)):
        raise LiveFailure("referral_guidance_identity_conflict")
    function_tool.description = description
    if raw_name not in recorded["tools"]:
        recorded["tools"][raw_name] = details
        journal._persist()
    return function_tool


def _live_tools(kind: str, logs_dir: Path, projection_root: Path, journal: RealDevelopmentJournal,
                schemas: dict[str, dict[str, Any]], ledger: Any, *, binding: Any = None,
                binding_lock: Any = None, openai_client: Any = None, profile: Any = None,
                exchanges: list[dict[str, Any]] | None = None, request_context: Any = None) -> list[Any]:
    import contextvars
    from agents.tool import FunctionTool

    prior_lookup_result: list[str] = []
    active_call_id = contextvars.ContextVar("real_local_tool_call_id", default=None)

    def record_effect(name: str, result: str) -> None:
        call_id = active_call_id.get()
        if not isinstance(call_id, str):
            raise LiveFailure("local_tool_call_id_unavailable")
        recorded_result = result if kind == "b-smoke" else (
            f"sha256:{hashlib.sha256(result.encode()).hexdigest()};chars:{len(result)}")
        journal.record_effect({"tool": name, "call_id": call_id, "result": recorded_result})

    async def lookup(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        answer = f"lookup-result:{args['query'].strip()}"
        prior_lookup_result[:] = [answer]
        return answer

    async def transform(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        if not prior_lookup_result or args["value"] != prior_lookup_result[-1]:
            raise LiveFailure("smoke_tool_dependency_invalid")
        answer = f"transform-result:{args['value'].strip()}"
        return answer

    workspace_root = WORKSPACE_CONTAINER_ROOT
    allowed_projection = {
        str(projection_root / "instruction.md"), str(projection_root / "tool_reference.md"),
        str(projection_root / "healthverse-task-assets" / "tool_reference.md"),
        str(projection_root / "chi-bench-task-assets" / "tool_reference.md"),
        "/opt/healthverse-task-assets/tool_reference.md", "/opt/chi-bench-task-assets/tool_reference.md",
        "/workspace/skills/managed-care-operations-handbook/SKILL.md",
    }

    def workspace_path(value: Any, *, allow_directory: bool = False) -> Path | None:
        return _workspace_path(workspace_root, value, allow_directory=allow_directory)

    async def read_file(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        path_value = args.get("path")
        workspace_file = workspace_path(path_value)
        handbook_root = Path("/workspace/skills/managed-care-operations-handbook")
        handbook_file = None
        try:
            handbook_candidate = Path(path_value).relative_to(handbook_root)
            if ".." not in handbook_candidate.parts:
                cursor = handbook_root
                if not cursor.is_symlink():
                    for part in handbook_candidate.parts:
                        cursor = cursor / part
                        if cursor.is_symlink():
                            break
                    else:
                        handbook_file = cursor
        except Exception:
            pass
        if type(path_value) is not str or (path_value not in allowed_projection and workspace_file is None and handbook_file is None):
            return "ERROR: path is outside the task projection allowlist"
        path = workspace_file or handbook_file or Path(path_value)
        if path.is_symlink() or not path.is_file():
            return "ERROR: projected file is unavailable"
        offset, limit = args.get("offset"), args.get("limit")
        from pdf_resource_reader import read_allowed_file
        pdf_enabled = getattr(getattr(journal, "policy", None), "scope", None) == "real_development"
        return read_allowed_file(path, offset, limit, pdf_enabled=pdf_enabled)

    async def list_files(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        allowed_dirs = {str(projection_root), str(projection_root / "healthverse-task-assets"),
                        str(projection_root / "chi-bench-task-assets"),
                        "/workspace/skills/managed-care-operations-handbook"}
        path_value = args.get("path")
        workspace_dir = workspace_path(path_value, allow_directory=True)
        handbook_root = Path("/workspace/skills/managed-care-operations-handbook")
        handbook_dir = None
        try:
            rel = Path(path_value).relative_to(handbook_root)
            if ".." not in rel.parts:
                handbook_dir = Path(path_value)
        except Exception:
            pass
        if type(path_value) is not str or (path_value not in allowed_dirs and workspace_dir is None and handbook_dir is None):
            return "ERROR: directory is outside the task projection allowlist"
        path = workspace_dir or handbook_dir or Path(path_value)
        if path.is_symlink() or not path.is_dir():
            return "ERROR: projected directory is unavailable"
        return "\n".join(sorted(p.name for p in path.iterdir()
                                if not p.is_symlink() and (p.is_file() or p.is_dir())))

    async def write_file(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        path = workspace_path(args.get("path"))
        content = args.get("content")
        if path is None or type(content) is not str:
            return "ERROR: writes are limited to provider/shared workspace files"
        path.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in (workspace_root, *path.parents) if parent.exists()):
            return "ERROR: symlink paths are not allowed"
        path.write_text(content, encoding="utf-8")
        return f"wrote {len(content.encode('utf-8'))} bytes to {path}"

    async def edit_file(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        path = workspace_path(args.get("path"))
        old, new = args.get("old_string"), args.get("new_string")
        if path is None or type(old) is not str or type(new) is not str or not old:
            return "ERROR: edits are limited to provider/shared workspace files"
        if path.is_symlink() or not path.is_file():
            return "ERROR: workspace file does not exist"
        text = path.read_text(encoding="utf-8")
        if old not in text:
            return "ERROR: old_string not found"
        replace_all = args.get("replace_all", False)
        path.write_text(text.replace(old, new) if replace_all else text.replace(old, new, 1), encoding="utf-8")
        return f"edited {path}"

    async def claim_done(_ctx: Any, _payload: str) -> str:
        return "task marked as done"

    async def sleep_tool(_ctx: Any, payload: str) -> str:
        import asyncio
        seconds = min(max(float(json.loads(payload).get("seconds", 1)), 0.0), 30.0)
        await asyncio.sleep(seconds)
        return f"slept {seconds:g}s"

    async def read_patient_observation(_ctx: Any, payload: str) -> str:
        args = json.loads(payload)
        from patient_identity_binding import Refusal
        try:
            return binding.read_observation(args["patient_id"], args["offset"])
        except Refusal as exc:
            return f"REFUSED: {exc}"

    async def confirm_patient(_ctx: Any, payload: str) -> str:
        from patient_identity_binding import PROMPT, PROMPT_VERSION, MAX_CONFIRM_INPUT, CONFIRM_MAX_OUTPUT_TOKENS, Refusal
        args = json.loads(payload)
        try:
            evidence = binding.confirmation_input(args["patient_id"], exchanges or [])
            if (not args["instruction_quote"].strip() or args["instruction_quote"] not in binding.instruction
                    or not args["chart_quote"].strip() or args["chart_quote"] not in binding.charts[args["patient_id"]]["text"]):
                raise Refusal("selection_evidence_unverified")
        except Refusal as exc:
            binding.event("confirmation_refused", reason=str(exc))
            return f"REFUSED: {exc}"
        evidence = json.dumps({"selection": args, "public_observations": json.loads(evidence)}, ensure_ascii=False)
        if len(evidence.encode()) > MAX_CONFIRM_INPUT:
            binding.event("confirmation_refused", reason="confirmation_input_too_large")
            return "REFUSED: confirmation_input_too_large"
        binding.confirmations += 1
        binding.event("confirmation_attempt", attempt=binding.confirmations, purpose="patient_confirmation",
                      prompt_version=PROMPT_VERSION, prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
                      evidence_sha256=hashlib.sha256(evidence.encode()).hexdigest(), provider_round=ledger.rounds + 1)
        token = request_context.set(("patient_confirmation", hashlib.sha256(evidence.encode()).hexdigest())) if request_context is not None else None
        try:
            response = await openai_client.chat.completions.create(
                model=profile.model, messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": evidence}],
                max_tokens=CONFIRM_MAX_OUTPUT_TOKENS, response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": "high"})
        finally:
            if token is not None:
                request_context.reset(token)
        choices = getattr(response, "choices", None)
        choice = choices[0] if type(choices) is list and len(choices) == 1 else None
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        finish_reason = getattr(choice, "finish_reason", None)
        if choice is None or message is None:
            result = {"status": "invalid", "reason": "confirmation_format_invalid"}
        elif (getattr(message, "role", None) != "assistant"
              or getattr(message, "tool_calls", None) not in (None, [])
              or getattr(message, "function_call", None) is not None):
            result = {"status": "invalid", "reason": "confirmation_format_invalid"}
        elif finish_reason == "length":
            result = {"status": "invalid", "reason": "confirmation_output_truncated"}
        elif finish_reason != "stop":
            result = {"status": "invalid", "reason": "confirmation_format_invalid"}
        elif not isinstance(content, str) or not content.strip():
            result = {"status": "invalid", "reason": "confirmation_empty"}
        else:
            result = binding.assess(args["patient_id"], content)
        binding.event("confirmation_result", attempt=binding.confirmations, result=result,
                      response_content=content if isinstance(content, str) else None)
        return json.dumps(result, ensure_ascii=False)

    def fn(name: str, description: str, schema: dict[str, Any], callback: Any) -> Any:
        async def tracked(ctx: Any, payload: str) -> Any:
            try:
                arguments = json.loads(payload, object_pairs_hook=_no_duplicate_keys,
                                       parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
            except Exception:
                raise LiveFailure("tool_arguments_invalid") from None
            pending = next((item for item in ledger.pending_calls or []
                            if item.get("tool") == name and item.get("arguments") == arguments), None)
            if pending is None:
                raise LiveFailure("tool_dispatch_unvalidated")
            ledger.pending_calls.remove(pending)
            call_id = pending["call_id"]
            journal.start_dispatch(call_id=call_id, model_name=name, raw_name=name, arguments=arguments)
            token = active_call_id.set(call_id)
            try:
                if binding is not None and name in {"local-fs-write", "local-fs-edit", "local-confirm-patient"}:
                    async with binding_lock:
                        refusal = binding.batch_refusals.get(call_id)
                        if not refusal and name in {"local-fs-write", "local-fs-edit"}:
                            path = workspace_path(arguments.get("path"))
                            if path is None or binding.cases.get(path.relative_to(workspace_root).parts[0]) != binding.bound or binding.bound is None or binding.poisoned:
                                refusal = "workspace_case_unverified"
                        if refusal:
                            binding.event("refusal", call_id=call_id, tool=name, reason=refusal)
                            result = f"REFUSED: {refusal}"
                        else:
                            result = await callback(ctx, payload)
                else:
                    result = await callback(ctx, payload)
                journal.finish_dispatch(call_id=call_id, result=result)
                record_effect(name, result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str))
            except BaseException:
                if binding is not None and name in {"local-fs-write", "local-fs-edit", "local-confirm-patient"}:
                    binding.poisoned = True
                try:
                    journal.finish_dispatch(call_id=call_id, result=None, error=True)
                except Exception:
                    pass
                finally:
                    active_call_id.reset(token)
                raise
            active_call_id.reset(token)
            return result

        return FunctionTool(name=name, description=description, params_json_schema=schema,
                            on_invoke_tool=tracked, strict_json_schema=False)

    empty = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    if kind == "b-smoke":
        tools = [
            fn("smoke_lookup", "Look up the supplied fixed smoke query.",
               {"type": "object", "properties": {"query": {"type": "string", "minLength": 1}},
                "required": ["query"], "additionalProperties": False}, lookup),
            fn("smoke_transform", "Transform the exact string returned by smoke_lookup.",
               {"type": "object", "properties": {"value": {"type": "string", "minLength": 1}},
                "required": ["value"], "additionalProperties": False}, transform),
        ]
        schemas.update({"smoke_lookup": tools[0].params_json_schema,
                        "smoke_transform": tools[1].params_json_schema})
    else:
        read_schema = {"type": "object", "properties": {"path": {"type": "string"},
                       "offset": {"type": "integer", "minimum": 1},
                       "limit": {"type": "integer", "minimum": 1}},
                       "required": ["path"], "additionalProperties": False}
        list_schema = {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"], "additionalProperties": False}
        write_schema = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"], "additionalProperties": False}
        edit_schema = {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"},
                       "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}},
                       "required": ["path", "old_string", "new_string"], "additionalProperties": False}
        schemas.update({"local-fs-read": read_schema, "local-fs-list": list_schema,
                        "local-fs-write": write_schema, "local-fs-edit": edit_schema,
                        "local-claim_done": empty,
                        "local-sleep": {"type": "object", "properties": {"seconds": {"type": "number", "minimum": 0, "maximum": 30}},
                                        "required": ["seconds"], "additionalProperties": False}})
        tools = [fn("local-fs-read", "Read only allowlisted projected task/handbook files and provider/shared workspace files.", read_schema, read_file),
                 fn("local-fs-list", "List files only in the task projection or provider/shared workspace directories.", list_schema, list_files),
                 fn("local-fs-write", "Create or overwrite files only inside provider/shared workspace directories.", write_schema, write_file),
                 fn("local-fs-edit", "Edit existing files only inside provider/shared workspace directories.", edit_schema, edit_file)]
        if binding is not None:
            from patient_identity_binding import CONFIRM_DESCRIPTION, READ_DESCRIPTION
            read_observation_schema = {"type": "object", "properties": {"patient_id": {"type": "string"},
                                        "offset": {"type": "integer", "minimum": 0}},
                                       "required": ["patient_id", "offset"], "additionalProperties": False}
            confirm_schema = {"type": "object", "properties": {"patient_id": {"type": "string"},
                              "instruction_quote": {"type": "string", "minLength": 1},
                              "chart_quote": {"type": "string", "minLength": 1}},
                              "required": ["patient_id", "instruction_quote", "chart_quote"], "additionalProperties": False}
            schemas.update({"local-read-patient-observation": read_observation_schema, "local-confirm-patient": confirm_schema})
            tools.extend([fn("local-read-patient-observation", READ_DESCRIPTION, read_observation_schema, read_patient_observation),
                          fn("local-confirm-patient", CONFIRM_DESCRIPTION, confirm_schema, confirm_patient)])
    tools.extend([fn("local-claim_done", "Mark the task as complete after finishing the work.", empty, claim_done),
                  fn("local-sleep", "Pause briefly while waiting for a known operation.",
                     schemas.get("local-sleep", {"type": "object", "properties": {"seconds": {"type": "number", "minimum": 0, "maximum": 30}},
                                                  "required": ["seconds"], "additionalProperties": False}), sleep_tool)])
    return tools


def _validate_live_response(response: dict[str, Any], ledger: Any, profile: Any,
                            schemas: dict[str, dict[str, Any]], allowed_names: set[str],
                            journal: RealDevelopmentJournal,
                            raw_names: dict[str, str], *, kind: str = "c-once",
                            observed_history: list[dict[str, Any]] | None = None,
                            binding: Any = None) -> None:
    if response.get("model") != profile.raw["response_model"]:
        raise LiveFailure("response_model_mismatch")
    choices = response.get("choices")
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise LiveFailure("response_shape_invalid")
    choice = choices[0]
    message = choice.get("message")
    if type(message) is not dict or message.get("role") != "assistant":
        raise LiveFailure("response_shape_invalid")
    if type(message.get("reasoning_content")) is not str:
        raise LiveFailure("reasoning_missing")
    finish = choice.get("finish_reason")
    content = message.get("content")
    if content is not None and type(content) is not str:
        raise LiveFailure("response_shape_invalid")
    if finish == "stop":
        if not isinstance(content, str) or not content.strip() or message.get("tool_calls") not in (None, []):
            raise LiveFailure("final_content_invalid")
        return
    if finish != "tool_calls" or type(message.get("tool_calls")) is not list or not message["tool_calls"]:
        raise LiveFailure("finish_reason_invalid")
    parsed = []
    batch_ids: set[str] = set()
    for call in message["tool_calls"]:
        if type(call) is not dict or call.get("type") != "function":
            raise LiveFailure("tool_batch_invalid")
        call_id = call.get("id")
        function = call.get("function")
        name = function.get("name") if type(function) is dict else None
        raw_args = function.get("arguments") if type(function) is dict else None
        if type(call_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call_id) or call_id in batch_ids:
            raise LiveFailure("tool_batch_invalid")
        if type(name) is not str or name not in allowed_names or name not in schemas:
            raise LiveFailure("tool_not_allowlisted_or_schema_missing")
        try:
            args = json.loads(raw_args, object_pairs_hook=_no_duplicate_keys,
                              parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
        except Exception:
            raise LiveFailure("tool_arguments_invalid") from None
        if not _strict_tool_arguments(schemas[name], args):
            raise LiveFailure("tool_arguments_invalid")
        if kind == "b-smoke" and name == "smoke_transform":
            if not any(entry.get("tool") == "smoke_lookup"
                       and entry.get("result") == args.get("value")
                       and type(entry.get("observed_at_request_round")) is int
                       and entry["observed_at_request_round"] <= ledger.rounds
                       for entry in (observed_history or [])):
                raise LiveFailure("smoke_transform_without_observed_lookup")
        batch_ids.add(call_id)
        parsed.append((call_id, name, args))
    seen = ledger.validated_call_ids
    if binding is not None:
        from patient_identity_binding import Refusal
        if any(name == "local-confirm-patient" for _, name, _ in parsed) and len(parsed) != 1:
            raise LiveFailure("patient_confirmation_batch_invalid")
        for call_id, name, args in parsed:
            raw_name = raw_names.get(name, name)
            if raw_name.startswith("local-"):
                if raw_name in {"local-fs-write", "local-fs-edit"}:
                    path = _workspace_path(WORKSPACE_CONTAINER_ROOT, args.get("path"))
                    if path is None or binding.bound is None or binding.poisoned or binding.cases.get(path.relative_to(WORKSPACE_CONTAINER_ROOT).parts[0]) != binding.bound:
                        binding.batch_refusals[call_id] = "workspace_case_unverified"
                continue
            try:
                binding.check(raw_name, args)
            except Refusal as exc:
                binding.batch_refusals[call_id] = str(exc)
    for call_id, _name, _args in parsed:
        if call_id in seen:
            raise LiveFailure("tool_call_id_duplicate")
    ledger.pending_calls.extend({"call_id": i, "tool": n, "arguments": a} for i, n, a in parsed)
    seen.update(batch_ids)
    journal.record_validated_dispatches([
        {"call_id": call_id, "model_name": name, "raw_name": raw_names.get(name, name),
         "argument_keys": sorted(args),
         "arguments_sha256": hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
         "response_round": ledger.rounds,
         "state": "validated", "validated_at": datetime.now(timezone.utc).isoformat()}
        for call_id, name, args in parsed
    ])


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _observe_live_history(body: dict[str, Any], exchanges: list[dict[str, Any]], request_round: int) -> None:
    calls: dict[str, tuple[str, str]] = {}
    for message in body.get("messages", []):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls", []):
            function = call.get("function", {})
            calls[call.get("id")] = (function.get("name"), function.get("arguments"))
    seen_ids = {entry.get("call_id") for entry in exchanges}
    for message in body.get("messages", []):
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        call_id = message.get("tool_call_id")
        if call_id in seen_ids:
            continue
        name, arguments = calls.get(call_id, (None, None))
        result = message.get("content")
        if not isinstance(name, str):
            raise LiveFailure("tool_history_invalid")
        if isinstance(result, str):
            derived_text = result
            provenance = "raw_wire_tool_content_string"
        elif (isinstance(result, list) and result and all(
                type(part) is dict and set(part) == {"type", "text"} and part.get("type") == "text"
                and isinstance(part.get("text"), str) for part in result)):
            derived_text = "".join(part["text"] for part in result)
            provenance = "derived_text_concatenated_in_wire_order_from_raw_text_blocks"
        else:
            raise LiveFailure("tool_history_invalid")
        exchanges.append({"call_id": call_id, "tool": name, "arguments": arguments,
                          "result": derived_text, "raw_wire_content": result,
                          "observed_at_request_round": request_round,
                          "provenance": provenance})


def _b_smoke_evidence_valid(journal: RealDevelopmentJournal, exchanges: list[dict[str, Any]],
                            final_output: str) -> bool:
    dispatches = journal.run_doc.get("tool_dispatches", [])
    effects = journal.run_doc.get("tool_effects", [])
    lookups = [item for item in dispatches if item.get("model_name") == "smoke_lookup"
               and item.get("state") == "returned"]
    transforms = [item for item in dispatches if item.get("model_name") == "smoke_transform"
                  and item.get("state") == "returned"]
    if len(lookups) != 1 or len(transforms) != 1 or len(journal.run_doc.get("requests", [])) < 3:
        return False
    lookup, transform = lookups[0], transforms[0]
    if lookup.get("response_round", 99) >= transform.get("response_round", 0):
        return False
    lookup_history = next((item for item in exchanges if item.get("call_id") == lookup.get("call_id")
                           and item.get("tool") == "smoke_lookup"), None)
    transform_history = next((item for item in exchanges if item.get("call_id") == transform.get("call_id")
                              and item.get("tool") == "smoke_transform"), None)
    lookup_effect = next((item for item in effects if item.get("call_id") == lookup.get("call_id")
                          and item.get("tool") == "smoke_lookup"), None)
    transform_effect = next((item for item in effects if item.get("call_id") == transform.get("call_id")
                             and item.get("tool") == "smoke_transform"), None)
    if not all((lookup_history, transform_history, lookup_effect, transform_effect)):
        return False
    observed_round = lookup_history.get("observed_at_request_round")
    response_round = transform.get("response_round")
    if (type(observed_round) is not int or type(response_round) is not int
            or observed_round > response_round):
        return False
    try:
        transform_args = json.loads(transform_history["arguments"], object_pairs_hook=_no_duplicate_keys)
    except Exception:
        return False
    return (lookup_history.get("result") == lookup_effect.get("result")
            and transform_args.get("value") == lookup_history.get("result")
            and transform_history.get("result") == transform_effect.get("result")
            and isinstance(final_output, str) and bool(final_output.strip()))


def _install_dispatch_recorder(official_runner: Any, mcp_util: Any, journal: RealDevelopmentJournal,
                               binding: Any = None, binding_lock: Any = None,
                               active_mcp: Any = None) -> tuple[Any, Any]:
    original_install = official_runner._install_oversize_output_patch
    original_invoke = mcp_util.__dict__["invoke_mcp_tool"]

    def install_then_wrap(logs_dir: Path) -> None:
        original_install(logs_dir)
        patched_invoke = mcp_util.invoke_mcp_tool

        async def monitored(_cls: Any, server: Any, tool: Any, context: Any, input_json: str, *, meta: Any = None):
            raw_name = getattr(tool, "name", None)
            if not isinstance(raw_name, str):
                raise LiveFailure("tool_dispatch_identity_mismatch")
            model_name = re.sub(r"[^a-zA-Z0-9_-]", "__", raw_name)
            try:
                arguments = json.loads(input_json, object_pairs_hook=_no_duplicate_keys,
                                       parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
            except Exception:
                raise LiveFailure("tool_arguments_invalid") from None
            candidates = [item for item in journal.run_doc.get("tool_dispatches", [])
                          if item.get("state") == "validated" and item.get("raw_name") == raw_name
                          and item.get("model_name") == model_name]
            if not candidates:
                raise LiveFailure("tool_dispatch_identity_mismatch")
            selected = next((item for item in candidates if item.get("arguments_sha256") == hashlib.sha256(
                json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()), None)
            if selected is None:
                raise LiveFailure("tool_dispatch_identity_mismatch")
            call_id = selected["call_id"]
            journal.start_dispatch(call_id=call_id, model_name=model_name, raw_name=raw_name, arguments=arguments)
            try:
                if binding is None:
                    value = await patched_invoke(server, tool, context, input_json, meta=meta)
                else:
                    from patient_identity_binding import Refusal
                    async with binding_lock:
                        refusal = binding.batch_refusals.get(call_id)
                        if not refusal:
                            try:
                                binding.check(raw_name, arguments)
                            except Refusal as exc:
                                refusal = str(exc)
                        if refusal:
                            binding.event("refusal", call_id=call_id, tool=raw_name, reason=refusal)
                            value = f"REFUSED: {refusal}"
                        else:
                            token = active_mcp.set((call_id, raw_name, arguments))
                            try:
                                value = await patched_invoke(server, tool, context, input_json, meta=meta)
                            except BaseException:
                                binding.poisoned = True
                                raise
                            finally:
                                active_mcp.reset(token)
            except BaseException:
                journal.finish_dispatch(call_id=call_id, result=None, error=True)
                raise
            try:
                journal.finish_dispatch(call_id=call_id, result=value)
            except BaseException:
                if binding is not None:
                    binding.poisoned = True
                raise
            return value

        mcp_util.invoke_mcp_tool = classmethod(monitored)

    official_runner._install_oversize_output_patch = install_then_wrap
    return original_install, original_invoke


async def _worker_run(args: argparse.Namespace) -> int:
    import asyncio
    import contextlib
    import io
    import httpx
    from contextlib import asynccontextmanager

    from b_execution_policy import load_local_policy
    from b_provider_profile import load_profile
    from b_provider_transport import GuardFailure, GuardedTransport
    from model_runner_adapter import (
        Ledger, _patch_empty_history_compatibility, _same_route_reasoning,
    )

    kind, run_id = args.kind, args.run_id
    if not isinstance(run_id, str) or ID_RE.fullmatch(run_id) is None:
        raise LiveFailure("run_id_invalid")
    _validate_worker_mounts(args)
    profile = load_profile()
    k = getattr(args, "k_development", False)
    policy = load_real_development_policy() if k else load_local_policy()
    instruction_file = args.instruction_file
    logs_dir = args.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=False)
    secret = os.environ.get("DEEPSEEK_API_KEY")
    if not secret:
        raise LiveFailure("provider_credential_missing")
    if kind == "c-once":
        _transition_c_claim(args.budget_root, run_id, "runner_started_once",
                            execution_identity=_execution_identity(k=True) if k else _execution_identity(),
                            profile_sha256=profile.sha256, k=k, task_id=getattr(args, "task_id", TASK_ID))
    journal = RealDevelopmentJournal(args.budget_root, run_id, profile=profile, policy=policy)
    ledger = Ledger("real-provider", initial_cost_cny=float(journal.cumulative_spend),
                    prior_cost_source=journal.state["prior_source"])
    schemas: dict[str, dict[str, Any]] = {}
    raw_names: dict[str, str] = {}
    allowed_names: set[str] = set()
    exchanges: list[dict[str, Any]] = []
    binding = None
    binding_lock = None
    active_mcp = None
    request_context = None
    if k and kind == "c-once":
        import contextvars
        from patient_identity_binding import PatientBinding
        binding = PatientBinding(instruction_file.read_text(encoding="utf-8"), journal)
        binding_lock = asyncio.Lock()
        active_mcp = contextvars.ContextVar("patient_binding_mcp", default=None)
        request_context = contextvars.ContextVar("patient_binding_request", default=None)
    result_code = 1
    primary_error: str | None = None
    cleanup_error: str | None = None
    openai_client = None
    client_http = None
    b_success_candidate: dict[str, Any] | None = None
    restore: list[tuple[Any, str, Any]] = []
    runner_stdout, runner_stderr = io.StringIO(), io.StringIO()
    original_max_turns = os.environ.get("OPENAI_AGENTS_MAX_TURNS")
    overridden_max_turns = bool(k and kind == "c-once")
    try:
        if overridden_max_turns:
            from request_budget import K_C_CONTRACT, MAX_REQUESTS
            os.environ["OPENAI_AGENTS_MAX_TURNS"] = str(MAX_REQUESTS)
            journal.run_doc["run_kind"] = "c-once"
            journal._persist()
        if binding is not None:
            from patient_identity_binding import CONFIRM_DESCRIPTION, READ_DESCRIPTION, PROMPT, PROMPT_VERSION
            from referral_field_guidance import VERSION as REFERRAL_GUIDANCE_VERSION, GUIDANCE_SHA256
            journal.run_doc["referral_field_guidance"] = {
                "version": REFERRAL_GUIDANCE_VERSION, "guidance_sha256": GUIDANCE_SHA256, "tools": {}}
            binding.event("protocol", prompt_version=PROMPT_VERSION, prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
                          confirm_tool_description_sha256=hashlib.sha256(CONFIRM_DESCRIPTION.encode()).hexdigest(),
                          read_tool_description_sha256=hashlib.sha256(READ_DESCRIPTION.encode()).hexdigest())
        if k and kind == "c-once" and getattr(args, "task_id", TASK_ID) != TASK_ID:
            from provider_task_resources import identity
            journal.run_doc["task_id"] = args.task_id
            journal.run_doc["task_resource_identity"] = identity(args.task_id)
            journal._persist()
        import agents.mcp as agents_mcp
        from agents.models.openai_chatcompletions import Converter, OpenAIChatCompletionsModel
        from agents import ModelSettings, ModelRetrySettings
        from openai import AsyncOpenAI
        from agents.tracing import get_trace_provider
        from agents.mcp.util import MCPUtil
        from chi_bench.experiment.agents import openai_agents_runner as official_runner
        import chi_bench.experiment.agents.openai_agents_local_tools as local_tools_module

        originals = {
            "context": official_runner._agent_model_context,
            "settings": official_runner._build_model_settings,
            "tools": local_tools_module.build_local_tools,
            "mcp": agents_mcp.MCPServerStreamableHttp,
            "mcp_to_tool": MCPUtil.__dict__["to_function_tool"],
            "mcp_name_sanitizer": getattr(MCPUtil, "_chi_bench_name_sanitizer_installed", False),
            "conv_message": Converter.message_to_output_items,
            "conv_history": Converter.items_to_messages,
            "trace": get_trace_provider(),
        }
        # The profile only permits the fixed DeepSeek chat-completions route.
        try:
            wire_snapshot = {"model": profile.model, "endpoint": profile.endpoint,
                             "api": profile.raw["api"], "thinking": profile.raw["thinking"],
                             "reasoning_effort": profile.raw["reasoning_effort"]}
            if wire_snapshot != {"model": "deepseek-flash", "endpoint": "https://api.deepseek.com",
                                 "api": "chat_completions", "thinking": {"type": "enabled"},
                                 "reasoning_effort": "high"}:
                raise LiveFailure("profile_identity_mismatch")
            http_transport = httpx.AsyncHTTPTransport(retries=0, verify=True)
            output_ceiling = min(profile.max_output_tokens, 1024) if kind == "b-smoke" else profile.max_output_tokens
            def validate_provider_response(payload: dict[str, Any]) -> None:
                if request_context is not None and request_context.get() is not None:
                    if payload.get("model") != profile.raw["response_model"]:
                        raise LiveFailure("response_model_mismatch")
                    return
                _validate_live_response(payload, ledger, profile, schemas, allowed_names, journal, raw_names,
                                        kind=kind, observed_history=exchanges, binding=binding)
            client_http = httpx.AsyncClient(transport=GuardedTransport(
                profile=profile, journal=journal, lower=http_transport, ledger=ledger,
                cap_cny=policy.hard_cap_cny,
                validate_response=validate_provider_response,
                allowed_tool_names=allowed_names,
                observe_request=lambda body: _observe_live_history(body, exchanges, ledger.rounds),
                max_rounds=6 if kind == "b-smoke" else (MAX_REQUESTS if overridden_max_turns else profile.max_rounds),
                allow_text_blocks_in_tool_history=kind == "c-once",
                confirmation_context=request_context.get if request_context is not None else None,
                **({"run_contract": K_C_CONTRACT,
                    "base_system_instructions": official_runner.SYSTEM_PROMPT} if overridden_max_turns else {}),
            ), trust_env=False, follow_redirects=False, timeout=httpx.Timeout(60.0, connect=10.0))
            openai_client = AsyncOpenAI(api_key=secret, base_url=profile.endpoint + "/v1",
                                        http_client=client_http, max_retries=0)
            if overridden_max_turns:
                from request_budget import feedback, claim_recorded
                class BudgetedModel(OpenAIChatCompletionsModel):
                    async def get_response(self, system_instructions: str | None, *args: Any, **kwargs: Any):
                        if system_instructions != official_runner.SYSTEM_PROMPT:
                            raise LiveFailure("request_budget_base_prompt_invalid")
                        try:
                            suffix, _ = feedback(ledger.rounds, claim_recorded(journal))
                        except ValueError:
                            ledger.error_code = "provider_request_limit_reached"
                            raise LiveFailure("provider_request_limit_reached") from None
                        return await super().get_response(system_instructions + suffix, *args, **kwargs)
                model_class = BudgetedModel
            else:
                model_class = OpenAIChatCompletionsModel
            sdk_model = model_class(model=profile.model, openai_client=openai_client,
                                    should_replay_reasoning_content=_same_route_reasoning)

            @asynccontextmanager
            async def model_context(_model: str, _mode: str):
                yield sdk_model

            def settings(_effort: str | None = None, *, separate_reasoning: bool = False):
                del separate_reasoning
                return ModelSettings(max_tokens=output_ceiling,
                                     reasoning={"effort": "high"},
                                     extra_body={"thinking": {"type": "enabled"}},
                                     retry=ModelRetrySettings(max_retries=0))

            projection_root = instruction_file.parent if kind == "c-once" else logs_dir
            local_tools = _live_tools(kind, logs_dir, projection_root, journal, schemas, ledger,
                                      binding=binding, binding_lock=binding_lock, openai_client=openai_client,
                                      profile=profile, exchanges=exchanges, request_context=request_context)
            for local_tool in local_tools:
                local_name = getattr(local_tool, "name", None)
                local_schema = getattr(local_tool, "params_json_schema", None)
                if not isinstance(local_name, str) or not isinstance(local_schema, dict):
                    raise LiveFailure("local_tool_schema_invalid")
                prior_schema = schemas.get(local_name)
                if prior_schema is not None and prior_schema != local_schema:
                    raise LiveFailure("local_tool_schema_collision")
                schemas.setdefault(local_name, local_schema)
                raw_names[local_name] = local_name
            allowed_names.update(schemas)
            local_tools_module.build_local_tools = lambda _logs: local_tools

            original_mcp_factory = agents_mcp.MCPServerStreamableHttp
            dispatch_install, dispatch_invoke = _install_dispatch_recorder(official_runner, MCPUtil, journal,
                                                                            binding, binding_lock, active_mcp)
            original_to_function = MCPUtil.__dict__["to_function_tool"]

            def strict_to_function_tool(_cls: Any, tool: Any, server: Any, convert_schemas_to_strict: bool,
                                        agent: Any = None, failure_error_function: Any = None):
                function_tool = original_to_function.__func__(
                    _cls, tool, server, convert_schemas_to_strict, agent=agent,
                    failure_error_function=None,
                )
                if k and kind == "c-once":
                    _apply_referral_guidance(function_tool, getattr(tool, "name", None), journal)
                return function_tool

            MCPUtil.to_function_tool = classmethod(strict_to_function_tool)
            if kind == "b-smoke":
                class EmptySmokeMCP:
                    name = "real-b-smoke-empty-mcp"
                    async def __aenter__(self): return self
                    async def __aexit__(self, *_args): return False
                    async def list_tools(self, *_args, **_kwargs): return []
                agents_mcp.MCPServerStreamableHttp = lambda *_a, **_kw: EmptySmokeMCP()
            else:
                class CapturedMCP:
                    def __init__(self, *a: Any, **kw: Any):
                        kw["max_retry_attempts"] = 0
                        self.inner = original_mcp_factory(*a, **kw)
                    async def __aenter__(self): await self.inner.__aenter__(); return self
                    async def __aexit__(self, *a: Any): return await self.inner.__aexit__(*a)
                    async def list_tools(self, *a: Any, **kw: Any):
                        tools = await self.inner.list_tools(*a, **kw)
                        for tool in tools:
                            pair = _tool_schema(tool)
                            if pair is None: raise LiveFailure("mcp_schema_unavailable")
                            name, schema = pair
                            if re.match(r"^(chart|cases|inbox|docs|forms|auth|people|p2p_session)(?:[./:_-]|__)", name) is None:
                                raise LiveFailure("mcp_namespace_not_allowlisted")
                            model_name = re.sub(r"[^a-zA-Z0-9_-]", "__", name)
                            if model_name in schemas:
                                if raw_names.get(model_name) == name and schemas[model_name] == schema:
                                    continue
                                raise LiveFailure("mcp_tool_name_collision")
                            schemas[model_name] = schema
                            raw_names[model_name] = name
                            allowed_names.add(model_name)
                        if not tools: raise LiveFailure("mcp_schema_empty")
                        return tools
                    async def call_tool(self, *a: Any, **kw: Any):
                        result = await self.inner.call_tool(*a, **kw)
                        if binding is not None:
                            call = active_mcp.get()
                            if call is None:
                                raise LiveFailure("patient_binding_call_missing")
                            if getattr(result, "isError", False):
                                binding.poisoned = True
                                raise LiveFailure("patient_binding_backend_error")
                            binding.observe(call[0], call[1], call[2], result)
                        return result
                    def __getattr__(self, name: str): return getattr(self.inner, name)
                agents_mcp.MCPServerStreamableHttp = CapturedMCP
            official_runner._agent_model_context = model_context
            official_runner._build_model_settings = settings
            old_converter_message, old_converter_history = _patch_empty_history_compatibility(
                Converter, profile.endpoint, profile.model)
            restore = [(official_runner, "_agent_model_context", originals["context"]),
                       (official_runner, "_build_model_settings", originals["settings"]),
                       (official_runner, "_install_oversize_output_patch", dispatch_install),
                       (local_tools_module, "build_local_tools", originals["tools"]),
                       (agents_mcp, "MCPServerStreamableHttp", originals["mcp"]),
                       (MCPUtil, "invoke_mcp_tool", dispatch_invoke),
                       (MCPUtil, "to_function_tool", originals["mcp_to_tool"]),
                       (MCPUtil, "_chi_bench_name_sanitizer_installed", originals["mcp_name_sanitizer"]),
                       (Converter, "message_to_output_items", old_converter_message),
                       (Converter, "items_to_messages", old_converter_history)]
            # The upstream runner disables traces and writes its complete result/trace in logs_dir.
            with contextlib.redirect_stdout(runner_stdout), contextlib.redirect_stderr(runner_stderr):
                try:
                    await official_runner.run_agent(instruction_file.read_text(encoding="utf-8"), args.mcp_url,
                                                    logs_dir=logs_dir)
                    result_code = 0
                except SystemExit as exc:
                    result_code = int(exc.code or 0)
                    if result_code:
                        if (overridden_max_turns and ledger.rounds == MAX_REQUESTS
                                and "Agent error: MaxTurnsExceeded:" in runner_stderr.getvalue()):
                            primary_error = "provider_request_limit_reached"
                        else:
                            primary_error = ledger.error_code or "official_runner_failed"
                except Exception as exc:
                    result_code = 1
                    primary_error = getattr(exc, "code", "official_runner_failed")
                    # Keep a non-sensitive exception class for offline diagnostics; exception
                    # messages can contain request URLs, response bodies, or credentials.
                    runner_stderr.write(f"worker_exception_type={type(exc).__name__}\n")
        except Exception as exc:
            primary_error = getattr(exc, "code", "live_setup_failed")
            result_code = 1
            runner_stderr.write(f"setup_exception_type={type(exc).__name__}\n")
    finally:
        if overridden_max_turns:
            if original_max_turns is None:
                os.environ.pop("OPENAI_AGENTS_MAX_TURNS", None)
            else:
                os.environ["OPENAI_AGENTS_MAX_TURNS"] = original_max_turns
        for obj, attr, original in reversed(restore):
            try:
                setattr(obj, attr, original)
            except Exception:
                cleanup_error = cleanup_error or "runner_global_restore_failed"
        if openai_client is not None:
            try:
                await openai_client.close()
            except Exception:
                cleanup_error = cleanup_error or "provider_client_close_failed"
        elif client_http is not None:
            try:
                await client_http.aclose()
            except Exception:
                cleanup_error = cleanup_error or "provider_transport_close_failed"
        try:
            (logs_dir / "run_log.txt").write_text(runner_stdout.getvalue() + runner_stderr.getvalue(), encoding="utf-8")
            _scrub_secret(logs_dir, secret)
        except Exception:
            cleanup_error = cleanup_error or "runner_logs_persist_failed"
        try:
            if exchanges:
                journal.record_history(exchanges)
            if kind == "b-smoke":
                output_path = logs_dir / "run_output.txt"
                final_output = output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
                if not _b_smoke_evidence_valid(journal, exchanges, final_output):
                    result_code = 1
                    primary_error = primary_error or "smoke_tool_exchange_incomplete_or_independent"
            required_artifacts = ("run_result.json", "run_output.txt", "trace.jsonl", "run_log.txt")
            missing_artifacts = [name for name in required_artifacts
                                 if not (logs_dir / name).is_file() or (logs_dir / name).stat().st_size == 0]
            if missing_artifacts:
                result_code = 1
                primary_error = primary_error or "official_runner_artifacts_missing"
            if cleanup_error is not None:
                result_code = 1
            journal.finalize(status="complete" if result_code == 0 else "incomplete",
                             primary_error=primary_error, cleanup_error=cleanup_error)
            if kind == "b-smoke" and result_code == 0:
                run_path = args.budget_root / "runs" / f"{run_id}.json"
                b_success = {"schema": B_SUCCESS_SCHEMA, "campaign_id": CAMPAIGN_ID, "task_id": TASK_ID,
                             "run_id": run_id, "status": "success", "profile_sha256": profile.sha256,
                             "execution_identity": journal.state["execution_identity"],
                             "usage": dict(journal.run_doc["real_usage"]),
                             "estimated_cost_cny": journal.run_doc["estimated_cost_cny"],
                             "run_journal_sha256": hashlib.sha256(run_path.read_bytes()).hexdigest(),
                             "runner_result_sha256": hashlib.sha256((logs_dir / "run_result.json").read_bytes()).hexdigest(),
                             "run_output_sha256": hashlib.sha256((logs_dir / "run_output.txt").read_bytes()).hexdigest(),
                             "trace_sha256": hashlib.sha256((logs_dir / "trace.jsonl").read_bytes()).hexdigest(),
                             "run_log_sha256": hashlib.sha256((logs_dir / "run_log.txt").read_bytes()).hexdigest(),
                             "official_reward": None, "success_at": datetime.now(timezone.utc).isoformat()}
                b_success_candidate = b_success
        except Exception as exc:
            result_code = 1
            primary_error = primary_error or "real_journal_finalize_failed"
            runner_stderr.write(f"journal_finalization_exception_type={type(exc).__name__}\n")
            try:
                journal.run_doc["primary_error_code"] = primary_error
                journal.run_doc["persistence_error_code"] = primary_error
                journal.run_doc["state"] = "incomplete"
            except Exception:
                pass
        try:
            journal.close()
        except Exception as exc:
            result_code = 1
            cleanup_error = cleanup_error or "journal_close_failed"
            runner_stderr.write(f"journal_close_exception_type={type(exc).__name__}\n")
            try:
                journal.run_doc["state"] = "incomplete"
                journal.run_doc["cleanup_error_code"] = cleanup_error
                _atomic_json(journal.run_path, journal.run_doc)
            except Exception:
                primary_error = primary_error or "run_document_reconciliation_failed"
    if b_success_candidate is not None and result_code == 0:
        receipt = args.budget_root / "b-success.json"
        try:
            _atomic_json(receipt, b_success_candidate, exclusive=True)
        except Exception:
            result_code = 1
            primary_error = "b_success_evidence_persist_failed"
            try:
                receipt.unlink(missing_ok=True)
                _fsync_parent(receipt)
            except Exception:
                pass
    return result_code


def _scrub_secret(logs_dir: Path, secret: str) -> None:
    if not secret:
        return
    for path in logs_dir.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if secret in text:
            path.write_text(text.replace(secret, "[REDACTED_SECRET]"), encoding="utf-8")


def _validate_worker_mounts(args: argparse.Namespace) -> None:
    # The fake orchestration supplies host paths directly to the in-process worker;
    # this sentinel is never populated by the public CLI parser.
    if getattr(args, "_test_context", None) is _MOCK_ORCHESTRATION_TEST:
        return
    expected_budget = Path("/participant/real-budget")
    expected_logs = Path("/participant/run/runner-logs")
    expected_instruction = (Path("/participant/projection/instruction.md") if args.kind == "c-once"
                            else Path("/participant/run/b-smoke-instruction.md"))
    expected_mcp = (f"http://chi-agent-a-world-{args.run_id}:8020/mcp" if args.kind == "c-once"
                    else "http://127.0.0.1:9/unused-mcp-for-b-smoke")
    if (args.budget_root != expected_budget or args.logs_dir != expected_logs
            or args.instruction_file != expected_instruction or args.mcp_url != expected_mcp):
        raise LiveFailure("worker_scope_arguments_invalid")


def _run_worker(args: argparse.Namespace) -> int:
    import asyncio
    if args.kind == "c-once" and getattr(args, "k_development", False) and args.task_id != TASK_ID:
        from provider_task_resources import TASK_FILES
        if args.task_id not in TASK_FILES:
            raise LiveFailure("official_task_resources_invalid")
    return asyncio.run(_worker_run(args))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    pre = sub.add_parser("preflight")
    pre.add_argument("--budget-root", type=Path, default=ROOT / REAL_ROOT_RELATIVE)
    init = sub.add_parser("init-prior")
    init.add_argument("--budget-root", type=Path, default=ROOT / REAL_ROOT_RELATIVE)
    for name in ("b-smoke", "c-once"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run-id", required=True)
        cmd.add_argument("--budget-root", type=Path, default=ROOT / REAL_ROOT_RELATIVE)
    sub.add_parser("adopt-prior")
    transition = sub.add_parser("rebind-source")
    transition.add_argument("--reason", required=True)
    for name in ("k-b-smoke", "c-run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run-id", required=True)
        if name == "c-run":
            from provider_task_resources import TASK_FILES
            cmd.add_argument("--task-id", required=True, choices=tuple(TASK_FILES))
    worker = sub.add_parser("worker")
    worker.add_argument("--kind", choices=("b-smoke", "c-once"), required=True)
    worker.add_argument("--run-id", required=True)
    worker.add_argument("--budget-root", type=Path, required=True)
    worker.add_argument("--logs-dir", type=Path, required=True)
    worker.add_argument("--instruction-file", type=Path, required=True)
    worker.add_argument("--mcp-url", required=True)
    worker.add_argument("--k-development", action="store_true")
    worker.add_argument("--task-id", default=TASK_ID)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        k_root = ROOT / K_ROOT_RELATIVE
        if args.command == "adopt-prior":
            _k_locked(k_root, lambda: adopt_prior(ROOT / REAL_ROOT_RELATIVE, k_root))
            print(_json({"status": "adopted", "official_reward": None}))
            return 0
        if args.command == "rebind-source":
            _k_locked(k_root, lambda: rebind_source(k_root, args.reason))
            print(_json({"status": "rebound", "official_reward": None}))
            return 0
        if args.command in {"k-b-smoke", "c-run"}:
            if ID_RE.fullmatch(args.run_id) is None:
                raise LiveFailure("run_id_invalid")
            kind = "b-smoke" if args.command == "k-b-smoke" else "c-once"
            result = _k_locked(k_root, lambda: _k_run(kind, args.run_id, k_root, getattr(args, "task_id", TASK_ID)))
            print(_json(result))
            return 0 if result.get("status") in {"completed_ungraded", "smoke_completed"} else 1
        if args.command == "plan":
            print(_json(build_read_only_plan()))
            return 0
        if args.command == "preflight":
            result = build_preflight(args.budget_root)
            print(_json(result))
            return 0 if result["identity"]["status"] == "verified" and result["budget"]["status"] == "known" and result["budget"]["can_reserve_one_max_request"] else 1
        if args.command == "init-prior":
            if args.budget_root.resolve() != (ROOT / REAL_ROOT_RELATIVE).resolve():
                raise LiveFailure("real_budget_root_mismatch")
            state = initialize_real_accounting(
                args.budget_root,
                prior_source="reviewed_project_campaign_history_no_real_B_or_C_calls_2026-10-27",
            )
            print(_json({"status": "initialized", "campaign_id": state["campaign_id"],
                         "prior_spend_cny": state["prior_spend_cny"], "prior_source": state["prior_source"],
                         "synthetic_ledgers_read": False, "credentials_read": False}))
            return 0
        if args.command in {"b-smoke", "c-once"}:
            if not isinstance(args.run_id, str) or ID_RE.fullmatch(args.run_id) is None:
                raise LiveFailure("run_id_invalid")
            result = _orchestrate(args.command, args.run_id, args.budget_root)
            print(_json(result))
            return 0 if result.get("status") in {"completed_ungraded", "smoke_completed"} else 1
        if args.command == "worker":
            return _run_worker(args)
    except LiveFailure as exc:
        print(_json({"status": "blocked", "safe_error_code": exc.code,
                     "credentials_logged": False, "official_reward": None}), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
