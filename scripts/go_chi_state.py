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
import unicodedata
from pathlib import Path

from opencode_go_provider import GoFailure

SCHEMA = "chi-task-state-v3"
VERSION = "chi-task-state-v3"
SCHEMA_V4 = "chi-task-state-v4"
VERSION_V4 = "chi-task-state-v4"
ANCHOR_SCHEMA = "chi-intent-anchor-v1"
CONTEXT_POLICY_V3 = "chi-context-v3"
DRIFT_CLASS_LIMIT = 2
DRIFT_RUN_LIMIT = 3
LEGACY_SCHEMAS = frozenset({"chi-task-state-v1", "chi-task-state-v2"})
COMPLETION_SCHEMA = "chi-completion-v3"
COMPLETION_SCHEMA_V4 = "chi-completion-v4"
COMPLETION_SCHEMA_V5 = "chi-completion-v5"
REQUIREMENTS_POLICY = "chi-requirements-v1"
MAX_STATE_BYTES = 65536
MAX_TEXT = 800
MAX_REQUIREMENTS = 8
REQUIREMENT_ID = re.compile(r"^r[0-9]{1,2}$")
REQUIREMENT_STATUSES = frozenset({"open", "done", "waived"})
WAIVER_REASONS = frozenset({"not_applicable_public_rule"})
REQUIREMENT_ITEM_KEYS = {"id", "quote", "status", "evidence_call_id", "waiver_reason", "note"}
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


def _normalized_quote(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


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


def _mutation_case_id(tool: str, kind: str, arguments) -> str | None:
    """Return the case a mutation targets, when the program can derive it.

    MCP mutations carry an explicit ``case_id``. Local file mutations derive the
    case from the workspace path ``<root>/<case>/<role|shared>/...``. A mutation
    whose case cannot be derived is left to the other gates.
    """
    if type(arguments) is not dict:
        return None
    if kind == "mcp":
        value = arguments.get("case_id")
        return value if type(value) is str and CASE_ID.fullmatch(value) else None
    if kind == "local" and tool in {"local-fs-write", "local-fs-edit"}:
        path = arguments.get("path")
        if type(path) is not str or not path.startswith("/") or len(path) > 2048:
            return None
        parts = Path(path).parts
        for index, part in enumerate(parts):
            if index >= 1 and part in {"provider", "payer", "cm", "shared"}:
                candidate = parts[index - 1]
                if CASE_ID.fullmatch(candidate):
                    return candidate
        return None
    return None


def file_resource(tool: str, kind: str, arguments) -> str | None:
    """Return a bounded program-owned file resource id for delivery evidence.

    Only local file tools with an absolute path have a stable resource. The
    model cannot supply a repair note or nominate another path as the same
    resource; matching is by exact path plus the observation scope.
    """
    if kind != "local" or tool not in {"local-fs-write", "local-fs-edit", "local-fs-read"}:
        return None
    if type(arguments) is not dict:
        return None
    path = arguments.get("path")
    if (type(path) is not str or not path.startswith("/") or len(path) > 2048
            or "\x00" in path or any(ord(ch) < 32 for ch in path)):
        return None
    return path


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

    def __init__(self, root, *, run: str, role: str, binding=None,
                 requirements=None, instruction=None, context_policy=None):
        if requirements not in {None, REQUIREMENTS_POLICY}:
            raise GoFailure("chi_requirements_configuration_invalid")
        if requirements == REQUIREMENTS_POLICY and (type(instruction) is not str or not instruction.strip()):
            raise GoFailure("chi_requirements_configuration_invalid")
        self._context_v3 = context_policy == CONTEXT_POLICY_V3
        self._requirements_enabled = requirements == REQUIREMENTS_POLICY
        self._instruction = instruction if self._requirements_enabled else None
        self._requirements_sha = (hashlib.sha256(instruction.encode("utf-8")).hexdigest()
                                  if self._requirements_enabled else None)
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
        self._update_keys = set(UPDATE_KEYS)
        if self._requirements_enabled:
            self.data.update({
                "schema": SCHEMA_V4,
                "requirements": [],
                "requirements_declared": False,
                "requirements_instruction_sha256": self._requirements_sha,
            })
            self._update_keys.add("requirements")
        if self._context_v3:
            self.data["drift"] = {"classes": {}, "total": 0, "events": []}
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
            "resource": file_resource(tool, kind, arguments),
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
        if self._context_v3:
            self._bind_target_from_observation(observation)
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

    def _bind_target_from_observation(self, observation: dict) -> None:
        # Bind only from a successful task-scoped read. Payer/provider use the
        # local workspace; CM charts commonly have no readable case file, so the
        # canonical cm_chart.get_chart_data read is the CM task-scope signal.
        # Arbitrary queue reads (for example payer_intake_hub.get_intake_case)
        # never select the target.
        scope = observation.get("scope")
        case_scoped = type(scope) is str and scope.startswith("case:")
        if (case_scoped and observation.get("effect") == "read"
                and observation.get("event") == "returned"
                and self.data["target"]["case_id"] is None):
            local_read = observation.get("kind") == "local"
            cm_chart_read = (self.data["role"] == "cm"
                             and observation.get("kind") == "mcp"
                             and observation.get("tool") == "cm_chart.get_chart_data")
            if local_read or cm_chart_read:
                case_id = scope[5:]
                if CASE_ID.fullmatch(case_id):
                    self.data["target"]["case_id"] = case_id
        if self.data["role"] == "provider":
            bound = getattr(self.binding, "bound", None)
            if type(bound) is str and bound and self.data["target"]["patient_id"] is None:
                self.data["target"]["patient_id"] = bound

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

    def _unique_observation(self, call_id: object) -> dict:
        if type(call_id) is not str:
            raise StateRefusal("chi_state_requirement_evidence_invalid")
        matches = [item for item in self.data["observations"] if item["call_id"] == call_id]
        if len(matches) != 1:
            raise StateRefusal("chi_state_requirement_evidence_invalid")
        return matches[0]

    def _requirement_scope(self, observation: dict) -> None:
        scope = observation.get("scope")
        if scope == "conflict":
            raise StateRefusal("chi_state_requirement_evidence_invalid")
        case_id = self.data["target"]["case_id"]
        if case_id is None:
            if scope != "shared_public":
                raise StateRefusal("chi_state_requirement_evidence_invalid")
            return
        if scope not in {"case:" + case_id, "shared_public"}:
            raise StateRefusal("chi_state_requirement_evidence_invalid")

    def _validate_requirement_source(self, item: dict) -> None:
        source = self._unique_observation(item.get("evidence_call_id"))
        if source["event"] != "returned":
            raise StateRefusal("chi_state_requirement_evidence_invalid")
        if item["status"] == "done":
            if source.get("source_kind") == "neutral" or source["tool"] in NEUTRAL_LOCAL:
                raise StateRefusal("chi_state_requirement_evidence_invalid")
        elif item["status"] == "waived":
            if source.get("effect") != "read" or source.get("source_kind") == "neutral":
                raise StateRefusal("chi_state_requirement_evidence_invalid")
        else:
            raise StateRefusal("chi_state_requirement_evidence_invalid")
        self._requirement_scope(source)

    def _parse_requirement(self, item: object) -> dict:
        if type(item) is not dict or set(item) != REQUIREMENT_ITEM_KEYS:
            raise StateRefusal("chi_state_requirement_invalid")
        identifier = item["id"]
        quote = item["quote"]
        status = item["status"]
        evidence = item["evidence_call_id"]
        waiver = item["waiver_reason"]
        note = item["note"]
        if type(identifier) is not str or not REQUIREMENT_ID.fullmatch(identifier):
            raise StateRefusal("chi_state_requirement_invalid")
        if type(quote) is not str or not quote or len(quote) > MAX_TEXT:
            raise StateRefusal("chi_state_requirement_quote_invalid")
        normalized = _normalized_quote(quote)
        if not 16 <= len(normalized) <= 400 or quote not in self._instruction:
            raise StateRefusal("chi_state_requirement_quote_invalid")
        if type(status) is not str or status not in REQUIREMENT_STATUSES:
            raise StateRefusal("chi_state_requirement_invalid")
        if evidence is not None and (type(evidence) is not str or not CALL_ID.fullmatch(evidence)):
            raise StateRefusal("chi_state_requirement_invalid")
        if waiver is not None and (type(waiver) is not str or waiver not in WAIVER_REASONS):
            raise StateRefusal("chi_state_requirement_transition_invalid")
        if note is not None and (type(note) is not str or not note.strip() or len(note) > MAX_TEXT):
            raise StateRefusal("chi_state_requirement_invalid")
        if status == "open":
            if any(value is not None for value in (evidence, waiver, note)):
                raise StateRefusal("chi_state_requirement_invalid")
        elif status == "done":
            if waiver is not None:
                raise StateRefusal("chi_state_requirement_transition_invalid")
            if evidence is None:
                raise StateRefusal("chi_state_requirement_evidence_invalid")
            if note is None:
                raise StateRefusal("chi_state_requirement_invalid")
        else:
            if waiver is None:
                raise StateRefusal("chi_state_requirement_transition_invalid")
            if evidence is None:
                raise StateRefusal("chi_state_requirement_evidence_invalid")
            if note is None:
                raise StateRefusal("chi_state_requirement_invalid")
        return {"id": identifier, "quote": quote, "status": status,
                "evidence_call_id": evidence, "waiver_reason": waiver, "note": note}

    def _apply_requirements(self, payload: object) -> None:
        if not self._requirements_enabled:
            raise StateRefusal("chi_state_requirement_invalid")
        if type(payload) is not list or len(payload) > MAX_REQUIREMENTS:
            raise StateRefusal("chi_state_requirement_invalid")
        parsed, seen = [], set()
        for item in payload:
            value = self._parse_requirement(item)
            if value["id"] in seen:
                raise StateRefusal("chi_state_requirement_invalid")
            seen.add(value["id"])
            parsed.append(value)
        existing = self.data["requirements"]
        if len(parsed) < len(existing):
            raise StateRefusal("chi_state_requirement_transition_invalid")
        for index, old in enumerate(existing):
            new = parsed[index]
            if new["id"] != old["id"] or new["quote"] != old["quote"]:
                raise StateRefusal("chi_state_requirement_transition_invalid")
            if old["status"] in {"done", "waived"}:
                if new != old:
                    raise StateRefusal("chi_state_requirement_transition_invalid")
            elif new["status"] == "open":
                if new != old:
                    raise StateRefusal("chi_state_requirement_transition_invalid")
        for new in parsed[len(existing):]:
            if new["status"] != "open":
                raise StateRefusal("chi_state_requirement_transition_invalid")
        for item in parsed:
            if item["status"] in {"done", "waived"}:
                self._validate_requirement_source(item)
        self.data["requirements"] = parsed
        self.data["requirements_declared"] = True

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
        if self._requirements_enabled:
            for item in self.data.get("requirements", []):
                if item["status"] in {"done", "waived"}:
                    self._validate_requirement_source(item)

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
        if type(payload) is not dict or not payload or set(payload) - self._update_keys:
            raise StateRefusal("chi_state_update_invalid")
        if self._context_v3 and ({"facts", "target"} & set(payload)):
            raise StateRefusal("chi_state_program_owned")
        backup = json.loads(json.dumps(self.data))
        try:
            if "target" in payload:
                self._apply_target(payload["target"])
            if "requirements" in payload:
                self._apply_requirements(payload["requirements"])
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

    def drift_check(self, tool: str, kind: str, arguments) -> str | None:
        """Classify v3 drift; soft refusals are counted, hard violations stop."""
        if not self._context_v3 or tool in {"local-claim_done", "local-state-update",
                                             "local-task-state", "local-completion-check",
                                             "local-role-guidance"}:
            return None
        effect = effect_for(tool, kind)
        rule = None
        if effect == "mutation":
            target_case = self.data["target"]["case_id"]
            mutation_case = _mutation_case_id(tool, kind, arguments)
            if (target_case is not None and mutation_case is not None
                    and mutation_case != target_case):
                rule = "target_mismatch"
            elif tool in {"local-fs-write", "local-fs-edit"}:
                case_id = mutation_case
                if case_id is not None and not any(
                        item.get("event") == "returned" and item.get("effect") == "read"
                        and item.get("scope") == "case:" + case_id
                        for item in self.data["observations"]):
                    rule = "unread_write"
            elif tool == "auth.submit_authorization":
                if not any(item.get("event") == "returned" and item.get("effect") == "read"
                           and type(item.get("scope")) is str and item["scope"].startswith("case:")
                           for item in self.data["observations"]):
                    rule = "unread_write"
        if rule is None and effect == "read":
            repeat = self.data.get("repeat") or {}
            if repeat.get("fingerprint") == _fingerprint(tool, kind, arguments) \
                    and int(repeat.get("count", 0)) >= 2:
                rule = "repeat_call"
        if rule is None:
            return None
        drift = self.data.setdefault("drift", {"classes": {}, "total": 0, "events": []})
        hard = rule in {"unread_write", "target_mismatch"}
        count = int(drift["classes"].get(rule, 0)) + 1
        if hard or count > DRIFT_CLASS_LIMIT or drift["total"] >= DRIFT_RUN_LIMIT:
            drift["classes"][rule] = count
            drift["total"] = int(drift["total"]) + 1
            self._persist()
            return "HARD:" + rule
        drift["classes"][rule] = count
        drift["total"] = int(drift["total"]) + 1
        self._persist()
        return "SOFT:" + rule + ":" + str(count)

    def drift_record(self, rule: str, call_id: str, severity: str, outcome: str) -> None:
        if not self._context_v3:
            return
        if severity not in {"soft", "hard"} or outcome not in {"refused", "stopped"}:
            raise StateRefusal("chi_state_update_invalid")
        drift = self.data.setdefault("drift", {"classes": {}, "total": 0, "events": []})
        drift["events"].append({"schema": "chi-drift-event-v1", "rule": rule,
                                "call_id": call_id, "severity": severity,
                                "outcome": outcome,
                                "count": int(drift["classes"].get(rule, 0))})
        drift["events"] = drift["events"][-32:]
        self._persist()

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

    def _failed_business_mutations(self) -> list[dict]:
        return [item for item in self.data["observations"]
                if item.get("source_kind") in {"business_mutation", "unknown_mutation"}
                and item.get("event") in {"returned_error", "failed"}]

    def _file_mutations(self) -> list[dict]:
        return [item for item in self.data["observations"]
                if item.get("source_kind") == "file_deliverable"]

    def _unresolved_file_deliveries(self) -> list[dict]:
        """Return only file failures not repaired by a later same-resource success.

        The failure observations stay in state. A later successful write/edit
        to the exact same path and scope is the only program-owned repair
        evidence; unrelated paths, other cases/roles and model notes do not
        clear the failure.
        """
        failures = {}
        successes = {}
        for item in self._file_mutations():
            resource = item.get("resource")
            key = (item.get("scope"), resource) if type(resource) is str else None
            if item["event"] in {"failed", "returned_error"}:
                if key is None:
                    failures[("unkeyed", item["call_id"])] = item
                else:
                    failures[key] = item
            elif item["event"] == "returned" and key is not None:
                successes[key] = max(successes.get(key, 0), item["seq"])
        unresolved = []
        for key, failure in failures.items():
            if key[0] == "unkeyed" or successes.get(key, 0) <= failure["seq"]:
                unresolved.append(failure)
        return sorted(unresolved, key=lambda item: item["seq"])

    def _completion(self) -> tuple[bool, str | None, str, str, str | None]:
        """One shared completion evaluation for claim feedback and reports."""
        if self.data.get("claim_violation"):
            return False, "completion_blocked_claim_violation", "blocked", "violation", None
        open_unknowns = [item for item in self.data["unknowns"] if item["status"] == "open"]
        if open_unknowns:
            return False, "completion_blocked_unknown:" + open_unknowns[0]["id"], "blocked", "unknown", None
        unresolved = self._unresolved_file_deliveries()
        if unresolved:
            return (False, "completion_file_write_failed:" + unresolved[0]["call_id"],
                    "blocked", "not_verified", "file_delivery")
        if self._requirements_enabled:
            if not self.data["requirements_declared"]:
                return False, "completion_requirements_undeclared", "blocked", "not_verified", None
            items = self.data["requirements"]
            if not items:
                return False, "completion_requirements_empty", "blocked", "not_verified", None
            open_items = [item for item in items if item["status"] == "open"]
            if open_items:
                return (False, "completion_requirements_open:" + open_items[0]["id"],
                        "blocked", "not_verified", None)
            for item in items:
                try:
                    self._validate_requirement_source(item)
                except StateRefusal:
                    return (False, "completion_requirements_evidence_invalid:" + item["id"],
                            "blocked", "not_verified", None)
        if self._context_v3:
            from go_chi_completion import evaluate
            allowed, reason, _details = evaluate(self.data)
            if not allowed:
                return False, reason, "blocked", "not_verified", "terminal_object"
            failed = self._failed_business_mutations()
            if failed:
                return (False, "completion_business_write_failed:" + failed[-1]["call_id"],
                        "blocked", "not_verified", "business_status")
        status = self.data["latest_business_status"]
        business = self._business_mutations()
        if business:
            last = business[-1]
            if status is None or status["source_seq"] <= last["seq"]:
                return (False, "completion_readback_required:" + last["call_id"],
                        "blocked", "not_verified", "business_status")
            source = next((item for item in self.data["observations"]
                           if item["call_id"] == status["source_call_id"]), None)
            # An unattributed mutation (for example a letter delivery that only
            # takes letter_id) cannot be matched by scope; _apply_status has
            # already restricted the status source to the target case, so a
            # later business-status read is a valid readback.
            if self._context_v3 and (
                    source is None
                    or (last.get("scope") != "unattributed"
                        and source.get("scope") != last.get("scope"))):
                return (False, "completion_readback_required:" + last["call_id"],
                        "blocked", "not_verified", "business_status")
        if status is None:
            return True, None, "not_applicable", "not_observed", None
        return True, None, "mechanical_pass", "observed", None

    def can_claim(self) -> tuple[bool, str | None]:
        allowed, reason, _verification, _effect, _missing = self._completion()
        return allowed, reason

    def _requirements_report(self) -> dict:
        items = self.data["requirements"]
        done = sum(1 for item in items if item["status"] == "done")
        waived = sum(1 for item in items if item["status"] == "waived")
        open_ids = [item["id"] for item in items if item["status"] == "open"]
        count = len(items)
        declared = bool(self.data["requirements_declared"])
        if not declared:
            status = "undeclared"
        elif count == 0:
            status = "empty_unverified"
        elif open_ids:
            status = "open"
        elif waived:
            status = "closed_with_waivers"
        else:
            status = "closed_reported"
        return {
            "policy": REQUIREMENTS_POLICY,
            "instruction_sha256": self.data["requirements_instruction_sha256"],
            "declared": declared,
            "status": status,
            "count": count,
            "done": done,
            "waived": waived,
            "open": len(open_ids),
            "open_ids": open_ids,
            "verification": "provenance_only",
            "semantic_completion_verified": False,
        }

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
        unresolved = self._unresolved_file_deliveries()
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
        if self._requirements_enabled:
            limitations.append("requirements_provenance_only_not_semantic_completion")
        note = ("mechanical/source check only; not a clinical or official verdict; "
                "a later successful write/edit to the same path and scope repairs a "
                "known file-write failure, while unrelated paths, unresolved unknowns "
                "and failed repairs still block; a successful file write after a "
                "business readback does not require another business readback")
        if self._requirements_enabled:
            note += ("; requirement done/waived is provenance-only and does not prove "
                     "semantic business completion")
        report = {
            "schema": (COMPLETION_SCHEMA_V5 if self._context_v3 else
                       COMPLETION_SCHEMA_V4 if self._requirements_enabled else COMPLETION_SCHEMA),
            "verification": verification,
            "business_effect": effect,
            "reason": reason,
            "target": dict(self.data["target"]),
            "claim": self.data["claim"],
            "claim_policy": "mandatory_claim" if self._context_v3 else "optional_final_text",
            "latest_business_status": status_view,
            "last_business_mutation": reference(last_business),
            "last_file_mutation": reference(last_file),
            "last_mutation_call_id": last_business["call_id"] if last_business else None,
            "required_readback": required,
            "unresolved_file_deliveries": [
                {"call_id": item["call_id"], "tool": item["tool"],
                 "resource": item.get("resource"), "event": item["event"]}
                for item in unresolved
            ],
            "open_unknowns": open_unknowns,
            "claim_violation": bool(self.data.get("claim_violation")),
            "stagnation": self.data.get("stagnation"),
            "remaining_limitations": limitations,
            "note": note,
        }
        if self._context_v3:
            from go_chi_completion import evaluate
            _allowed, _reason, details = evaluate(self.data)
            report["completion_evidence"] = details
        if self._requirements_enabled:
            report["requirements"] = self._requirements_report()
        return report

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
    def _has_tool(self, names) -> bool:
        wanted = set(names)
        return any(item.get("event") in {"returned", "returned_error"}
                   and item.get("tool") in wanted for item in self.data["observations"])

    def _current_stage(self) -> str:
        role = self.data["role"]
        if role == "provider":
            if self.data["target"]["case_id"] is None:
                return "identify_target"
            if not self._has_tool({"cases.create_from_order"}):
                return "verify_evidence"
            if not self._has_tool({"forms.save_form_response", "docs.create_submission_bundle"}):
                return "prepare_packet"
            if not self._has_tool({"auth.submit_authorization", "auth.finalize_provider_determination"}):
                return "submit_or_defer"
            return "verify_and_close"
        if role == "payer":
            if not self._has_tool({"payer_intake_hub.get_intake_case"}):
                return "intake_review"
            if not self._has_tool({"review.get_nurse_review_data", "review.get_md_review_data"}):
                return "verify_documents"
            if not self._has_tool({"review.save_criteria_evaluation"}):
                return "assess_criteria"
            if not self._has_tool({"determination.finalize"}):
                return "choose_disposition"
            if not self._has_tool({"payer_letter_center.generate_approval",
                                   "payer_letter_center.generate_partial_approval",
                                   "payer_letter_center.generate_denial",
                                   "payer_letter_center.generate_pend",
                                   "payer_letter_center.generate_notification"}):
                return "produce_letter"
            return "finalize_and_readback"
        if not self._has_tool({"cm_intake.get_referral"}):
            return "open_case"
        if not self._has_tool({"cm_chart.get_chart_data"}):
            return "chart_review"
        if not self._has_tool({"cm_outreach.start_outreach_call", "cm_outreach.send_message"}):
            return "outreach"
        if not self._has_tool({"cm_assessment.complete_assessment"}):
            return "assessment"
        if not self._has_tool({"cm_care_plan.finalize"}):
            return "care_plan"
        return "close_or_report"

    def anchor(self) -> dict:
        """Return the deterministic wire-only intent anchor for this state."""
        from go_chi_guidance import guidance
        summary = self.summary()
        stage_id = self._current_stage()
        stages = guidance(self.data["role"], summary).get("stages", [])
        stage = next((item for item in stages if item.get("id") == stage_id), None)
        if stage is None:
            raise GoFailure("chi_anchor_invalid")
        payload = {
            "schema": ANCHOR_SCHEMA,
            "role": self.data["role"],
            "goal": stage.get("goal"),
            "target": dict(self.data["target"]),
            "non_goals": list(stage.get("stop_if", [])),
            "current_step": stage_id,
            "acceptance": list(stage.get("readback", [])),
            "forbidden": [
                "do not invent identifiers or evidence",
                "do not write a different patient/case than the observed target",
                "do not continue after an unknown write effect",
                "do not claim completion without a returned business readback",
            ],
        }
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
        return {"text": text, "sha256": _sha(payload), "stage": stage_id,
                "schema": ANCHOR_SCHEMA}

    def summary(self) -> dict:
        data = self.data
        observations = data["observations"][-LIMITS["observations_in_summary"]:]
        result = {
            "schema": VERSION_V4 if self._requirements_enabled else VERSION,
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
                {key: item.get(key) for key in ("seq", "call_id", "tool", "effect",
                                                "source_kind", "resource", "scope", "event")}
                for item in observations
            ],
            "observation_count": len(data["observations"]),
            "drift": data.get("drift"),
            "limits": dict(LIMITS),
        }
        if self._requirements_enabled:
            result["requirements"] = list(data["requirements"])
            result["requirements_declared"] = bool(data["requirements_declared"])
        return result
