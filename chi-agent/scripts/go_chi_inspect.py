"""Read-only inspection of a bounded, operator-supplied Go Console export."""
from __future__ import annotations
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from evaluation_bundle import _check_components, _read_regular_bounded
from opencode_go_provider import GoFailure, _unique


def inspect_provider(path: Path, expected_sha256: str, pending: dict | None) -> dict:
    if type(expected_sha256) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise GoFailure('chi_provider_record_invalid')
    try:
        path = _check_components(Path(path), 'chi_provider_record_invalid', final_may_be_missing=False)
        raw = _read_regular_bounded(path, 1024 * 1024, 'chi_provider_record_invalid')
        if hashlib.sha256(raw).hexdigest() != expected_sha256: raise ValueError
        doc = json.loads(raw, object_pairs_hook=_unique, parse_float=Decimal,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(doc) is not dict or set(doc) != {'event'} or type(doc['event']) is not dict: raise ValueError
        e = doc['event']
        fixed = {'category': 'inference', 'model': 'deepseek-v4.1-flash', 'requestedModel': 'deepseek-v4.1-flash',
                 'provider': 'opencode', 'product': 'go', 'protocol': 'openai-chat', 'method': 'POST',
                 'path': '/inference/go/openai/v1/chat/completions', 'stream': False, 'statusCode': 200,
                 'outcome': 'succeeded', 'reasoningEffort': 'high', 'reasoningMode': 'effort', 'attemptCount': 1}
        if any(type(e.get(k)) is not type(v) or e[k] != v for k, v in fixed.items()): raise ValueError
        for key in ('id', 'requestID', 'sessionID'):
            if type(e.get(key)) is not str or not e[key] or len(e[key]) > 256: raise ValueError
        if e['id'] != e['requestID'] or not re.fullmatch(r'chi-[0-9a-f]{32}', e['sessionID']): raise ValueError
        headers = e['requestHeaders']
        if (type(headers) is not dict or headers.get('x-opencode-session') != e['sessionID']
                or headers.get('user-agent') != 'chi-agent' or e.get('userAgent') != 'chi-agent'
                or type(headers.get('content-length')) is not str or not re.fullmatch(r'[1-9][0-9]{0,7}', headers['content-length'])): raise ValueError
        length = int(headers['content-length'])
        if length > 8 * 1024 * 1024: raise ValueError
        times = ('startedAt', 'finishedAt', 'durationMs', 'firstTokenAt', 'lastTokenAt', 'timeToFirstTokenMs')
        tokens = ('inputTokens', 'outputTokens', 'reasoningTokens', 'cacheReadTokens', 'cacheWriteTokens')
        if any(type(e.get(k)) is not int or e[k] < 0 for k in times + tokens): raise ValueError
        if (not 0 < e['startedAt'] <= e['firstTokenAt'] <= e['lastTokenAt'] <= e['finishedAt']
                or e['durationMs'] != e['finishedAt'] - e['startedAt']
                or e['timeToFirstTokenMs'] != e['firstTokenAt'] - e['startedAt']
                or e['durationMs'] > 3600000 or e['inputTokens'] > 1048576 or e['outputTokens'] > 32768
                or e['reasoningTokens'] > e['outputTokens']): raise ValueError
        cost = e.get('cost')
        if type(cost) not in (int, Decimal) or not Decimal(cost).is_finite() or Decimal(cost) < 0: raise ValueError
        attempts = e['attempts']
        if (type(attempts) is not list or len(attempts) != 1 or type(attempts[0]) is not dict
                or attempts[0].get('provider') != 'opencode' or attempts[0].get('model') != 'deepseek-v4.1-flash'
                or type(attempts[0].get('statusCode')) is not int or attempts[0]['statusCode'] != 200
                or type(attempts[0].get('durationMs')) is not int or not 0 <= attempts[0]['durationMs'] <= e['durationMs']): raise ValueError
        dispatch = pending.get('dispatch') if type(pending) is dict else None
        if type(pending) is dict:
            max_output = 1024 if pending.get('kind') == 'coding_b' else 32768 if pending.get('purpose') == 'confirmation' else 8192
            if e['outputTokens'] > max_output: raise ValueError
            body_bytes = pending.get('body_bytes')
            if dispatch is None and body_bytes is not None and length != body_bytes: raise ValueError
        correlation = {'status': 'unavailable', 'unique_match': False, 'purpose': 'unavailable'}
        if dispatch is not None:
            checks = {'session_sha256': hashlib.sha256(e['sessionID'].encode()).hexdigest() == dispatch['session_sha256'],
                      'body_bytes': length == dispatch['body_bytes'],
                      'started_within_30_seconds': abs(e['startedAt'] - dispatch['started_utc_ms']) <= 30000}
            correlation = {'status': 'consistent' if all(checks.values()) else 'mismatch',
                           'checks': checks, 'unique_match': False, 'purpose': 'unavailable'}
        return {'status': 'inspected', 'sha256': expected_sha256, 'console_cost': str(cost),
                'tokens': {k: e[k] for k in tokens}, 'correlation': correlation,
                'missing': ['response_usage_cost', 'charged_usd', 'billing_source', 'list_cost_usd', 'allowance_usd'],
                'execution_allowed': False}
    except Exception:
        raise GoFailure('chi_provider_record_invalid') from None
