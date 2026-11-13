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

from .opencode_go_provider import GoFailure

SCHEMA = "chi-task-state-v3"
VERSION = "chi-task-state-v3"
SCHEMA_V4 = "chi-task-state-v4"
VERSION_V4 = "chi-task-state-v4"
ANCHOR_SCHEMA = "chi-intent-anchor-v1"
CONTEXT_POLICY_V3 = "chi-context-v3"
PROVIDER_ACTION_STATUS = {"submit_pa": "ready_to_submit", "gather_more_evidence": "docs_needed", "do_not_submit": "closed"}
PROVIDER_SUBMITTED_STATUSES = frozenset({"submitted", "resubmitted", "under_review", "approved", "partially_approved", "denied", "pended_action_required", "appealed", "appeal_upheld", "appeal_overturned", "external_appealed", "external_appeal_upheld", "external_appeal_overturned", "closed"})
PROVIDER_POS_CODES = {"11": "office", "21": "inpatient_hospital", "22": "outpatient_hospital", "19": "outpatient_hospital"}
PROVIDER_CHART_PAGE = "local-read-patient-observation"
PROVIDER_ORDER_FIELDS = {"chart.get_patient_chart_by_patient": "orders", "chart.list_candidate_orders": "items"}
PROVIDER_CLINICAL_FIELDS = ("summaries", "conditions", "observations", "encounters", "orders",
                            "procedures", "medications", "allergies", "notes", "items")
PROVIDER_POS_LABELS = {"office": "office", "inpatient_hospital": "inpatient hospital",
                       "outpatient_hospital": "outpatient hospital", "ambulatory_surgical_center": "ambulatory surgical center",
                       "emergency_room": "emergency room", "skilled_nursing_facility": "skilled nursing facility",
                       "home": "home", "telehealth": "telehealth", "urgent_care": "urgent care",
                       "rehabilitation_facility": "rehabilitation facility", "hospice": "hospice"}

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
    "local-read-patient-roster": "read",
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


def _provider_texts(value):
    if type(value) is str:
        yield value
    elif type(value) is list:
        for item in value:
            yield from _provider_texts(item)
    elif type(value) is dict:
        for item in value.values():
            yield from _provider_texts(item)


def _provider_orders(value, field, patient_id, args):
    items = value.get(field)
    if type(items) is not list:
        return []
    source_order = args.get("source_order_id")
    code = args.get("procedure_code")
    return [item for item in items if type(item) is dict and item.get("patient_id") == patient_id
            and (not source_order or item.get("id") == source_order)
            and type(code) is str and item.get("procedure_code") == code]


def _provider_site(order):
    site = order.get('site_of_service')
    return PROVIDER_POS_CODES.get(site, site) if type(site) is str else None


def _provider_location_statement(text, quote, label, args):
    if not re.search(r'\b' + re.escape(label) + r'\b', quote, re.I):
        return False
    names = [re.escape(name.strip()) for name in (args.get('description'), args.get('procedure_code'))
             if type(name) is str and name.strip()]
    if not names:
        return False
    service = r'(?:' + '|'.join(names) + r')'
    action = r'(?:is\s+)?(?:scheduled|planned|to be performed|performed)\s+(?:at|in)\s+'
    site = r'(?:an?\s+|the\s+)?' + re.escape(label)
    patterns = (r'(?:the\s+)?' + service + r'\s+' + action + site,
                r'(?:the\s+)?(?:service|procedure|test|study|treatment)\s+(?:for\s+)?' + service + r'\s+' + action + site)
    return any(quote in line and any(re.fullmatch(pattern, line.strip(), re.I) for pattern in patterns)
               for line in re.split(r'[.!?](?=\s|$)|\r?\n', text))


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
        if tool in {"local-read-patient-observation", "local-read-patient-roster"}:
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
        self._provider_enabled = self._context_v3 and role == "provider" and binding is not None
        self._provider_guard = None
        self._provider_delivered = {}
        self.provider_file_versions = {}
        if self._provider_enabled:
            self.data["provider_pre_submission"] = {"schema": "chi-provider-pre-submission-v1", "location": None, "reviews": {}, "cases": {}, "generated_documents": []}
        self._update_keys = set(UPDATE_KEYS)
        if self._provider_enabled:
            self._update_keys.update({"provider_location", "provider_review"})
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

    def provider_configure(self, guard_getter, delivered, instruction, instruction_path, handbook_root, tool_references):
        self._provider_guard = guard_getter
        self._provider_delivered = delivered
        self._provider_instruction = instruction
        self._provider_instruction_path = str(instruction_path)
        self._provider_handbook = Path(handbook_root)
        self._provider_references = {str(path) for path in tool_references}

    def _provider_chart_page(self, record, visible):
        from .patient_identity_binding import Refusal

        args = record['arguments']
        if args.get('patient_id') != self.binding.bound:
            raise StateRefusal('provider_clinical_source_invalid')
        try:
            page = json.loads(visible)
            expected = self.binding.read_observation(self.binding.bound, args['offset'], args.get('sha256'))
            if type(page) is not dict or page != json.loads(expected):
                raise ValueError
            return page
        except (Refusal, ValueError, KeyError, TypeError):
            raise StateRefusal('provider_clinical_source_invalid') from None

    def _provider_source(self, call_id, quote, kind):
        if type(quote) is not str or not 1 <= len(quote) <= 800:
            raise StateRefusal("provider_source_quote_invalid")
        if call_id == "instruction":
            if kind != "location" or quote not in self._provider_instruction:
                raise StateRefusal("provider_source_unverified")
            text = self._provider_instruction
            return {"call_id": call_id, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "start": text.index(quote), "end": text.index(quote) + len(quote)}
        guard = self._provider_guard() if self._provider_guard else None
        if guard is None or call_id not in self._provider_delivered:
            raise StateRefusal("provider_source_not_delivered")
        rec = next((r for r in guard.contract.records if r['id'] == call_id), None)
        obs = next((o for o in self.data['observations'] if o['call_id'] == call_id), None)
        if rec is None or obs is None or obs['event'] != 'returned':
            raise StateRefusal("provider_source_unverified")
        canonical = guard.canonical_tools.get(rec['name'], rec['name'])
        visible = self._provider_delivered[call_id]
        if canonical == PROVIDER_CHART_PAGE:
            if kind == 'policy':
                raise StateRefusal('provider_policy_source_invalid')
            page = self._provider_chart_page(rec, visible)
            text = page['content']
            if quote not in text:
                raise StateRefusal('provider_source_quote_invalid')
            chart = self.binding.charts[self.binding.bound]['value']
            fields = {key: chart[key] for key in PROVIDER_CLINICAL_FIELDS if key in chart}
            if kind == 'clinical' and (len(quote.strip()) < 8 or quote not in json.dumps(fields, ensure_ascii=False)):
                raise StateRefusal('provider_clinical_quote_invalid')
            start = text.index(quote)
            return {'call_id': call_id, 'sha256': page['sha256'],
                    'view_sha256': hashlib.sha256(visible.encode()).hexdigest(),
                    'start': start, 'end': start + len(quote)}
        if quote not in visible:
            raise StateRefusal("provider_source_quote_invalid")
        if kind == 'policy':
            if canonical != 'local-fs-read' or obs.get('scope') != 'shared_public':
                raise StateRefusal("provider_policy_source_invalid")
            path = rec['arguments'].get('path')
            try:
                in_handbook = Path(path).is_relative_to(self._provider_handbook)
            except (TypeError, ValueError):
                in_handbook = False
            if path == self._provider_instruction_path or not (in_handbook or path in self._provider_references):
                raise StateRefusal("provider_policy_source_invalid")
        else:
            if canonical not in {'chart.get_patient_chart_by_patient', 'chart.list_candidate_orders', 'docs.get_document'}:
                raise StateRefusal("provider_clinical_source_invalid")
            if canonical.startswith('chart.') and rec['arguments'].get('patient_id') != self.binding.bound:
                raise StateRefusal("provider_clinical_source_invalid")
            if canonical == 'docs.get_document' and rec['arguments'].get('document_id') in self.data['provider_pre_submission']['generated_documents']:
                raise StateRefusal("provider_clinical_source_invalid")
            if canonical == 'docs.get_document' and (self.binding.patient_documents.get(rec['arguments'].get('document_id')) != self.binding.bound
                                                       and rec['arguments'].get('document_id') not in self.binding.documents):
                raise StateRefusal("provider_clinical_source_invalid")
        if kind == 'clinical' or (kind == 'location' and canonical == 'docs.get_document'):
            try:
                delivered_value = json.loads(visible)
                if canonical == 'docs.get_document':
                    document = delivered_value['document']
                    if (type(document) is not dict or document.get('id') != rec['arguments'].get('document_id')
                            or document.get('patient_id') != self.binding.bound
                            or (kind == 'location' and document.get('case_id') is not None)
                            or type(document.get('content')) is not str
                            or quote not in document['content']):
                        raise ValueError
                else:
                    if len(quote.strip()) < 8:
                        raise ValueError
                    if canonical == 'chart.get_patient_chart_by_patient':
                        if type(delivered_value.get('patient')) is not dict or delivered_value['patient'].get('id') != self.binding.bound:
                            raise ValueError
                    elif canonical == 'chart.list_candidate_orders':
                        items = delivered_value.get('items')
                        if type(items) is not list or any(type(x) is not dict or x.get('patient_id') != self.binding.bound for x in items):
                            raise ValueError
                    allowed = {key: delivered_value[key] for key in PROVIDER_CLINICAL_FIELDS if key in delivered_value}
                    if quote not in json.dumps(allowed, ensure_ascii=False) and not any(
                            quote in value for value in _provider_texts(allowed)):
                        raise ValueError
            except (TypeError, KeyError, ValueError):
                raise StateRefusal('provider_clinical_quote_invalid') from None
        full = guard.full_results.get(call_id, rec['result'])
        file_sha = self.provider_file_versions.get(call_id) if canonical == 'local-fs-read' else None
        if canonical == 'local-fs-read' and file_sha is None:
            raise StateRefusal('provider_source_version_unavailable')
        return {"call_id": call_id, "sha256": hashlib.sha256(full.encode()).hexdigest(),
                "file_sha256": file_sha,
                "view_sha256": hashlib.sha256(visible.encode()).hexdigest(),
                "start": visible.index(quote), "end": visible.index(quote) + len(quote),
                "resource": _sha([canonical, rec['arguments']])}

    def _provider_current(self, source):
        if source is None:
            return False
        if source['call_id'] == 'instruction':
            return hashlib.sha256(self._provider_instruction.encode()).hexdigest() == source['sha256']
        guard = self._provider_guard() if self._provider_guard else None
        if guard is None:
            return False
        records = guard.contract.records
        original = next((r for r in records if r['id'] == source['call_id']), None)
        if original is None:
            return False
        name = guard.canonical_tools.get(original['name'], original['name'])
        if name == PROVIDER_CHART_PAGE:
            try:
                page = self._provider_chart_page(original, self._provider_delivered[source['call_id']])
            except StateRefusal:
                return False
            return page['sha256'] == source['sha256']
        if name == 'local-fs-read':
            path = original['arguments'].get('path')
            matching = [r for r in records if r['name'] == original['name'] and r['arguments'].get('path') == path
                        and r['id'] in self.provider_file_versions and
                        any(o['call_id'] == r['id'] and o['event'] == 'returned' for o in self.data['observations'])]
            return bool(matching) and self.provider_file_versions[matching[-1]['id']] == source['file_sha256']
        matching = [r for r in records if r['result'] is not None and
                    _sha([guard.canonical_tools.get(r['name'], r['name']), r['arguments']]) == source['resource'] and
                    any(o['call_id'] == r['id'] and o['event'] == 'returned' for o in self.data['observations'])]
        if not matching:
            return False
        latest = matching[-1]
        full = guard.full_results.get(latest['id'], latest['result'])
        return hashlib.sha256(full.encode()).hexdigest() == source['sha256']

    def _provider_apply_location(self, value):
        if type(value) is not dict or set(value) != {'site_of_service', 'source_call_id', 'quote'} or not self.binding.bound:
            raise StateRefusal('provider_location_invalid')
        sites = {'office', 'inpatient_hospital', 'outpatient_hospital', 'ambulatory_surgical_center', 'emergency_room',
                 'skilled_nursing_facility', 'home', 'telehealth', 'urgent_care', 'rehabilitation_facility', 'hospice', 'other'}
        if value['site_of_service'] not in sites:
            raise StateRefusal('provider_location_invalid')
        source = self._provider_source(value['source_call_id'], value['quote'], 'location')
        self.data['provider_pre_submission']['location'] = {'site_of_service': value['site_of_service'], 'source': source}

    def _provider_apply_review(self, value):
        keys = {'case_id', 'action', 'rationale', 'policy_source_call_id', 'policy_quote', 'clinical_source_call_id', 'clinical_quote'}
        if type(value) is not dict or set(value) != keys or value['action'] not in {'submit_pa','gather_more_evidence','do_not_submit'}:
            raise StateRefusal('provider_review_invalid')
        case_id = value['case_id']
        case = self.data['provider_pre_submission']['cases'].get(case_id)
        if case is None or self.binding.bound != case['patient_id'] or self.binding.cases.get(case_id) != self.binding.bound:
            raise StateRefusal('provider_review_case_unverified')
        rationale = _text(value['rationale'], field='rationale')
        if case.get('submit_attempted'):
            raise StateRefusal('provider_submission_already_recorded')
        if value['policy_source_call_id'] == value['clinical_source_call_id']:
            raise StateRefusal('provider_review_sources_not_independent')
        policy = self._provider_source(value['policy_source_call_id'], value['policy_quote'], 'policy')
        clinical = self._provider_source(value['clinical_source_call_id'], value['clinical_quote'], 'clinical')
        guard = self._provider_guard()
        rec = next(r for r in guard.contract.records if r['id'] == value['clinical_source_call_id'])
        if guard.canonical_tools.get(rec['name'], rec['name']) == 'docs.get_document':
            doc = rec['arguments'].get('document_id')
            try:
                value_doc = json.loads(self._provider_delivered[rec['id']])['document']
            except (ValueError, KeyError, TypeError):
                raise StateRefusal('provider_clinical_source_invalid') from None
            if (doc in self.binding.documents and self.binding.documents[doc] != case_id
                    or value_doc.get('case_id') not in (None, case_id)):
                raise StateRefusal('provider_clinical_source_invalid')
        self.data['provider_pre_submission']['reviews'][case_id] = {'action': value['action'],
            'rationale_sha256': hashlib.sha256(rationale.encode()).hexdigest(), 'policy': policy, 'clinical': clinical}
        case['decision'] = None
        case['bundle'] = None
        case['readback'] = None

    def _provider_location_matches(self, args):
        location = self.data['provider_pre_submission']['location']
        if location is None or location['site_of_service'] != args.get('site_of_service') or not self._provider_current(location['source']):
            return False
        site = location['site_of_service']
        source = location['source']
        call_id = source['call_id']
        # Any latest independently observed order that identifies this service
        # must agree, including a chart/list cross-read of the same order.
        guard = self._provider_guard() if self._provider_guard else None
        latest = {}
        if guard is not None:
            returned = {item['call_id'] for item in self.data['observations'] if item['event'] == 'returned'}
            for rec in guard.contract.records:
                canonical = guard.canonical_tools.get(rec['name'], rec['name'])
                if (canonical in PROVIDER_ORDER_FIELDS
                        and rec['arguments'].get('patient_id') == self.binding.bound and rec['result'] is not None
                        and rec['id'] in returned):
                    latest[canonical] = rec
            for canonical, rec in latest.items():
                if canonical == 'chart.get_patient_chart_by_patient':
                    value = self.binding.charts.get(self.binding.bound, {}).get('value')
                else:
                    value = self._provider_payload(guard, rec)
                if value is None:
                    return False
                field = PROVIDER_ORDER_FIELDS[canonical]
                source_order = args.get('source_order_id')
                orders = value.get(field, [])
                if type(orders) is not list or (source_order and any(
                        type(order) is dict and order.get('id') == source_order
                        and order.get('patient_id') == self.binding.bound
                        and order.get('procedure_code') != args.get('procedure_code') for order in orders)):
                    return False
                for order in _provider_orders(value, field, self.binding.bound, args):
                    order_site = _provider_site(order)
                    if order_site and order_site != site:
                        return False
        label = PROVIDER_POS_LABELS.get(site)
        if call_id == 'instruction':
            text = self._provider_instruction
            quote = text[source['start']:source['end']].rstrip('.!?')
            return label is not None and _provider_location_statement(text, quote, label, args)
        if guard is None:
            return False
        rec = next((r for r in guard.contract.records if r['id'] == call_id), None)
        if rec is None:
            return False
        canonical = guard.canonical_tools.get(rec['name'], rec['name'])
        text = self._provider_delivered[call_id]
        try:
            if canonical == PROVIDER_CHART_PAGE:
                page = self._provider_chart_page(rec, text)
                text = page['content']
                quote = text[source['start']:source['end']]
                chart = self.binding.charts[self.binding.bound]['value']
                for order in _provider_orders(chart, 'orders', self.binding.bound, args):
                    raw_site = order.get('site_of_service')
                    serialized = json.dumps(order, ensure_ascii=False)
                    start = text.find(serialized)
                    field = '"site_of_service": ' + json.dumps(raw_site, ensure_ascii=False)
                    if (_provider_site(order) == site and start >= 0 and raw_site in quote and quote in field
                            and start <= source['start'] < source['end'] <= start + len(serialized)):
                        return True
                value = chart
                canonical = 'chart.get_patient_chart_by_patient'
            else:
                quote = text[source['start']:source['end']]
                value = self._provider_payload(guard, rec)
                if value is None:
                    return False
                field = PROVIDER_ORDER_FIELDS.get(canonical)
                if field is not None:
                    delivered = json.loads(text)
                    seen_orders = _provider_orders(delivered, field, self.binding.bound, args)
                    if any(_provider_site(order) == site and order['site_of_service'] in quote
                           and quote in json.dumps(order, ensure_ascii=False) for order in seen_orders):
                        return True
        except (ValueError, KeyError, TypeError):
            return False
        if label is None:
            return False
        evidence = value.get('document', {}).get('content') if canonical == 'docs.get_document' else {
            key: value[key] for key in PROVIDER_CLINICAL_FIELDS if key in value}
        quote = quote.rstrip('.!?')
        return any(_provider_location_statement(candidate, quote, label, args) for candidate in _provider_texts(evidence))

    def _provider_payload(self, guard, record):
        text = guard.full_results.get(record['id'], record['result'])
        try:
            value = json.JSONDecoder().raw_decode(text.lstrip())[0]
        except (TypeError, ValueError, AttributeError):
            return None
        return value if type(value) is dict else None

    def provider_gate(self, tool, args):
        if not self._provider_enabled:
            return None
        if tool == 'cases.create_from_order':
            return None if self._provider_location_matches(args) else 'provider_location_evidence_required'
        case_id = args.get('case_id')
        data = self.data['provider_pre_submission']
        case = data['cases'].get(case_id)
        if case is None:
            return None
        if tool == 'auth.respond_to_pend' and not (case.get('submit') and case.get('readback') and case['readback']['status'] == 'pended_action_required'):
            return 'provider_submission_before_pend_required'
        if self.binding.bound != case['patient_id'] or self.binding.cases.get(case_id) != case['patient_id']:
            return 'provider_case_unverified'
        if case.get('submit_attempted') and case.get('submit') is None and effect_for(tool, 'mcp') == 'mutation':
            return 'provider_submission_outcome_unverified'
        review = data['reviews'].get(case_id)
        fresh = review is not None and self._provider_current(review['policy']) and self._provider_current(review['clinical'])
        if tool in {'auth.finalize_provider_determination', 'docs.create_submission_bundle', 'auth.submit_authorization'} and case.get('submit_attempted'):
            return 'provider_submission_already_recorded'
        if tool == 'auth.finalize_provider_determination':
            return None if fresh and args.get('final_action') == review['action'] else 'provider_review_required_or_stale'
        if tool in {'docs.create_submission_bundle', 'auth.submit_authorization'}:
            decision = case.get('decision')
            if not fresh or not decision or decision['action'] != 'submit_pa' or decision['action'] != review['action']:
                return 'provider_submit_decision_required_or_stale'
            if tool == 'auth.submit_authorization':
                bundle = case.get('bundle')
                if not bundle or bundle['ready'] is not True or args.get('bundle_document_id') != bundle['id']:
                    return 'provider_ready_bundle_required'
        return None

    def _provider_observe(self, call_id, tool, args, result, event, provider_result=None):
        if not self._provider_enabled or event != 'returned' or type(args) is not dict or type(result) is not str:
            return
        data = self.data['provider_pre_submission']; pid = self.binding.bound
        existing = data['cases'].get(args.get('case_id'))
        if existing is not None and tool == 'auth.submit_authorization':
            existing['submit_attempted'] = True
        if existing is not None and tool == 'docs.create_submission_bundle':
            existing['bundle_written'] = True
            existing['bundle'] = None
        if existing is not None and effect_for(tool, 'mcp') == 'mutation':
            existing['readback'] = None
        if type(provider_result) is dict:
            value = provider_result
        else:
            try:
                value = json.loads(result)
            except ValueError:
                value = None
        if type(value) is not dict:
            if tool == 'cases.create_from_order':
                self.binding.poisoned = True
                raise GoFailure('provider_create_result_unverified')
            if existing is not None and tool in {'auth.finalize_provider_determination', 'docs.create_submission_bundle', 'auth.submit_authorization'}:
                self._register_unknown(self.data['observations'][-1])
            return
        if effect_for(tool, 'mcp') == 'mutation':
            for key in ('document', 'bundle_document'):
                doc = value.get(key)
                if type(doc) is dict and type(doc.get('id')) is str and doc['id'] not in data['generated_documents']:
                    data['generated_documents'].append(doc['id'])
        if tool == 'cases.create_from_order':
            case, patient, order = value.get('case'), value.get('patient'), value.get('service_request')
            if (type(case) is dict and type(patient) is dict and type(order) is dict and
                    type(case.get('id')) is str and case.get('patient_id') == pid == patient.get('id') == order.get('patient_id')
                    and args.get('patient_id') == pid and case.get('service_request_id') == order.get('id')
                    and (not args.get('source_order_id') or args['source_order_id'] == order.get('id'))
                    and self.binding.cases.get(case['id']) == pid):
                data['cases'][case['id']] = {'patient_id': pid, 'create_call_id': call_id,
                    'decision': None, 'bundle': None, 'submit': None, 'submit_attempted': False, 'readback': None, 'bundle_written': False}
            else:
                self.binding.poisoned = True
                raise GoFailure('provider_create_result_unverified')
            return
        case_id = args.get('case_id'); item = data['cases'].get(case_id)
        if item is None or self.binding.cases.get(case_id) != item['patient_id']:
            return
        case = value.get('case')
        if tool == 'auth.finalize_provider_determination':
            action = args.get('final_action'); expected = PROVIDER_ACTION_STATUS
            review = data['reviews'].get(case_id)
            item['decision'] = None; item['readback'] = None; item['bundle'] = None
            if (type(case) is dict and case.get('id') == case_id and case.get('patient_id') == pid
                    and action in expected and case.get('status') == expected[action] and review and review['action'] == action
                    and self._provider_current(review['policy']) and self._provider_current(review['clinical'])):
                item['decision'] = {'action': action, 'status': case['status'], 'call_id': call_id}
            else:
                self._register_unknown(self.data['observations'][-1])
        elif tool == 'docs.create_submission_bundle':
            item['bundle_written'] = True
            item['bundle'] = None
            bundle, readiness = value.get('bundle_document'), value.get('readiness')
            if (type(bundle) is dict and type(bundle.get('id')) is str and bundle.get('case_id') == case_id
                    and bundle.get('patient_id') == pid and bundle.get('kind') == 'submission_bundle'
                    and type(readiness) is dict and type(readiness.get('ready_to_submit')) is bool
                    and type(readiness.get('missing_items')) is list and type(readiness.get('warnings')) is list
                    and (not readiness['ready_to_submit'] or not readiness['missing_items'])):
                item['bundle'] = {'id': bundle['id'], 'ready': readiness['ready_to_submit'], 'call_id': call_id}
            else:
                self._register_unknown(self.data['observations'][-1])
        elif tool == 'auth.submit_authorization':
            item['submit'] = None; item['readback'] = None
            if (type(case) is dict and case.get('id') == case_id and case.get('patient_id') == pid
                    and case.get('status') in PROVIDER_SUBMITTED_STATUSES and item.get('bundle')
                    and args.get('bundle_document_id') == item['bundle']['id']):
                item['submit'] = {'call_id': call_id, 'bundle_id': item['bundle']['id'], 'status': case['status']}
            else:
                self._register_unknown(self.data['observations'][-1])
        elif tool == 'cases.get_case':
            item['readback'] = None
            packets = value.get('submission_packets')
            if (type(case) is dict and case.get('id') == case_id and case.get('patient_id') == pid
                    and type(case.get('status')) is str and type(packets) is list):
                decision = item.get('decision'); action = decision.get('action') if decision else None
                submit = item.get('submit')
                if action in {'gather_more_evidence','do_not_submit'}:
                    good = (not packets and not item['bundle_written'] and submit is None and
                            case['status'] == {'gather_more_evidence':'docs_needed','do_not_submit':'closed'}[action])
                elif action == 'submit_pa' and submit:
                    good = (case['status'] in PROVIDER_SUBMITTED_STATUSES and
                            any(type(p) is dict and p.get('case_id') == case_id and p.get('status') in {'submitted', 'resubmitted'} and
                                type(p.get('payload')) is dict and p['payload'].get('bundle_document_id') == submit['bundle_id'] for p in packets))
                else:
                    good = False
                if good:
                    item['readback'] = {'call_id':call_id, 'status':case['status']}

    # -- program observations -------------------------------------------
    def scope_for_arguments(self, arguments) -> str:
        if type(arguments) is dict and type(arguments.get("case_id")) is str:
            value = arguments["case_id"]
            if CASE_ID.fullmatch(value):
                return "case:" + value
        return "unattributed"

    def observe(self, *, call_id: str, tool: str, kind: str, arguments=None, result=None,
                event: str = "returned", round_number: int = 0, scope: str | None = None, provider_result=None) -> dict:
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
        self._provider_observe(call_id, tool, arguments, result, event, provider_result)
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
            if "provider_location" in payload:
                self._provider_apply_location(payload["provider_location"])
            if "provider_review" in payload:
                self._provider_apply_review(payload["provider_review"])
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

    def _provider_last_readback(self, mutation):
        if not self._provider_enabled or mutation is None:
            return None
        scope = mutation.get('scope')
        for case_id, case in self.data['provider_pre_submission']['cases'].items():
            if not (scope == 'case:' + case_id or mutation['call_id'] == case['create_call_id']):
                continue
            readback = case.get('readback')
            if not readback:
                continue
            source = next((o for o in self.data['observations'] if o['call_id'] == readback['call_id']), None)
            if source and source['event'] == 'returned' and source['seq'] > mutation['seq']:
                return case, source
        return None

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
        if self._provider_enabled:
            data = self.data['provider_pre_submission']
            for case_id, case in data['cases'].items():
                review = data['reviews'].get(case_id)
                if (review is None or not self._provider_current(review['policy'])
                        or not self._provider_current(review['clinical'])):
                    return False, 'completion_provider_review_required_or_stale', 'blocked', 'not_verified', 'terminal_object'
                if not case['decision'] or case['decision']['action'] != review['action']:
                    return False, 'completion_provider_decision_unverified', 'blocked', 'not_verified', 'terminal_object'
                if not case['readback']:
                    return False, 'completion_provider_branch_readback_required', 'blocked', 'not_verified', 'business_status'
        if self._context_v3:
            from .completion import evaluate
            allowed, reason, _details = evaluate(self.data)
            if not allowed:
                return False, reason, "blocked", "not_verified", "terminal_object"
            failed = self._failed_business_mutations()
            if failed:
                return (False, "completion_business_write_failed:" + failed[-1]["call_id"],
                        "blocked", "not_verified", "business_status")
        status = self.data["latest_business_status"]
        business = self._business_mutations()
        provider_readback = self._provider_last_readback(business[-1]) if business else None
        if business and provider_readback is None:
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
        if provider_readback is not None:
            return True, None, "mechanical_pass", "observed", None
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
        provider_readback = self._provider_last_readback(last_business)
        if provider_readback is not None:
            case, source = provider_readback
            status_view = {'text': case['readback']['status'], 'source_call_id': source['call_id'],
                           'source_seq': source['seq'], 'source_tool': source['tool'],
                           'source_kind': source['source_kind'], 'source_scope': source['scope'],
                           'source_event': source['event']}
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
            from .completion import evaluate
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
        business = self._business_mutations()
        readback = self._provider_last_readback(business[-1]) if business else None
        self.data["claim"] = {
            "version": self.data["version"],
            "target": dict(self.data["target"]),
            "verified_status_call_id": readback[1]["call_id"] if readback else status["source_call_id"] if status else None,
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
        from .role_guidance import guidance
        summary = self.summary()
        stage_id = self._current_stage()
        if self._provider_enabled:
            pre = self.data['provider_pre_submission']
            selected_id = self.data['target']['case_id']
            if selected_id is None and len(pre['cases']) == 1:
                selected_id = next(iter(pre['cases']))
            case = pre['cases'].get(selected_id)
            review = pre['reviews'].get(selected_id)
            if case is not None and (review is None or case['decision'] is None):
                stage_id = 'verify_evidence'
            elif case is not None and (case['decision']['action'] != 'submit_pa' or case['submit']):
                stage_id = 'verify_and_close'
            elif case is not None and case.get('bundle') and case['bundle']['ready']:
                stage_id = 'submit_or_defer'
            elif case is not None:
                stage_id = 'prepare_packet'
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
        if self._provider_enabled:
            data = self.data['provider_pre_submission']
            selected_id = self.data['target']['case_id']
            if selected_id is None and len(data['cases']) == 1:
                selected_id = next(iter(data['cases']))
            case = data['cases'].get(selected_id)
            if case is None and self.binding.bound is not None and not data['cases']:
                payload['goal'] = 'Find explicit evidence of where the requested service is performed, then record provider_location.'
                payload['acceptance'] = ['Quote the actual service location from a delivered patient order or explicit public task evidence.']
            if case is not None:
                review = data['reviews'].get(selected_id)
                if review is None:
                    payload['goal'] = 'Review public policy and scoped clinical evidence before deciding whether to submit.'
                    payload['acceptance'] = ['Record exact public policy and patient evidence quotes, action, and reasons including any missing or contrary support.']
                elif not case['decision']:
                    payload['goal'] = 'Record the provider determination before creating a submission bundle.'
                    payload['acceptance'] = ['Record the same action with auth.finalize_provider_determination.']
                elif case['decision']['action'] != 'submit_pa':
                    payload['acceptance'] = ['Read the same case and verify its status and empty submission_packets.']
                payload['forbidden'].append('do not create a bundle or submit without the verified submit decision')
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
        if self._provider_enabled:
            result["provider_pre_submission"] = data["provider_pre_submission"]
        if self._requirements_enabled:
            result["requirements"] = list(data["requirements"])
            result["requirements_declared"] = bool(data["requirements_declared"])
        return result
