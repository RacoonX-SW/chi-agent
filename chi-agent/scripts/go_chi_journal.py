"""Persistent USD journal primitive for Go CHI; not a live execution entry.

An integration must hold an independently audited local Go development journal
lock for the entire session when operating in that development environment.
This module does not itself establish that external prerequisite.
"""
from __future__ import annotations

import fcntl
import copy
import hashlib
import json
import os
import re
from decimal import Decimal
from pathlib import Path

from opencode_go_provider import GoFailure, _atomic, _billing, _object
from b_provider_transport import _reject_symlink_ancestors
from go_chi_evidence import (envelope, write as write_evidence, verify as verify_evidence,
                             write_tool, verify_tool)
from evaluation_bundle import _read_regular_bounded, _write_exclusive, _fsync_dir

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
MAX_STATE_BYTES = 32 * 1024 * 1024


def _state_object(path: Path) -> dict:
    from opencode_go_provider import _unique
    try:
        raw = _read_regular_bounded(path, MAX_STATE_BYTES, "chi_history_invalid")
        value = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError
        return value
    except Exception:
        raise GoFailure("chi_history_invalid") from None


def _run_digest(run: dict) -> str:
    return hashlib.sha256(json.dumps(run, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _receipt(run: dict, identity: str) -> dict:
    return {"schema": "chi-go-b-success-v1", "identity": identity, "run": run["run"],
            "evaluation": run["evaluation"], "task": run["task"], "attempt": run["attempt"],
            "run_sha256": _run_digest(run)}


def _seal(run: dict, identity: str) -> dict:
    return {"schema": "chi-go-run-seal-v1", "identity": identity,
            "run": run["run"], "run_sha256": _run_digest(run)}


def publish_b_receipt(root: Path, identity: str, run: dict) -> None:
    """Publish only after the SDK client and both journal locks have closed."""
    if run.get("kind") != "coding_b" or run.get("status") != "complete":
        raise GoFailure("chi_b_receipt_invalid")
    directory = Path(root) / "b-receipts"
    _reject_symlink_ancestors(directory, "chi_path_invalid")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    _reject_symlink_ancestors(directory, "chi_path_invalid")
    _atomic(directory / (run["run"] + ".json"), _receipt(run, identity), exclusive=True)
    pending = Path(root) / "tool-inflight" / run["run"] / "__b_receipt__.pending"
    _reject_symlink_ancestors(pending.parent, "chi_path_invalid")
    if pending.is_symlink():
        raise GoFailure("chi_path_invalid")
    if pending.exists():
        pending.unlink()
        _fsync_dir(pending.parent)


def audit_or_rebind(root: Path, expected_identity: str, expected_sha256: str,
                    new_identity: str | None = None, reason: str | None = None) -> dict:
    """Audit under the CHI lock; caller must hold the already-audited Q lock."""
    root = Path(root)
    if (any(type(x) is not str or not DIGEST.fullmatch(x) for x in (expected_identity, expected_sha256))
            or (new_identity is not None and (type(new_identity) is not str or not DIGEST.fullmatch(new_identity)
                or new_identity == expected_identity or type(reason) is not str or not reason.strip() or len(reason) > 256))):
        raise GoFailure("chi_migration_invalid")
    _reject_symlink_ancestors(root, "chi_path_invalid")
    if not root.is_dir(): raise GoFailure("chi_history_missing")
    lock = os.open(root / ".lock", os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = root / "chi-accounting.json"
        raw = _read_regular_bounded(path, MAX_STATE_BYTES, "chi_history_invalid")
        if hashlib.sha256(raw).hexdigest() != expected_sha256: raise GoFailure("chi_migration_hash_mismatch")
        auditor = object.__new__(ChiJournal)
        auditor.root, auditor.path, auditor.state = root, path, _state_object(path)
        auditor._validate(expected_identity)
        state = auditor.state
        if (state["pending"] is not None or state["halted"] is not None
                or any(a["status"] not in {"complete", "failed"} for a in state["attempts"])):
            raise GoFailure("chi_migration_history_unsettled")
        if new_identity is None:
            return {"status": "audited", "identity": expected_identity, "accounting_sha256": expected_sha256,
                    "attempts": len(state["attempts"])}
        marker = root / "migration.pending"
        _write_exclusive(marker, b"migration in progress\n")
        _fsync_dir(root)
        archives = root / "source-archives"
        archives.mkdir(mode=0o700, exist_ok=True)
        _reject_symlink_ancestors(archives, "chi_path_invalid")
        transitions = state.get("source_transitions", [])
        archive = archives / f"{len(transitions) + 1:04d}-{expected_sha256}.json"
        _write_exclusive(archive, raw)
        _fsync_dir(archives)
        updated = copy.deepcopy(state)
        updated["identity"] = new_identity
        updated["source_transitions"] = transitions + [{"old_identity": expected_identity,
            "new_identity": new_identity, "accounting_sha256": expected_sha256, "reason": reason.strip()}]
        _atomic(path, updated)
        marker.unlink()
        _fsync_dir(root)
        return {"status": "rebound", "old_identity": expected_identity, "new_identity": new_identity,
                "archived_sha256": expected_sha256, "attempts": len(state["attempts"])}
    finally:
        os.close(lock)


def inspect_history(root: Path, expected_identity: str, expected_sha256: str) -> dict:
    """Read-only audit under CHI lock; caller holds the independently audited Q lock."""
    root = Path(root)
    if any(type(x) is not str or not DIGEST.fullmatch(x) for x in (expected_identity, expected_sha256)):
        raise GoFailure('chi_inspect_invalid')
    _reject_symlink_ancestors(root, 'chi_path_invalid')
    lock = os.open(root / '.lock', os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = root / 'chi-accounting.json'
        raw = _read_regular_bounded(path, MAX_STATE_BYTES, 'chi_history_invalid')
        if hashlib.sha256(raw).hexdigest() != expected_sha256: raise GoFailure('chi_inspect_hash_mismatch')
        auditor = object.__new__(ChiJournal)
        auditor.root, auditor.path, auditor.state = root, path, _state_object(path)
        auditor._validate(expected_identity)
        state = auditor.state
        pending = state['pending']
        result = {'status': 'inspected', 'execution_allowed': False, 'identity': expected_identity,
                  'accounting_sha256': expected_sha256, 'pending': pending, 'halted': state['halted'],
                  'usage': auditor.usage_totals(), 'missing': []}
        for attempt in state['attempts']:
            for item in attempt['requests']:
                if item['status'] == 'settled':
                    for field in ('charged_usd', 'billing_source', 'list_cost_usd', 'allowance_usd'):
                        if item['billing'][field] is None and field not in result['missing']:
                            result['missing'].append(field)
        if pending is not None:
            attempt = next(a for a in state['attempts'] if a['run'] == pending['run'])
            request = attempt['requests'][pending['round'] - 1]
            doc = verify_evidence(root, pending['run'], pending['round'], 'request', request['request_evidence_sha256'])
            result['pending_request'] = {'purpose': request['purpose'], 'request_sha256': request['request_sha256'],
                                         'dispatch': doc.get('dispatch'), 'run_status': attempt['status'], 'kind': attempt['kind'],
                                         'body_bytes': len(doc['body_utf8'].encode('utf-8')) if doc.get('body_utf8') is not None else None}
            if doc.get('dispatch') is None: result['missing'].append('dispatch_metadata')
            if doc.get('body_utf8') is None: result['missing'].append('request_body_bytes')
            if request['response_evidence_sha256'] is None: result['missing'].append('provider_response')
            for field in ('charged_usd', 'billing_source', 'list_cost_usd', 'allowance_usd'):
                if field not in result['missing']: result['missing'].append(field)
        return result
    finally:
        os.close(lock)


class ChiJournal:
    """Exclusive one-identity namespace with immutable attempt claims.

    Each request is reserved durably before dispatch. Missing or unknown usage
    blocks every later attempt in the namespace. Source changes require a new,
    separately reviewed migration; this class never silently rebinds identity.
    """
    def __init__(self, root: Path, *, identity: str, evaluation: str, task: str,
                 attempt: str, run: str, kind: str = "chi", require_b: bool = False,
                 launch: dict | None = None):
        if (type(identity) is not str or not DIGEST.fullmatch(identity)
                or kind not in {"chi", "coding_b"}
                or (launch is not None and type(launch) is not dict)
                or any(type(x) is not str or not ID.fullmatch(x)
                       for x in (evaluation, task, attempt, run))):
            raise GoFailure("chi_identity_invalid")
        self.root = Path(root)
        self.run_id = run
        self.lock = None
        try:
            _reject_symlink_ancestors(self.root, "chi_path_invalid")
            self.root.mkdir(parents=True, exist_ok=True)
            _reject_symlink_ancestors(self.root, "chi_path_invalid")
            self.lock = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.path = self.root / "chi-accounting.json"
            if not self.path.exists():
                if any(p.name != ".lock" for p in self.root.iterdir()):
                    raise GoFailure("chi_history_missing")
                _atomic(self.path, {"schema": "chi-go-evaluation-usd-v1", "identity": identity,
                                    "account_prior_history": "unknown", "attempts": [], "pending": None,
                                    "halted": None}, exclusive=True)
            self.state = _state_object(self.path)
            self._validate(identity)
            if self.state["pending"] is not None:
                raise GoFailure("chi_usage_unknown")
            if self.state["halted"] is not None:
                raise GoFailure("chi_billing_halted")
            if require_b:
                def valid_b(item):
                    if not (item["kind"] == "coding_b" and item["status"] == "complete"
                            and item["task"] == "synthetic-coding-b"
                            and item["launch"].get("kind") == "coding_b"
                            and len(item["requests"]) >= 3
                            and [(event.get("tool"), event.get("event")) for event in item["tool_events"]] ==
                                [("inspect_code", "started"), ("inspect_code", "returned"),
                                 ("verify_patch", "started"), ("verify_patch", "returned")]
                            and item["tool_events"][1].get("result_sha256") == hashlib.sha256(b"def add(a, b):\n    return a - b\n").hexdigest()
                            and item["tool_events"][3].get("result_sha256") == hashlib.sha256(b"verification:pass").hexdigest()):
                        return False
                    path = self.root / "b-receipts" / (item["run"] + ".json")
                    try:
                        _reject_symlink_ancestors(path.parent, "chi_path_invalid")
                        return _object(path) == _receipt(item, identity)
                    except Exception:
                        return False
                if kind != "chi" or not any(valid_b(item) for item in self.state["attempts"]):
                    raise GoFailure("chi_b_receipt_missing")
            if any(a["run"] == run or (a["evaluation"], a["task"], a["attempt"]) == (evaluation, task, attempt)
                   for a in self.state["attempts"]):
                raise GoFailure("chi_attempt_or_run_exists")
            self.run = {"evaluation": evaluation, "task": task, "attempt": attempt, "run": run,
                        "kind": kind, "status": "started", "requests": [], "patient_binding_events": [],
                        "claim_done": False, "tool_events": [], "safe_error_code": None,
                        "launch": launch or {}}
            self.run_doc = self.run
            self.state["attempts"].append(self.run)
            self._persist()
        except BaseException:
            self.close()
            raise

    def _validate(self, identity: str) -> None:
        try:
            s = self.state
            if (self.root / "migration.pending").exists() or (self.root / "migration.pending").is_symlink():
                raise ValueError
            transitions = s.get("source_transitions", [])
            if type(transitions) is not list: raise ValueError
            archive = self.root / "source-archives"
            if archive.is_symlink(): raise ValueError
            expected_archives, run_identities, previous, previous_attempts = set(), {}, None, []
            for index, transition in enumerate(transitions):
                if (type(transition) is not dict or set(transition) != {"old_identity", "new_identity", "accounting_sha256", "reason"}
                        or any(type(transition[k]) is not str or not DIGEST.fullmatch(transition[k])
                               for k in ("old_identity", "new_identity", "accounting_sha256"))
                        or transition["old_identity"] == transition["new_identity"]
                        or type(transition["reason"]) is not str or not transition["reason"].strip()
                        or len(transition["reason"]) > 256
                        or (previous is not None and previous != transition["old_identity"])):
                    raise ValueError
                name = f"{index + 1:04d}-{transition['accounting_sha256']}.json"
                path = archive / name
                raw = _read_regular_bounded(path, MAX_STATE_BYTES, "chi_history_invalid")
                if hashlib.sha256(raw).hexdigest() != transition["accounting_sha256"]: raise ValueError
                snapshot = _state_object(path)
                attempts = snapshot.get("attempts")
                if (snapshot.get("identity") != transition["old_identity"]
                        or snapshot.get("source_transitions", []) != transitions[:index]
                        or snapshot.get("pending") is not None or snapshot.get("halted") is not None
                        or type(attempts) is not list or attempts[:len(previous_attempts)] != previous_attempts
                        or s["attempts"][:len(attempts)] != attempts
                        or any(a.get("status") not in {"complete", "failed"} for a in attempts)):
                    raise ValueError
                for attempt in attempts[len(previous_attempts):]:
                    run_identities[attempt["run"]] = transition["old_identity"]
                previous_attempts, previous = attempts, transition["new_identity"]
                expected_archives.add(name)
            if transitions and previous != identity: raise ValueError
            if archive.exists() and {p.name for p in archive.iterdir()} != expected_archives: raise ValueError
            if expected_archives and not archive.is_dir(): raise ValueError
            inflight = self.root / "tool-inflight"
            if inflight.is_symlink(): raise ValueError
            if inflight.exists():
                pending_claim = s.get("pending")
                allowed_pending = None
                if (type(pending_claim) is dict and type(pending_claim.get("run")) is str
                        and type(pending_claim.get("round")) is int):
                    allowed_pending = (pending_claim["run"], f"__wire_{pending_claim['round']:03d}.pending")
                for directory in inflight.iterdir():
                    if directory.is_symlink() or not directory.is_dir(): raise ValueError
                    for path in directory.iterdir():
                        if (path.is_symlink() or not path.is_file()
                                or (directory.name, path.name) != allowed_pending): raise ValueError
            keys = {"schema", "identity", "account_prior_history", "attempts", "pending", "halted"}
            if (type(s) is not dict or set(s) not in (keys, keys | {"source_transitions"})
                    or s["schema"] != "chi-go-evaluation-usd-v1" or s["identity"] != identity
                    or s["account_prior_history"] != "unknown" or type(s["attempts"]) is not list
                    or s["halted"] not in (None, "billing_details_unknown", "billing_source_unexpected")):
                raise ValueError
            identities, runs, halt = set(), set(), None
            pending = None
            expected_evidence = set()
            expected_tool_evidence = set()
            expected_seals = set()
            expected_receipts = set()
            for a in s["attempts"]:
                if (type(a) is not dict or set(a) != {"evaluation", "task", "attempt", "run", "kind", "status", "requests", "patient_binding_events", "claim_done", "tool_events", "safe_error_code", "launch"}
                        or any(type(a[k]) is not str or not ID.fullmatch(a[k]) for k in ("evaluation", "task", "attempt", "run"))
                        or a["kind"] not in {"chi", "coding_b"}
                        or type(a["patient_binding_events"]) is not list
                        or type(a["claim_done"]) is not bool
                        or type(a["launch"]) is not dict
                        or type(a["tool_events"]) is not list
                        or any(type(event) is not dict for event in a["tool_events"])
                        or (a["safe_error_code"] is not None and (type(a["safe_error_code"]) is not str
                            or not re.fullmatch(r"[a-z0-9_]{1,64}", a["safe_error_code"])))
                        or any(type(event) is not dict or type(event.get("event")) is not str for event in a["patient_binding_events"])
                        or a["status"] not in {"started", "complete", "failed"} or type(a["requests"]) is not list
                        or len(a["requests"]) > (6 if a["kind"] == "coding_b" else 50)):
                    raise ValueError
                if a["safe_error_code"] in {"chi_evidence_persistence_failed", "chi_persistence_failed",
                                             "chi_log_persistence_failed", "chi_b_receipt_persistence_failed",
                                             "chi_cleanup_failed"}:
                    raise ValueError
                key = (a["evaluation"], a["task"], a["attempt"])
                if key in identities or a["run"] in runs:
                    raise ValueError
                identities.add(key); runs.add(a["run"])
                if a["status"] in {"complete", "failed"}:
                    seal_path = self.root / "run-seals" / (a["run"] + ".json")
                    _reject_symlink_ancestors(seal_path.parent, "chi_path_invalid")
                    run_identity = run_identities.get(a["run"], identity)
                    if _object(seal_path) != _seal(a, run_identity): raise ValueError
                    expected_seals.add(seal_path.name)
                    if a["kind"] == "coding_b" and a["status"] == "complete":
                        receipt = self.root / "b-receipts" / (a["run"] + ".json")
                        _reject_symlink_ancestors(receipt.parent, "chi_path_invalid")
                        if _object(receipt) != _receipt(a, run_identity): raise ValueError
                        expected_receipts.add(receipt.name)
                started, finished = {}, set()
                for event in a["tool_events"]:
                    if (type(event.get("call_id")) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", event["call_id"])
                            or type(event.get("tool")) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", event["tool"])):
                        raise ValueError
                    call_id = event["call_id"]
                    if event.get("event") == "started":
                        if (set(event) != {"call_id", "tool", "event", "arguments_sha256"} or call_id in started
                                or type(event.get("arguments_sha256")) is not str or not DIGEST.fullmatch(event["arguments_sha256"])):
                            raise ValueError
                        started[call_id] = event["tool"]
                    elif event.get("event") == "refused" and call_id not in started:
                        if (set(event) != {"call_id", "tool", "event", "arguments_sha256", "result_sha256", "result_evidence_sha256"}
                                or call_id in finished
                                or any(type(event.get(key)) is not str or not DIGEST.fullmatch(event[key])
                                       for key in ("arguments_sha256", "result_sha256", "result_evidence_sha256"))):
                            raise ValueError
                        started[call_id] = event["tool"]
                        finished.add(call_id)
                    elif event.get("event") in {"returned", "returned_error", "refused", "failed"}:
                        keys = {"call_id", "tool", "event", "result_sha256", "result_evidence_sha256"}
                        if event["event"] == "failed": keys.add("safe_error_code")
                        if (set(event) != keys or call_id not in started
                                or call_id in finished or event["tool"] != started[call_id]
                                or any(type(event.get(key)) is not str or not DIGEST.fullmatch(event[key])
                                       for key in ("result_sha256", "result_evidence_sha256"))
                                or (event["event"] == "failed" and
                                    (type(event.get("safe_error_code")) is not str or
                                     not re.fullmatch(r"[a-z0-9_]{1,64}", event["safe_error_code"])) )):
                            raise ValueError
                        finished.add(call_id)
                    else:
                        raise ValueError
                    if event.get("event") != "started":
                        evidence = verify_tool(self.root, a["run"], call_id, event["result_evidence_sha256"])
                        if evidence.get("raw_sha256") != event["result_sha256"]: raise ValueError
                        if evidence.get("body_utf8") is not None and hashlib.sha256(evidence["body_utf8"].encode()).hexdigest() != event["result_sha256"]:
                            raise ValueError
                        expected_tool_evidence.add((a["run"], call_id + ".json"))
                if set(started) != finished:
                    raise ValueError
                confirms = 0
                for index, item in enumerate(a["requests"], 1):
                    if (type(item) is not dict or item.get("round") != index
                            or item.get("purpose") not in {"main", "confirmation"}
                            or (a["kind"] == "coding_b" and item.get("purpose") != "main")
                            or item.get("max_tokens") != (1024 if a["kind"] == "coding_b" else 8192 if item.get("purpose") == "main" else 32768)
                            or type(item.get("request_sha256")) is not str or not DIGEST.fullmatch(item["request_sha256"])):
                        raise ValueError
                    required = {"round", "purpose", "max_tokens", "request_sha256", "status",
                                "request_evidence_sha256", "response_evidence_sha256", "diagnostic_evidence_sha256"}
                    if 'dispatch_version' in item:
                        required.add('dispatch_version')
                        if item['dispatch_version'] != 'chi-go-dispatch-v1': raise ValueError
                    if item.get("status") == "settled":
                        required |= {"usage", "billing", "billing_error"}
                    if set(item) != required:
                        raise ValueError
                    request_ref = item["request_evidence_sha256"]
                    if type(request_ref) is not str or not DIGEST.fullmatch(request_ref): raise ValueError
                    req = verify_evidence(self.root, a["run"], index, "request", request_ref)
                    if (req.get("schema") != "chi-go-wire-evidence-v1" or req.get("kind") != "request"
                            or req.get("raw_sha256") != item["request_sha256"]): raise ValueError
                    if req.get("body_utf8") is not None and hashlib.sha256(req["body_utf8"].encode()).hexdigest() != req["raw_sha256"]:
                        raise ValueError
                    if ('dispatch' in req) != ('dispatch_version' in item): raise ValueError
                    if 'dispatch' in req:
                        dispatch = req['dispatch']
                        if (type(dispatch) is not dict or set(dispatch) != {'version', 'purpose', 'session_sha256', 'started_utc_ms', 'body_bytes'}
                                or dispatch['version'] != 'chi-go-dispatch-v1' or dispatch['purpose'] != item['purpose']
                                or type(dispatch['session_sha256']) is not str or not DIGEST.fullmatch(dispatch['session_sha256'])
                                or type(dispatch['started_utc_ms']) is not int or dispatch['started_utc_ms'] <= 0
                                or type(dispatch['body_bytes']) is not int or not 0 < dispatch['body_bytes'] <= 8 * 1024 * 1024
                                or (req.get('body_utf8') is not None and dispatch['body_bytes'] != len(req['body_utf8'].encode()))):
                            raise ValueError
                    expected_evidence.add((a["run"], f"{index:03d}-request.json"))
                    for kind in ("response", "diagnostic"):
                        ref = item[kind + "_evidence_sha256"]
                        if ref is not None:
                            if type(ref) is not str or not DIGEST.fullmatch(ref): raise ValueError
                            evidence = verify_evidence(self.root, a["run"], index, kind, ref)
                            if evidence.get("kind") != kind: raise ValueError
                            if kind == "response":
                                if (evidence.get("schema") != "chi-go-wire-evidence-v1"
                                        or type(evidence.get("raw_sha256")) is not str or not DIGEST.fullmatch(evidence["raw_sha256"])
                                        or type(evidence.get("http_status")) is not int or not 100 <= evidence["http_status"] <= 599
                                        or type(evidence.get("elapsed_ms")) is not int or evidence["elapsed_ms"] < 0): raise ValueError
                                if evidence.get("body_utf8") is not None and hashlib.sha256(evidence["body_utf8"].encode()).hexdigest() != evidence["raw_sha256"]:
                                    raise ValueError
                                if item["status"] == "settled":
                                    usage = evidence.get("usage")
                                    if (type(usage) is not dict or usage.get("prompt_tokens") != item["usage"]["input_tokens"]
                                            or usage.get("completion_tokens") != item["usage"]["output_tokens"]): raise ValueError
                                    from b_provider_transport import GuardedTransport
                                    GuardedTransport._usage({"usage": usage})
                                    billed, billing_error = _billing(usage)
                                    if billed != item["billing"] or billing_error != item["billing_error"]:
                                        raise ValueError
                            elif (evidence.get("schema") != "chi-go-diagnostic-v1"
                                  or type(evidence.get("code")) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", evidence["code"])
                                  or type(evidence.get("elapsed_ms")) is not int or evidence["elapsed_ms"] < 0):
                                raise ValueError
                            expected_evidence.add((a["run"], f"{index:03d}-{kind}.json"))
                    if item["status"] == "settled" and (item["response_evidence_sha256"] is None
                                                         or item["diagnostic_evidence_sha256"] is None):
                        raise ValueError
                    confirms += item["purpose"] == "confirmation"
                    if confirms > 2 or halt is not None or pending is not None:
                        raise ValueError
                    if item.get("status") in {"pending", "unknown"}:
                        pending = {"run": a["run"], "round": index}
                    elif item.get("status") == "settled":
                        if (type(item["usage"]) is not dict or set(item["usage"]) != {"input_tokens", "output_tokens"}
                                or any(type(v) is not int or v < 0 for v in item["usage"].values())
                                or type(item["billing"]) is not dict):
                            raise ValueError
                        billed = item["billing"]
                        if set(billed) != {"charged_usd", "list_cost_usd", "allowance_usd", "billing_source"}:
                            raise ValueError
                        for name in ("charged_usd", "list_cost_usd", "allowance_usd"):
                            if billed[name] is not None and (type(billed[name]) is not str or not Decimal(billed[name]).is_finite() or Decimal(billed[name]) < 0):
                                raise ValueError
                        inferred = ("billing_details_unknown" if billed["billing_source"] is None else
                                    "billing_source_unexpected" if billed["billing_source"] not in {"go", "go-plus"}
                                    or (billed["charged_usd"] is not None and Decimal(billed["charged_usd"]) != 0) else
                                    "billing_details_unknown" if any(billed[k] is None for k in ("charged_usd", "list_cost_usd", "allowance_usd")) else None)
                        if inferred != item["billing_error"]:
                            raise ValueError
                        halt = inferred
                    else:
                        raise ValueError
            if pending != s["pending"] or halt != s["halted"]:
                raise ValueError
            evidence_root = self.root / "wire-evidence"
            if evidence_root.is_symlink(): raise ValueError
            actual_evidence = set()
            if evidence_root.exists():
                for directory in evidence_root.iterdir():
                    if directory.is_symlink() or not directory.is_dir() or not ID.fullmatch(directory.name): raise ValueError
                    for path in directory.iterdir():
                        if path.is_symlink() or not path.is_file(): raise ValueError
                        actual_evidence.add((directory.name, path.name))
                    if not any(run == directory.name for run, _ in expected_evidence): raise ValueError
            if actual_evidence != expected_evidence: raise ValueError
            tool_root = self.root / "tool-evidence"
            if tool_root.is_symlink(): raise ValueError
            actual_tool_evidence = set()
            if tool_root.exists():
                for directory in tool_root.iterdir():
                    if directory.is_symlink() or not directory.is_dir() or not ID.fullmatch(directory.name): raise ValueError
                    for path in directory.iterdir():
                        if path.is_symlink() or not path.is_file(): raise ValueError
                        actual_tool_evidence.add((directory.name, path.name))
                    if not any(run == directory.name for run, _ in expected_tool_evidence): raise ValueError
            if actual_tool_evidence != expected_tool_evidence: raise ValueError
            seal_root = self.root / "run-seals"
            if seal_root.is_symlink(): raise ValueError
            actual_seals = set()
            if seal_root.exists():
                for path in seal_root.iterdir():
                    if path.is_symlink() or not path.is_file(): raise ValueError
                    actual_seals.add(path.name)
            if actual_seals != expected_seals: raise ValueError
            receipts = self.root / "b-receipts"
            if receipts.is_symlink(): raise ValueError
            if receipts.exists() and ({p.name for p in receipts.iterdir()} != expected_receipts
                                      or any(p.is_symlink() or not p.is_file() for p in receipts.iterdir())): raise ValueError
            if expected_receipts and not receipts.is_dir(): raise ValueError
        except Exception:
            raise GoFailure("chi_history_invalid") from None

    def _persist(self):
        if len((json.dumps(self.state, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()) > MAX_STATE_BYTES:
            raise GoFailure("chi_state_limit")
        _atomic(self.path, self.state)

    def record_claim(self) -> None:
        self.run["claim_done"] = True
        self._persist()

    def start_tool(self, call_id: str, name: str, arguments: dict) -> None:
        if (type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name)
                or type(arguments) is not dict
                or any(event.get("call_id") == call_id for event in self.run["tool_events"])):
            raise GoFailure("chi_tool_event_invalid")
        encoded = json.dumps(arguments, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self._mark_tool_inflight(call_id)
        self.run["tool_events"].append({"call_id": call_id, "tool": name, "event": "started",
                                        "arguments_sha256": hashlib.sha256(encoded).hexdigest()})
        try: self._persist()
        except Exception: raise GoFailure("chi_evidence_persistence_failed") from None

    def record_tool(self, call_id: str, name: str, result: str, *, event: str = "returned",
                    secrets: tuple[str, ...] = ()) -> None:
        matches = [item for item in self.run["tool_events"] if item.get("call_id") == call_id]
        if (len(matches) != 1 or matches[0].get("event") != "started" or matches[0].get("tool") != name
                or event not in {"returned", "returned_error", "refused", "failed"} or type(result) is not str):
            raise GoFailure("chi_tool_event_invalid")
        reference = write_tool(self.root, self.run_id, call_id, result, secrets)
        item = {"call_id": call_id, "tool": name, "event": event,
                "result_sha256": hashlib.sha256(result.encode()).hexdigest(), "result_evidence_sha256": reference}
        if event == "failed":
            item["safe_error_code"] = result if re.fullmatch(r"[a-z0-9_]{1,64}", result) else "chi_tool_execution_failed"
        self.run["tool_events"].append(item)
        try: self._persist()
        except Exception: raise GoFailure("chi_evidence_persistence_failed") from None
        self._clear_tool_inflight(call_id)

    def refuse_tool(self, call_id: str, name: str, arguments: dict, result: str, *,
                    secrets: tuple[str, ...] = ()) -> None:
        if (type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name)
                or type(arguments) is not dict or type(result) is not str
                or any(event.get("call_id") == call_id for event in self.run["tool_events"])):
            raise GoFailure("chi_tool_event_invalid")
        encoded = json.dumps(arguments, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self._mark_tool_inflight(call_id)
        reference = write_tool(self.root, self.run_id, call_id, result, secrets)
        self.run["tool_events"].append({"call_id": call_id, "tool": name, "event": "refused",
                                        "arguments_sha256": hashlib.sha256(encoded).hexdigest(),
                                        "result_sha256": hashlib.sha256(result.encode()).hexdigest(),
                                        "result_evidence_sha256": reference})
        try: self._persist()
        except Exception: raise GoFailure("chi_evidence_persistence_failed") from None
        self._clear_tool_inflight(call_id)

    def _mark_tool_inflight(self, call_id: str) -> None:
        if type(call_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call_id):
            raise GoFailure("chi_tool_event_invalid")
        directory = self.root / "tool-inflight" / self.run_id
        _reject_symlink_ancestors(directory, "chi_path_invalid")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _reject_symlink_ancestors(directory, "chi_path_invalid")
        try:
            _write_exclusive(directory / (call_id + ".pending"), b"tool execution pending\n")
            _fsync_dir(directory)
        except Exception:
            raise GoFailure("chi_evidence_persistence_failed") from None

    def _clear_tool_inflight(self, call_id: str) -> None:
        directory = self.root / "tool-inflight" / self.run_id
        try:
            (directory / (call_id + ".pending")).unlink()
            _fsync_dir(directory)
        except Exception:
            raise GoFailure("chi_evidence_persistence_failed") from None

    def reserve(self, raw: bytes, purpose: str, *, secrets: tuple[str, ...] = (), dispatch=None) -> None:
        if self.state["pending"] is not None or self.state["halted"] is not None:
            raise GoFailure("chi_usage_unknown")
        if purpose not in {"main", "confirmation"} or type(raw) is not bytes:
            raise GoFailure("chi_reservation_invalid")
        if self.run["kind"] == "coding_b" and purpose != "main":
            raise GoFailure("chi_reservation_invalid")
        if len(self.run["requests"]) >= (6 if self.run["kind"] == "coding_b" else 50):
            raise GoFailure("chi_request_limit")
        if purpose == "confirmation" and sum(x["purpose"] == "confirmation" for x in self.run["requests"]) >= 2:
            raise GoFailure("chi_confirmation_limit")
        if dispatch is not None and (type(dispatch) is not dict or set(dispatch) != {'version', 'purpose', 'session_sha256', 'started_utc_ms', 'body_bytes'}
                or dispatch['version'] != 'chi-go-dispatch-v1' or dispatch['purpose'] != purpose
                or type(dispatch['session_sha256']) is not str or not DIGEST.fullmatch(dispatch['session_sha256'])
                or type(dispatch['started_utc_ms']) is not int or dispatch['started_utc_ms'] <= 0
                or type(dispatch['body_bytes']) is not int or not 0 < dispatch['body_bytes'] <= 8 * 1024 * 1024
                or dispatch['body_bytes'] != len(raw)):
            raise GoFailure('chi_reservation_invalid')
        self._mark_tool_inflight(f"__wire_{len(self.run['requests']) + 1:03d}")
        entry = {"round": len(self.run["requests"]) + 1, "purpose": purpose,
                 "max_tokens": 1024 if self.run["kind"] == "coding_b" else 8192 if purpose == "main" else 32768,
                 "request_sha256": hashlib.sha256(raw).hexdigest(), "status": "pending",
                 "request_evidence_sha256": None, "response_evidence_sha256": None,
                 "diagnostic_evidence_sha256": None}
        if dispatch is not None: entry['dispatch_version'] = 'chi-go-dispatch-v1'
        request_doc = envelope(raw, kind="request", secrets=secrets, dispatch=dispatch)
        entry["request_evidence_sha256"] = write_evidence(self.root, self.run_id, entry["round"], "request", request_doc)
        self.run["requests"].append(entry)
        self.state["pending"] = {"run": self.run["run"], "round": entry["round"]}
        self._persist()

    def record_response(self, raw: bytes, status: int, elapsed_ms: int, *, secrets: tuple[str, ...] = ()) -> None:
        entry = self.run["requests"][-1]
        if self.state["pending"] is None or entry["response_evidence_sha256"] is not None:
            raise GoFailure("chi_pending_invalid")
        doc = envelope(raw, kind="response", secrets=secrets, status=status, elapsed_ms=elapsed_ms)
        entry["response_evidence_sha256"] = write_evidence(self.root, self.run_id, entry["round"], "response", doc)
        self._persist()

    def record_diagnostic(self, code: str, elapsed_ms: int) -> None:
        if type(code) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", code):
            raise GoFailure("chi_diagnostic_invalid")
        entry = self.run["requests"][-1]
        if entry["diagnostic_evidence_sha256"] is not None:
            raise GoFailure("chi_diagnostic_invalid")
        doc = {"schema": "chi-go-diagnostic-v1", "kind": "diagnostic", "code": code, "elapsed_ms": elapsed_ms}
        entry["diagnostic_evidence_sha256"] = write_evidence(self.root, self.run_id, entry["round"], "diagnostic", doc)
        self._persist()
        self._clear_tool_inflight(f"__wire_{entry['round']:03d}")

    def settle(self, usage: dict) -> None:
        if self.state["pending"] is None:
            raise GoFailure("chi_pending_invalid")
        try:
            incoming, outgoing = usage["prompt_tokens"], usage["completion_tokens"]
            if any(type(x) is not int or x < 0 for x in (incoming, outgoing)):
                raise ValueError
            billed, halt = _billing(usage)
        except Exception:
            raise GoFailure("chi_usage_unknown") from None
        entry = self.run["requests"][-1]
        entry.update(status="settled", usage={"input_tokens": incoming, "output_tokens": outgoing},
                     billing=billed, billing_error=halt)
        self.state["halted"] = halt
        self.state["pending"] = None
        self._persist()
        if halt:
            raise GoFailure(halt)

    def finish(self, status: str, error: str | None = None) -> None:
        if status not in {"complete", "failed"} or self.run["status"] != "started":
            raise GoFailure("chi_status_invalid")
        if error is not None and (type(error) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", error)):
            raise GoFailure("chi_status_invalid")
        self._mark_tool_inflight("__run_finalize__")
        self.run["status"] = status
        self.run["safe_error_code"] = error
        self._persist()
        directory = self.root / "run-seals"
        _reject_symlink_ancestors(directory, "chi_path_invalid")
        directory.mkdir(mode=0o700, exist_ok=True)
        _reject_symlink_ancestors(directory, "chi_path_invalid")
        try:
            _atomic(directory / (self.run_id + ".json"), _seal(self.run, self.state["identity"]), exclusive=True)
        except Exception:
            raise GoFailure("chi_evidence_persistence_failed") from None
        self._clear_tool_inflight("__run_finalize__")

    def prepare_b_receipt(self) -> None:
        if self.run["kind"] != "coding_b" or self.run["status"] != "complete":
            raise GoFailure("chi_b_receipt_invalid")
        self._mark_tool_inflight("__b_receipt__")

    def usage_totals(self) -> dict:
        """Report three distinct USD measures; never combine allowance and cost."""
        names = ("charged_usd", "list_cost_usd", "allowance_usd")
        totals = {name: Decimal(0) for name in names}
        complete = {name: True for name in names}
        incoming = outgoing = 0
        for attempt in self.state["attempts"]:
            for request in attempt["requests"]:
                if request["status"] != "settled":
                    for name in names:
                        complete[name] = False
                    continue
                incoming += request["usage"]["input_tokens"]
                outgoing += request["usage"]["output_tokens"]
                for name in names:
                    value = request["billing"][name]
                    if value is None:
                        complete[name] = False
                    else:
                        totals[name] += Decimal(value)
        return {"input_tokens_known": incoming, "output_tokens_known": outgoing,
                "usd": {name: {"known": str(totals[name]), "complete": complete[name]} for name in names},
                "account_prior_history": "unknown"}

    def close(self) -> None:
        if self.lock is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            os.close(self.lock)
            self.lock = None
