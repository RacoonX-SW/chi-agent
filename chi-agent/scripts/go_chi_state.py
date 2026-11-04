"""Bounded per-run business state for Go CHI (chi-task-state-v2).

The state records what this run actually observed, what the model claims or
plans, what is still missing, and which write effects are unknown. It is run
evidence, not an accounting ledger: it never writes chi-accounting.json and it
never rewrites journal bytes.

Only the program registers observations (from real tool calls). The model may
submit facts/plans/gaps/status updates through a validated payload, always
citing an observation registered earlier in this run.

v2 distinguishes business-status reads, policy/handbook evidence, patient
evidence and file deliverables. A file read cannot establish a business status;
a successful deliverable write after a business readback does not require a
second business readback. Legacy v1 states keep their original meaning and are
never rewritten or re-graded by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

from opencode_go_provider import GoFailure

SCHEMA = "chi-task-state-v2"
VERSION = "chi-task-state-v2"
LEGACY_SCHEMAS = frozenset({"chi-task-state-v1"})
COMPLETION_SCHEMA = "chi-completion-v2"
MAX_STATE_BYTES = 65536
MAX_TEXT = 800
LIMITS = {
    "observations": 256,
    "facts": 64,
    "plans": 16,
    "gaps": 32,
    "unknowns": 16,
    "next_candidates": 8,
    "observations_in_summary": 20,
}
CALL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
UNKNOWN_ID = re.compile(r"^u[0-9]{1,3}$")
READ_VERBS = {"get", "list", "read", "search", "check", "calculate", "audit", "validate"}
LOCAL_EFFECTS = {
    "local-fs-read": "read",
    "local-fs-list": "read",
    "local-fs-search": "read",
    "local-task-state": "neutral",
    "local-role-guidance": "neutral",
    "local-read-patient-observation": "read",
    "local-fs-write": "mutation",
    "local-fs-edit": "mutation",
    "local-confirm-patient": "neutral",
    "local-claim_done": "neutral",
    "local-state-update": "neutral",
}
UPDATE_KEYS = {"facts", "plans", "gaps", "target", "latest_business_status",
               "next_candidates", "resolve_unknown"}

# Canonical public MCP reads that expose the target case/resource state. The
# list is program-owned and exact; a model cannot nominate a new status source.
# Names come from the pinned public catalog (`provider_tool_names`,
# `payer_agent_tool_names` and `cm_server`), not from hidden implementations.
BUSINESS_STATUS_READS = {
    "provider": frozenset({
        "cases.get_case",
        "auth.check_status",
    }),
    "payer": frozenset({
        "payer_intake_hub.get_intake_case",
        "triage.get",
        "review.get_nurse_review_data",
        "review.get_md_review_data",
        "determination.get_summary",
        "p2p.list",
        "payer_letter_center.list",
    }),
    "cm": frozenset({
        "cm_chart.get_chart_data",
    }),
}
FILE_READ_TOOLS = frozenset({"local-fs-read", "local-fs-list", "local-fs-search"})
FILE_WRITE_TOOLS = frozenset({"local-fs-write", "local-fs-edit"})
NEUTRAL_LOCAL = frozenset({"local-task-state", "local-role-guidance", "local-state-update",
                           "local-confirm-patient", "local-claim_done"})


class StateRefusal(ValueError):
    """A correctable model/update error; returned to the model as REFUSED."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, *, field: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise StateRefusal("chi_state_update_invalid")
    return value


def _fingerprint(tool: str, kind: str, arguments) -> str:
    return _sha({"tool": tool, "kind": kind,
                 "arguments": arguments if arguments is not None else {}})


def effect_for(tool: str, kind: str) -> str:
    """Classify a tool as read/mutation/neutral; unknown tools default to mutation."""
    if type(tool) is not str or not tool:
        raise StateRefusal("chi_state_update_invalid")
    if kind == "local":
        return LOCAL_EFFECTS.get(tool, "mutation")
    if kind != "mcp":
        raise StateRefusal("chi_state_update_invalid")
    name = tool.rsplit(".", 1)[-1]
    verb = name.split("_", 1)[0]
    return "read" if verb in READ_VERBS else "mutation"


def tool_kind(tool: str) -> str:
    """Infer the observation kind for a stored tool name."""
    if type(tool) is not str or not tool:
        raise StateRefusal("chi_state_update_invalid")
    return "local" if tool.startswith("local-") or tool in LOCAL_EFFECTS else "mcp"


def source_kind_for(role: str, tool: str, kind: str, scope: str, effect: str | None = None) -> str:
    """Classify an observation for completion: business status vs other evidence.

    Only a returned, case-scoped read from BUSINESS_STATUS_READS can establish a
    business status. File, policy/handbook, patient and general business reads
    stay evidence and cannot be promoted to a terminal status by the model.
    """
    if role not in BUSINESS_STATUS_READS:
        raise StateRefusal("chi_state_update_invalid")
    effect = effect_for(tool, kind) if effect is None else effect
    if kind == "local":
        if tool in FILE_WRITE_TOOLS:
            return "file_deliverable"
        if tool in FILE_READ_TOOLS:
            if type(scope) is str and scope.startswith("case:"):
                return "file_evidence"
            if scope == "shared_public":
                return "policy_evidence"
            return "other_evidence"
        if tool == "local-read-patient-observation":
            return "patient_evidence"
        if tool in NEUTRAL_LOCAL:
            return "neutral"
        return "unknown_mutation" if effect == "mutation" else "other_evidence"
    if kind != "mcp":
        raise StateRefusal("chi_state_update_invalid")
    if effect == "mutation":
        return "business_mutation"
    if tool in BUSINESS_STATUS_READS[role]:
        return "business_status"
    return "business_evidence"


def _atomic_write(path: Path, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_STATE_BYTES:
        raise StateRefusal("chi_state_limit")
    if path.is_symlink():
        raise GoFailure("chi_state_persistence_failed")
    fd, temporary = tempfile.mkstemp(prefix=".task-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


class TaskState:
    """One run's bounded task state with immutable version snapshots."""

    def __init__(self, root, *, run: str, role: str, binding=None):
        if (type(run) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", run)
                or role not in {"provider", "payer", "cm"}):
            raise GoFailure("chi_state_invalid")
        self.root = Path(root)
        self.binding = binding
        if self.root.exists():
            raise GoFailure("chi_state_exists")
        try:
            self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
            (self.root / "versions").mkdir(mode=0o700, exist_ok=False)
        except OSError:
            raise GoFailure("chi_state_persistence_failed") from None
        self.path = self.root / "task-state.json"
        self.data = {
            "schema": SCHEMA,
            "run": run,
            "role": role,
            "version": 0,
            "target": {"case_id": None, "patient_id": None},
            "observations": [],
            "facts": [],
            "plans": [],
            "gaps": [],
            "unknowns": [],
            "latest_business_status": None,
            "next_candidates": [],
            "claim": None,
            "claim_violation": False,
            "repeat": {"fingerprint": None, "count": 0, "tool": None, "effect": None},
            "stagnation": None,
            "updated_at_utc_ms": 0,
        }
        self._persist(snapshot=False)

    # -- persistence -----------------------------------------------------
    def _persist(self, *, snapshot: bool = True) -> None:
        self.data["updated_at_utc_ms"] = time.time_ns() // 1000000
        try:
            _atomic_write(self.path, self.data)
            if snapshot and self.data["version"] > 0:
                target = self.root / "versions" / f"{self.data['version']:06d}.json"
                _atomic_write(target, self.data)
        except StateRefusal:
            raise
        except Exception:
            raise GoFailure("chi_state_persistence_failed") from None

    # -- program observations -------------------------------------------
    def scope_for_arguments(self, arguments) -> str:
        if type(arguments) is dict and type(arguments.get("case_id")) is str:
            value = arguments["case_id"]
            if CASE_ID.fullmatch(value):
                return "case:" + value
        return "unattributed"

    def observe(self, *, call_id: str, tool: str, kind: str, arguments=None, result=None,
                event: str = "returned", round_number: int = 0, scope: str | None = None) -> dict:
        if (type(call_id) is not str or not CALL_ID.fullmatch(call_id) or event not in
                {"returned", "returned_error", "refused", "failed"}):
            raise StateRefusal("chi_state_update_invalid")
        effect = effect_for(tool, kind)
        if scope is None:
            scope = self.scope_for_arguments(arguments)
        if scope not in {"shared_public", "unattributed", "conflict"} and not scope.startswith("case:"):
            scope = "unattributed"
        if len(self.data["observations"]) >= LIMITS["observations"]:
            raise GoFailure("chi_state_limit")
        observation = {
            "seq": len(self.data["observations"]) + 1,
            "call_id": call_id,
            "tool": tool,
            "kind": kind,
            "effect": effect,
            "source_kind": source_kind_for(self.data["role"], tool, kind, scope, effect),
            "scope": scope,
            "arguments_sha256": _sha(arguments if arguments is not None else {}),
            "result_sha256": _sha(result if result is not None else ""),
            "event": event,
            "round": round_number if type(round_number) is int and round_number >= 0 else 0,
        }
        fingerprint = _fingerprint(tool, kind, arguments)
        repeat = self.data.get("repeat") or {}
        if repeat.get("fingerprint") == fingerprint:
            count = int(repeat.get("count", 0)) + 1
        else:
            count = 1
        self.data["repeat"] = {"fingerprint": fingerprint, "count": count,
                               "tool": tool, "effect": effect}
        if count >= 3:
            self.data["stagnation"] = {"tool": tool, "count": count,
                                       "call_id": call_id, "effect": effect}
        self.data["observations"].append(observation)
        if effect == "mutation":
            # A write after a completion claim invalidates that claim. Dispatch
            # should normally refuse this (see mutation_block_reason); this is
            # defense in depth for any other observation path.
            self.data["claim"] = None
        if effect == "mutation" and event == "failed":
            self._register_unknown(observation)
        self.data["version"] += 1
        self._persist()
        return observation

    def _register_unknown(self, observation: dict) -> None:
        if len(self.data["unknowns"]) >= LIMITS["unknowns"]:
            raise GoFailure("chi_state_limit")
        existing = {item["call_id"] for item in self.data["unknowns"]}
        if observation["call_id"] in existing:
            return
        self.data["unknowns"].append({
            "id": f"u{len(self.data['unknowns']) + 1}",
            "call_id": observation["call_id"],
            "tool": observation["tool"],
            "scope": observation["scope"],
            "seq": observation["seq"],
            "status": "open",
            "resolution_call_id": None,
            "note": None,
        })

    # -- model updates ---------------------------------------------------
    def _observation(self, call_id: object) -> dict:
        if type(call_id) is not str:
            raise StateRefusal("chi_state_source_unobserved")
        for item in self.data["observations"]:
            if item["call_id"] == call_id:
                return item
        raise StateRefusal("chi_state_source_unobserved")

    def _check_source_scope(self, observation: dict) -> None:
        if observation["scope"] == "conflict":
            raise StateRefusal("chi_state_source_conflict")
        case_id = self.data["target"]["case_id"]
        if case_id is None:
            if observation["scope"].startswith("case:"):
                raise StateRefusal("chi_state_target_required")
            return
        if observation["scope"] not in {"case:" + case_id, "shared_public"}:
            raise StateRefusal("chi_state_case_mismatch")

    def _apply_target(self, payload: dict) -> None:
        if type(payload) is not dict or not payload or set(payload) - {"case_id", "patient_id"}:
            raise StateRefusal("chi_state_update_invalid")
        target = self.data["target"]
        for key in ("case_id", "patient_id"):
            if key not in payload:
                continue
            value = payload[key]
            if value is None:
                continue
            pattern = CASE_ID if key == "case_id" else CASE_ID
            if type(value) is not str or not pattern.fullmatch(value):
                raise StateRefusal("chi_state_update_invalid")
            if target[key] is not None and target[key] != value:
                raise StateRefusal("chi_state_target_locked")
            if key == "case_id":
                observed = {item["scope"] for item in self.data["observations"]}
                if "case:" + value not in observed:
                    raise StateRefusal("chi_state_case_mismatch")
                target["case_id"] = value
                self._validate_existing_sources()
            else:
                if self.data["role"] != "provider":
                    raise StateRefusal("chi_state_target_invalid")
                bound = getattr(self.binding, "bound", None)
                if bound is None:
                    raise StateRefusal("chi_state_patient_unbound")
                if value != bound:
                    raise StateRefusal("chi_state_case_mismatch")
                target["patient_id"] = value

    def _validate_existing_sources(self) -> None:
        case_id = self.data["target"]["case_id"]
        if case_id is None:
            return
        allowed = {"case:" + case_id, "shared_public"}
        sources = [item["source_call_id"] for item in self.data["facts"]]
        sources += [item["source_call_id"] for item in self.data["gaps"]
                    if item.get("source_call_id") is not None]
        status = self.data["latest_business_status"]
        if status is not None:
            sources.append(status["source_call_id"])
        for call_id in sources:
            observation = next((item for item in self.data["observations"]
                                if item["call_id"] == call_id), None)
            if observation is None or observation["scope"] not in allowed:
                raise StateRefusal("chi_state_case_mismatch")

    def _apply_facts(self, payload: object) -> None:
        if type(payload) is not list or len(payload) > LIMITS["facts"]:
            raise StateRefusal("chi_state_update_invalid")
        for item in payload:
            if type(item) is not dict or set(item) != {"text", "source_call_id"}:
                raise StateRefusal("chi_state_update_invalid")
            text = _text(item["text"], field="text")
            source = self._observation(item["source_call_id"])
            if source["event"] != "returned":
                raise StateRefusal("chi_state_source_unobserved")
            self._check_source_scope(source)
            entry = {"text": text, "source_call_id": source["call_id"], "source_seq": source["seq"]}
            if entry not in self.data["facts"]:
                self.data["facts"].append(entry)
        if len(self.data["facts"]) > LIMITS["facts"]:
            raise StateRefusal("chi_state_limit")

    def _apply_plans(self, payload: object) -> None:
        if type(payload) is not list or len(payload) > LIMITS["plans"]:
            raise StateRefusal("chi_state_update_invalid")
        for text in payload:
            entry = {"text": _text(text, field="text"), "created_version": self.data["version"] + 1}
            if entry["text"] not in {item["text"] for item in self.data["plans"]}:
                self.data["plans"].append(entry)
        if len(self.data["plans"]) > LIMITS["plans"]:
            raise StateRefusal("chi_state_limit")

    def _apply_gaps(self, payload: object) -> None:
        if type(payload) is not list or len(payload) > LIMITS["gaps"]:
            raise StateRefusal("chi_state_update_invalid")
        for item in payload:
            if type(item) is not dict or set(item) - {"text", "status", "source_call_id"} \
                    or set(item) < {"text", "status"} or item["status"] not in {"open", "resolved"}:
                raise StateRefusal("chi_state_update_invalid")
            text = _text(item["text"], field="text")
            source_id = item.get("source_call_id")
            if source_id is not None:
                source = self._observation(source_id)
                if source["event"] != "returned":
                    raise StateRefusal("chi_state_source_unobserved")
                self._check_source_scope(source)
            self.data["gaps"].append({"text": text, "status": item["status"],
                                      "source_call_id": source_id})
        if len(self.data["gaps"]) > LIMITS["gaps"]:
            raise StateRefusal("chi_state_limit")

    def _apply_status(self, payload: object) -> None:
        if type(payload) is not dict or set(payload) != {"text", "source_call_id"}:
            raise StateRefusal("chi_state_update_invalid")
        text = _text(payload["text"], field="text")
        source = self._observation(payload["source_call_id"])
        if source["effect"] != "read" or source["event"] != "returned":
            raise StateRefusal("chi_state_source_not_read")
        if source.get("source_kind") != "business_status":
            # File, policy, patient and general business evidence cannot become
            # the terminal status just because the model cites it.
            raise StateRefusal("chi_state_source_not_business")
        self._check_source_scope(source)
        if self.data["target"]["case_id"] is None:
            raise StateRefusal("chi_state_target_required")
        current = self.data["latest_business_status"]
        if current is not None and source["seq"] < current["source_seq"]:
            raise StateRefusal("chi_state_stale")
        self.data["latest_business_status"] = {"text": text, "source_call_id": source["call_id"],
                                               "source_seq": source["seq"]}

    def _apply_next(self, payload: object) -> None:
        if type(payload) is not list or len(payload) > LIMITS["next_candidates"]:
            raise StateRefusal("chi_state_update_invalid")
        self.data["next_candidates"] = [{"text": _text(item, field="text")} for item in payload]

    def _apply_resolutions(self, payload: object) -> None:
        if type(payload) is not list or not payload or len(payload) > LIMITS["unknowns"]:
            raise StateRefusal("chi_state_update_invalid")
        for item in payload:
            if type(item) is not dict or set(item) != {"unknown_id", "source_call_id", "note"}:
                raise StateRefusal("chi_state_update_invalid")
            unknown = next((entry for entry in self.data["unknowns"]
                            if entry["id"] == item["unknown_id"]), None)
            if unknown is None or unknown["status"] != "open":
                raise StateRefusal("chi_state_unknown_invalid")
            source = self._observation(item["source_call_id"])
            if source["effect"] != "read" or source["event"] != "returned" \
                    or source["seq"] <= unknown["seq"]:
                raise StateRefusal("chi_state_source_not_read")
            unknown_kind = source_kind_for(self.data["role"], unknown["tool"],
                                           tool_kind(unknown["tool"]), unknown["scope"])
            allowed = ({"file_evidence"} if unknown_kind == "file_deliverable"
                       else {"business_status"} if unknown_kind in {"business_mutation", "unknown_mutation"}
                       else {"business_status", "business_evidence", "file_evidence",
                             "policy_evidence", "patient_evidence"})
            if source.get("source_kind") not in allowed:
                # A failed business write cannot be resolved by reading a file
                # or policy, and a failed file write cannot be resolved by a
                # business-status read.
                raise StateRefusal("chi_state_source_not_read")
            if unknown["scope"] not in {"unattributed", source["scope"]}:
                raise StateRefusal("chi_state_case_mismatch")
            unknown["status"] = "resolved"
            unknown["resolution_call_id"] = source["call_id"]
            unknown["note"] = _text(item["note"], field="note")

    def propose(self, payload: object) -> dict:
        """Validate and apply one model-proposed update; return the new version."""
        if type(payload) is not dict or not payload or set(payload) - UPDATE_KEYS:
            raise StateRefusal("chi_state_update_invalid")
        backup = json.loads(json.dumps(self.data))
        try:
            if "target" in payload:
                self._apply_target(payload["target"])
            if "facts" in payload:
                self._apply_facts(payload["facts"])
            if "plans" in payload:
                self._apply_plans(payload["plans"])
            if "gaps" in payload:
                self._apply_gaps(payload["gaps"])
            if "latest_business_status" in payload:
                self._apply_status(payload["latest_business_status"])
            if "next_candidates" in payload:
                self._apply_next(payload["next_candidates"])
            if "resolve_unknown" in payload:
                self._apply_resolutions(payload["resolve_unknown"])
            self.data["version"] += 1
            self._persist()
            return {"status": "updated", "version": self.data["version"],
                    "target": dict(self.data["target"])}
        except StateRefusal:
            self.data = backup
            raise
        except GoFailure:
            self.data = backup
            raise
        except Exception:
            self.data = backup
            raise GoFailure("chi_state_persistence_failed") from None

    # -- completion ------------------------------------------------------
    def claim_recorded(self) -> bool:
        return self.data["claim"] is not None

    def mutation_block_reason(self, tool: str, kind: str) -> str | None:
        """Refuse a new write after completion; journal claims are monotonic."""
        if self.data["claim"] is not None and effect_for(tool, kind) == "mutation":
            return "task_already_claimed_mutation_forbidden"
        return None

    def stagnation_warning(self, tool: str, kind: str, arguments) -> str | None:
        """Warn before a third identical read; do not block yet."""
        if effect_for(tool, kind) != "read":
            return None
        repeat = self.data.get("repeat") or {}
        if (repeat.get("fingerprint") == _fingerprint(tool, kind, arguments)
                and int(repeat.get("count", 0)) >= 2):
            return ("STAGNATION: repeated identical read; change approach or stop "
                    "instead of repeating the same call")
        return None

    def stagnation_block_reason(self, tool: str, kind: str, arguments) -> str | None:
        if effect_for(tool, kind) != "read":
            return None
        repeat = self.data.get("repeat") or {}
        if (repeat.get("fingerprint") == _fingerprint(tool, kind, arguments)
                and int(repeat.get("count", 0)) >= 4):
            return "stagnation_detected"
        return None

    def block_mutation(self, tool: str, kind: str, arguments=None) -> str | None:
        """Refuse an unsafe write; do not rewrite journal claims."""
        reason = self.mutation_block_reason(tool, kind)
        if reason is not None:
            if not self.data.get("claim_violation"):
                self.data["claim_violation"] = True
                self._persist()
            return reason
        open_unknown = next((item for item in self.data["unknowns"]
                             if item["status"] == "open"), None)
        if open_unknown is not None and effect_for(tool, kind) == "mutation":
            return "unknown_write_effect_pending:" + open_unknown["id"]
        if effect_for(tool, kind) == "mutation" and arguments is not None:
            repeat = self.data.get("repeat") or {}
            if (repeat.get("fingerprint") == _fingerprint(tool, kind, arguments)
                    and int(repeat.get("count", 0)) >= 1):
                self.data["stagnation"] = {"tool": tool, "count": int(repeat["count"]) + 1,
                                           "call_id": None, "effect": "mutation"}
                self._persist()
                return "repeated_write_forbidden"
        return None

    def _business_mutations(self) -> list[dict]:
        return [item for item in self.data["observations"]
                if item.get("source_kind") in {"business_mutation", "unknown_mutation"}
                and item["event"] != "refused"]

    def _file_mutations(self) -> list[dict]:
        return [item for item in self.data["observations"]
                if item.get("source_kind") == "file_deliverable"]

    def _completion(self) -> tuple[bool, str | None, str, str, str | None]:
        """One shared completion evaluation for claim feedback and reports."""
        if self.data.get("claim_violation"):
            return False, "completion_blocked_claim_violation", "blocked", "violation", None
        open_unknowns = [item for item in self.data["unknowns"] if item["status"] == "open"]
        if open_unknowns:
            return False, "completion_blocked_unknown:" + open_unknowns[0]["id"], "blocked", "unknown", None
        failed_files = [item for item in self._file_mutations()
                        if item["event"] in {"failed", "returned_error"}]
        if failed_files:
            return (False, "completion_file_write_failed:" + failed_files[-1]["call_id"],
                    "blocked", "not_verified", "file_delivery")
        status = self.data["latest_business_status"]
        business = self._business_mutations()
        if business:
            last = business[-1]
            if status is None or status["source_seq"] <= last["seq"]:
                return (False, "completion_readback_required:" + last["call_id"],
                        "blocked", "not_verified", "business_status")
        if status is None:
            return True, None, "not_applicable", "not_observed", None
        return True, None, "mechanical_pass", "observed", None

    def can_claim(self) -> tuple[bool, str | None]:
        allowed, reason, _verification, _effect, _missing = self._completion()
        return allowed, reason

    def completion_report(self) -> dict:
        """Mechanical completion evidence, not a business or official verdict."""
        allowed, reason, verification, effect, required = self._completion()
        status = self.data["latest_business_status"]
        status_view = None
        if status is not None:
            source = next((item for item in self.data["observations"]
                           if item["call_id"] == status["source_call_id"]), None)
            status_view = dict(status)
            status_view.update({
                "source_tool": source["tool"] if source else None,
                "source_kind": source.get("source_kind") if source else None,
                "source_scope": source["scope"] if source else None,
                "source_event": source["event"] if source else None,
            })
        business = self._business_mutations()
        files = self._file_mutations()
        last_business = business[-1] if business else None
        last_file = files[-1] if files else None
        open_unknowns = [item["id"] for item in self.data["unknowns"] if item["status"] == "open"]

        def reference(item):
            return None if item is None else {
                "call_id": item["call_id"], "tool": item["tool"],
                "seq": item["seq"], "event": item["event"],
            }

        limitations = []
        if self.data["claim"] is None:
            limitations.append("final_text_without_claim_not_blocked")
        return {
            "schema": COMPLETION_SCHEMA,
            "verification": verification,
            "business_effect": effect,
            "reason": reason,
            "target": dict(self.data["target"]),
            "claim": self.data["claim"],
            "claim_policy": "optional_final_text",
            "latest_business_status": status_view,
            "last_business_mutation": reference(last_business),
            "last_file_mutation": reference(last_file),
            "last_mutation_call_id": last_business["call_id"] if last_business else None,
            "required_readback": required,
            "open_unknowns": open_unknowns,
            "claim_violation": bool(self.data.get("claim_violation")),
            "stagnation": self.data.get("stagnation"),
            "remaining_limitations": limitations,
            "note": ("mechanical/source check only; not a clinical or official verdict; "
                     "a successful file write after a business readback does not require "
                     "another business readback, while failed file writes still block"),
        }

    def record_claim(self) -> dict:
        allowed, reason = self.can_claim()
        if not allowed:
            return {"status": "refused", "reason": reason}
        status = self.data["latest_business_status"]
        self.data["claim"] = {
            "version": self.data["version"],
            "target": dict(self.data["target"]),
            "verified_status_call_id": status["source_call_id"] if status else None,
            "at_utc_ms": time.time_ns() // 1000000,
            "kind": "model_claim",
        }
        self._persist()
        return {"status": "recorded"}

    # -- model-readable summary -----------------------------------------
    def summary(self) -> dict:
        data = self.data
        observations = data["observations"][-LIMITS["observations_in_summary"]:]
        return {
            "schema": VERSION,
            "version": data["version"],
            "role": data["role"],
            "target": dict(data["target"]),
            "facts": list(data["facts"]),
            "plans": list(data["plans"]),
            "gaps": list(data["gaps"]),
            "unknowns": list(data["unknowns"]),
            "latest_business_status": data["latest_business_status"],
            "next_candidates": list(data["next_candidates"]),
            "claim": data["claim"],
            "claim_violation": data.get("claim_violation", False),
            "stagnation": data.get("stagnation"),
            "observations": [
                {key: item[key] for key in ("seq", "call_id", "tool", "effect",
                                            "source_kind", "scope", "event")}
                for item in observations
            ],
            "observation_count": len(data["observations"]),
            "limits": dict(LIMITS),
        }
