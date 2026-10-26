"""Reusable pre-send reserve / post-response settle boundary.

The guard accepts the actual HTTP request emitted by the SDK and an injected
lower transport. It contains no canned responses or scenario selection.
Persistent journals created here are explicitly synthetic-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import fcntl
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import httpx

from b_execution_policy import ExecutionPolicy, PolicyFailure, is_validated_policy, load_local_policy
from b_provider_profile import ProviderProfile, is_validated_profile


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
TOOL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
EVALUATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MILLION = Decimal(1_000_000)
MAX_WIRE_BYTES = 8 * 1024 * 1024  # Resource limit only; never a token estimate.


class GuardFailure(Exception):
    def __init__(self, code: str, phase: str):
        super().__init__(code)
        self.code = code
        self.phase = phase


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _atomic_replace(path: Path, payload: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _strict_cap_matches(value: Any, expected: Decimal | None) -> bool:
    if expected is None:
        return value is None
    return type(value) is Decimal and value.is_finite() and value == expected


def _reject_symlink_ancestors(path: Path, code: str) -> None:
    """Reject parent traversal and links without normalizing away components."""
    lexical = Path(path)
    if ".." in lexical.parts:
        raise GuardFailure(code, "preflight")
    absolute = Path(os.path.abspath(lexical))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            details = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise GuardFailure(code, "preflight") from None
        if not stat.S_ISDIR(details.st_mode):
            raise GuardFailure(code, "preflight")


class SyntheticJournal:
    """Exclusive bounded journal for synthetic rehearsals; never a real ledger."""

    def __init__(self, root: Path, run_id: str, *, initial_prior_cny: Decimal = Decimal(0),
                 prior_source: str = "synthetic-rehearsal-prior-v1", cap_cny: Decimal | None = None,
                 policy: ExecutionPolicy | None = None, _allow_evaluation: bool = False):
        if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
            raise GuardFailure("run_id_invalid", "preflight")
        try:
            policy = policy or load_local_policy()
        except PolicyFailure as exc:
            raise GuardFailure(exc.code, "preflight") from None
        if (not is_validated_policy(policy)
                or (policy.scope == "evaluation_rehearsal" and not _allow_evaluation)
                or policy.scope not in {"local_development", "evaluation_rehearsal"}):
            raise GuardFailure("execution_policy_invalid", "preflight")
        if cap_cny is not None and not _strict_cap_matches(cap_cny, policy.hard_cap_cny):
            raise GuardFailure("execution_policy_cap_mismatch", "preflight")
        if (type(prior_source) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", prior_source) is None
                or type(initial_prior_cny) is not Decimal or not initial_prior_cny.is_finite()
                or initial_prior_cny < 0):
            raise GuardFailure("synthetic_prior_invalid", "preflight")
        self.root = root
        self.run_id = run_id
        self.policy = policy
        self.cap_cny = policy.hard_cap_cny
        self.run_path = root / f"{run_id}.json"
        self.state_path = root / "synthetic-accounting.json"
        self.lock_path = root / ".synthetic-namespace.lock"
        self.lock_fd: int | None = None
        self._lock_owned = False
        self.closed = False
        self.run_doc: dict[str, Any] = {
            "schema": "chi-b-synthetic-journal-v1", "namespace": policy.scope,
            "run_id": run_id, "state": "prepared", "requests": [],
            "execution_policy": {"policy_id": policy.policy_id, "policy_sha256": policy.sha256,
                                 "scope": policy.scope, "mode": policy.mode,
                                 "hard_cap_cny": str(policy.hard_cap_cny) if policy.hard_cap_cny is not None else None},
            "primary_error_code": None, "persistence_error_code": None,
            "real_usage": None, "real_cost_cny": None, "official_reward": None,
        }
        try:
            _reject_symlink_ancestors(root, "synthetic_journal_path_invalid")
            root.mkdir(parents=True, exist_ok=True)
            _reject_symlink_ancestors(root, "synthetic_journal_path_invalid")
            if self.state_path.is_symlink():
                raise GuardFailure("synthetic_journal_path_invalid", "preflight")
            self.lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_owned = True
        except BlockingIOError:
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None
                self._lock_owned = False
            raise GuardFailure("synthetic_namespace_busy_or_pending", "preflight") from None
        except OSError:
            if self.lock_fd is not None:
                try:
                    os.close(self.lock_fd)
                except OSError:
                    pass
                self.lock_fd = None
                self._lock_owned = False
            raise GuardFailure("synthetic_journal_unavailable", "preflight") from None
        try:
            if not self.state_path.exists() and any(root.glob("*.json")):
                raise GuardFailure("synthetic_journal_missing", "preflight")
            fd = os.open(self.run_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(_json_bytes(self.run_doc))
                handle.flush()
                os.fsync(handle.fileno())
            if not self.state_path.exists():
                self.state = {
                    "schema": "chi-b-synthetic-accounting-v1", "namespace": policy.scope,
                    "prior_spend_cny": str(initial_prior_cny), "prior_source": prior_source.strip(),
                    "known_settled_cost_cny": "0", "known_input_tokens": 0,
                    "known_output_tokens": 0, "usage_complete": True, "pending": None,
                    "profile_sha256": None, "cap_cny": str(policy.hard_cap_cny) if policy.hard_cap_cny is not None else None,
                    "policy_sha256": policy.sha256,
                }
                self._write_state()
            else:
                self.state = self._read_state()
                if self.state.get("pending") is not None or self.state.get("usage_complete") is not True:
                    raise GuardFailure("synthetic_prior_pending_unknown", "preflight")
                if self.state.get("namespace") != policy.scope:
                    raise GuardFailure("synthetic_journal_invalid", "preflight")
                stored_cap_raw = self.state["cap_cny"]
                stored_cap = Decimal(stored_cap_raw) if stored_cap_raw is not None else None
                if stored_cap != policy.hard_cap_cny:
                    raise GuardFailure("synthetic_cap_invalid", "preflight")
                self.cap_cny = stored_cap
        except GuardFailure:
            self._release_lock()
            raise
        except FileExistsError:
            self._release_lock()
            raise GuardFailure("run_id_exists", "preflight") from None
        except Exception:
            self._release_lock()
            raise GuardFailure("synthetic_journal_unavailable", "preflight") from None

    def _read_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"), parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
            required = {"schema", "namespace", "prior_spend_cny", "prior_source", "known_settled_cost_cny",
                        "known_input_tokens", "known_output_tokens", "usage_complete", "pending", "profile_sha256",
                        "cap_cny", "policy_sha256"}
            if (not isinstance(data, dict) or set(data) != required
                    or data.get("schema") != "chi-b-synthetic-accounting-v1"
                    or data.get("namespace") != self.policy.scope
                    or type(data.get("prior_source")) is not str
                    or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", data["prior_source"]) is None
                    or type(data.get("usage_complete")) is not bool):
                raise ValueError
            if (type(data.get("prior_spend_cny")) is not str
                    or type(data.get("known_settled_cost_cny")) is not str
                    or data.get("policy_sha256") != self.policy.sha256):
                raise ValueError
            prior = Decimal(data["prior_spend_cny"])
            settled = Decimal(data["known_settled_cost_cny"])
            if self.policy.hard_cap_cny is None:
                if data["cap_cny"] is not None:
                    raise ValueError
                cap = None
            else:
                if type(data["cap_cny"]) is not str:
                    raise ValueError
                cap = Decimal(data["cap_cny"])
            if (not prior.is_finite() or not settled.is_finite() or prior < 0 or settled < 0
                    or cap != self.policy.hard_cap_cny):
                raise ValueError
            if any(type(data.get(key)) is not int or not 0 <= data[key] <= 10**12
                   for key in ("known_input_tokens", "known_output_tokens")):
                raise ValueError
            if (data["profile_sha256"] is not None
                    and (type(data["profile_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", data["profile_sha256"]) is None)):
                raise ValueError
            if (settled > 0 or data["known_input_tokens"] > 0 or data["known_output_tokens"] > 0) and data["profile_sha256"] is None:
                raise ValueError
            if data["pending"] is not None and not isinstance(data["pending"], dict):
                raise ValueError
            if data["pending"] is not None and (data["usage_complete"] is not False
                    or type(data["pending"].get("run_id")) is not str
                    or type(data["pending"].get("reserve_upper_cost_cny")) is not str):
                raise ValueError
            if data["pending"] is None and data["usage_complete"] is not True:
                raise GuardFailure("synthetic_prior_usage_unknown", "preflight")
            return data
        except GuardFailure:
            raise
        except Exception:
            raise GuardFailure("synthetic_journal_invalid", "preflight") from None

    def _write_state(self) -> None:
        self._require_active_lock()
        _atomic_replace(self.state_path, _json_bytes(self.state))
        self._persist_run()

    def _persist_run(self) -> None:
        self._require_active_lock()
        _atomic_replace(self.run_path, _json_bytes(self.run_doc))

    def _persist_finalization(self) -> None:
        """Update only this run's terminal evidence after releasing shared ownership."""
        if self.run_doc.get("state") not in {"complete", "incomplete", "unknown"}:
            raise GuardFailure("journal_finalization_invalid", "persistence")
        try:
            _atomic_replace(self.run_path, _json_bytes(self.run_doc))
        except Exception:
            raise GuardFailure("journal_write_failed", "persistence") from None

    def _require_active_lock(self) -> None:
        if self.closed or not self._lock_owned or self.lock_fd is None:
            raise GuardFailure("journal_lock_not_owned", "persistence")

    @property
    def cumulative_spend(self) -> Decimal:
        return Decimal(self.state["prior_spend_cny"]) + Decimal(self.state["known_settled_cost_cny"])

    def reserve(self, profile: ProviderProfile, request: httpx.Request, body: dict[str, Any], raw: bytes,
                max_output: int, round_number: int) -> Decimal:
        self._require_active_lock()
        if not is_validated_policy(self.policy):
            raise GuardFailure("execution_policy_invalid", "request_guard")
        if not _strict_cap_matches(self.cap_cny, self.policy.hard_cap_cny):
            raise GuardFailure("synthetic_cap_invalid", "request_guard")
        if not is_validated_profile(profile):
            raise GuardFailure("profile_untrusted_or_stale", "request_guard")
        # The persisted namespace is authoritative, even if this Guard/Ledger
        # instance was freshly constructed after another request became pending.
        persisted = self._read_state()
        if persisted.get("pending") is not None or persisted.get("usage_complete") is not True:
            raise GuardFailure("synthetic_prior_pending_unknown", "request_guard")
        if persisted != self.state:
            raise GuardFailure("synthetic_journal_state_changed", "request_guard")
        reserve = (
            Decimal(profile.input_reserve_tokens) * profile.input_price
            + Decimal(max_output) * profile.output_price
        ) / MILLION
        before = self.cumulative_spend
        if (self.policy.mode == "capped" and self.cap_cny is not None
                and before + reserve > self.cap_cny):
            raise GuardFailure("budget_exhausted", "request_guard")
        existing_profile = self.state.get("profile_sha256")
        if existing_profile is not None and existing_profile != profile.sha256:
            raise GuardFailure("synthetic_profile_changed", "request_guard")
        self.state["profile_sha256"] = profile.sha256
        entry = {
            "round": round_number, "status": "pending", "input_reserve_tokens": profile.input_reserve_tokens,
            "input_reserve_kind": "documented_context_ceiling_not_measured",
            "output_reserve_tokens": max_output, "reserve_upper_cost_cny": str(reserve),
            "cumulative_upper_cost_cny": str(before + reserve),
            "request_sha256": hashlib.sha256(raw).hexdigest(), "request_wire_bytes": len(raw),
            "route": str(request.url), "model": body["model"],
            "prior_cost_source": self.state["prior_source"],
        }
        self.state["pending"] = {"run_id": self.run_id, **entry}
        self.state["usage_complete"] = False
        self.run_doc["requests"].append(entry)
        self.run_doc["state"] = "pending"
        try:
            self._write_state()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"
            raise GuardFailure("journal_write_failed", "request_guard") from None
        return reserve

    def settle(self, actual_cost: Decimal, incoming: int, outgoing: int) -> bool:
        self._require_active_lock()
        pending = self.state.get("pending")
        if not isinstance(pending, dict) or pending.get("run_id") != self.run_id:
            raise GuardFailure("journal_pending_missing", "response_accounting")
        reserve = Decimal(pending["reserve_upper_cost_cny"])
        within_reserve = actual_cost <= reserve
        entry = self.run_doc["requests"][-1]
        entry.update({"status": "settled" if within_reserve else "settled_over_reserve",
                      "usage_provenance": "provider_response_usage_synthetic_fixture",
                      "input_tokens": incoming, "output_tokens": outgoing,
                      "actual_usage_upper_cost_cny": str(actual_cost),
                      "known_aggregate_upper_cost_cny": str(self.cumulative_spend + actual_cost),
                      "reserve_comparison": "within" if within_reserve else "exceeded"})
        self.state["known_settled_cost_cny"] = str(Decimal(self.state["known_settled_cost_cny"]) + actual_cost)
        self.state["known_input_tokens"] = self.state.get("known_input_tokens", 0) + incoming
        self.state["known_output_tokens"] = self.state.get("known_output_tokens", 0) + outgoing
        self.state["pending"] = None
        self.state["usage_complete"] = True
        self.run_doc["state"] = "settled"
        self._write_state()
        return within_reserve

    def mark_unknown(self, code: str) -> None:
        self._require_active_lock()
        pending = self.state.get("pending")
        if isinstance(pending, dict):
            pending["status"] = "unknown"
            pending["reason_code"] = code
        self.run_doc["state"] = "unknown"
        self.run_doc["primary_error_code"] = code
        self.state["usage_complete"] = False
        if self.run_doc["requests"]:
            self.run_doc["requests"][-1]["status"] = "unknown"
            self.run_doc["requests"][-1]["reason_code"] = code
        try:
            self._write_state()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"

    def mark_error(self, code: str) -> None:
        self._require_active_lock()
        self.run_doc["primary_error_code"] = code
        if self.state.get("pending") is None:
            self.run_doc["state"] = "incomplete"
        try:
            self._persist_run()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        self._require_active_lock()
        self.run_doc["metadata"] = metadata
        try:
            self._persist_run()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"
            raise GuardFailure("journal_write_failed", "preflight") from None

    def set_result(self, *, send_count: int, effects: list[dict[str, Any]],
                   observed_tool_history: list[dict[str, Any]], final_response: str | None) -> None:
        self._require_active_lock()
        self.run_doc["transport_send_count"] = send_count
        self.run_doc["effects"] = effects
        self.run_doc["observed_tool_history"] = observed_tool_history
        self.run_doc["final_response"] = final_response
        complete = self.state.get("usage_complete") is not False
        self.run_doc["accounting"] = {
            "provenance": "synthetic_fixture_provider_response_usage",
            "namespace": self.policy.scope,
            "execution_policy": {"policy_id": self.policy.policy_id, "policy_sha256": self.policy.sha256,
                                 "scope": self.policy.scope, "mode": self.policy.mode,
                                 "hard_cap_cny": str(self.cap_cny) if self.cap_cny is not None else None},
            "prior_spend_cny": self.state["prior_spend_cny"],
            "prior_spend_source": self.state["prior_source"],
            "known_prefix_usage": {"input_tokens": self.state.get("known_input_tokens", 0),
                                   "output_tokens": self.state.get("known_output_tokens", 0)},
            "known_prefix_cost_upper_cny": self.state["known_settled_cost_cny"],
            "usage_complete": complete,
            "aggregate_usage": ({"input_tokens": self.state.get("known_input_tokens", 0),
                                 "output_tokens": self.state.get("known_output_tokens", 0)} if complete else None),
            "aggregate_cost_upper_cny": self.state["known_settled_cost_cny"] if complete else None,
            "budget_known_prefix_upper_cny": str(self.cumulative_spend),
            "budget_pending_reserve_cny": (self.state["pending"].get("reserve_upper_cost_cny")
                                           if isinstance(self.state.get("pending"), dict) else None),
            "real_usage": None, "real_cost_cny": None,
        }
        self.run_doc["known_aggregate_upper_cost_cny"] = str(self.cumulative_spend)
        try:
            self._persist_run()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"
            raise GuardFailure("journal_write_failed", "persistence") from None

    def record_effect(self, effect: dict[str, Any]) -> None:
        self._require_active_lock()
        if (not isinstance(effect, dict) or set(effect) != {"tool", "call_id", "result"}
                or not isinstance(effect["tool"], str) or not isinstance(effect["call_id"], str)
                or not isinstance(effect["result"], str)):
            raise GuardFailure("tool_effect_invalid", "tool_execution")
        self.run_doc.setdefault("effects", []).append({
            "tool": effect["tool"], "call_id": effect["call_id"], "result": effect["result"],
        })
        try:
            self._persist_run()
        except Exception:
            self.run_doc["persistence_error_code"] = "journal_write_failed"
            raise GuardFailure("journal_write_failed", "tool_execution") from None

    def finish(self, *, success: bool, cleanup_error_code: str | None = None) -> None:
        self._require_active_lock()
        self.run_doc["cleanup_error_code"] = cleanup_error_code
        if self.state.get("pending") is not None:
            self.run_doc["state"] = "unknown"
        elif success and self.run_doc.get("primary_error_code") is None and cleanup_error_code is None:
            self.run_doc["state"] = "complete"
        elif self.run_doc.get("state") != "unknown":
            self.run_doc["state"] = "incomplete"
        complete = success and self.state.get("pending") is None and self.run_doc.get("primary_error_code") is None and cleanup_error_code is None
        if complete:
            self.run_doc["state"] = "finalizing"
        self._persist_run()
        if self.state.get("pending") is None:
            try:
                self._release_lock(strict=True)
            except GuardFailure:
                self.run_doc["cleanup_error_code"] = "namespace_lock_release_failed"
                self.run_doc["persistence_error_code"] = "namespace_lock_release_failed"
                self.run_doc["state"] = "incomplete"
                try:
                    self._persist_finalization()
                except GuardFailure:
                    pass
                raise
            if complete:
                self.run_doc["state"] = "complete"
            self._persist_finalization()

    def _release_lock(self, *, strict: bool = False) -> None:
        failure = False
        if self.lock_fd is not None:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)
            except OSError:
                failure = True
            self.lock_fd = None
            self._lock_owned = False
        if failure and strict:
            raise GuardFailure("namespace_lock_release_failed", "persistence")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.state.get("pending") is None:
            self._release_lock()
        elif self.lock_fd is not None:
            try:
                os.close(self.lock_fd)
            except OSError:
                pass
            self.lock_fd = None
            self._lock_owned = False


class EvaluationJournal(SyntheticJournal):
    """One durable, policy-bound attempt with isolated accounting and evidence."""

    def __init__(self, root: Path, run_id: str, *, evaluation_id: str, task_id: str,
                 attempt_id: str, policy: ExecutionPolicy, profile: ProviderProfile):
        for value in (evaluation_id, task_id, attempt_id):
            if type(value) is not str or EVALUATION_ID_RE.fullmatch(value) is None:
                raise GuardFailure("evaluation_identity_invalid", "preflight")
        if (not is_validated_policy(policy) or policy.scope != "evaluation_rehearsal"
                or not is_validated_profile(profile)):
            raise GuardFailure("execution_policy_invalid", "preflight")
        if type(run_id) is not str or RUN_ID_RE.fullmatch(run_id) is None:
            raise GuardFailure("run_id_invalid", "preflight")

        base = Path(root)
        eval_root = base / evaluation_id
        claim_dir = eval_root / "claims" / task_id
        attempt_root = eval_root / "attempts" / task_id / attempt_id
        registry_lock = eval_root / ".registry.lock"
        registry_path = eval_root / "policy-registry.json"
        claim_path = claim_dir / f"{attempt_id}.json"
        registry = {
            "schema": "chi-evaluation-policy-registry-v1",
            "evaluation_id": evaluation_id,
            "policy": policy.raw,
            "policy_sha256": policy.sha256,
            "provider_profile_sha256": profile.sha256,
        }

        try:
            _reject_symlink_ancestors(base, "evaluation_path_invalid")
            self._ensure_directory(base)
            _reject_symlink_ancestors(base, "evaluation_path_invalid")
            for path in (eval_root, eval_root / "claims", claim_dir,
                         eval_root / "attempts", eval_root / "attempts" / task_id):
                self._ensure_one_directory(path)
                _reject_symlink_ancestors(path, "evaluation_path_invalid")
            if attempt_root.exists() or attempt_root.is_symlink():
                raise GuardFailure("evaluation_attempt_path_conflict", "preflight")
            registry_fd = os.open(registry_lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            registry_locked = False
            try:
                try:
                    fcntl.flock(registry_fd, fcntl.LOCK_EX)
                    registry_locked = True
                except BlockingIOError:
                    raise GuardFailure("evaluation_registry_busy", "preflight") from None
                if registry_path.is_symlink():
                    raise GuardFailure("evaluation_policy_registry_invalid", "preflight")
                if registry_path.exists():
                    stored = json.loads(registry_path.read_text(encoding="utf-8"),
                                        object_pairs_hook=_unique_json_object,
                                        parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
                    if stored != registry:
                        raise GuardFailure("evaluation_policy_conflict", "preflight")
                else:
                    self._write_exclusive(registry_path, _json_bytes(registry), "evaluation_policy_registry_invalid")
                if claim_path.is_symlink() or claim_path.exists():
                    raise GuardFailure("evaluation_attempt_claim_exists", "preflight")
                attempt_root.mkdir()
                self._fsync_directory(attempt_root.parent)
                claim = {
                    "schema": "chi-evaluation-attempt-claim-v1", "evaluation_id": evaluation_id,
                    "task_id": task_id, "attempt_id": attempt_id, "run_id": run_id,
                    "policy_sha256": policy.sha256, "provider_profile_sha256": profile.sha256,
                    "state": "claimed", "real_usage": None, "real_cost_cny": None,
                    "official_reward": None,
                }
                self._write_exclusive(claim_path, _json_bytes(claim), "evaluation_attempt_claim_exists")
            finally:
                try:
                    if registry_locked:
                        fcntl.flock(registry_fd, fcntl.LOCK_UN)
                finally:
                    os.close(registry_fd)
        except GuardFailure:
            raise
        except FileExistsError:
            raise GuardFailure("evaluation_attempt_claim_exists", "preflight") from None
        except Exception:
            raise GuardFailure("evaluation_journal_unavailable", "preflight") from None

        self.evaluation_id = evaluation_id
        self.task_id = task_id
        self.attempt_id = attempt_id
        self.claim_path = claim_path
        try:
            super().__init__(attempt_root, run_id, initial_prior_cny=Decimal(0),
                             prior_source="evaluation-attempt-synthetic-start",
                             cap_cny=policy.hard_cap_cny, policy=policy, _allow_evaluation=True)
        except Exception:
            raise
        self.run_doc["evaluation_identity"] = {
            "evaluation_id": evaluation_id, "task_id": task_id, "attempt_id": attempt_id,
            "run_id_is_output_label_only": True, "claim_path": str(claim_path),
        }
        try:
            self._persist_run()
        except Exception:
            self.run_doc["state"] = "incomplete"
            self.run_doc["primary_error_code"] = "evaluation_identity_persist_failed"
            self.run_doc["persistence_error_code"] = "journal_write_failed"
            try:
                self._persist_finalization()
            except GuardFailure:
                pass
            try:
                self._release_lock(strict=True)
            except GuardFailure:
                self.run_doc["cleanup_error_code"] = "namespace_lock_release_failed"
                try:
                    self._persist_finalization()
                except GuardFailure:
                    pass
            raise GuardFailure("evaluation_identity_persist_failed", "persistence") from None

    @staticmethod
    def _write_exclusive(path: Path, payload: bytes, failure_code: str) -> None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except FileExistsError:
            raise GuardFailure(failure_code, "preflight") from None
        except Exception:
            raise GuardFailure("evaluation_journal_unavailable", "preflight") from None

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        directory_fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @classmethod
    def _ensure_directory(cls, path: Path) -> None:
        _reject_symlink_ancestors(path, "evaluation_path_invalid")
        missing: list[Path] = []
        cursor = path
        while not cursor.exists():
            if cursor.is_symlink():
                raise GuardFailure("evaluation_path_invalid", "preflight")
            missing.append(cursor)
            cursor = cursor.parent
        if not cursor.is_dir() or cursor.is_symlink():
            raise GuardFailure("evaluation_path_invalid", "preflight")
        for directory in reversed(missing):
            cls._ensure_one_directory(directory)

    @classmethod
    def _ensure_one_directory(cls, directory: Path) -> None:
        if directory.is_symlink():
            raise GuardFailure("evaluation_path_invalid", "preflight")
        try:
            directory.mkdir()
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise GuardFailure("evaluation_path_invalid", "preflight") from None
            return
        except OSError:
            raise GuardFailure("evaluation_journal_unavailable", "preflight") from None
        cls._fsync_directory(directory.parent)


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


class GuardedTransport(httpx.AsyncBaseTransport):
    """Validate exact route/body, persist a full conservative reserve, then send."""

    def __init__(self, *, profile: ProviderProfile, journal: SyntheticJournal,
                 lower: httpx.AsyncBaseTransport, ledger: Any, cap_cny: Decimal | None,
                 validate_response: Callable[[dict[str, Any]], None],
                 allowed_tool_names: set[str] | frozenset[str],
                 observe_request: Callable[[dict[str, Any]], None] | None = None):
        if not is_validated_profile(profile):
            raise GuardFailure("profile_untrusted_or_stale", "preflight")
        journal._require_active_lock()
        if (not is_validated_policy(journal.policy)
                or not _strict_cap_matches(cap_cny, journal.policy.hard_cap_cny)
                or not _strict_cap_matches(journal.cap_cny, journal.policy.hard_cap_cny)):
            raise GuardFailure("execution_policy_invalid", "preflight")
        self.profile = profile
        self.journal = journal
        self.lower = lower
        self.ledger = ledger
        self.cap_cny = cap_cny
        self.validate_response = validate_response
        self.allowed_tool_names = frozenset(allowed_tool_names)
        self.observe_request = observe_request

    def _validate_request(self, request: httpx.Request, raw: bytes) -> dict[str, Any]:
        if self.ledger.error_code is not None:
            raise GuardFailure(self.ledger.error_code, "request_guard")
        url = request.url
        if (url.scheme != "https" or url.host != "api.deepseek.com" or url.port is not None
                or url.path != "/v1/chat/completions" or url.query or url.fragment or url.userinfo):
            raise GuardFailure("route_invalid", "request_guard")
        if request.method != "POST" or len(raw) > MAX_WIRE_BYTES:
            raise GuardFailure("request_shape_invalid", "request_guard")
        try:
            body = json.loads(raw, parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
        except Exception:
            raise GuardFailure("request_serialization_invalid", "request_guard") from None
        if not isinstance(body, dict):
            raise GuardFailure("request_serialization_invalid", "request_guard")
        if any(key in body for key in ("endpoint", "api", "key_env", "candidate", "profile_id")):
            raise GuardFailure("route_wire_separation_invalid", "request_guard")
        if body.get("model") != self.profile.model:
            raise GuardFailure("request_model_mismatch", "request_guard")
        max_output = body.get("max_tokens")
        if isinstance(max_output, bool) or not isinstance(max_output, int) or not 1 <= max_output <= self.profile.max_output_tokens:
            raise GuardFailure("output_limit", "request_guard")
        if body.get("reasoning_effort") != "high" or body.get("thinking") != {"type": "enabled"}:
            raise GuardFailure("wire_profile_mismatch", "request_guard")
        if ("stream" in body and body["stream"] is not False) or (
            "n" in body and (type(body["n"]) is not int or body["n"] != 1)
        ):
            raise GuardFailure("generation_shape_unsupported", "request_guard")
        if "stream_options" in body:
            raise GuardFailure("generation_shape_unsupported", "request_guard")
        if any(key in body for key in (
            "max_completion_tokens", "max_output_tokens", "completion_limit", "functions", "function_call",
            "best_of", "num_completions", "candidate_count",
        )):
            raise GuardFailure("generation_limit_ambiguous", "request_guard")
        if ("modalities" in body and body["modalities"] != ["text"]) or "audio" in body:
            raise GuardFailure("generation_shape_unsupported", "request_guard")
        if not isinstance(body.get("messages"), list) or self.ledger.rounds >= self.profile.max_rounds:
            raise GuardFailure("round_or_history_invalid", "request_guard")
        tools = body.get("tools", [])
        if not isinstance(tools, list):
            raise GuardFailure("tool_schema_invalid", "request_guard")
        names: set[str] = set()
        for tool in tools:
            function = tool.get("function") if isinstance(tool, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            if (not isinstance(tool, dict) or tool.get("type") != "function"
                    or not isinstance(name, str) or name not in self.allowed_tool_names
                    or name in names):
                raise GuardFailure("tool_schema_not_allowlisted", "request_guard")
            names.add(name)
        tool_choice = body.get("tool_choice")
        if isinstance(tool_choice, dict):
            selected = tool_choice.get("function")
            selected_name = selected.get("name") if isinstance(selected, dict) else None
            if (tool_choice.get("type") != "function" or not isinstance(selected_name, str)
                    or selected_name not in self.allowed_tool_names):
                raise GuardFailure("tool_schema_not_allowlisted", "request_guard")
        elif tool_choice is not None and (
            not isinstance(tool_choice, str) or tool_choice not in {"auto", "none", "required"}
        ):
            raise GuardFailure("tool_schema_not_allowlisted", "request_guard")
        pending: set[str] = set()
        seen: set[str] = set()
        for message in body["messages"]:
            if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant", "tool"}:
                raise GuardFailure("history_invalid", "request_guard")
            role = message["role"]
            content = message.get("content")
            if role in {"system", "user", "tool"} and not isinstance(content, str):
                raise GuardFailure("history_invalid", "request_guard")
            if role == "assistant" and content is not None and not isinstance(content, str):
                raise GuardFailure("history_invalid", "request_guard")
            if role == "assistant":
                reasoning = message.get("reasoning_content")
                if not isinstance(reasoning, str):
                    raise GuardFailure("history_reasoning_missing", "request_guard")
                calls = message.get("tool_calls", [])
                if not isinstance(calls, list):
                    raise GuardFailure("history_invalid", "request_guard")
                for call in calls:
                    function = call.get("function") if isinstance(call, dict) else None
                    call_id = call.get("id") if isinstance(call, dict) else None
                    name = function.get("name") if isinstance(function, dict) else None
                    if (not isinstance(call_id, str) or TOOL_ID_RE.fullmatch(call_id) is None
                            or call_id in seen or not isinstance(name, str)
                            or name not in self.allowed_tool_names):
                        raise GuardFailure("history_invalid", "request_guard")
                    seen.add(call_id)
                    pending.add(call_id)
            elif role == "tool":
                call_id = message.get("tool_call_id")
                if not isinstance(call_id, str) or call_id not in pending:
                    raise GuardFailure("history_invalid", "request_guard")
                pending.remove(call_id)
        if pending:
            raise GuardFailure("history_incomplete", "request_guard")
        return body

    @staticmethod
    def _usage(payload: dict[str, Any]) -> tuple[int, int]:
        raw = payload.get("usage")
        if not isinstance(raw, dict):
            raise GuardFailure("usage_unknown", "response_accounting")
        values = (raw.get("prompt_tokens"), raw.get("completion_tokens"), raw.get("total_tokens"))
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 or x > 10**12 for x in values):
            raise GuardFailure("usage_unknown", "response_accounting")
        incoming, outgoing, total = values
        if total != incoming + outgoing:
            raise GuardFailure("usage_unknown", "response_accounting")
        if "prompt_tokens_details" in raw:
            details = raw["prompt_tokens_details"]
            if not isinstance(details, dict):
                raise GuardFailure("usage_unknown", "response_accounting")
            if "cached_tokens" in details:
                hits = details["cached_tokens"]
                if type(hits) is not int or not 0 <= hits <= incoming:
                    raise GuardFailure("usage_unknown", "response_accounting")
            if "cache_miss_tokens" in details:
                misses = details["cache_miss_tokens"]
                if type(misses) is not int or not 0 <= misses <= incoming:
                    raise GuardFailure("usage_unknown", "response_accounting")
                if "cached_tokens" in details and misses + details["cached_tokens"] != incoming:
                    raise GuardFailure("usage_unknown", "response_accounting")
        if "prompt_cache_hit_tokens" in raw or "prompt_cache_miss_tokens" in raw:
            hit_direct, miss_direct = raw.get("prompt_cache_hit_tokens"), raw.get("prompt_cache_miss_tokens")
            if (type(hit_direct) is not int or hit_direct < 0
                    or type(miss_direct) is not int or miss_direct < 0
                    or hit_direct + miss_direct != incoming):
                raise GuardFailure("usage_unknown", "response_accounting")
            details = raw.get("prompt_tokens_details")
            if isinstance(details, dict) and "cached_tokens" in details and details["cached_tokens"] != hit_direct:
                raise GuardFailure("usage_unknown", "response_accounting")
        if "completion_tokens_details" in raw:
            completion_details = raw["completion_tokens_details"]
            if not isinstance(completion_details, dict):
                raise GuardFailure("usage_unknown", "response_accounting")
            if "reasoning_tokens" in completion_details:
                reasoning = completion_details["reasoning_tokens"]
                if (type(reasoning) is not int
                        or reasoning < 0 or reasoning > outgoing):
                    raise GuardFailure("usage_unknown", "response_accounting")
        return incoming, outgoing

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            self.journal._require_active_lock()
            if (not is_validated_policy(self.journal.policy)
                    or not _strict_cap_matches(self.journal.cap_cny, self.journal.policy.hard_cap_cny)
                    or not _strict_cap_matches(self.cap_cny, self.journal.policy.hard_cap_cny)):
                raise GuardFailure("execution_policy_invalid", "request_guard")
        except GuardFailure as exc:
            self.ledger.error_code = exc.code
            raise
        try:
            raw = request.content
            body = self._validate_request(request, raw)
            max_output = body["max_tokens"]
            next_round = self.ledger.rounds + 1
            self.journal.reserve(self.profile, request, body, raw, max_output, next_round)
        except GuardFailure as exc:
            self.ledger.error_code = exc.code
            self.journal.mark_error(exc.code)
            raise
        except Exception:
            self.ledger.error_code = "request_guard_failed"
            self.journal.mark_error("request_guard_failed")
            raise GuardFailure("request_guard_failed", "request_guard") from None

        self.ledger.rounds += 1
        self.ledger.transport_calls += 1
        self.ledger.requests.append({"url": str(request.url), "method": request.method,
                                     "body": body, "body_sha256": hashlib.sha256(raw).hexdigest(),
                                     "wire_bytes": len(raw), "token_bound": "documented_context_ceiling_not_measured",
                                     "provenance": "real_sdk_serialized_http_request"})
        if self.observe_request is not None:
            self.observe_request(body)
        try:
            response = await self.lower.handle_async_request(request)
        except httpx.ConnectError:
            self.ledger.error_code = "transport_connect_error"
            self.ledger.usage_complete = False
            self.ledger.aggregate_input_tokens = None
            self.ledger.aggregate_output_tokens = None
            self.ledger.aggregate_cost_cny = None
            self.journal.mark_unknown("transport_connect_error")
            raise
        except httpx.TimeoutException:
            self.ledger.error_code = "transport_timeout"
            self.ledger.usage_complete = False
            self.ledger.aggregate_input_tokens = None
            self.ledger.aggregate_output_tokens = None
            self.ledger.aggregate_cost_cny = None
            self.journal.mark_unknown("transport_timeout")
            raise
        except Exception:
            self.ledger.error_code = "transport_failed"
            self.ledger.usage_complete = False
            self.ledger.aggregate_input_tokens = None
            self.ledger.aggregate_output_tokens = None
            self.ledger.aggregate_cost_cny = None
            self.journal.mark_unknown("transport_failed")
            raise
        if response.status_code >= 400:
            code = "http_rate_limited" if response.status_code == 429 else "http_unavailable" if response.status_code in {500, 502, 503, 504} else "http_rejected"
            self.ledger.error_code = code
            self.ledger.usage_complete = False
            self.ledger.aggregate_input_tokens = None
            self.ledger.aggregate_output_tokens = None
            self.ledger.aggregate_cost_cny = None
            self.journal.mark_unknown(code)
            return response
        try:
            response_bytes = await response.aread()
            payload = json.loads(response_bytes, parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
            if not isinstance(payload, dict):
                raise GuardFailure("response_shape_invalid", "response_validation")
            incoming, outgoing = self._usage(payload)
            actual_cost = (Decimal(incoming) * self.profile.input_price + Decimal(outgoing) * self.profile.output_price) / MILLION
            within_reserve = self.journal.settle(actual_cost, incoming, outgoing)
            self.ledger.known_input_tokens += incoming
            self.ledger.known_output_tokens += outgoing
            self.ledger.usage_complete = True
            self.ledger.aggregate_input_tokens = self.ledger.known_input_tokens
            self.ledger.aggregate_output_tokens = self.ledger.known_output_tokens
            self.ledger.known_cost_cny = Decimal(str(self.ledger.known_cost_cny)) + actual_cost
            self.ledger.aggregate_cost_cny = self.ledger.known_cost_cny
            if (incoming > self.profile.input_reserve_tokens or outgoing > max_output
                    or incoming + outgoing > self.profile.input_reserve_tokens or not within_reserve):
                self.ledger.error_code = "returned_usage_over_limit"
                self.journal.mark_error("returned_usage_over_limit")
                raise GuardFailure("returned_usage_over_limit", "response_accounting")
            self.validate_response(payload)
            # aread() already applies httpx's content decoder. Returning the
            # consumed response preserves cached decoded bytes; rebuilding it
            # with content-encoding would decode gzip a second time.
            return response
        except GuardFailure as exc:
            self.ledger.error_code = exc.code
            if self.journal.state.get("pending") is not None:
                self.ledger.usage_complete = False
                self.ledger.aggregate_input_tokens = None
                self.ledger.aggregate_output_tokens = None
                self.ledger.aggregate_cost_cny = None
                self.journal.mark_unknown(exc.code)
            else:
                self.journal.mark_error(exc.code)
            raise
        except Exception as exc:
            injected_code = getattr(exc, "code", None) if exc.__class__.__name__ in {"IntegrationFailure", "GuardFailure"} else None
            safe_code = injected_code if isinstance(injected_code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", injected_code) else "response_invalid"
            self.ledger.error_code = safe_code
            if self.journal.state.get("pending") is not None:
                self.ledger.usage_complete = False
                self.ledger.aggregate_input_tokens = None
                self.ledger.aggregate_output_tokens = None
                self.ledger.aggregate_cost_cny = None
                self.journal.mark_unknown(safe_code)
            else:
                self.journal.mark_error(safe_code)
            raise GuardFailure(safe_code, "response_validation") from None

    async def aclose(self) -> None:
        await self.lower.aclose()
