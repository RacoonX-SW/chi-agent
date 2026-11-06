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
import math
import os
import re
from decimal import Decimal
from pathlib import Path

from opencode_go_provider import GoFailure, _atomic, _billing, _object, _unique, _contains_secret
from b_provider_transport import _reject_symlink_ancestors
from go_chi_diagnostics import (SCHEMA_V2, build_cause, validate_cause, validate_v1, validate_v2)
from go_chi_evidence import (envelope, write as write_evidence, verify as verify_evidence,
                             write_tool, verify_tool)
from evaluation_bundle import _read_regular_bounded, _write_exclusive, _fsync_dir
from go_chi_policy import FEE_POLICY, SUMMARY_VERSIONS, output_limit

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
MAX_STATE_BYTES = 32 * 1024 * 1024
RECOVERY_POLICY = "chi-output-recovery-v1"
SUMMARY_POLICY = "chi-input-summary-v1"
REQUIREMENTS_POLICY = "chi-requirements-v1"


def _requirements_enabled(launch: dict, kind: str) -> bool:
    if type(launch) is not dict or type(kind) is not str \
            or kind not in {"chi", "coding_b", "patient_probe"}:
        raise GoFailure("chi_identity_invalid")
    if "requirements" not in launch:
        return False
    if (kind != "chi" or type(launch["requirements"]) is not str
            or launch["requirements"] != REQUIREMENTS_POLICY
            or "input_summary" in launch or "output_recovery" in launch
            or launch.get("evidence_shadow") == "shadow"):
        raise GoFailure("chi_requirements_configuration_invalid")
    return True


def _recovery_enabled(launch: dict, kind: str) -> bool:
    """Validate the optional launch version without mutating persisted data."""
    if (type(launch) is not dict or type(kind) is not str
            or kind not in {"chi", "coding_b", "patient_probe"}):
        raise GoFailure("chi_identity_invalid")
    if "output_recovery" not in launch:
        return False
    if (kind != "chi" or type(launch["output_recovery"]) is not str
            or launch["output_recovery"] != RECOVERY_POLICY):
        raise GoFailure("chi_identity_invalid")
    if "requirements" in launch:
        raise GoFailure("chi_requirements_configuration_invalid")
    return True


def _summary_enabled(launch: dict, kind: str) -> bool:
    if type(launch) is not dict or kind not in {"chi", "coding_b", "patient_probe"}:
        raise GoFailure("chi_summary_configuration_invalid")
    if "input_summary" not in launch:
        return False
    if "requirements" in launch:
        raise GoFailure("chi_requirements_configuration_invalid")
    if (kind != "chi" or type(launch['input_summary']) is not str
            or launch['input_summary'] not in SUMMARY_VERSIONS or 'output_recovery' in launch
            or launch.get('evidence_shadow') == 'shadow'):
        raise GoFailure("chi_summary_configuration_invalid")
    return True


def _fee_decision(usage: dict, policy: str | None) -> tuple[dict, str | None, str | None]:
    """Keep provider billing_error, separately derive the versioned stop decision."""
    billed, error = _billing(usage)
    if policy is None:
        return billed, error, error
    if policy != FEE_POLICY:
        raise GoFailure('chi_fee_policy_invalid')
    details = usage.get('opencode')
    if details is not None and type(details) is not dict: raise GoFailure('chi_billing_invalid')
    details = details or {}
    for value in (usage.get('cost'), details.get('list_cost'), details.get('allowance')):
        if value is not None and (type(value) not in (int, float) or value < 0 or value > 1_000_000_000
                                  or not math.isfinite(value)):
            raise GoFailure('chi_billing_invalid')
    source = details.get('billing_source')
    if source is not None and type(source) is not str: raise GoFailure('chi_billing_invalid')
    if 'estimated' in details and (type(details['estimated']) is not bool or details['estimated']):
        raise GoFailure('chi_billing_invalid')
    if (source is not None and source not in {'go', 'go-plus'}) or (usage.get('cost') is not None and usage['cost'] > 0):
        return billed, error, 'billing_source_unexpected'
    return billed, error, None


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


def _acknowledged(root: Path, state: dict) -> dict:
    """Validate the append-only acknowledgement chain and return its targets."""
    refs = state.get('acknowledgements', [])
    if type(refs) is not list: raise ValueError
    directory = root / 'unsettled-acknowledgements'
    if directory.is_symlink(): raise ValueError
    if directory.exists() and not refs: raise ValueError
    expected, targets = set(), {}
    for index, ref in enumerate(refs, 1):
        if type(ref) is not dict or set(ref) != {'event_sha256'} or type(ref['event_sha256']) is not str or not DIGEST.fullmatch(ref['event_sha256']): raise ValueError
        event_name = f'{index:04d}-event-{ref["event_sha256"]}.json'
        event_raw = _read_regular_bounded(directory / event_name, 1024 * 1024, 'chi_history_invalid')
        if hashlib.sha256(event_raw).hexdigest() != ref['event_sha256']: raise ValueError
        from opencode_go_provider import _unique
        event = json.loads(event_raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (type(event) is not dict or set(event) != {'schema', 'identity', 'accounting_sha256', 'provider_sha256', 'run', 'round', 'request_sha256', 'reason'}
                or event['schema'] != 'chi-go-unsettled-ack-v1'
                or any(type(event[k]) is not str or not DIGEST.fullmatch(event[k]) for k in ('identity', 'accounting_sha256', 'provider_sha256', 'request_sha256'))
                or type(event['run']) is not str or not ID.fullmatch(event['run'])
                or type(event['round']) is not int or event['round'] < 1
                or type(event['reason']) is not str or not event['reason'].strip() or len(event['reason']) > 256): raise ValueError
        names = {'event': event_name, 'accounting': f'{index:04d}-accounting-{event["accounting_sha256"]}.json',
                 'provider': f'{index:04d}-provider-{event["provider_sha256"]}.json'}
        expected.update(names.values())
        raws = {kind: _read_regular_bounded(directory / names[kind], MAX_STATE_BYTES if kind == 'accounting' else 1024 * 1024, 'chi_history_invalid')
                for kind in ('accounting', 'provider')}
        if (hashlib.sha256(raws['accounting']).hexdigest() != event['accounting_sha256']
                or hashlib.sha256(raws['provider']).hexdigest() != event['provider_sha256']): raise ValueError
        snapshot = json.loads(raws['accounting'], object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        target = (event['run'], event['round'])
        required_keys = {'schema', 'identity', 'account_prior_history', 'attempts', 'pending', 'halted'}
        if (type(snapshot) is not dict or not required_keys <= set(snapshot)
                or set(snapshot) - required_keys - {'source_transitions', 'acknowledgements'}
                or snapshot['schema'] != 'chi-go-evaluation-usd-v1' or snapshot['account_prior_history'] != 'unknown'
                or target in targets or snapshot.get('identity') != event['identity']
                or snapshot.get('acknowledgements', []) != refs[:index-1]
                or snapshot.get('pending') != {'run': event['run'], 'round': event['round']}
                or snapshot.get('halted') is not None or type(snapshot.get('attempts')) is not list
                or state['attempts'][:len(snapshot['attempts'])] != snapshot['attempts']): raise ValueError
        pending_targets = {(a['run'], n) for a in snapshot['attempts']
                           for n, request in enumerate(a['requests'], 1)
                           if request['status'] in {'pending', 'unknown'}}
        if not set(targets) <= pending_targets or pending_targets - set(targets) != {target}: raise ValueError
        transitions = snapshot.get('source_transitions', [])
        current_transitions = state.get('source_transitions', [])
        if (type(transitions) is not list or transitions != current_transitions[:len(transitions)]
                or (current_transitions[len(transitions)]['old_identity'] if len(transitions) < len(current_transitions)
                    else state['identity']) != event['identity']): raise ValueError
        attempt = next(a for a in snapshot['attempts'] if a['run'] == event['run'])
        request = attempt['requests'][event['round'] - 1]
        if (attempt['status'] != 'failed' or request['status'] not in {'pending', 'unknown'}
                or request['request_sha256'] != event['request_sha256'] or request['diagnostic_evidence_sha256'] is None
                or request['response_evidence_sha256'] is not None): raise ValueError
        request_doc = verify_evidence(root, event['run'], event['round'], 'request', request['request_evidence_sha256'])
        diagnostic = verify_evidence(root, event['run'], event['round'], 'diagnostic', request['diagnostic_evidence_sha256'])
        if diagnostic.get('code') != 'chi_timeout' or request_doc.get('dispatch') is not None: raise ValueError
        from go_chi_inspect import inspect_provider
        body = request_doc.get('body_utf8')
        pending = {'kind': attempt['kind'], 'purpose': request['purpose'], 'dispatch': request_doc.get('dispatch'),
                   'body_bytes': len(body.encode()) if body is not None else None}
        if pending['body_bytes'] is None and pending['dispatch'] is None: raise ValueError
        provider_result = inspect_provider(directory / names['provider'], event['provider_sha256'], pending)
        if provider_result['correlation']['status'] == 'mismatch': raise ValueError
        targets[target] = event
    if directory.exists() and ({p.name for p in directory.iterdir()} != expected
            or any(p.is_symlink() or not p.is_file() for p in directory.iterdir())): raise ValueError
    if expected and not directory.is_dir(): raise ValueError
    return targets


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
                  'usage': auditor.usage_totals(), 'missing': [],
                  'acknowledged_unsettled': [{'run': e['run'], 'round': e['round'], 'request_sha256': e['request_sha256'],
                                               'status': 'unsettled'} for e in _acknowledged(root, state).values()],
                  'reconciled_provider_timeouts': []}
        summary_runs = [attempt for attempt in state['attempts'] if 'summary_events' in attempt]
        if summary_runs:
            result['input_summaries'] = [{'run': attempt['run'], 'status': (attempt['summary_events'][0]['status']
                                         if attempt['summary_events'] else 'not_started'),
                                         'summary_round': (attempt['summary_events'][0]['summary_round']
                                                           if attempt['summary_events'] else None),
                                         'projected_views': (len(attempt['summary_events'][0]['projections'])
                                                             if attempt['summary_events'] else 0),
                                         'reserved_main_requests': (sum(ref['round'] <= len(attempt['requests'])
                                             for ref in attempt['summary_events'][0]['projections'])
                                             if attempt['summary_events'] else 0)}
                                        for attempt in summary_runs]
        for index, ref in enumerate(state.get('reconciliations', []), 1):
            event_path = root / 'reconciliations' / f'{index:04d}-event-{ref["event_sha256"]}.json'
            event = json.loads(_read_regular_bounded(event_path, 1024 * 1024, 'chi_history_invalid'))
            result['reconciled_provider_timeouts'].append({
                'run': event['run'], 'round': event['round'], 'request_sha256': event['request_sha256'],
                'provider_request_id': event['provider_request_id'],
                'tokens': {'input_tokens': event['input_tokens'], 'output_tokens': event['output_tokens']},
                'console_cost': event['console_cost'], 'status': 'provider_proven_unsettled'})
        for attempt in state['attempts']:
            for item in attempt['requests']:
                if item['status'] == 'settled':
                    for field in ('charged_usd', 'billing_source', 'list_cost_usd', 'allowance_usd'):
                        if item['billing'][field] is None and field not in result['missing']:
                            result['missing'].append(field)
        causes = []
        for attempt in state['attempts']:
            for index, item in enumerate(attempt['requests'], 1):
                if item.get('diagnostic_evidence_sha256') is None:
                    continue
                doc = verify_evidence(root, attempt['run'], index, 'diagnostic',
                                      item['diagnostic_evidence_sha256'])
                if doc.get('schema') == SCHEMA_V2:
                    causes.append({'run': attempt['run'], 'round': index,
                                   'code': doc.get('code'), 'cause': doc.get('cause')})
        if causes:
            result['diagnostic_causes'] = causes
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


def acknowledge_unsettled(root: Path, *, identity: str, accounting_sha256: str, run: str, round_number: int,
                          request_sha256: str, provider_path: Path, provider_sha256: str, reason: str) -> dict:
    """Record the user's bounded decision; neither settle nor alter the failed attempt."""
    from evaluation_bundle import _check_components
    from go_chi_inspect import inspect_provider
    if (any(type(x) is not str or not DIGEST.fullmatch(x) for x in (identity, accounting_sha256, request_sha256, provider_sha256))
            or type(run) is not str or not ID.fullmatch(run) or type(round_number) is not int or round_number < 1
            or type(reason) is not str or not reason.strip() or len(reason) > 256): raise GoFailure('chi_ack_invalid')
    root = Path(root); _reject_symlink_ancestors(root, 'chi_path_invalid')
    lock = os.open(root / '.lock', os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = root / 'chi-accounting.json'
        raw = _read_regular_bounded(path, MAX_STATE_BYTES, 'chi_history_invalid')
        if hashlib.sha256(raw).hexdigest() != accounting_sha256: raise GoFailure('chi_ack_hash_mismatch')
        auditor = object.__new__(ChiJournal); auditor.root, auditor.path, auditor.state = root, path, _state_object(path)
        auditor._validate(identity)
        state = auditor.state
        if state['pending'] != {'run': run, 'round': round_number} or state['halted'] is not None:
            raise GoFailure('chi_ack_target_invalid')
        attempt = next((a for a in state['attempts'] if a['run'] == run), None)
        if attempt is None or attempt['status'] != 'failed' or round_number > len(attempt['requests']): raise GoFailure('chi_ack_target_invalid')
        request = attempt['requests'][round_number - 1]
        if (request['status'] not in {'pending', 'unknown'} or request['request_sha256'] != request_sha256
                or request['diagnostic_evidence_sha256'] is None or request['response_evidence_sha256'] is not None): raise GoFailure('chi_ack_target_invalid')
        inflight = root / 'tool-inflight'
        if inflight.exists() and any(any(p.iterdir()) for p in inflight.iterdir()): raise GoFailure('chi_ack_inflight')
        doc = verify_evidence(root, run, round_number, 'request', request['request_evidence_sha256'])
        diagnostic = verify_evidence(root, run, round_number, 'diagnostic', request['diagnostic_evidence_sha256'])
        if diagnostic.get('code') != 'chi_timeout' or doc.get('dispatch') is not None: raise GoFailure('chi_ack_target_invalid')
        body = doc.get('body_utf8')
        pending = {'kind': attempt['kind'], 'purpose': request['purpose'], 'dispatch': doc.get('dispatch'),
                   'body_bytes': len(body.encode()) if body is not None else None}
        if pending['body_bytes'] is None and pending['dispatch'] is None: raise GoFailure('chi_ack_target_invalid')
        result = inspect_provider(provider_path, provider_sha256, pending)
        if result['correlation']['status'] == 'mismatch': raise GoFailure('chi_ack_provider_mismatch')
        provider_path = _check_components(Path(provider_path), 'chi_provider_record_invalid', final_may_be_missing=False)
        provider_raw = _read_regular_bounded(provider_path, 1024 * 1024, 'chi_provider_record_invalid')
        if hashlib.sha256(provider_raw).hexdigest() != provider_sha256: raise GoFailure('chi_provider_record_invalid')
        refs = state.get('acknowledgements', []); index = len(refs) + 1
        event = {'schema': 'chi-go-unsettled-ack-v1', 'identity': identity, 'accounting_sha256': accounting_sha256,
                 'provider_sha256': provider_sha256, 'run': run, 'round': round_number,
                 'request_sha256': request_sha256, 'reason': reason.strip()}
        event_raw = (json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode()
        marker = root / 'acknowledgement.pending'
        _write_exclusive(marker, b'acknowledgement in progress\n'); _fsync_dir(root)
        directory = root / 'unsettled-acknowledgements'
        directory.mkdir(mode=0o700, exist_ok=True); _reject_symlink_ancestors(directory, 'chi_path_invalid'); _fsync_dir(root)
        for kind, payload in (('accounting', raw), ('provider', provider_raw), ('event', event_raw)):
            _write_exclusive(directory / f'{index:04d}-{kind}-{hashlib.sha256(payload).hexdigest()}.json', payload)
            _fsync_dir(directory)
        updated = copy.deepcopy(state)
        updated['pending'] = None
        updated['acknowledgements'] = refs + [{'event_sha256': hashlib.sha256(event_raw).hexdigest()}]
        _atomic(path, updated)
        marker.unlink(); _fsync_dir(root)
        return {'status': 'acknowledged_unsettled', 'run': run, 'round': round_number,
                'execution_allowed': False, 'settled': False, 'event_sha256': hashlib.sha256(event_raw).hexdigest()}
    finally:
        os.close(lock)


def reconcile_provider_timeout(root: Path, *, identity: str, accounting_sha256: str, run: str,
                               round_number: int, request_sha256: str, provider_path: Path,
                               provider_sha256: str, reason: str) -> dict:
    """Clear admission for a timeout only when a provider record proves the request.

    The request stays unknown and the failed attempt/seal are not rewritten.
    The event records provider identity, tokens and cost; billing splits remain
    incomplete rather than being fabricated.
    """
    from evaluation_bundle import _check_components
    from go_chi_inspect import inspect_provider
    if (any(type(x) is not str or not DIGEST.fullmatch(x)
            for x in (identity, accounting_sha256, request_sha256, provider_sha256))
            or type(run) is not str or not ID.fullmatch(run) or type(round_number) is not int or round_number < 1
            or type(reason) is not str or not reason.strip() or len(reason) > 256):
        raise GoFailure('chi_reconcile_invalid')
    root = Path(root); _reject_symlink_ancestors(root, 'chi_path_invalid')
    lock = os.open(root / '.lock', os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = root / 'chi-accounting.json'
        raw = _read_regular_bounded(path, MAX_STATE_BYTES, 'chi_history_invalid')
        if hashlib.sha256(raw).hexdigest() != accounting_sha256: raise GoFailure('chi_reconcile_hash_mismatch')
        auditor = object.__new__(ChiJournal)
        auditor.root, auditor.path, auditor.state = root, path, _state_object(path)
        auditor._validate(identity)
        state = auditor.state
        if state['pending'] != {'run': run, 'round': round_number} or state['halted'] is not None:
            raise GoFailure('chi_reconcile_target_invalid')
        attempt = next((a for a in state['attempts'] if a['run'] == run), None)
        if attempt is None or attempt['status'] != 'failed' or round_number > len(attempt['requests']):
            raise GoFailure('chi_reconcile_target_invalid')
        request = attempt['requests'][round_number - 1]
        if (request['status'] not in {'pending', 'unknown'} or request['request_sha256'] != request_sha256
                or request['diagnostic_evidence_sha256'] is None or request['response_evidence_sha256'] is not None):
            raise GoFailure('chi_reconcile_target_invalid')
        inflight = root / 'tool-inflight'
        if inflight.exists() and any(any(p.iterdir()) for p in inflight.iterdir()):
            raise GoFailure('chi_reconcile_inflight')
        doc = verify_evidence(root, run, round_number, 'request', request['request_evidence_sha256'])
        diagnostic = verify_evidence(root, run, round_number, 'diagnostic', request['diagnostic_evidence_sha256'])
        if diagnostic.get('code') != 'chi_timeout' or doc.get('dispatch') is None:
            raise GoFailure('chi_reconcile_target_invalid')
        body = doc.get('body_utf8')
        pending = {'kind': attempt['kind'], 'purpose': request['purpose'], 'dispatch': doc.get('dispatch'),
                   'body_bytes': len(body.encode()) if body is not None else None}
        inspection = inspect_provider(provider_path, provider_sha256, pending)
        if inspection['correlation']['status'] != 'consistent':
            raise GoFailure('chi_reconcile_provider_mismatch')
        provider_path = _check_components(Path(provider_path), 'chi_provider_record_invalid', final_may_be_missing=False)
        provider_raw = _read_regular_bounded(provider_path, 1024 * 1024, 'chi_provider_record_invalid')
        if hashlib.sha256(provider_raw).hexdigest() != provider_sha256:
            raise GoFailure('chi_provider_record_invalid')
        event = {
            'schema': 'chi-go-provider-reconciliation-v1', 'identity': identity,
            'accounting_sha256': accounting_sha256, 'provider_sha256': provider_sha256,
            'provider_request_id': inspection['request_id'], 'run': run, 'round': round_number,
            'request_sha256': request_sha256,
            'input_tokens': inspection['tokens']['inputTokens'],
            'output_tokens': inspection['tokens']['outputTokens'],
            'console_cost': inspection['console_cost'], 'reason': reason.strip(),
        }
        event_raw = (json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode()
        event_sha = hashlib.sha256(event_raw).hexdigest()
        marker = root / 'reconciliation.pending'
        _write_exclusive(marker, b'reconciliation in progress\n'); _fsync_dir(root)
        directory = root / 'reconciliations'
        directory.mkdir(mode=0o700, exist_ok=True)
        _reject_symlink_ancestors(directory, 'chi_path_invalid'); _fsync_dir(root)
        index = len(state.get('reconciliations', [])) + 1
        for kind, payload in (('accounting', raw), ('provider', provider_raw), ('event', event_raw)):
            _write_exclusive(directory / f'{index:04d}-{kind}-{hashlib.sha256(payload).hexdigest()}.json', payload)
            _fsync_dir(directory)
        updated = copy.deepcopy(state)
        updated['pending'] = None
        updated['reconciliations'] = state.get('reconciliations', []) + [{'event_sha256': event_sha}]
        _atomic(path, updated)
        marker.unlink(); _fsync_dir(root)
        return {'status': 'reconciled_provider_timeout', 'run': run, 'round': round_number,
                'execution_allowed': False, 'request_retry_allowed': False,
                'admission_cleared': True, 'settled': False, 'event_sha256': event_sha,
                'provider_request_id': inspection['request_id'],
                'tokens': {'input_tokens': inspection['tokens']['inputTokens'],
                           'output_tokens': inspection['tokens']['outputTokens']},
                'console_cost': inspection['console_cost']}
    finally:
        os.close(lock)


def _recovery_source(root: Path, run: dict, parent_round: int):
    """Reconstruct a recovery source only from verified, settled evidence."""
    from b_provider_transport import GuardedTransport
    from go_chi_recovery import derive_view, mode_and_fragment
    if (type(parent_round) is not int or not 1 <= parent_round <= len(run["requests"])):
        raise ValueError("chi_recovery_invalid")
    item = run["requests"][parent_round - 1]
    if (type(item) is not dict or item.get("round") != parent_round or item.get("purpose") != "main"
            or item.get("status") != "settled"):
        raise ValueError("chi_recovery_invalid")
    docs = [verify_evidence(root, run["run"], parent_round, kind, item[kind + "_evidence_sha256"])
            for kind in ("request", "response", "diagnostic")]
    request, response, diagnostic = docs
    if (request.get("kind") != "request" or response.get("kind") != "response"
            or not (validate_v1(diagnostic) or validate_v2(diagnostic))
            or diagnostic.get("kind") != "diagnostic" or diagnostic.get("code") != "ok"
            or response.get("http_status") != 200
            or any(doc.get("schema") != "chi-go-wire-evidence-v1" or doc.get("redaction") is not None
                   or type(doc.get("body_utf8")) is not str or type(doc.get("raw_sha256")) is not str
                   or hashlib.sha256(doc["body_utf8"].encode()).hexdigest() != doc["raw_sha256"]
                   for doc in (request, response))
            or request["raw_sha256"] != item["request_sha256"]):
        raise ValueError("chi_recovery_invalid")
    parse = lambda raw: json.loads(raw, object_pairs_hook=_unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    request_body, response_body = parse(request["body_utf8"]), parse(response["body_utf8"])
    if (type(request_body) is not dict or type(request_body.get("max_tokens")) is not int
            or request_body["max_tokens"] != 8192):
        raise ValueError("chi_recovery_invalid")
    incoming, outgoing = GuardedTransport._usage(response_body)
    if (item.get("usage") != {"input_tokens": incoming, "output_tokens": outgoing}
            or response.get("usage") != response_body.get("usage") or incoming > 1048576 or outgoing > 8192):
        raise ValueError("chi_recovery_invalid")
    billed, error, halt = _fee_decision(response_body["usage"], run["launch"].get("fee_policy"))
    if billed != item.get("billing") or error != item.get("billing_error") or halt is not None:
        raise ValueError("chi_recovery_invalid")
    mode_and_fragment(response_body)
    old_used = sum(r.get("purpose") != "patient_simulator" for r in run["requests"][:parent_round - 1])
    candidates = []
    for claimed in (False, True):
        try:
            view = derive_view(request_body, response_body, old_used=old_used, claimed=claimed)
            candidates.append((claimed, view))
        except ValueError:
            pass
    if len(candidates) != 1:
        raise ValueError("chi_recovery_history_changed")
    claimed, view = candidates[0]
    return request_body, response_body, response["raw_sha256"], old_used, claimed, view


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
                or kind not in {"chi", "coding_b", "patient_probe"}
                or (launch is not None and type(launch) is not dict)
                or any(type(x) is not str or not ID.fullmatch(x)
                       for x in (evaluation, task, attempt, run))):
            raise GoFailure("chi_identity_invalid")
        recovery_enabled = _recovery_enabled(launch if launch is not None else {}, kind)
        summary_enabled = _summary_enabled(launch if launch is not None else {}, kind)
        _requirements_enabled(launch if launch is not None else {}, kind)
        if launch is not None and 'aux_contract' in launch:
            if (launch['aux_contract'] != 'patient-simulator-v1' or kind not in {'chi', 'patient_probe'}
                    or (kind == 'chi' and launch.get('role') != 'cm')):
                raise GoFailure('chi_identity_invalid')
        if kind == 'patient_probe' and (launch is None or launch.get('aux_contract') != 'patient-simulator-v1'):
            raise GoFailure('chi_identity_invalid')
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
                if kind not in {"chi", "patient_probe"} or not any(valid_b(item) for item in self.state["attempts"]):
                    raise GoFailure("chi_b_receipt_missing")
            if any(a["run"] == run or (a["evaluation"], a["task"], a["attempt"]) == (evaluation, task, attempt)
                   for a in self.state["attempts"]):
                raise GoFailure("chi_attempt_or_run_exists")
            self.run = {"evaluation": evaluation, "task": task, "attempt": attempt, "run": run,
                        "kind": kind, "status": "started", "requests": [], "patient_binding_events": [],
                        "claim_done": False, "tool_events": [], "safe_error_code": None,
                        "launch": launch or {}}
            if recovery_enabled:
                self.run["recovery_events"] = []
            if summary_enabled:
                self.run["summary_events"] = []
            self.run_doc = self.run
            self.state["attempts"].append(self.run)
            self._persist()
        except BaseException:
            self.close()
            raise

    def _validate(self, identity: str) -> None:
        try:
            s = self.state
            if any((self.root / name).exists() or (self.root / name).is_symlink() for name in
                   ('migration.pending', 'acknowledgement.pending', 'reconciliation.pending')):
                raise ValueError
            acknowledged = _acknowledged(self.root, s)
            used_acknowledgements = set()
            reconciliations = s.get('reconciliations', [])
            if type(reconciliations) is not list: raise ValueError
            reconciled, reconciled_requests, expected_reconciliations = set(), {}, set()
            reconciliation_dir = self.root / 'reconciliations'
            for index, ref in enumerate(reconciliations, 1):
                if (type(ref) is not dict or set(ref) != {'event_sha256'}
                        or type(ref['event_sha256']) is not str or not DIGEST.fullmatch(ref['event_sha256'])):
                    raise ValueError
                name = f'{index:04d}-event-{ref["event_sha256"]}.json'
                path = reconciliation_dir / name
                raw = _read_regular_bounded(path, 1024 * 1024, 'chi_history_invalid')
                if hashlib.sha256(raw).hexdigest() != ref['event_sha256']: raise ValueError
                event = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                keys = {'schema', 'identity', 'accounting_sha256', 'provider_sha256',
                        'provider_request_id', 'run', 'round', 'request_sha256',
                        'input_tokens', 'output_tokens', 'console_cost', 'reason'}
                if (type(event) is not dict or set(event) != keys
                        or event['schema'] != 'chi-go-provider-reconciliation-v1'
                        or event['identity'] != s['identity']
                        or any(type(event[k]) is not str or not DIGEST.fullmatch(event[k])
                               for k in ('accounting_sha256', 'provider_sha256', 'request_sha256'))
                        or type(event['provider_request_id']) is not str or not event['provider_request_id']
                        or type(event['run']) is not str or not ID.fullmatch(event['run'])
                        or type(event['round']) is not int or event['round'] < 1
                        or type(event['input_tokens']) is not int or event['input_tokens'] < 0
                        or type(event['output_tokens']) is not int or event['output_tokens'] < 0
                        or type(event['console_cost']) is not str or not Decimal(event['console_cost']).is_finite()
                        or Decimal(event['console_cost']) < 0
                        or type(event['reason']) is not str or not event['reason'].strip() or len(event['reason']) > 256):
                    raise ValueError
                target = (event['run'], event['round'])
                if target in reconciled: raise ValueError
                accounting_name = f'{index:04d}-accounting-{event["accounting_sha256"]}.json'
                accounting_raw = _read_regular_bounded(reconciliation_dir / accounting_name, MAX_STATE_BYTES,
                                                       'chi_history_invalid')
                if hashlib.sha256(accounting_raw).hexdigest() != event['accounting_sha256']:
                    raise ValueError
                provider_name = f'{index:04d}-provider-{event["provider_sha256"]}.json'
                provider_raw = _read_regular_bounded(reconciliation_dir / provider_name, 1024 * 1024,
                                                     'chi_history_invalid')
                if hashlib.sha256(provider_raw).hexdigest() != event['provider_sha256']:
                    raise ValueError
                reconciled.add(target); reconciled_requests[target] = event['request_sha256']
                expected_reconciliations.update({name, accounting_name, provider_name})
            used_reconciliations = set()
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
                        or snapshot.get('acknowledgements', []) != s.get('acknowledgements', [])[:len(snapshot.get('acknowledgements', []))]
                        or snapshot.get("pending") is not None or snapshot.get("halted") is not None
                        or type(attempts) is not list or attempts[:len(previous_attempts)] != previous_attempts
                        or s["attempts"][:len(attempts)] != attempts
                        or any(a.get("status") not in {"complete", "failed"} for a in attempts)):
                    raise ValueError
                acknowledged_prefix = set(list(acknowledged)[:len(snapshot.get('acknowledgements', []))])
                if any((a['run'], n) not in acknowledged_prefix for a in attempts
                       for n, req in enumerate(a['requests'], 1) if req['status'] in {'pending', 'unknown'}):
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
                allowed_parent = None
                if allowed_pending:
                    attempts = [a for a in s.get('attempts', []) if a.get('run') == pending_claim['run']]
                    if len(attempts) == 1 and 0 < pending_claim['round'] <= len(attempts[0].get('requests', [])):
                        req = attempts[0]['requests'][pending_claim['round'] - 1]
                        parent = req.get('parent_call_id')
                        if req.get('purpose') == 'patient_simulator' and isinstance(parent, str):
                            allowed_parent = (pending_claim['run'], parent + '.pending')
                for directory in inflight.iterdir():
                    if directory.is_symlink() or not directory.is_dir(): raise ValueError
                    for path in directory.iterdir():
                        if (path.is_symlink() or not path.is_file()
                                or (directory.name, path.name) not in (allowed_pending, allowed_parent)): raise ValueError
            keys = {"schema", "identity", "account_prior_history", "attempts", "pending", "halted"}
            if (type(s) is not dict or not keys <= set(s) or set(s) - keys - {'source_transitions', 'acknowledgements', 'reconciliations'}
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
                if type(a) is not dict:
                    raise ValueError
                recovery_enabled = _recovery_enabled(a.get("launch"), a.get("kind"))
                summary_enabled = _summary_enabled(a.get("launch"), a.get("kind"))
                _requirements_enabled(a.get("launch"), a.get("kind"))
                run_keys = {"evaluation", "task", "attempt", "run", "kind", "status", "requests", "patient_binding_events", "claim_done", "tool_events", "safe_error_code", "launch"}
                if recovery_enabled:
                    run_keys.add("recovery_events")
                if summary_enabled:
                    run_keys.add("summary_events")
                if (set(a) != run_keys
                        or (recovery_enabled and (type(a["recovery_events"]) is not list or len(a["recovery_events"]) > 2))
                        or (summary_enabled and (type(a['summary_events']) is not list or len(a['summary_events']) > 1))
                        or any(type(a[k]) is not str or not ID.fullmatch(a[k]) for k in ("evaluation", "task", "attempt", "run"))
                        or a["kind"] not in {"chi", "coding_b", "patient_probe"}
                        or type(a["patient_binding_events"]) is not list
                        or type(a["claim_done"]) is not bool
                        or type(a["launch"]) is not dict
                        or type(a["tool_events"]) is not list
                        or any(type(event) is not dict for event in a["tool_events"])
                        or (a["safe_error_code"] is not None and (type(a["safe_error_code"]) is not str
                            or not re.fullmatch(r"[a-z0-9_]{1,64}", a["safe_error_code"])))
                        or any(type(event) is not dict or type(event.get("event")) is not str for event in a["patient_binding_events"])
                        or a["status"] not in {"started", "complete", "failed"} or type(a["requests"]) is not list
                        or len(a["requests"]) > (6 if a["kind"] == "coding_b" else 2 if a['kind'] == 'patient_probe' else 60 if a['launch'].get('aux_contract') == 'patient-simulator-v1' else 50)):
                    raise ValueError
                aux_enabled = a['launch'].get('aux_contract') == 'patient-simulator-v1'
                if 'aux_contract' in a['launch'] and not aux_enabled: raise ValueError
                if aux_enabled and (a['kind'] not in {'chi', 'patient_probe'}
                        or (a['kind'] == 'chi' and a['launch'].get('role') != 'cm')): raise ValueError
                if a['kind'] == 'patient_probe' and not aux_enabled: raise ValueError
                if sum(r.get('purpose') in {'main', 'confirmation', 'continuation', 'summary'} for r in a['requests']) > (6 if a['kind'] == 'coding_b' else 50): raise ValueError
                if sum(r.get('purpose') == 'patient_simulator' for r in a['requests']) > (2 if a['kind'] == 'patient_probe' else 10 if aux_enabled else 0): raise ValueError
                fee_policy = a['launch'].get('fee_policy')
                if fee_policy not in (None, FEE_POLICY): raise ValueError
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
                unfinished = set(started) - finished
                if unfinished:
                    claim = s.get('pending')
                    if (type(claim) is not dict or claim.get('run') != a['run']
                            or type(claim.get('round')) is not int or not 0 < claim['round'] <= len(a['requests'])): raise ValueError
                    pending_request = a['requests'][claim['round'] - 1]
                    if (pending_request.get('purpose') != 'patient_simulator'
                            or unfinished != {pending_request.get('parent_call_id')}
                            or not (self.root / 'tool-inflight' / a['run'] / (pending_request['parent_call_id'] + '.pending')).is_file()): raise ValueError
                confirms = 0
                for index, item in enumerate(a["requests"], 1):
                    effective_fee_stop = None
                    if (type(item) is not dict or item.get("round") != index
                            or item.get("purpose") not in ({"main", "confirmation"} | ({"patient_simulator"} if aux_enabled else set()) | ({"continuation"} if recovery_enabled else set()) | ({"summary"} if summary_enabled else set()))
                            or (a["kind"] == "coding_b" and item.get("purpose") != "main")
                            or (a['kind'] == 'patient_probe' and item.get('purpose') != 'patient_simulator')
                            or item.get("max_tokens") != output_limit(a['kind'], item.get('purpose'), a['launch'].get('input_summary'))
                            or type(item.get("request_sha256")) is not str or not DIGEST.fullmatch(item["request_sha256"])):
                        raise ValueError
                    required = {"round", "purpose", "max_tokens", "request_sha256", "status",
                                "request_evidence_sha256", "response_evidence_sha256", "diagnostic_evidence_sha256"}
                    if item['purpose'] == 'patient_simulator':
                        required.add('parent_call_id')
                        parent = item.get('parent_call_id')
                        if a['kind'] == 'patient_probe':
                            if parent is not None: raise ValueError
                        elif not isinstance(parent, str) or started.get(parent) != 'cm_outreach.send_message': raise ValueError
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
                                    billed, billing_error, effective_fee_stop = _fee_decision(usage, fee_policy)
                                    if billed != item["billing"] or billing_error != item["billing_error"]:
                                        raise ValueError
                            elif not (validate_v1(evidence) or validate_v2(evidence)):
                                raise ValueError
                            expected_evidence.add((a["run"], f"{index:03d}-{kind}.json"))
                    if item["status"] == "settled" and (item["response_evidence_sha256"] is None
                                                         or item["diagnostic_evidence_sha256"] is None):
                        raise ValueError
                    confirms += item["purpose"] == "confirmation"
                    if confirms > 2 or halt is not None or pending is not None:
                        raise ValueError
                    if item.get("status") in {"pending", "unknown"}:
                        target = (a['run'], index)
                        if target in acknowledged:
                            used_acknowledgements.add(target)
                        elif target in reconciled:
                            if item['request_sha256'] != reconciled_requests[target]:
                                raise ValueError
                            used_reconciliations.add(target)
                        else:
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
                        if fee_policy is None and inferred != item["billing_error"]:
                            raise ValueError
                        halt = inferred if fee_policy is None else effective_fee_stop
                    else:
                        raise ValueError
                if recovery_enabled:
                    from go_chi_recovery import validate_permit
                    from go_chi_recovery import canonical_sha
                    seen_parents, bound_rounds = set(), set()
                    for event in a["recovery_events"]:
                        if (type(event) is not dict or set(event) != {"parent_round", "permit_sha256", "continuation_round"}
                                or type(event["parent_round"]) is not int or event["parent_round"] in seen_parents
                                or type(event["permit_sha256"]) is not str or not DIGEST.fullmatch(event["permit_sha256"])
                                or (event["continuation_round"] is not None and type(event["continuation_round"]) is not int)):
                            raise ValueError
                        number = event["parent_round"]
                        seen_parents.add(number)
                        request_body, response_body, response_sha, old_used, claimed, _ = _recovery_source(self.root, a, number)
                        permit = verify_evidence(self.root, a["run"], number, "recovery", event["permit_sha256"])
                        validate_permit(permit, identity=run_identities.get(a["run"], identity), run=a,
                                        parent_round=number, parent_request=request_body, parent_response=response_body,
                                        response_sha256=response_sha, old_used=old_used, claimed=claimed)
                        continuation = event["continuation_round"]
                        if continuation is None:
                            if number != len(a["requests"]) or a["status"] == "complete": raise ValueError
                        else:
                            if (continuation != number + 1 or continuation > len(a["requests"])
                                    or continuation in bound_rounds): raise ValueError
                            bound_rounds.add(continuation)
                            item = a["requests"][continuation - 1]
                            if item["purpose"] != "continuation": raise ValueError
                            evidence = verify_evidence(self.root, a["run"], continuation, "request", item["request_evidence_sha256"])
                            if evidence.get("redaction") is not None or type(evidence.get("body_utf8")) is not str: raise ValueError
                            raw_body = json.loads(evidence["body_utf8"], object_pairs_hook=_unique,
                                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                            if canonical_sha(raw_body) != permit["view_sha256"]: raise ValueError
                        expected_evidence.add((a["run"], f"{number:03d}-recovery.json"))
                    if bound_rounds != {item["round"] for item in a["requests"] if item["purpose"] == "continuation"}:
                        raise ValueError
                if summary_enabled:
                    self._validate_summary_history(a, run_identities.get(a['run'], identity), expected_evidence)
            if (used_acknowledgements != set(acknowledged) or used_reconciliations != reconciled
                    or pending != s["pending"] or halt != s["halted"]):
                raise ValueError
            if reconciliation_dir.exists():
                if reconciliation_dir.is_symlink() or not reconciliation_dir.is_dir(): raise ValueError
                actual_reconciliations = {path.name for path in reconciliation_dir.iterdir()}
                if actual_reconciliations != expected_reconciliations: raise ValueError
                if any(path.is_symlink() or not path.is_file() for path in reconciliation_dir.iterdir()): raise ValueError
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
        except Exception as exc:
            raise GoFailure("chi_history_invalid") from exc

    def _persist(self):
        if getattr(self, "_recovery_persistence_failed", False):
            raise GoFailure("chi_recovery_persistence_failed")
        if len((json.dumps(self.state, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()) > MAX_STATE_BYTES:
            raise GoFailure("chi_state_limit")
        _atomic(self.path, self.state)

    def record_claim(self) -> None:
        self.run["claim_done"] = True
        self._persist()

    def _validate_summary_history(self, run, identity, expected_evidence):
        from go_chi_summary import (candidate_from_response, canonical_sha, derive_view, select_closed,
                                    summary_request, validate_saved_source)
        events = run['summary_events']
        summary_rounds = [item['round'] for item in run['requests'] if item['purpose'] == 'summary']
        if not events:
            if summary_rounds: raise ValueError
            return
        event = events[0]
        fields = {'selection_sha256', 'summary_round', 'candidate_sha256', 'checkpoint_sha256', 'status', 'projections'}
        if (type(event) is not dict or set(event) != fields
                or type(event['selection_sha256']) is not str or not DIGEST.fullmatch(event['selection_sha256'])
                or event['status'] not in {'selected', 'requested', 'candidate', 'installed', 'rejected', 'failed'}
                or type(event['projections']) is not list):
            raise ValueError
        number = event['summary_round']
        if number is None:
            if event['status'] != 'selected' or summary_rounds or run['status'] == 'complete': raise ValueError
            number = len(run['requests']) + 1
        elif (type(number) is not int or number < 1 or number > len(run['requests'])
              or summary_rounds != [number] or event['status'] == 'selected'):
            raise ValueError
        if event['status'] != 'installed' and event['summary_round'] is not None and len(run['requests']) != number:
            raise ValueError
        if (event['status'] == 'installed' and len(run['requests']) > number
                and run['requests'][number]['purpose'] != 'main'):
            raise ValueError
        selection = verify_evidence(self.root, run['run'], number, 'summary-selection', event['selection_sha256'])
        selection_fields = {'schema', 'identity', 'run', 'source_body', 'source_sha256', 'source_raw', 'source_raw_sha256', 'source_used', 'claimed',
                            'selection', 'selection_sha256', 'protected', 'protected_sha256', 'canonical_tools',
                            'summary_body', 'summary_sha256'}
        if (set(selection) != selection_fields or selection['schema'] != 'chi-summary-selection-v1'
                or selection['identity'] != identity or selection['run'] != run['run']
                or type(selection['source_used']) is not int or type(selection['claimed']) is not bool
                or type(selection['source_raw']) is not str
                or hashlib.sha256(selection['source_raw'].encode()).hexdigest() != selection['source_raw_sha256']
                or canonical_sha(json.loads(selection['source_raw'], object_pairs_hook=_unique)) != selection['source_sha256']
                or selection['source_sha256'] != canonical_sha(selection['source_body'])
                or selection['selection_sha256'] != canonical_sha(selection['selection'])
                or selection['protected_sha256'] != canonical_sha(selection['protected'])
                or selection['summary_sha256'] != canonical_sha(selection['summary_body'])
                or selection['selection_sha256'] != canonical_sha(select_closed(selection['source_body']['messages']))
                or selection['summary_sha256'] != canonical_sha(summary_request(selection['source_body'], selection['selection'], selection['protected'], run['launch']['input_summary']))):
            raise ValueError
        scoped = copy.deepcopy(run)
        scoped['requests'] = scoped['requests'][:number - 1]
        validate_saved_source(root=self.root, run=scoped, identity=identity, body=selection['source_body'],
                              used=selection['source_used'], claimed=selection['claimed'],
                              canonical_tools=selection['canonical_tools'], protected=selection['protected'])
        expected_evidence.add((run['run'], f'{number:03d}-summary-selection.json'))
        if event['summary_round'] is not None:
            request = run['requests'][number - 1]
            doc = verify_evidence(self.root, run['run'], number, 'request', request['request_evidence_sha256'])
            if (doc['redaction'] is not None or type(doc['body_utf8']) is not str
                    or canonical_sha(json.loads(doc['body_utf8'], object_pairs_hook=_unique)) != selection['summary_sha256']):
                raise ValueError
        candidate_ref, checkpoint_ref = event['candidate_sha256'], event['checkpoint_sha256']
        if candidate_ref is not None:
            if type(candidate_ref) is not str or not DIGEST.fullmatch(candidate_ref): raise ValueError
            candidate_doc = verify_evidence(self.root, run['run'], number, 'summary-candidate', candidate_ref)
            if (set(candidate_doc) != {'schema', 'selection_sha256', 'response_sha256', 'candidate', 'candidate_sha256'}
                    or candidate_doc['schema'] != 'chi-summary-candidate-evidence-v1'
                    or candidate_doc['selection_sha256'] != event['selection_sha256']
                    or candidate_doc['candidate_sha256'] != canonical_sha(candidate_doc['candidate'])):
                raise ValueError
            item = run['requests'][number - 1]
            if item['status'] != 'settled': raise ValueError
            response = verify_evidence(self.root, run['run'], number, 'response', item['response_evidence_sha256'])
            diagnostic = verify_evidence(self.root, run['run'], number, 'diagnostic', item['diagnostic_evidence_sha256'])
            if (response['raw_sha256'] != candidate_doc['response_sha256'] or response['http_status'] != 200
                    or response['redaction'] is not None or type(response['body_utf8']) is not str
                    or diagnostic['code'] != 'ok'):
                raise ValueError
            payload = json.loads(response['body_utf8'], object_pairs_hook=_unique)
            candidate = candidate_from_response(payload, selection_sha256=selection['selection_sha256'],
                                                protected_sha256=selection['protected_sha256'], sources=selection['selection']['sources'])
            if canonical_sha(candidate) != candidate_doc['candidate_sha256']: raise ValueError
            expected_evidence.add((run['run'], f'{number:03d}-summary-candidate.json'))
        if checkpoint_ref is not None:
            if type(checkpoint_ref) is not str or not DIGEST.fullmatch(checkpoint_ref) or candidate_ref is None: raise ValueError
            checkpoint = verify_evidence(self.root, run['run'], number, 'summary-checkpoint', checkpoint_ref)
            if checkpoint != {'schema': 'chi-summary-checkpoint-v1', 'selection_sha256': event['selection_sha256'],
                              'candidate_sha256': candidate_ref, 'candidate_protected_sha256': selection['protected_sha256'],
                              'selection_value_sha256': selection['selection_sha256']}:
                raise ValueError
            expected_evidence.add((run['run'], f'{number:03d}-summary-checkpoint.json'))
        if ((event['status'] == 'candidate') != (candidate_ref is not None and checkpoint_ref is None)
                or (event['status'] == 'installed') != (checkpoint_ref is not None)
                or (event['status'] in {'selected', 'requested', 'rejected', 'failed'} and candidate_ref is not None)
                or (event['projections'] and event['status'] != 'installed')):
            raise ValueError
        if run['status'] == 'complete' and (event['status'] != 'installed' or not event['projections']):
            raise ValueError
        previous_round = number
        for index, ref in enumerate(event['projections']):
            if (type(ref) is not dict or set(ref) != {'round', 'projection_sha256'}
                    or type(ref['round']) is not int or ref['round'] <= previous_round
                    or ref['round'] > len(run['requests']) + 1
                    or type(ref['projection_sha256']) is not str or not DIGEST.fullmatch(ref['projection_sha256'])):
                raise ValueError
            target = ref['round']
            previous_round = target
            projection = verify_evidence(self.root, run['run'], target, 'summary-projection', ref['projection_sha256'])
            keys = {'schema', 'checkpoint_sha256', 'source_raw', 'source_raw_sha256', 'source_body', 'source_sha256',
                    'source_used', 'claimed', 'protected', 'protected_sha256', 'summary_was_sent', 'wire_sha256'}
            if (set(projection) != keys or projection['schema'] != 'chi-summary-projection-v1'
                    or projection['checkpoint_sha256'] != checkpoint_ref
                    or type(projection['source_raw']) is not str
                    or hashlib.sha256(projection['source_raw'].encode()).hexdigest() != projection['source_raw_sha256']
                    or canonical_sha(json.loads(projection['source_raw'], object_pairs_hook=_unique)) != projection['source_sha256']
                    or projection['source_sha256'] != canonical_sha(projection['source_body'])
                    or projection['protected_sha256'] != canonical_sha(projection['protected'])
                    or type(projection['source_used']) is not int or type(projection['claimed']) is not bool
                    or type(projection['summary_was_sent']) is not bool or projection['summary_was_sent'] != (index == 0)):
                raise ValueError
            if index == 0 and (target != number + 1 or projection['protected_sha256'] != selection['protected_sha256']):
                raise ValueError
            scoped = copy.deepcopy(run)
            scoped['requests'] = scoped['requests'][:target - 1]
            if index == 0:
                scoped['requests'].pop()
            validate_saved_source(root=self.root, run=scoped, identity=identity, body=projection['source_body'],
                                  used=projection['source_used'], claimed=projection['claimed'],
                                  canonical_tools=selection['canonical_tools'], protected=projection['protected'])
            view = derive_view(projection['source_body'], used=projection['source_used'], claimed=projection['claimed'],
                               selection=selection['selection'], protected=projection['protected'],
                               candidate=candidate_doc['candidate'], candidate_protected_sha256=selection['protected_sha256'],
                               summary_was_sent=index == 0)
            wire = json.dumps(view, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if (canonical_sha(view) != projection['wire_sha256']
                    or len(projection['source_raw'].encode()) - len(wire) < 1024):
                raise ValueError
            if target <= len(run['requests']):
                item = run['requests'][target - 1]
                request = verify_evidence(self.root, run['run'], target, 'request', item['request_evidence_sha256'])
                if (item['purpose'] != 'main' or request['redaction'] is not None
                        or type(request['body_utf8']) is not str
                        or canonical_sha(json.loads(request['body_utf8'], object_pairs_hook=_unique)) != projection['wire_sha256']):
                    raise ValueError
            elif index != len(event['projections']) - 1 or run['status'] == 'complete':
                raise ValueError
            expected_evidence.add((run['run'], f'{target:03d}-summary-projection.json'))
        main_after_summary = {item['round'] for item in run['requests'] if item['purpose'] == 'main' and item['round'] > number}
        if main_after_summary != {ref['round'] for ref in event['projections'] if ref['round'] <= len(run['requests'])}:
            raise ValueError

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

    def issue_recovery(self, view_body: dict, *, secrets: tuple[str, ...] = ()) -> int:
        """Persist one consumed, immutable permit without issuing a request."""
        from go_chi_recovery import (POLICY, VIEW, INSTRUCTION_VERSION, canonical_sha,
                                     mode_and_fragment, validate_permit)
        if getattr(self, "_recovery_persistence_failed", False):
            raise GoFailure("chi_recovery_persistence_failed")
        if (not _recovery_enabled(self.run["launch"], self.run["kind"])
                or self.run["status"] != "started" or self.state["pending"] is not None
                or self.state["halted"] is not None or not self.run["requests"]):
            raise GoFailure("chi_recovery_invalid")
        events = self.run["recovery_events"]
        if len(events) >= 2:
            raise GoFailure("chi_recovery_limit")
        number = len(self.run["requests"])
        if any(event["parent_round"] == number for event in events):
            raise GoFailure("chi_recovery_limit")
        try:
            request_body, response_body, response_sha, old_used, claimed, view = _recovery_source(self.root, self.run, number)
            if claimed != self.run["claim_done"] or canonical_sha(view_body) != canonical_sha(view):
                raise ValueError
            mode, _ = mode_and_fragment(response_body)
            permit = {"schema": "chi-recovery-permit-v1", "policy": POLICY, "identity": self.state["identity"],
                      **{k: self.run[k] for k in ("evaluation", "task", "attempt", "run")},
                      "root_round": number, "parent_round": number, "parent_response_sha256": response_sha,
                      "mode": mode, "chain_ordinal": 1, "history_version": "chi-tool-history-v1",
                      "history_sha256": canonical_sha(request_body["messages"]),
                      "instruction_version": INSTRUCTION_VERSION, "view_version": VIEW,
                      "view_sha256": canonical_sha(view), "view_body": view,
                      "continuation_round": None, "decision": "issued", "result": "pending"}
            validate_permit(permit, identity=self.state["identity"], run=self.run, parent_round=number,
                            parent_request=request_body, parent_response=response_body, response_sha256=response_sha,
                            old_used=old_used, claimed=claimed)
            raw = json.dumps(permit, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if (_contains_secret(permit, *secrets) or any(secret and secret in raw for secret in secrets)):
                raise ValueError
        except Exception:
            raise GoFailure("chi_recovery_invalid") from None
        try:
            sha = write_evidence(self.root, self.run_id, number, "recovery", permit)
            events.append({"parent_round": number, "permit_sha256": sha, "continuation_round": None})
            self._persist()
        except Exception:
            self._recovery_persistence_failed = True
            raise GoFailure("chi_recovery_persistence_failed") from None
        return len(events) - 1

    def reserve(self, raw: bytes, purpose: str, *, secrets: tuple[str, ...] = (), dispatch=None,
                parent_call_id=None, recovery_permit=None, summary_permit=None, summary_projection=None) -> None:
        try:
            self._reserve(raw, purpose, secrets=secrets, dispatch=dispatch, parent_call_id=parent_call_id,
                          recovery_permit=recovery_permit, summary_permit=summary_permit,
                          summary_projection=summary_projection)
        except BaseException:
            if purpose == "continuation": self._recovery_persistence_failed = True
            if purpose == "summary": self._summary_persistence_failed = True
            if summary_projection is not None: self._summary_persistence_failed = True
            raise

    def select_summary(self, source_body, protected, canonical_tools, *, source_raw, secrets=()):
        """Persist the one-shot source selection before any summary request."""
        from go_chi_summary import (canonical_sha, protected_snapshot, select_closed,
                                    summary_request, validate_source)
        if (getattr(self, '_summary_persistence_failed', False)
                or not _summary_enabled(self.run['launch'], self.run['kind'])
                or self.run['summary_events'] or self.state['pending'] is not None
                or self.state['halted'] is not None or self.run['status'] != 'started'):
            raise GoFailure('chi_summary_unavailable')
        used = sum(item['purpose'] != 'patient_simulator' for item in self.run['requests'])
        if used >= 49:
            raise GoFailure('chi_summary_limit')
        try:
            if (type(source_raw) is not bytes or _contains_secret(source_body, *secrets)
                    or _contains_secret(protected, *secrets)
                    or canonical_sha(json.loads(source_raw, object_pairs_hook=_unique)) != canonical_sha(source_body)
                    or any(secret.encode() in source_raw for secret in secrets if secret)):
                raise ValueError
            contract, actions = validate_source(root=self.root, run=self.run, body=source_body, used=used,
                                                claimed=self.run['claim_done'], canonical_tools=canonical_tools)
            if (type(canonical_tools) is not dict or set(canonical_tools) != set(contract.schemas)
                    or any(type(value) is not str for value in canonical_tools.values())
                    or len(set(canonical_tools.values())) != len(canonical_tools)):
                raise ValueError
            expected = protected_snapshot(journal=self, contract=contract, canonical_tools=canonical_tools,
                role=self.run['launch']['role'], instruction=source_body['messages'][1]['content'],
                system=source_body['messages'][0]['content'][:-len(__import__('request_budget').feedback(used, self.run['claim_done'])[0])],
                patient_binding=protected['patient_binding'], task_state=protected['task_state'])
            if canonical_sha(expected) != canonical_sha(protected) or actions != expected['tool_actions']:
                raise ValueError
            selection = select_closed(source_body['messages'])
            if selection is None:
                raise ValueError
            request = summary_request(source_body, selection, protected, self.run['launch']['input_summary'])
            number = len(self.run['requests']) + 1
            doc = {'schema': 'chi-summary-selection-v1', 'identity': self.state['identity'],
                   'run': self.run_id, 'source_body': source_body, 'source_sha256': canonical_sha(source_body),
                   'source_raw': source_raw.decode('utf-8'), 'source_raw_sha256': hashlib.sha256(source_raw).hexdigest(),
                   'source_used': used, 'claimed': self.run['claim_done'], 'selection': selection,
                   'selection_sha256': canonical_sha(selection), 'protected': protected,
                   'protected_sha256': canonical_sha(protected), 'canonical_tools': canonical_tools,
                   'summary_body': request, 'summary_sha256': canonical_sha(request)}
        except Exception:
            raise GoFailure('chi_summary_source_changed') from None
        try:
            reference = write_evidence(self.root, self.run_id, number, 'summary-selection', doc)
            self.run['summary_events'].append({'selection_sha256': reference, 'summary_round': None,
                                               'candidate_sha256': None, 'checkpoint_sha256': None,
                                               'status': 'selected', 'projections': []})
            self._persist()
            return 0, request
        except Exception:
            self._summary_persistence_failed = True
            raise GoFailure('chi_summary_persistence_failed') from None

    def install_summary(self, current_protected, *, context_limit, secrets=()):
        """Persist candidate and checkpoint before exposing an active view."""
        from go_chi_context import check_budget, measure_request
        from go_chi_summary import candidate_from_response, canonical_sha, derive_view
        try:
            if (getattr(self, '_summary_persistence_failed', False)
                    or not _summary_enabled(self.run['launch'], self.run['kind'])
                    or len(self.run['summary_events']) != 1):
                raise ValueError
            event = self.run['summary_events'][0]
            number = event['summary_round']
            if (event['status'] != 'requested' or type(number) is not int
                    or number != len(self.run['requests']) or self.state['pending'] is not None
                    or self.state['halted'] is not None):
                raise ValueError
            item = self.run['requests'][number - 1]
            if item['purpose'] != 'summary' or item['status'] != 'settled':
                raise ValueError
            selection = verify_evidence(self.root, self.run_id, number, 'summary-selection', event['selection_sha256'])
            response = verify_evidence(self.root, self.run_id, number, 'response', item['response_evidence_sha256'])
            diagnostic = verify_evidence(self.root, self.run_id, number, 'diagnostic', item['diagnostic_evidence_sha256'])
            if (response['http_status'] != 200 or response['redaction'] is not None
                    or type(response['body_utf8']) is not str or diagnostic['code'] != 'ok'
                    or canonical_sha(current_protected) != selection['protected_sha256']
                    or _contains_secret(current_protected, *secrets)):
                raise ValueError
            payload = json.loads(response['body_utf8'], object_pairs_hook=_unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            candidate = candidate_from_response(payload, selection_sha256=selection['selection_sha256'],
                                                protected_sha256=selection['protected_sha256'], sources=selection['selection']['sources'])
            if _contains_secret(candidate, *secrets):
                raise ValueError
            view = derive_view(selection['source_body'], used=selection['source_used'], claimed=selection['claimed'],
                               selection=selection['selection'], protected=current_protected, candidate=candidate,
                               candidate_protected_sha256=selection['protected_sha256'], summary_was_sent=True)
            raw = json.dumps(view, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            full = selection['source_raw'].encode()
            if len(full) - len(raw) < 1024 or check_budget(measure_request(view, raw), context_limit) is not None:
                raise ValueError
            candidate_doc = {'schema': 'chi-summary-candidate-evidence-v1', 'selection_sha256': event['selection_sha256'],
                             'response_sha256': response['raw_sha256'], 'candidate': candidate,
                             'candidate_sha256': canonical_sha(candidate)}
        except Exception:
            if 'event' in locals() and event.get('status') == 'requested':
                try:
                    event['status'] = 'rejected'
                    self._persist()
                except Exception:
                    self._summary_persistence_failed = True
                    raise GoFailure('chi_summary_persistence_failed') from None
            raise GoFailure('chi_summary_invalid') from None
        try:
            event['candidate_sha256'] = write_evidence(self.root, self.run_id, number, 'summary-candidate', candidate_doc)
            event['status'] = 'candidate'
            self._persist()
            checkpoint = {'schema': 'chi-summary-checkpoint-v1', 'selection_sha256': event['selection_sha256'],
                          'candidate_sha256': event['candidate_sha256'], 'candidate_protected_sha256': selection['protected_sha256'],
                          'selection_value_sha256': selection['selection_sha256']}
            event['checkpoint_sha256'] = write_evidence(self.root, self.run_id, number, 'summary-checkpoint', checkpoint)
            event['status'] = 'installed'
            self._persist()
            return view
        except Exception:
            self._summary_persistence_failed = True
            raise GoFailure('chi_summary_persistence_failed') from None

    def project_summary(self, source_body, source_raw, current_protected, *, source_used,
                        context_limit, secrets=()):
        """Persist a derived view and its complete independently verifiable source."""
        from go_chi_context import check_budget, measure_request
        from go_chi_summary import canonical_sha, derive_view, validate_saved_source
        try:
            if (getattr(self, '_summary_persistence_failed', False)
                    or not _summary_enabled(self.run['launch'], self.run['kind'])
                    or len(self.run['summary_events']) != 1 or self.run['summary_events'][0]['status'] != 'installed'
                    or self.state['pending'] is not None or self.state['halted'] is not None
                    or type(source_used) is not int or type(source_raw) is not bytes):
                raise ValueError
            event = self.run['summary_events'][0]
            number = len(self.run['requests']) + 1
            if any(item['round'] == number for item in event['projections']):
                raise ValueError
            actual_used = sum(item['purpose'] != 'patient_simulator' for item in self.run['requests'])
            first = not event['projections']
            if source_used + int(first) != actual_used:
                raise ValueError
            selection = verify_evidence(self.root, self.run_id, event['summary_round'], 'summary-selection', event['selection_sha256'])
            candidate_doc = verify_evidence(self.root, self.run_id, event['summary_round'], 'summary-candidate', event['candidate_sha256'])
            if first and canonical_sha(current_protected) != selection['protected_sha256']:
                raise ValueError
            scoped = copy.deepcopy(self.run)
            if first:
                if event['summary_round'] != len(scoped['requests']): raise ValueError
                scoped['requests'].pop()
            validate_saved_source(root=self.root, run=scoped, identity=self.state['identity'], body=source_body,
                                  used=source_used, claimed=self.run['claim_done'],
                                  canonical_tools=selection['canonical_tools'], protected=current_protected)
            if (canonical_sha(json.loads(source_raw, object_pairs_hook=_unique)) != canonical_sha(source_body)
                    or _contains_secret(source_body, *secrets) or _contains_secret(current_protected, *secrets)
                    or any(secret.encode() in source_raw for secret in secrets if secret)):
                raise ValueError
            view = derive_view(source_body, used=source_used, claimed=self.run['claim_done'],
                               selection=selection['selection'], protected=current_protected,
                               candidate=candidate_doc['candidate'], candidate_protected_sha256=selection['protected_sha256'],
                               summary_was_sent=first)
            wire = json.dumps(view, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if len(source_raw) - len(wire) < 1024 or check_budget(measure_request(view, wire), context_limit):
                raise ValueError
            doc = {'schema': 'chi-summary-projection-v1', 'checkpoint_sha256': event['checkpoint_sha256'],
                   'source_raw': source_raw.decode(), 'source_raw_sha256': hashlib.sha256(source_raw).hexdigest(),
                   'source_body': source_body, 'source_sha256': canonical_sha(source_body), 'source_used': source_used,
                   'claimed': self.run['claim_done'], 'protected': current_protected,
                   'protected_sha256': canonical_sha(current_protected), 'summary_was_sent': first,
                   'wire_sha256': canonical_sha(view)}
        except Exception:
            raise GoFailure('chi_summary_source_changed') from None
        try:
            reference = write_evidence(self.root, self.run_id, number, 'summary-projection', doc)
            event['projections'].append({'round': number, 'projection_sha256': reference})
            self._persist()
            return len(event['projections']) - 1, wire
        except Exception:
            self._summary_persistence_failed = True
            raise GoFailure('chi_summary_persistence_failed') from None

    def _reserve(self, raw: bytes, purpose: str, *, secrets: tuple[str, ...] = (), dispatch=None,
                 parent_call_id=None, recovery_permit=None, summary_permit=None, summary_projection=None) -> None:
        if getattr(self, "_recovery_persistence_failed", False):
            raise GoFailure("chi_recovery_persistence_failed")
        if self.state["pending"] is not None or self.state["halted"] is not None:
            raise GoFailure("chi_usage_unknown")
        aux = self.run['launch'].get('aux_contract') == 'patient-simulator-v1'
        enabled = _recovery_enabled(self.run['launch'], self.run['kind'])
        summary_enabled = _summary_enabled(self.run['launch'], self.run['kind'])
        purposes = ({"main", "confirmation"} | ({"patient_simulator"} if aux else set())
                    | ({"continuation"} if enabled else set()) | ({"summary"} if summary_enabled else set()))
        if purpose not in purposes or type(raw) is not bytes:
            raise GoFailure("chi_reservation_invalid")
        if purpose != "continuation" and recovery_permit is not None:
            raise GoFailure("chi_reservation_invalid")
        if purpose != 'summary' and summary_permit is not None:
            raise GoFailure('chi_reservation_invalid')
        if purpose != 'main' and summary_projection is not None:
            raise GoFailure('chi_reservation_invalid')
        if getattr(self, '_summary_persistence_failed', False):
            raise GoFailure('chi_summary_persistence_failed')
        summary_event = None
        if summary_enabled and self.run['summary_events']:
            summary_event = self.run['summary_events'][0]
            if summary_event['status'] in {'selected', 'requested', 'candidate', 'rejected', 'failed'} and purpose != 'summary':
                raise GoFailure('chi_summary_unavailable')
            projections = summary_event['projections']
            if summary_event['status'] == 'installed' and not projections and purpose != 'main':
                raise GoFailure('chi_summary_unavailable')
            if projections and projections[-1]['round'] > len(self.run['requests']) and purpose != 'main':
                raise GoFailure('chi_summary_unavailable')
            if summary_event['status'] == 'installed' and purpose == 'main':
                from go_chi_summary import canonical_sha
                if (type(summary_projection) is not int or not 0 <= summary_projection < len(projections)
                        or summary_projection != len(projections) - 1
                        or projections[-1]['round'] != len(self.run['requests']) + 1):
                    raise GoFailure('chi_summary_unavailable')
                try:
                    projection = verify_evidence(self.root, self.run_id, projections[-1]['round'],
                                                 'summary-projection', projections[-1]['projection_sha256'])
                    body = json.loads(raw, object_pairs_hook=_unique,
                                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    if canonical_sha(body) != projection['wire_sha256']:
                        raise ValueError
                except Exception:
                    raise GoFailure('chi_summary_source_changed') from None
        if summary_projection is not None and (summary_event is None or summary_event['status'] != 'installed'):
            raise GoFailure('chi_summary_unavailable')
        if purpose == 'summary':
            from go_chi_summary import canonical_sha
            if (type(summary_permit) is not int or summary_permit != 0 or summary_event is None
                    or summary_event['status'] != 'selected' or summary_event['summary_round'] is not None):
                raise GoFailure('chi_summary_unavailable')
            number = len(self.run['requests']) + 1
            try:
                selection_doc = verify_evidence(self.root, self.run_id, number, 'summary-selection',
                                                summary_event['selection_sha256'])
                body = json.loads(raw, object_pairs_hook=_unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if (canonical_sha(body) != selection_doc['summary_sha256']
                        or selection_doc['source_used'] != sum(item['purpose'] != 'patient_simulator' for item in self.run['requests'])
                        or self.run['claim_done'] != selection_doc['claimed']
                        or envelope(raw, kind='request', secrets=secrets)['redaction'] is not None):
                    raise ValueError
            except Exception:
                raise GoFailure('chi_summary_source_changed') from None
        if enabled and purpose != "continuation" and any(e["continuation_round"] is None for e in self.run["recovery_events"]):
            raise GoFailure("chi_recovery_invalid")
        selected = None
        if purpose == "continuation":
            if self.run["status"] != "started":
                raise GoFailure("chi_recovery_invalid")
            from go_chi_recovery import canonical_sha, validate_permit
            events = self.run["recovery_events"]
            if type(recovery_permit) is not int or not 0 <= recovery_permit < len(events):
                raise GoFailure("chi_recovery_invalid")
            selected = events[recovery_permit]
            if selected["continuation_round"] is not None or selected["parent_round"] != len(self.run["requests"]):
                raise GoFailure("chi_recovery_invalid")
            try:
                number = selected["parent_round"]
                parent_request, parent_response, response_sha, old_used, claimed, _ = _recovery_source(self.root, self.run, number)
                permit = verify_evidence(self.root, self.run_id, number, "recovery", selected["permit_sha256"])
                validate_permit(permit, identity=self.state["identity"], run=self.run, parent_round=number,
                                parent_request=parent_request, parent_response=parent_response,
                                response_sha256=response_sha, old_used=old_used, claimed=claimed)
                body = json.loads(raw, object_pairs_hook=_unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if claimed != self.run["claim_done"] or canonical_sha(body) != permit["view_sha256"]:
                    raise ValueError
                screened = envelope(raw, kind="request", secrets=secrets)
                if screened["redaction"] is not None or screened["body_utf8"] is None: raise ValueError
            except Exception:
                raise GoFailure("chi_recovery_invalid") from None
        if self.run["kind"] == "coding_b" and purpose != "main":
            raise GoFailure("chi_reservation_invalid")
        if purpose != 'patient_simulator' and sum(x['purpose'] != 'patient_simulator' for x in self.run['requests']) >= (6 if self.run['kind'] == 'coding_b' else 50):
            raise GoFailure("chi_request_limit")
        if purpose == 'patient_simulator':
            if sum(x['purpose'] == purpose for x in self.run['requests']) >= (2 if self.run['kind'] == 'patient_probe' else 10): raise GoFailure('chi_aux_request_limit')
            if self.run['kind'] == 'patient_probe':
                if parent_call_id is not None: raise GoFailure('chi_aux_parent_invalid')
            else:
                active = [e for e in self.run['tool_events'] if e.get('call_id') == parent_call_id]
                if len(active) != 1 or active[0].get('event') != 'started' or active[0].get('tool') != 'cm_outreach.send_message': raise GoFailure('chi_aux_parent_invalid')
        elif parent_call_id is not None or self.run['kind'] == 'patient_probe': raise GoFailure('chi_reservation_invalid')
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
                 "max_tokens": output_limit(self.run['kind'], purpose, self.run['launch'].get('input_summary')),
                 "request_sha256": hashlib.sha256(raw).hexdigest(), "status": "pending",
                 "request_evidence_sha256": None, "response_evidence_sha256": None,
                 "diagnostic_evidence_sha256": None}
        if purpose == 'patient_simulator': entry['parent_call_id'] = parent_call_id
        if dispatch is not None: entry['dispatch_version'] = 'chi-go-dispatch-v1'
        request_doc = envelope(raw, kind="request", secrets=secrets, dispatch=dispatch)
        entry["request_evidence_sha256"] = write_evidence(self.root, self.run_id, entry["round"], "request", request_doc)
        self.run["requests"].append(entry)
        if selected is not None:
            selected["continuation_round"] = entry["round"]
        if purpose == 'summary':
            summary_event['summary_round'] = entry['round']
            summary_event['status'] = 'requested'
        self.state["pending"] = {"run": self.run["run"], "round": entry["round"]}
        self._persist()

    def record_response(self, raw: bytes, status: int, elapsed_ms: int, *, secrets: tuple[str, ...] = ()) -> None:
        entry = self.run["requests"][-1]
        if self.state["pending"] is None or entry["response_evidence_sha256"] is not None:
            raise GoFailure("chi_pending_invalid")
        doc = envelope(raw, kind="response", secrets=secrets, status=status, elapsed_ms=elapsed_ms)
        entry["response_evidence_sha256"] = write_evidence(self.root, self.run_id, entry["round"], "response", doc)
        self._persist()

    def record_diagnostic(self, code: str, elapsed_ms: int, *, cause=None) -> None:
        if (type(code) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", code)
                or type(elapsed_ms) is not int or isinstance(elapsed_ms, bool) or elapsed_ms < 0):
            raise GoFailure("chi_diagnostic_invalid")
        if code == "ok":
            if cause is not None:
                raise GoFailure("chi_diagnostic_invalid")
            final_cause = None
        elif cause is None:
            final_cause = build_cause("other", "unspecified")
        elif validate_cause(cause):
            final_cause = {key: cause[key] for key in ("schema", "stage", "reason")}
        else:
            raise GoFailure("chi_diagnostic_invalid")
        entry = self.run["requests"][-1]
        if entry["diagnostic_evidence_sha256"] is not None:
            raise GoFailure("chi_diagnostic_invalid")
        doc = {"schema": SCHEMA_V2, "kind": "diagnostic", "code": code,
               "elapsed_ms": elapsed_ms, "cause": final_cause}
        entry["diagnostic_evidence_sha256"] = write_evidence(self.root, self.run_id, entry["round"], "diagnostic", doc)
        self._persist()
        self._clear_tool_inflight(f"__wire_{entry['round']:03d}")

    def settle(self, usage: dict) -> None:
        if self.state["pending"] is None:
            raise GoFailure("chi_pending_invalid")
        try:
            from b_provider_transport import GuardedTransport
            incoming, outgoing = GuardedTransport._usage({'usage': usage})
            billed, billing_error, halt = _fee_decision(usage, self.run['launch'].get('fee_policy'))
        except GoFailure:
            raise
        except Exception:
            raise GoFailure("chi_usage_unknown") from None
        entry = self.run["requests"][-1]
        entry.update(status="settled", usage={"input_tokens": incoming, "output_tokens": outgoing},
                     billing=billed, billing_error=billing_error)
        self.state["halted"] = halt
        self.state["pending"] = None
        self._persist()
        if halt:
            raise GoFailure(halt)

    def finish(self, status: str, error: str | None = None) -> None:
        if status not in {"complete", "failed"} or self.run["status"] != "started":
            raise GoFailure("chi_status_invalid")
        if status == "complete" and any(event["continuation_round"] is None for event in self.run.get("recovery_events", [])):
            raise GoFailure("chi_recovery_invalid")
        if status == 'complete' and any(event['status'] != 'installed' or not event['projections']
                                        or event['projections'][-1]['round'] > len(self.run['requests'])
                                        for event in self.run.get('summary_events', [])):
            raise GoFailure('chi_summary_unavailable')
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
        warnings = 0
        unsettled = []
        billing_incomplete = False
        for attempt in self.state["attempts"]:
            for request in attempt["requests"]:
                if request["status"] != "settled":
                    billing_incomplete = True
                    unsettled.append({'run': attempt['run'], 'round': request['round'], 'status': request['status']})
                    for name in names:
                        complete[name] = False
                    continue
                billed = request['billing']
                billing_incomplete = billing_incomplete or any(value is None for value in billed.values())
                warnings += (attempt['launch'].get('fee_policy') == FEE_POLICY
                             and request['billing_error'] == 'billing_details_unknown'
                             and (billed['charged_usd'] is None or Decimal(billed['charged_usd']) == 0)
                             and (billed['billing_source'] is None or billed['billing_source'] in {'go', 'go-plus'}))
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
                "account_prior_history": "unknown", 'billing_details_warnings': warnings,
                'billing_complete': not billing_incomplete and all(complete.values()),
                'unsettled_requests': unsettled}

    def close(self) -> None:
        if self.lock is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            os.close(self.lock)
            self.lock = None
