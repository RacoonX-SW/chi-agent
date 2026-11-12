"""Bounded, no-overwrite request evidence for Go CHI accounting."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .evaluation_bundle import _check_components, _read_regular_bounded, _write_exclusive, _fsync_dir
from .opencode_go_provider import GoFailure, _contains_secret, _unique

MAX_EVIDENCE_BYTES = 20 * 1024 * 1024


def _safe_usage(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if type(value) is list:
        return [_safe_usage(item, secrets) for item in value]
    if type(value) is dict:
        return {_safe_usage(key, secrets): _safe_usage(item, secrets) for key, item in value.items()}
    return value


def envelope(raw: bytes, *, kind: str, secrets: tuple[str, ...], status=None, elapsed_ms=None, dispatch=None) -> dict:
    result = {"schema": "chi-go-wire-evidence-v1", "kind": kind, "raw_sha256": hashlib.sha256(raw).hexdigest(),
              "body_utf8": None, "redaction": None, "usage": None, "http_status": status, "elapsed_ms": elapsed_ms}
    if dispatch is not None:
        if kind != 'request': raise ValueError('dispatch_invalid')
        result['dispatch'] = dispatch
    if kind == "response" and len(raw) > 4 * 1024 * 1024:
        result["redaction"] = "body_too_large"
        return result
    try:
        text = raw.decode("utf-8", errors="strict")
        parsed = json.loads(text, object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if _contains_secret(parsed, *secrets) or any(secret.encode() in raw for secret in secrets if secret):
            result["redaction"] = "secret_detected"
        else:
            result["body_utf8"] = text
        if kind == "response" and type(parsed) is dict and type(parsed.get("usage")) is dict:
            result["usage"] = _safe_usage(parsed["usage"], secrets)
    except Exception:
        # Invalid or opaque bytes cannot be reliably screened for encoded secrets.
        result["redaction"] = "unparseable_body"
    return result


def write(root: Path, run: str, number: int, kind: str, value: dict) -> str:
    directory = Path(root) / "wire-evidence" / run
    try:
        _check_components(directory, "chi_evidence_path_invalid")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _check_components(directory, "chi_evidence_path_invalid", final_may_be_missing=False)
        payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(payload) > MAX_EVIDENCE_BYTES:
            raise ValueError
        path = directory / f"{number:03d}-{kind}.json"
        _write_exclusive(path, payload)
        _fsync_dir(directory)
        return hashlib.sha256(payload).hexdigest()
    except Exception:
        raise GoFailure("chi_evidence_persistence_failed") from None


def verify(root: Path, run: str, number: int, kind: str, expected: str) -> dict:
    try:
        path = _check_components(Path(root) / "wire-evidence" / run / f"{number:03d}-{kind}.json",
                                 "chi_evidence_invalid", final_may_be_missing=False)
        raw = _read_regular_bounded(path, MAX_EVIDENCE_BYTES, "chi_evidence_invalid")
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError
        return value
    except Exception:
        raise GoFailure("chi_evidence_invalid") from None


def write_tool(root: Path, run: str, call_id: str, result: str, secrets: tuple[str, ...]) -> str:
    raw = result.encode("utf-8")
    doc = {"schema": "chi-go-tool-evidence-v1", "kind": "tool", "raw_sha256": hashlib.sha256(raw).hexdigest(),
           "body_utf8": None, "redaction": None}
    if len(raw) > 8 * 1024 * 1024:
        doc["redaction"] = "body_too_large"
    else:
        unsafe = _contains_secret(result, *secrets)
        try:
            parsed = json.loads(result, object_pairs_hook=_unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            unsafe = unsafe or _contains_secret(parsed, *secrets)
        except Exception:
            # Non-JSON text is screened by the raw-string check above. Store it
            # verbatim so the v3 source replay can reproduce what the model saw;
            # policy/PDF text commonly contains backslashes.
            pass
        if unsafe:
            doc["redaction"] = "secret_detected"
        else:
            doc["body_utf8"] = result
    directory = Path(root) / "tool-evidence" / run
    try:
        _check_components(directory, "chi_evidence_path_invalid")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _check_components(directory, "chi_evidence_path_invalid", final_may_be_missing=False)
        payload = (json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(payload) > MAX_EVIDENCE_BYTES: raise ValueError
        _write_exclusive(directory / (call_id + ".json"), payload)
        _fsync_dir(directory)
        return hashlib.sha256(payload).hexdigest()
    except Exception:
        raise GoFailure("chi_evidence_persistence_failed") from None


def verify_tool(root: Path, run: str, call_id: str, expected: str) -> dict:
    try:
        path = _check_components(Path(root) / "tool-evidence" / run / (call_id + ".json"),
                                 "chi_evidence_invalid", final_may_be_missing=False)
        raw = _read_regular_bounded(path, MAX_EVIDENCE_BYTES, "chi_evidence_invalid")
        if hashlib.sha256(raw).hexdigest() != expected: raise ValueError
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or value.get("schema") != "chi-go-tool-evidence-v1" or value.get("kind") != "tool":
            raise ValueError
        return value
    except Exception:
        raise GoFailure("chi_evidence_invalid") from None
